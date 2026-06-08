# nodes/enforcer.py
import json
import logging
from model import LLMSingleton
from brand_metrics import BrandMetricsSQL
from prompts.enforcer import ENFORCER_PROMPT
from graph.state import GraphState

logger = logging.getLogger(__name__)

from utils.observe import observe


def _parse_llm_json(raw: str) -> dict:
    """Strip markdown fences and parse JSON from LLM output."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def _flatten_feedback(feedback) -> str:
    """
    Flatten the nested feedback dict into a single actionable string
    for the writer revision prompt.
    Handles both old string format and new dict format gracefully.
    """
    if isinstance(feedback, str):
        return feedback

    if isinstance(feedback, dict):
        parts = []
        for dimension, note in feedback.items():
            if note and note.strip():
                parts.append(f"[{dimension.upper()}] {note.strip()}")
        return "\n".join(parts) if parts else ""

    return ""

def _extract_section(text: str, header: str) -> str:
    lines = text.split('\n')
    capture = False
    result = []
    for line in lines:
        if header.upper() in line.upper():
            capture = True
            continue
        if capture and line.strip().startswith('#'):
            break
        if capture:
            result.append(line)
    return '\n'.join(result).strip()



@observe("enforcer_node")
def enforcer_node(state: GraphState, analyzer: BrandMetricsSQL) -> GraphState:
    content        = state["content"]
    metrics        = analyzer.get_context()
    iteration      = state.get("iteration", 1)
    max_iterations = 3

    # Extract mechanical rules from brand_brains for hard constraint verification
    opening_formula      = _extract_section(metrics, "OPENING FORMULA")
    closing_formula      = _extract_section(metrics, "CLOSING FORMULA")
    paragraph_constraints = _extract_section(metrics, "Paragraph constraints")
    heading_format       = _extract_section(metrics, "Heading format")
    evidence_anchoring   = _extract_section(metrics, "Evidence anchoring")
    hedging_frequency    = _extract_section(metrics, "TONE SIGNATURE")
    brand_name           = _extract_section(metrics, "BRAND NAME")

    # Fallbacks
    if not opening_formula:
        opening_formula = "Relatable observation → uncomfortable truth pivot with brand authority → one-sentence contrast"
    if not closing_formula:
        closing_formula = "Brand methodology sentence → parallel contrast (two short sentences) → soft CTA as question"
    if not paragraph_constraints:
        paragraph_constraints = "Max 4 sentences per paragraph"
    if not heading_format:
        heading_format = "Bold numbered headings (1, 2, 3...) for main arguments; no bullet points"
    if not evidence_anchoring:
        evidence_anchoring = "Every major claim must have a specific number, timeframe, or client outcome"
    if not hedging_frequency:
        hedging_frequency = "Low — avoid might, could, perhaps, may"
    if not brand_name:
        brand_name = "the brand"

    brand_name_anchoring = f"Brand name '{brand_name.strip()}' must appear at least once anchored to a specific number, timeframe, or experience"

    result = LLMSingleton.get().invoke(
        ENFORCER_PROMPT.format(
            metrics=metrics,
            content=content,
            opening_formula=opening_formula,
            closing_formula=closing_formula,
            paragraph_constraints=paragraph_constraints,
            heading_format=heading_format,
            evidence_anchoring=evidence_anchoring,
            hedging_frequency=hedging_frequency,
            brand_name_anchoring=brand_name_anchoring,
        )
    )

    try:
        evaluation = _parse_llm_json(result.content)
    except Exception:
        logger.error("Failed to parse enforcer output, defaulting to approve")
        evaluation = {
            "approved": True,
            "score": 7.0,
            "style_match": 0.0,
            "tone_match": 0.0,
            "structure_match": 0.0,
            "signature_match": 0.0,
            "feedback": "",
            "creative_angle": "unknown"
        }

    # Build hard_constraint_evidence from the nested feedback dict
    hard_constraint_evidence = {}
    raw_feedback = evaluation.get("feedback", "")
    if isinstance(raw_feedback, dict):
        for dimension, note in raw_feedback.items():
            if note and note.strip():
                hard_constraint_evidence[dimension] = {
                    "status": "fail",
                    "evidence": note.strip(),
                    "required": "",
                    "rewrite_instruction": note.strip()
                }

    flat_feedback = _flatten_feedback(raw_feedback)

    # Parse hard constraints with evidence and rewrite instructions
    hard_constraints = evaluation.get("hard_constraints", {})
    hard_constraint_evidence = evaluation.get("hard_constraints", {})

    any_hard_fail = False
    if isinstance(hard_constraints, dict):
        for key, value in hard_constraints.items():
            if isinstance(value, dict) and value.get("status") == "fail":
                any_hard_fail = True
                break
            elif isinstance(value, str) and value.lower() == "fail":
                any_hard_fail = True
                break

    if any_hard_fail:
        logger.info(
            "Hard constraint failure detected at iteration %d — forcing revision",
            iteration
        )
        evaluation["approved"] = False
        evaluation["score"] = min(evaluation.get("score", 5.0), 5.0)
        # Zero out dimension scores when hard constraints fail
        evaluation["style_match"] = 0.0
        evaluation["tone_match"] = 0.0
        evaluation["structure_match"] = 0.0
        evaluation["signature_match"] = 0.0

        # Build feedback from hard constraint failures with rewrite instructions
        if not flat_feedback:
            failure_parts = []
            for key, value in hard_constraints.items():
                if isinstance(value, dict) and value.get("status") == "fail":
                    evidence = value.get("evidence", "")
                    required = value.get("required", "")
                    rewrite = value.get("rewrite_instruction", "")
                    parts = [f"[HARD CONSTRAINT] {key}: FAILED"]
                    if evidence:
                        parts.append(f"  Your text: {evidence}")
                    if required:
                        parts.append(f"  Required: {required}")
                    if rewrite:
                        parts.append(f"  Rewrite: {rewrite}")
                    failure_parts.append("\n".join(parts))
                elif isinstance(value, str) and value.lower() == "fail":
                    failure_parts.append(f"[HARD CONSTRAINT] {key}: FAILED")
            flat_feedback = "\n\n".join(failure_parts) if failure_parts else (
                "[HARD CONSTRAINT] One or more structural requirements failed. "
                "Review the brand's opening formula, closing formula, paragraph constraints, "
                "and evidence anchoring rules."
            )

    # Force a revision cycle if score is below threshold and iterations remain
    MIN_SCORE = 7.5
    if evaluation.get("score", 0.0) < MIN_SCORE and iteration < max_iterations:
        logger.info(
            "Score %.1f below threshold %.1f at iteration %d — forcing revision",
            evaluation["score"], MIN_SCORE, iteration
        )
        evaluation["approved"] = False
        if not flat_feedback:
            flat_feedback = (
                "[STRUCTURE] Opening does not match brand opening formula. "
                "Rewrite the first sentence as a direct provocative truth — not a question, not a scene-setter.\n"
                "[SIGNATURE] Brand name not present. Replace the first 'we' or 'our agency' reference "
                "with 'At [Brand Name], we...' anchored to a specific experience or number.\n"
                "[STYLE] Check for unanchored claims — every major assertion needs a specific number, "
                "timeframe, or client outcome."
            )

    # Hard cap — DO NOT approve at max iterations if hard constraints still fail
    if not evaluation["approved"] and iteration >= max_iterations:
        if any_hard_fail:
            logger.error("Max iterations reached with hard constraint failures — content rejected")
            evaluation["approved"] = False
            evaluation["score"] = min(evaluation.get("score", 5.0), 5.0)
        else:
            logger.warning("Max iterations reached, forcing approval")
            evaluation["approved"] = True

    logger.info(
        "Enforcer: approved=%s score=%.1f style=%.1f tone=%.1f structure=%.1f signature=%.1f iteration=%d",
        evaluation["approved"],
        evaluation["score"],
        evaluation.get("style_match", 0.0),
        evaluation.get("tone_match", 0.0),
        evaluation.get("structure_match", 0.0),
        evaluation.get("signature_match", 0.0),
        iteration
    )

    return {
    **state,
    "approved":                  evaluation["approved"],
    "score":                     evaluation["score"],
    "style_match":               evaluation.get("style_match", 0.0),
    "tone_match":                evaluation.get("tone_match", 0.0),
    "structure_match":           evaluation.get("structure_match", 0.0),
    "signature_match":           evaluation.get("signature_match", 0.0),
    "feedback":                  flat_feedback,
    "creative_angle":            evaluation.get("creative_angle", "unknown"),
    "hard_constraint_evidence":  hard_constraint_evidence, 
    
}

  

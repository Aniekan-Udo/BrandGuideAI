# nodes/enforcer.py
import json
import logging
import re
from model import LLMSingleton
from brand_metrics import BrandMetricsSQL
from brand_rag import BrandRAG
from prompts.enforcer import ENFORCER_PROMPT
from graph.state import GraphState

logger = logging.getLogger(__name__)

from utils.observe import observe


# def _parse_llm_json(raw: str) -> dict:
#     """Strip markdown fences and parse JSON from LLM output."""
#     raw = raw.strip()
#     if raw.startswith("```"):
#         raw = raw.split("```")[1]
#         if raw.startswith("json"):
#             raw = raw[4:]
#     return json.loads(raw.strip())

def _parse_llm_json(raw: str) -> dict:
    """Strip markdown fences and parse JSON from LLM output."""
    raw = raw.strip()
    match = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if match:
        raw = match.group(1)
    return json.loads(raw.strip())


def _extract_permitted_claims(metrics: str) -> str:
    """
    Extract the BRAND ASSET BANK section from the brand brain and format it
    as an explicit closed list of permitted claims for the hallucination check.

    This converts the unstructured asset bank text into a numbered whitelist
    so the enforcer LLM can do exact lookup rather than relying on recall.
    Returns a formatted string ready for prompt injection.
    """
    # Extract the BRAND ASSET BANK section
    match = re.search(
        r"#\s*BRAND ASSET BANK\s*\n(.*?)(?=\n#\s+[A-Z]|\Z)",
        metrics,
        re.DOTALL | re.IGNORECASE
    )
    if not match:
        return (
            "No asset bank extracted yet. "
            "All specific numeric claims (client counts, percentages, ROI figures) "
            "in the content are UNVERIFIABLE and must be treated as hallucinations. "
            "Flag any specific number tied to brand experience."
        )

    asset_text = match.group(1).strip()

    # Parse individual claim lines — handle both bullet and dash formats
    lines = [l.strip().lstrip("-•*").strip() for l in asset_text.splitlines() if l.strip()]

    # Separate into categories for clarity
    social_proof     = []
    frameworks       = []
    values           = []
    financial_targets = []
    other            = []

    current_category = None
    for line in lines:
        upper = line.upper()
        if "SOCIAL PROOF" in upper:
            current_category = "social_proof"
            continue
        elif "FRAMEWORK" in upper or "METHODOLOG" in upper:
            current_category = "frameworks"
            continue
        elif "VALUE" in upper or "BELIEF" in upper:
            current_category = "values"
            continue
        elif "FINANCIAL TARGET" in upper or "PROJECTION" in upper:
            current_category = "financial_targets"
            continue
        elif line.startswith("#") or (line.isupper() and len(line) > 5):
            current_category = "other"
            continue

        if not line or line.startswith("#"):
            continue

        if current_category == "social_proof":
            social_proof.append(line)
        elif current_category == "frameworks":
            frameworks.append(line)
        elif current_category == "values":
            values.append(line)
        elif current_category == "financial_targets":
            financial_targets.append(line)
        else:
            other.append(line)

    sections = []

    if social_proof:
        numbered = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(social_proof))
        sections.append(f"PERMITTED SOCIAL PROOF CLAIMS (exact numbers the brand may claim):\n{numbered}")

    if financial_targets:
        numbered = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(financial_targets))
        sections.append(
            f"PERMITTED FINANCIAL TARGETS & PROJECTIONS (specific numbers, percentages, dollar amounts, "
            f"timeframes, and quantified outcomes the brand may use):\n{numbered}"
        )

    if frameworks:
        numbered = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(frameworks))
        sections.append(f"PERMITTED FRAMEWORKS & METHODOLOGIES:\n{numbered}")

    if values:
        numbered = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(values))
        sections.append(f"PERMITTED STATED VALUES & BELIEFS:\n{numbered}")

    if other:
        numbered = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(other))
        sections.append(f"OTHER PERMITTED CLAIMS:\n{numbered}")

    if not sections:
        return (
            "Asset bank found but could not be parsed into discrete claims. "
            "Treat ALL specific numeric claims in the content as unverified "
            "unless they appear verbatim in the brand metrics text above."
        )

    header = (
        "The following is the COMPLETE list of specific claims this brand is permitted to make.\n"
        "Any specific number, percentage, client count, or named framework NOT on this list "
        "is a hallucination and must be flagged. EXCEPTION: numbers that appear verbatim in "
        "the PERMITTED FINANCIAL TARGETS & PROJECTIONS list are always allowed.\n\n"
    )
    return header + "\n\n".join(sections)

def _run_preflight_checks(content: str, metrics: str) -> list[str]:
    """Run deterministic rule checks to catch strict anti-patterns before invoking the LLM."""
    failures = []
    
    # 1. Check Punctuation
    punctuation_match = re.search(r"PUNCTUATION HABITS:\n(.*?)(?=\n[A-Z_]+:|\n#|\Z)", metrics, re.DOTALL | re.IGNORECASE)
    if punctuation_match:
        rules = punctuation_match.group(1).lower()
        if "avoid" in rules or "not used" in rules or "absent" in rules:
            if "exclamation" in rules and "!" in content:
                failures.append("Brand avoids exclamation marks (!), but they were found.")
            if "em dash" in rules or "em-dash" in rules:
                if "—" in content or "--" in content:
                    failures.append("Brand avoids em-dashes (— or --), but they were found.")
            if "semicolon" in rules and ";" in content:
                failures.append("Brand avoids semicolons (;), but they were found.")
            if "ellipses" in rules or "ellipsis" in rules:
                if "..." in content or "…" in content:
                    failures.append("Brand avoids ellipses (...), but they were found.")

    # 2. Check Question Usage
    question_match = re.search(r"QUESTION USAGE:\n(.*?)(?=\n[A-Z_]+:|\n#|\Z)", metrics, re.DOTALL | re.IGNORECASE)
    if question_match:
        rules = question_match.group(1).lower()
        if ("avoid" in rules or "absent" in rules or "not use" in rules or "none" in rules) and "?" in content:
            failures.append("Brand strictly avoids questions, but a question mark (?) was found.")
            
    return failures


@observe("enforcer_node")
def enforcer_node(state: GraphState, analyzer: BrandMetricsSQL, rag: BrandRAG = None) -> GraphState:
    content        = state["content"]
    metrics        = analyzer.get_context()
    iteration      = state.get("iteration", 1)
    max_iterations = 3

    # Build permitted claims whitelist from asset bank
    permitted_claims = _extract_permitted_claims(metrics)

    # 1. Run Fast Pre-flight Checks (Bypass LLM if failed)
    preflight_failures = _run_preflight_checks(content, metrics)
    if preflight_failures:
        logger.warning("Pre-flight checks failed at iteration %d: %s", iteration, preflight_failures)
        feedback = "DETERMINISTIC ANTI-PATTERN DETECTED — The content violates strict mechanical rules:\n"
        for failure in preflight_failures:
            feedback += f"- {failure}\n"
        feedback += "\nPlease fix these formatting errors. No further evaluation was performed."
        
        return {
            **state,
            "approved": False,
            "score": 0.0,
            "style_match": 0.0,
            "tone_match": 0.0,
            "structure_match": 0.0,
            "signature_match": 0.0,
            "feedback": feedback,
            "flagged_passages": "Multiple formatting violations.",
            "creative_angle": "unknown"
        }

    # The enforcer no longer uses raw RAG examples, relying strictly on synthesized rules.
    result = LLMSingleton.get("enforcement").invoke(
        ENFORCER_PROMPT.format(
            metrics=metrics,
            content=content,
            permitted_claims=permitted_claims
        )
    )

    logger.info("ENFORCER_RAW_OUTPUT:\n%s", result.content[:2000])

    try:
        evaluation = _parse_llm_json(result.content)
    except Exception:
        logger.error("Failed to parse enforcer output, defaulting to NOT approved")
        evaluation = {
            "hallucination_check": {"verdict": "FAIL", "hallucinated_claims": ["Parse failure — content requires re-evaluation."]},
            "approved": False,
            "score": 0.0,
            "style_match": 0.0,
            "tone_match": 0.0,
            "structure_match": 0.0,
            "signature_match": 0.0,
            "dimension_details": {},
            "flagged_passages": [],
            "feedback": "Enforcer evaluation failed — content requires re-evaluation.",
            "creative_angle": "unknown"
        }

    # Hard gate: hallucination failure overrides score and approval
    hallucination = evaluation.get("hallucination_check", {})
    hallucination_verdict = hallucination.get("verdict", "FAIL").upper()

    if hallucination_verdict == "FAIL":
        hallucinated = hallucination.get("hallucinated_claims", [])
        logger.warning(
            "HALLUCINATION DETECTED at iteration %d — %d fabricated claim(s): %s",
            iteration,
            len(hallucinated),
            hallucinated
        )
        # Cap score hard at 4.0 and force rejection regardless of other dimensions
        evaluation["approved"] = False
        evaluation["score"] = min(evaluation.get("score", 0.0), 4.0)

        # Build actionable feedback pointing to permitted alternatives
        hallucination_feedback = (
            "HALLUCINATION DETECTED — content contains fabricated claims not in the brand's asset bank.\n"
            "Fabricated claims found:\n"
        )
        for claim in hallucinated:
            hallucination_feedback += f"  - {claim}\n"
        hallucination_feedback += (
            "\nReplace all fabricated claims with permitted alternatives from the brand asset bank. "
            "Use only exact client counts, percentages, and framework names from the permitted claims list. "
            "If no suitable permitted claim exists for a numbered point, rewrite that point to use "
            "a general brand observation without specific numbers."
        )
        # Prepend hallucination feedback — it is the priority fix
        existing_feedback = evaluation.get("feedback", "")
        evaluation["feedback"] = hallucination_feedback + (
            f"\n\nADDITIONAL FEEDBACK:\n{existing_feedback}" if existing_feedback else ""
        )
        

    # Score gate: force revision if below threshold and iterations remain
    MIN_SCORE = 8.0
    if evaluation.get("score", 0.0) < MIN_SCORE and iteration < max_iterations:
        logger.info(
            "Score %.1f below threshold %.1f at iteration %d — forcing revision",
            evaluation["score"], MIN_SCORE, iteration
        )
        evaluation["approved"] = False
        if not evaluation.get("feedback"):
            evaluation["feedback"] = (
                "Content does not sufficiently match the brand voice. "
                "Focus on: anchoring claims to brand experience with specific permitted data, "
                "matching the brand's opening and closing patterns, "
                "and weaving in signature constructions naturally."
            )

    # Hard cap: approve at max iterations only if no hallucinations
    if not evaluation["approved"] and iteration >= max_iterations:
        if hallucination_verdict == "FAIL":
            logger.error(
                "Max iterations reached but hallucinations still present — NOT approving. "
                "Content contains fabricated claims and cannot be deployed."
            )
            # Do not force approve — hallucinated content must not be deployed
        else:
            logger.warning("Max iterations reached (no hallucinations), forcing approval")
            evaluation["approved"] = True

    logger.info(
        "Enforcer: hallucination=%s approved=%s score=%.1f style=%.1f tone=%.1f structure=%.1f signature=%.1f iteration=%d",
        hallucination_verdict,
        evaluation["approved"],
        evaluation["score"],
        evaluation.get("style_match", 0.0),
        evaluation.get("tone_match", 0.0),
        evaluation.get("structure_match", 0.0),
        evaluation.get("signature_match", 0.0),
        iteration
    )

    # Format flagged passages for the writer revision prompt
    flagged = evaluation.get("flagged_passages", [])
    if isinstance(flagged, list):
        flagged_str = "\n".join(f"- {p}" for p in flagged) if flagged else "No specific passages flagged."
    else:
        flagged_str = str(flagged) if flagged else "No specific passages flagged."

    return {
        **state,
        "approved":        evaluation["approved"],
        "score":           evaluation["score"],
        "style_match":     evaluation.get("style_match", 0.0),
        "tone_match":      evaluation.get("tone_match", 0.0),
        "structure_match": evaluation.get("structure_match", 0.0),
        "signature_match": evaluation.get("signature_match", 0.0),
        "feedback":        evaluation.get("feedback", ""),
        "flagged_passages": flagged_str,
        "creative_angle":  evaluation.get("creative_angle", "unknown")
    }
# nodes/enforcer.py
import json
import logging
from model import LLMSingleton
from brand_metrics import BrandMetricsSQL
from brand_rag import BrandRAG
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


@observe("enforcer_node")
def enforcer_node(state: GraphState, analyzer: BrandMetricsSQL, rag: BrandRAG = None) -> GraphState:
    content       = state["content"]
    metrics       = analyzer.get_context()
    iteration     = state.get("iteration", 1)
    max_iterations = 3

    # Retrieve brand voice examples for ground-truth comparison
    examples = ""
    if rag is not None:
        try:
            examples = rag.query(state.get("topic", "brand voice"))
        except Exception as e:
            logger.warning("RAG failed in enforcer, evaluating without examples: %s", e)

    result = LLMSingleton.get("enforcement").invoke(
        ENFORCER_PROMPT.format(
            metrics=metrics,
            content=content,
            examples=examples if examples else "No brand style examples available — evaluate against metrics only."
        )
    )
    
    logger.info("ENFORCER_RAW_OUTPUT:\n%s", result.content[:2000])

    try:
        evaluation = _parse_llm_json(result.content)
    except Exception:
        # #13: Default to NOT approved on parse failure — don't rubber-stamp broken output
        logger.error("Failed to parse enforcer output, defaulting to NOT approved")
        evaluation = {
            "approved": False,
            "score": 0.0,
            "style_match": 0.0,
            "tone_match": 0.0,
            "structure_match": 0.0,
            "signature_match": 0.0,
            "dimension_details": {},
            "flagged_passages": [],
            "feedback": "Enforcer evaluation failed — content requires re-evaluation. Focus on matching the brand's opening/closing patterns, sentence rhythm, and signature constructions.",
            "creative_angle": "unknown"
        }

    # Force a revision cycle if score is below threshold and iterations remain
    # This prevents the enforcer from rubber-stamping weak first drafts
    MIN_SCORE = 8.0
    if evaluation.get("score", 0.0) < MIN_SCORE and iteration < max_iterations:
        logger.info(
            "Score %.1f below threshold %.1f at iteration %d — forcing revision",
            evaluation["score"], MIN_SCORE, iteration
        )
        evaluation["approved"] = False
        # Ensure feedback is populated so the writer knows what to fix
        if not evaluation.get("feedback"):
            evaluation["feedback"] = (
                "Content does not sufficiently match the brand voice. "
                "Focus on: anchoring claims to brand experience with specific data, "
                "matching the brand's opening and closing patterns, "
                "and weaving in signature constructions naturally."
            )

    # Hard cap — approve at max iterations regardless of score
    if not evaluation["approved"] and iteration >= max_iterations:
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

    # Format flagged passages for the writer revision prompt
    flagged = evaluation.get("flagged_passages", [])
    if isinstance(flagged, list):
        flagged_str = "\n".join(f"- {p}" for p in flagged) if flagged else "No specific passages flagged."
    else:
        flagged_str = str(flagged) if flagged else "No specific passages flagged."

    return {
        **state,
        "approved": evaluation["approved"],
        "score": evaluation["score"],
        "style_match": evaluation.get("style_match", 0.0),
        "tone_match": evaluation.get("tone_match", 0.0),
        "structure_match": evaluation.get("structure_match", 0.0),
        "signature_match": evaluation.get("signature_match", 0.0),
        "feedback": evaluation.get("feedback", ""),
        "flagged_passages": flagged_str,
        "creative_angle": evaluation.get("creative_angle", "unknown")
    }
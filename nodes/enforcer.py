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


@observe("enforcer_node")
def enforcer_node(state: GraphState, analyzer: BrandMetricsSQL) -> GraphState:
    content       = state["content"]
    metrics       = analyzer.get_context()
    iteration     = state.get("iteration", 1)
    max_iterations = 3

    result = LLMSingleton.get().invoke(
        ENFORCER_PROMPT.format(
            metrics=metrics,
            content=content
        )
    )
    
    logger.info("ENFORCER_RAW_OUTPUT:\n%s", result.content[:2000])

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

    # Force a revision cycle if score is below threshold and iterations remain
    # This prevents the enforcer from rubber-stamping weak first drafts
    MIN_SCORE = 7.5
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
                "using first-person plural (we/our), matching the brand's opening and closing patterns, "
                "and weaving in signature phrases naturally."
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

    return {
        **state,
        "approved": evaluation["approved"],
        "score": evaluation["score"],
        "style_match": evaluation.get("style_match", 0.0),
        "tone_match": evaluation.get("tone_match", 0.0),
        "structure_match": evaluation.get("structure_match", 0.0),
        "signature_match": evaluation.get("signature_match", 0.0),
        "feedback": evaluation.get("feedback", ""),
        "creative_angle": evaluation.get("creative_angle", "unknown")
    }
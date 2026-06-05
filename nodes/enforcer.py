# nodes/enforcer.py
import json
import logging
from model import LLMSingleton
from brand_metrics import BrandMetricsSQL
from prompts.enforcer import ENFORCER_PROMPT
from graph.state import GraphState

logger = logging.getLogger(__name__)

from utils.observe import observe
@observe("researcher_node")
def enforcer_node(state: GraphState, analyzer: BrandMetricsSQL) -> GraphState:
    content = state["content"]
    metrics = analyzer.get_context()
    iteration = state.get("iteration", 1)
    max_iterations = 3


    result = LLMSingleton.get().invoke(
        ENFORCER_PROMPT.format(
            metrics=metrics,
            content=content
        )
    )

    try:
        evaluation = json.loads(result.content)
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
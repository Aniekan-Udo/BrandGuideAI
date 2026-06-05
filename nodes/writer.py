# nodes/writer.py
import logging
from model import LLMSingleton
from brand_rag import BrandRAG
from learning_memory import FeedbackPortSQL
from brand_metrics import BrandMetricsSQL
from prompts.writer import WRITER_INITIAL, WRITER_REVISION
from graph.state import GraphState

logger = logging.getLogger(__name__)
from utils.observe import observe


DEFAULT_METRICS = {
    "tone": "warm, conversational",
    "perspective": "first-person plural (we/our)",
    "style": "short punchy sentences",
    "avoid": ["passive voice", "corporate jargon"]
}

GENERIC_EXAMPLES = """
Example 1: Community-focused storytelling
"We believe every customer should feel valued. Here's how we do it..."

Example 2: Benefit-led messaging
"Looking for sustainable fashion? Our new collection is here..."
"""

DEFAULT_PATTERNS = {
    "approved": [],
    "rejected": []
}

@observe("writer_node")
def writer_node(state: GraphState, rag: BrandRAG, analyzer: BrandMetricsSQL,
                memory: FeedbackPortSQL) -> GraphState:
    """
    Generates or revises brand-consistent content.
    """
    topic        = state["topic"]
    content_type = state["content_type"]
    research     = state["research"]
    feedback     = state.get("feedback", "")
    iteration    = state.get("iteration", 0) + 1


    try:
        metrics  = analyzer.get_context()
    except Exception as e:
        logger.warning("Metrics analyzer failed, using defaults: %s", e)
        metrics = DEFAULT_METRICS
    

    try:
        examples = rag.query(topic)
    except Exception as e:
        logger.warning("RAG failed, using generic examples: %s", e)
        examples = GENERIC_EXAMPLES


    try:
        patterns = memory.get_patterns(content_type)
    except Exception as e:
        logger.warning("Memory failed, using empty patterns: %s", e)
        patterns = DEFAULT_PATTERNS

    approved = [p["angle"] for p in patterns.get("approved", [])][:3]
    rejected = [p["angle"] for p in patterns.get("rejected", [])][:2]

    if iteration == 1:
        prompt = WRITER_INITIAL.format(
            topic=topic,
            content_type=content_type,
            research=research,
            metrics=metrics,
            examples=examples,
            approved="\n".join(approved) if approved else "None yet",
            rejected="\n".join(rejected) if rejected else "None yet"
        )
    else:
        prompt = WRITER_REVISION.format(
            previous_content=state.get("content", ""),
            feedback=feedback,
            style_match=state.get("style_match", 0.0),
            tone_match=state.get("tone_match", 0.0),
            structure_match=state.get("structure_match", 0.0),
            signature_match=state.get("signature_match", 0.0),
            metrics=metrics,
            examples=examples
        )

 
    try:
        result = LLMSingleton.get().invoke(prompt)
        content = result.content
    except Exception as e:
        logger.error("LLM failed: %s", e)
        content = f"[System Error: Unable to generate content - {str(e)[:80]}]"

    logger.info("Writer iteration=%d complete for topic=%r", iteration, topic)

    return {
        **state,
        "content": content,
        "iteration": iteration
    }
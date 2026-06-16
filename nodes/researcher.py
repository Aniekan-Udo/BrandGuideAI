# nodes/researcher.py
import logging
from model import LLMSingleton
from search import TavilySearch
from brand_rag import BrandRAG
from brand_metrics import BrandMetricsSQL
from prompts.researcher import RESEARCH_SUMMARY
from graph.state import GraphState

logger = logging.getLogger(__name__)
from utils.observe import observe


@observe("researcher_node")
def researcher_node(state: GraphState, search: TavilySearch, rag: BrandRAG,
                    analyzer: BrandMetricsSQL = None) -> GraphState:
    """
    Retrieves research context for content generation.

    Default: queries RAG system using uploaded product documents
    as source of truth for content generation.

    Optional: performs web search when use_search is True,
    useful for trend-based or statistics-driven content.

    Args:
        state:    Current graph state
        search:   Search port for optional web search
        rag:      RAG system for product document retrieval
        analyzer: Brand metrics for context-aware research filtering

    Returns:
        Updated state with research context
    """
    topic = state["topic"]
    content_type = state["content_type"]

    # Extract brief brand context for research filtering (#7)
    brand_context = "No brand context available — summarize neutrally."
    if analyzer is not None:
        try:
            metrics = analyzer.get_context()
            if metrics:
                # Extract just the overview and value hierarchy for research filtering
                from nodes.writer import _extract_section
                overview = _extract_section(metrics, "BRAND VOICE OVERVIEW")
                value_hierarchy = _extract_section(metrics, "VALUE HIERARCHY")
                diagnostic = _extract_section(metrics, "DIAGNOSTIC STYLE")
                
                parts = [p for p in [overview, value_hierarchy, diagnostic] if p]
                if parts:
                    brand_context = " ".join(parts)[:500]  # Cap at 500 chars
        except Exception as e:
            logger.warning("Failed to extract brand context for research: %s", e)

    if state.get("use_search", False):
        raw_results = search.search(query=topic, max_results=5)
        research = LLMSingleton.get().invoke(
            RESEARCH_SUMMARY.format(
                topic=topic,
                content_type=content_type,
                results=raw_results,
                brand_context=brand_context
            )
        ).content
    else:
        research = rag.query(topic)

    logger.info(
        "Research complete via %s for topic=%r",
        "web_search" if state.get("use_search") else "rag",
        topic
    )

    return {**state, "research": research}
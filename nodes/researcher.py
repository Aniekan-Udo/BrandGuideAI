# nodes/researcher.py
import logging
from model import LLMSingleton
from search import TavilySearch
from brand_rag import BrandRAG
from prompts.researcher import RESEARCH_SUMMARY
from graph.state import GraphState

logger = logging.getLogger(__name__)
from utils.observe import observe
@observe("researcher_node")
def researcher_node(state: GraphState, search: TavilySearch, rag: BrandRAG) -> GraphState:
    """
    Retrieves research context for content generation.

    Default: queries RAG system using uploaded product documents
    as source of truth for content generation.

    Optional: performs web search when use_search is True,
    useful for trend-based or statistics-driven content.

    Args:
        state:  Current graph state
        search: Search port for optional web search
        llm:    LLM model for summarizing web search results
        rag:    RAG system for product document retrieval

    Returns:
        Updated state with research context
    """
    topic = state["topic"]
    content_type = state["content_type"]
    

    if state.get("use_search", False):
        raw_results = search.search(query=topic, max_results=5)
        research = LLMSingleton.get().invoke(
    RESEARCH_SUMMARY.format(
        topic=topic,
        content_type=content_type,
        results=raw_results
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
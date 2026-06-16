from graph.state import GraphState
from nodes import researcher_node, writer_node, enforcer_node, deployer_node
from search import TavilySearch
from brand_rag import BrandRAG
from learning_memory import FeedbackPortSQL
from brand_metrics import BrandMetricsSQL
from langgraph.graph import StateGraph, END
from functools import partial

def build_graph(
    search: TavilySearch,
    rag: BrandRAG,
    analyzer: BrandMetricsSQL,
    memory: FeedbackPortSQL,
) -> StateGraph:

    researcher = partial(researcher_node, rag=rag, search=search, analyzer=analyzer)
    writer     = partial(writer_node, rag=rag, analyzer=analyzer, memory=memory)
    enforcer   = partial(enforcer_node, analyzer=analyzer, rag=rag)
    deployer   = partial(deployer_node, memory=memory)

    graph = StateGraph(GraphState)

    graph.add_node("researcher", researcher)
    graph.add_node("writer",     writer)
    graph.add_node("enforcer",   enforcer)
    graph.add_node("deployer",   deployer)

    graph.set_entry_point("researcher")
    graph.add_edge("researcher", "writer")
    graph.add_edge("writer",     "enforcer")

    graph.add_conditional_edges(
        "enforcer",
        lambda s: "deployer" if s["approved"] else "writer"
    )

    graph.add_edge("deployer", END)

    return graph.compile()
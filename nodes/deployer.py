import uuid
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
from learning_memory import FeedbackPortSQL
from graph.state import GraphState
from database import get_db_session, Generation
from utils.observe import observe


@observe("deployer_node")
def deployer_node(state: GraphState, memory: FeedbackPortSQL) -> GraphState:
    generation_id = state["generation_id"]
    logger.info("DEPLOYER NODE: received content of length %s", len(state.get("content", "")))

    with get_db_session() as session:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = pg_insert(Generation).values(
            generation_id=generation_id,
            business_id=state["business_id"],
            content_type=state["content_type"],
            topic=state["topic"],
            format_type=state["format_type"],
            user_id=state.get("user_id"),
            status="completed",
            score=state.get("score", 0.0),
            content=state["content"],
            completed_at=datetime.utcnow()
        ).on_conflict_do_update(
            index_elements=["generation_id"],
            set_={
                "status": "completed",
                "score": state.get("score", 0.0),
                "content": state["content"],
                "completed_at": datetime.utcnow()
            }
        )
        session.execute(stmt)
        session.commit()

    memory.save(
        generation_id=generation_id,
        content_type=state["content_type"],
        creative_angle=state.get("creative_angle", "unknown"),
        generated_content=state["content"],
        auto_score=state.get("score", 0.0),
        topic=state["topic"],
        format_type=state["format_type"],
        user_id=state.get("user_id"),
        style_match=state.get("style_match", 0.0),
        tone_match=state.get("tone_match", 0.0),
        structure_match=state.get("structure_match", 0.0),
        signature_match=state.get("signature_match", 0.0)
    )

    logger.info(
        "Generation complete generation_id=%s score=%.1f iterations=%d",
        generation_id, state.get("score", 0.0), state.get("iteration", 1)
    )

    return {
        **state,
        "status": "complete"
    }
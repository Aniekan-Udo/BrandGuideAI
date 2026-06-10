import logging
import uuid
from sqlalchemy.exc import SQLAlchemyError
from database import get_db_session, ReviewerLearning

logger = logging.getLogger(__name__)


def promote_to_brand_metrics(generation_id: str) -> None:
    """
    Called by process_feedback after human feedback is saved.
    - Approved: no action needed — generation already saved to DB
    - Rejected: re-trigger full generation with human feedback
    """
    from celery_task import generate_content

    try:
        with get_db_session() as session:
            record = session.query(ReviewerLearning).filter_by(
                generation_id=generation_id,
                has_human_feedback=True
            ).first()

            if not record:
                logger.warning("No feedback found for generation_id=%s", generation_id)
                return

            if record.human_approved:
                logger.info("Generation %s approved — no re-trigger needed", generation_id)
                return

            # Rejected — re-trigger with human feedback injected
            generate_content.delay(
                generation_id=str(uuid.uuid4()),
                business_id=record.business_id,
                content_type=record.content_type,
                topic=record.topic,
                format_type=record.format_type,
                user_id=record.user_id,
                use_search=True,
                human_feedback=record.human_feedback,
            )
            logger.info("Re-generation triggered from rejected generation_id=%s", generation_id)

    except SQLAlchemyError as e:
        logger.error("DB error in promote_to_brand_metrics generation_id=%s: %s", generation_id, e)



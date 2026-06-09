from celery import Celery
from kombu import Queue
import os
import logging
from database import get_db_session

from graph import state

logger = logging.getLogger(__name__)
import json
import redis

import redis
redis_client = redis.Redis(host="redis", port=6379, decode_responses=True)

# ---------------------------------------------------------------------------
# Celery app
# ---------------------------------------------------------------------------

celery_app = Celery(
    "brandguard",
    broker=os.getenv("RABBIT_URL", "amqp://guest:guest@rabbitmq:5672//"),
    backend=os.getenv("REDIS_URL", "redis://redis:6379/0")
)


from kombu import Queue, Exchange

rag_exchange = Exchange("rag_refresh", type="direct")

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True, 
    task_reject_on_worker_lost=True,
    task_queues=[
        Queue("generation",  durable=True, exchange=Exchange("generation",  type="direct"), routing_key="generation"),
        Queue("feedback",    durable=True, exchange=Exchange("feedback",    type="direct"), routing_key="feedback"),
        Queue("retraining",  durable=True, exchange=Exchange("retraining",  type="direct"), routing_key="retraining"),
        Queue("rag_refresh", durable=True, exchange=Exchange("rag_refresh", type="direct"), routing_key="rag_refresh"), 
    ],
    task_default_queue="generation",
    task_routes={
        "tasks.generate_content":            {"queue": "generation"},
        "tasks.process_feedback":            {"queue": "feedback"},
        "tasks.retrain":                     {"queue": "retraining"},
        "tasks.refresh_rag":                 {"queue": "rag_refresh"},
        "tasks.extract_metrics":             {"queue": "rag_refresh"},  
        "tasks.promote_generation_feedback": {"queue": "rag_refresh"},  
    }
)

def get_redis():
    return redis.Redis(host="redis", port=6379, decode_responses=True)

# In each task that needs it:
r = get_redis()
# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    name="tasks.generate_content",
    max_retries=2,              # reduce from 3
    default_retry_delay=10,
    soft_time_limit=300,  # 5 minutes soft limit
    time_limit=360          # graceful stop at 85s
)
def generate_content(
    self,
    generation_id: str,
    business_id: str,
    content_type: str,
    topic: str,
    format_type: str,
    user_id: int = None,
    use_search: bool = False
):
    from brand_rag import BrandRAG, FastEmbedEmbedding
    from brand_metrics import BrandMetricsSQL
    from learning_memory import FeedbackPortSQL
    from search import TavilySearch
    from model import LLMSingleton
    from graph.graph import build_graph
    import asyncio
    from database import Generation
    from datetime import datetime
    from graph.state import GraphState
    import asyncio

    try:
        initial_state = GraphState(
            business_id=business_id,
            content_type=content_type,
            topic=topic,
            format_type=format_type,
            user_id=user_id,
            use_search=use_search,   
            research="",
            content="",
            creative_angle="",
            iteration=0,
            approved=False,
            feedback="",
            score=0.0,
            generation_id=generation_id,
            status="pending"
        )

        with get_db_session() as session:
            existing = session.get(Generation, generation_id)
            if existing and existing.status == "completed":
                logger.info(
                    "Generation already completed business_id=%s generation_id=%s",
                    business_id, generation_id
                )
                return {"status": "completed", "generation_id": generation_id}

        search   = TavilySearch(api_key=os.getenv("TAVILY_API_KEY"))
        rag      = BrandRAG(
                        business_id=business_id,
                        content_type=content_type,
                        embedding=FastEmbedEmbedding()
                    )
        analyzer = BrandMetricsSQL(
                        business_id=business_id,
                        content_type=content_type
                    )
        memory   = FeedbackPortSQL(business_id=business_id)

        graph_flow = build_graph(search, rag, analyzer, memory)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            final_state = loop.run_until_complete(_run_graph(graph_flow, initial_state))
        finally:
            loop.close()


        logger.info(
            "Generation complete business_id=%s generation_id=%s score=%.1f",
            business_id,
            final_state.get("generation_id", ""),
            final_state.get("score", 0.0)
        )

        return {
            "status":        "completed",
            "generation_id": generation_id,
            "score":         final_state.get("score", 0.0)
        }

    except Exception as exc:
        logger.error(
            "Generation failed business_id=%s generation_id=%s: %s",
            business_id, generation_id, exc
        )
        raise self.retry(exc=exc, countdown=10)


async def _run_graph(graph_flow, initial_state):
    from redis.asyncio import Redis

    async_redis = Redis(host="redis", port=6379, decode_responses=True)

    final_state = dict(initial_state)
    generation_id = initial_state['generation_id']
    stream_failed = False

    try:
        async for chunk in graph_flow.astream(initial_state):
            for node_name, node_state in chunk.items():
                if isinstance(node_state, dict):
                    final_state.update(chunk)

            if stream_failed:
                continue

            try:
                async with async_redis.pipeline() as pipe:
                    pipe.rpush(f"stream:{generation_id}", json.dumps(chunk))
                    pipe.expire(f"stream:{generation_id}", 3600)
                    await pipe.execute()
            except Exception as e:
                logger.warning("Stream failed for %s: %s", generation_id, e)
                stream_failed = True
                # Continue processing, just stop streaming
                # Client will poll DB for final result          
    except Exception as e:
        logger.error("Graph execution failed: %s", e)
        # Still save to DB what we got
        final_state["status"] = "failed"

    return final_state


@celery_app.task(
    bind=True,
    name="tasks.process_feedback",
    max_retries=3,
    default_retry_delay=5
)
def process_feedback(
    self,
    generation_id: str,
    business_id: str,
    content_type: str,
    human_approved: bool,
    human_score: float,
    human_feedback: str
) -> dict:
    try:
        from learning_memory import FeedbackPortSQL
        from database import get_db_session, ReviewerLearning

        memory = FeedbackPortSQL(business_id=business_id)

        with get_db_session() as session:
            existing = session.query(ReviewerLearning).filter_by(
                generation_id=generation_id,
                has_human_feedback=True
            ).first()

            if existing:
                logger.info(f"Feedback for {generation_id} already saved, skipping")
                return {"status": "already_saved", "generation_id": generation_id}

        memory.save_feedback(
            generation_id=generation_id,
            human_approved=human_approved,
            human_score=human_score,
            human_feedback=human_feedback
        )

        RETRAIN_THRESHOLD = 100

        with get_db_session() as session:
            unprocessed = session.query(ReviewerLearning).filter_by(
                business_id=business_id,
                content_type=content_type,
                has_human_feedback=True,
                used_for_retraining=False
            ).with_for_update().count()

            if unprocessed >= RETRAIN_THRESHOLD:
                session.query(ReviewerLearning).filter_by(
                    business_id=business_id,
                    content_type=content_type,
                    has_human_feedback=True,
                    used_for_retraining=False
                ).update({"used_for_retraining": True})
                session.commit()

                retrain.delay(
                    business_id=business_id,
                    content_type=content_type
                )

                logger.info(
                    "Retraining triggered business_id=%s unprocessed=%d",
                    business_id, unprocessed
                )

        return {"status": "saved", "generation_id": generation_id}

    except Exception as exc:
        logger.error("Feedback failed generation_id=%s: %s", generation_id, exc)
        raise self.retry(exc=exc, countdown=5)


@celery_app.task(
    bind=True,
    name="tasks.retrain",
    max_retries=2,
    default_retry_delay=60
)
def retrain(self, business_id, content_type):
    lock_key = f"retrain:{business_id}:{content_type}"
    lock = redis_client.lock(lock_key, timeout=300)

    if not lock.acquire(blocking=False):
        logger.info(f"Retraining already running for {business_id}, skipping")
        return {"status": "skipped", "reason": "already_running"}

    try:
        from brand_metrics import BrandMetricsSQL

        analyzer = BrandMetricsSQL(
                        business_id=business_id,
                        content_type=content_type
                    )
        analyzer._metrics_cache = None
        analyzer._extract_metrics()

        return {"status": "retrained", "business_id": business_id}

    except Exception as exc:
        logger.error("Retraining failed business_id=%s: %s", business_id, exc)
        raise self.retry(exc=exc, countdown=60)

    finally:
        lock.release()


@celery_app.task(
    bind=True,
    name="tasks.refresh_rag",
    max_retries=3,
    default_retry_delay=10
)
def refresh_rag(self, business_id, content_type, new_doc_content):
    import hashlib
    from brand_rag import BrandRAG, FastEmbedEmbedding
    from brand_metrics import BrandMetricsSQL

    doc_hash = hashlib.sha256(new_doc_content.encode()).hexdigest()
    lock_key = f"rag_refresh:{business_id}:{content_type}:{doc_hash}"
    lock = redis_client.lock(lock_key, timeout=120)

    if not lock.acquire(blocking=False):
        logger.info("RAG refresh already running for this document")
        return {"status": "skipped", "reason": "already_running"}

    try:
        rag = BrandRAG(
            business_id=business_id,
            content_type=content_type,
            embedding=FastEmbedEmbedding()
        )
        analyzer = BrandMetricsSQL(
            business_id=business_id,
            content_type=content_type
        )
        rag.refresh(new_doc_content)
        analyzer.invalidate_cache()
        logger.info(
            "RAG refresh complete business_id=%s content_type=%s",
            business_id, content_type
        )
        return {"status": "refreshed", "business_id": business_id}

    except Exception as exc:
        logger.error("RAG refresh failed business_id=%s: %s", business_id, exc)
        raise self.retry(exc=exc, countdown=10)

    finally:
        lock.release()


@celery_app.task(bind=True, name="tasks.extract_metrics", max_retries=3, default_retry_delay=10)
def extract_metrics(self, business_id: str, content_type: str, doc_id: int, doc_content: str):
    from brand_metrics import BrandMetricsSQL
    analyzer = BrandMetricsSQL(business_id=business_id, content_type=content_type)
    try:
        inserted = analyzer.extract_and_save(doc_id=doc_id, doc_content=doc_content)
        if not inserted:
            return {"status": "skipped", "reason": "already_extracted"}

        lock_key = f"context_rebuild:{business_id}:{content_type}"
        lock = redis_client.lock(lock_key, timeout=180)
        if not lock.acquire(blocking=True, blocking_timeout=30):
            return {"status": "complete", "synthesis": "deferred"}
        try:
            analyzer.build_and_cache_context()
        finally:
            lock.release()

        return {"status": "complete", "business_id": business_id, "doc_id": doc_id}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=10)


@celery_app.task(bind=True, name="tasks.promote_generation_feedback", max_retries=3, default_retry_delay=30)
def promote_generation_feedback(self, business_id: str, content_type: str, generation_content: str, human_approved: bool, score: float):
    from brand_metrics import BrandMetricsSQL

    score_weight = 2.0 if human_approved else (1.5 if score >= 9.0 else 1.2)
    analyzer = BrandMetricsSQL(business_id=business_id, content_type=content_type)

    try:
        inserted = analyzer.save_generation_feedback(generation_content=generation_content, score_weight=score_weight)
        if not inserted:
            return {"status": "skipped", "reason": "already_processed"}

        lock_key = f"context_rebuild:{business_id}:{content_type}"
        lock = redis_client.lock(lock_key, timeout=180)
        if lock.acquire(blocking=True, blocking_timeout=30):
            try:
                analyzer.build_and_cache_context()
            finally:
                lock.release()

        return {"status": "complete", "score_weight": score_weight}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)
from contextlib import asynccontextmanager
from fastapi import Depends, Request, File
from fastapi.responses import JSONResponse


from uuid import uuid4

import json
import time
from fastapi.responses import StreamingResponse

from fastapi import APIRouter
from limiter import limiter, RateLimitExceeded
router = APIRouter()
from utils import logger, create_idempotency_key


from schema import GenerateRequest, FeedbackRequest, TaskResponse






@router.post("/generate/stream")
@limiter.limit("60/minute")
async def generate_stream(request: Request, body: GenerateRequest):
    from celery_task import generate_content
    from database import get_db_session, Generation

    redis_client = request.app.state.redis
    generation_id = str(uuid4())

    with get_db_session() as session:
        record = Generation(
            generation_id=generation_id,
            business_id=body.business_id,
            content_type=body.content_type,
            topic=body.topic,
            format_type=body.format_type,
            user_id=body.user_id,
            status="pending"
        )
        session.add(record)

    generate_content.delay(
        generation_id=generation_id,
        business_id=body.business_id,
        content_type=body.content_type,
        topic=body.topic,
        format_type=body.format_type,
        user_id=body.user_id
    )

    async def stream():
        yield json.dumps({"generation_id": generation_id}) + "\n"

        
        start = time.monotonic()
        MAX_STREAM_SECONDS = 300

        while True:
            if await request.is_disconnected():
                break

            if time.monotonic() - start > MAX_STREAM_SECONDS:
                logger.warning(
                    "Stream timed out after %ds generation_id=%s",
                    MAX_STREAM_SECONDS, generation_id
                )
                break

            chunk = redis_client.blpop(f"stream:{generation_id}", timeout=5)

            if chunk is None:
                with get_db_session() as session:
                    record = session.get(Generation, generation_id)
                    if record and record.status in ("completed", "failed", "timeout"):
                        break
                continue

            yield chunk[1]

    return StreamingResponse(stream(), media_type="application/json")




@router.post("/feedback", response_model=TaskResponse)
@limiter.limit("30/minute")
async def submit_feedback(request: FeedbackRequest, req: Request):
    from celery_task import process_feedback

    task = process_feedback.delay(
        generation_id=request.generation_id,
        business_id=request.business_id,
        content_type=request.content_type,
        human_approved=request.human_approved,
        human_score=request.human_score,
        human_feedback=request.human_feedback
    )

    logger.info(
        "Feedback queued task_id=%s generation_id=%s approved=%s",
        task.id, request.generation_id, request.human_approved
    )

    return {"task_id": task.id, "status": "queued"}


@router.get("/health")
async def health():
    return {"status": "healthy"}


@router.get("/patterns/{business_id}/{content_type}")
async def get_patterns(business_id: str, content_type: str):
    from learning_memory import LearningMemorySQL

    memory = LearningMemorySQL(business_id=business_id)
    patterns = memory.get_patterns(content_type)

    return {
        "business_id": business_id,
        "content_type": content_type,
        "approved_count": len(patterns["approved"]),
        "rejected_count": len(patterns["rejected"]),
        "patterns": patterns
    }
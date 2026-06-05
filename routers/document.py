
from celery import group
from fastapi import HTTPException, Depends, Request
from sqlalchemy.orm import Session
from database import get_db
from schema import DocumentUploadRequest, TaskResponse
from typing import Annotated
from fastapi import UploadFile, File
from fastapi import APIRouter
from limiter import limiter
router = APIRouter()
from utils import create_idempotency_key, logger

@router.post("/documents/top-performing", response_model=TaskResponse)
@limiter.limit("20/minute")
async def upload(request: Request, body: DocumentUploadRequest, db: Annotated[Session, Depends(get_db)], file: UploadFile = File(...)):
    from celery_task import refresh_rag, extract_metrics
    from database import BrandDocument

    ALLOWED_TYPES = {"application/pdf", "text/plain", "text/csv"}
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="File type not supported")

    file_content = await file.read()
    if len(file_content) == 0:
        raise HTTPException(status_code=400, detail="File is empty")
    
    try:
        doc_content = file_content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded text")

    if len(doc_content) > 100000:  # Arbitrary limit of ~100k characters
        raise HTTPException(status_code=400, detail="File is too large")

    _idempotency_key = f"{request.business_id}:{create_idempotency_key(file_content)}"
    if app.state.redis.exists(_idempotency_key):
        raise HTTPException(status_code=409, detail="File already processed")


    
    doc = BrandDocument(
        business_id=body.business_id,
        content_type=body.content_type,
        file_content=doc_content,
        filename=file.filename or "upload",
    )
    try:
        db.add(doc)
        db.flush()  
        db.commit()
        doc_id = doc.id
    except Exception as e:
        db.rollback()
        logger.error("Database error while saving document: %s", e)
        raise HTTPException(status_code=500, detail="Failed to save document")


    task_group = group(
        refresh_rag.s(business_id=body.business_id, content_type=body.content_type, new_doc_content=doc_content),
        extract_metrics.s(business_id=body.business_id, content_type=body.content_type, doc_id=doc_id, doc_content=doc_content)
    )
    result = task_group.delay()
    app.state.redis.set(_idempotency_key, "processing", ex=86400)

    return {"task_id": result.id, "status": "queued"}

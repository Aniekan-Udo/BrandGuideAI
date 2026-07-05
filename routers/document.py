
from fastapi import HTTPException, Depends, Request, Form, File, UploadFile
from sqlalchemy.orm import Session
from database import get_db
from schema import TaskResponse
from typing import Annotated, Optional
from fastapi import APIRouter
from limiter import limiter
from utils import create_idempotency_key, logger
from celery import group

router = APIRouter()

@router.post("/documents/top-performing", response_model=TaskResponse)
@limiter.limit("20/minute")
async def upload(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    business_id: str = Form(...),
    content_type: str = Form(...),
    platform: Optional[str] = Form(None),
    performance_metric: Optional[str] = Form(None),
    file: UploadFile = File(...)
):
    from celery_task import refresh_rag, extract_metrics
    from database import BrandDocument

    ALLOWED_TYPES = {"application/pdf", "text/plain", "text/csv", "tex/docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="File type not supported")

    file_content = await file.read()
    if len(file_content) == 0:
        raise HTTPException(status_code=400, detail="File is empty")
    
    try:
        doc_content = file_content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded text")

    if len(doc_content) > 200000: 
        raise HTTPException(status_code=400, detail="File is too large")

    _idempotency_key = f"{business_id}:{create_idempotency_key(file_content)}"
    if request.app.state.redis.exists(_idempotency_key):
        raise HTTPException(status_code=409, detail="File already processed")

    # Get user_id from business_id to associate document with user
    from database import User
    try:
        user = db.query(User).filter(User.business_id == business_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Business ID not found")
        user_id = user.id
    except Exception as e:
        logger.error("Error fetching user for document upload: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")

    doc = BrandDocument(
        user_id=user_id,
        business_id=business_id,
        content_type=content_type,
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
        refresh_rag.s(business_id=business_id, content_type=content_type, new_doc_content=doc_content),
        extract_metrics.s(business_id=business_id, content_type=content_type, doc_id=doc_id, doc_content=doc_content)
    )
    result = task_group.delay()
    request.app.state.redis.set(_idempotency_key, "processing", ex=86400)

    # Return required generation_id along with task_id and status to satisfy TaskResponse schema
    return {"generation_id": "", "task_id": result.id, "status": "queued"}


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)]
):
    from database import BrandDocument
    from celery_task import refresh_rag, extract_metrics
    import hashlib

    doc = db.query(BrandDocument).filter(BrandDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    business_id = doc.business_id
    content_type = doc.content_type
    doc_content = doc.file_content

    # 1. Delete from DB
    db.delete(doc)
    db.commit()

    # 2. Clear Redis Idempotency Key
    if doc_content:
        content_hash = hashlib.md5(doc_content.encode()).hexdigest()
        idempotency_key = f"upload:{business_id}:{content_type}:{content_hash}"
        request.app.state.redis.delete(idempotency_key)

    # 3. Trigger Background Tasks to rebuild the Brand Brain and Vector Index
    # We pass None for new_doc_content to force a full rebuild of the RAG index
    # We trigger extract_metrics without a doc_id so it re-synthesizes from the remaining DB docs
    from celery import group
    task_group = group(
        refresh_rag.s(business_id=business_id, content_type=content_type, new_doc_content=None),
        extract_metrics.s(business_id=business_id, content_type=content_type, doc_id=None, doc_content=None)
    )
    task_group.delay()

    return {"message": "Document deleted and system rebuilding successfully"}

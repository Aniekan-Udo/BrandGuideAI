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
from database import get_db_session, BrandMetrics


@router.post("/brain/{business_id}/{content_type}/review")
@limiter.limit("20/minute")
async def review_brain(business_id: str, content_type: str, review: BrandMetrics):
    
    from datetime import datetime
    from brand_metrics import BrandMetricsSQL
    with get_db_session() as session:
        brain = session.query(BrandMetrics).filter_by(
            business_id=business_id,
            content_type=content_type,
            status='proposed',
        ).first()
        if not brain:
            raise HTTPException(404, "No proposed brain found")
        
        brain.status = review.status  # 'approved' or 'rejected'
        brain.review_notes = review.notes
        brain.reviewed_by = review.reviewer
        brain.reviewed_at = datetime.utcnow()
        session.commit()
        
        if review.status == 'approved':
            # Rebuild context
            analyzer = BrandMetricsSQL(business_id, content_type)
            analyzer.build_and_cache_context()
    
    return {"status": "updated", "new_status": review.status}
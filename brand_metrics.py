import hashlib
import json
import logging
from abc import ABC, abstractmethod
from threading import Lock

import redis
from sqlalchemy.exc import IntegrityError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from database import BrandMetrics, get_db_session, BrandBrain
from model import LLMSingleton
from prompts.metrics import METRICS_EXTRACTION, METRICS_SYNTHESIS

logger = logging.getLogger(__name__)

from datetime import datetime

# Redis TTL for cached brand context — 24 hours
CACHE_TTL = 86400

# Maximum number of recent per-document profiles passed in full to the
# synthesis LLM. Older rows are already baked into the previous synthesis
# and don't need to be re-sent verbatim.
MAX_RECENT_PROFILES = 10


class MetricPort(ABC):
    @property
    @abstractmethod
    def source(self) -> str:
        """Returns the storage backend — 'postgres', 'mongodb', etc."""

    @abstractmethod
    def extract_and_save(self, doc_id: int, doc_content: str) -> bool:
        """
        Extract metrics from a single document and persist as a new
        BrandMetrics row. Returns True if a new row was inserted,
        False if this document was already processed (idempotent).
        """
        ...

    @abstractmethod
    def build_and_cache_context(self) -> str:
        """
        Fetch all metric rows for this (business_id, content_type),
        synthesize them via LLM, and write the result to Redis.
        Returns the synthesized context string.
        """
        ...

    @abstractmethod
    def get_context(self) -> str:
        """
        Return the brand context string for use by the writer/enforcer.
        Reads from Redis cache; falls back to build_and_cache_context()
        if the cache is cold.
        """
        ...


class BrandMetricsSQL(MetricPort):
    def __init__(self, business_id: str, content_type: str):
        self.business_id = business_id
        self.content_type = content_type
        self._redis = redis.Redis(host="redis", port=6379, decode_responses=True)
        self._lock = Lock()

        # Two model tiers — cheap for per-doc extraction, better for synthesis
        self._extraction_llm = LLMSingleton.get("extraction")
        self._synthesis_llm = LLMSingleton.get("synthesis")

    @property
    def source(self) -> str:
        return "postgres"

    @property
    def _cache_key(self) -> str:
        return f"brand_context:{self.business_id}:{self.content_type}"

    # ------------------------------------------------------------------ #
    #  Extraction — runs once per document, called from Celery task       #
    # ------------------------------------------------------------------ #

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def extract_and_save(self, doc_id: int, doc_content: str) -> bool:
        doc_hash = hashlib.sha256(doc_content.encode()).hexdigest()

        # --- idempotency check ---
        with get_db_session() as session:
            exists = session.query(BrandMetrics).filter_by(
                business_id=self.business_id,
                content_type=self.content_type,
                doc_hash=doc_hash,
            ).first()
            if exists:
                logger.info(
                    "Metrics already extracted for doc_hash=%s business=%s",
                    doc_hash[:8], self.business_id
                )
                return False

        # --- LLM extraction (cheap model) ---
        result = self._extraction_llm.invoke(
            METRICS_EXTRACTION.format(
                document=doc_content,
                content_type=self.content_type,
            )
        )

        try:
            raw = result.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            extracted = json.loads(raw.strip())
        except json.JSONDecodeError:
            logger.error("Extraction LLM returned invalid JSON — skipping persist")
            return False

        # --- persist new row ---
        try:
            with get_db_session() as session:
                row = BrandMetrics(
                    business_id=self.business_id,
                    content_type=self.content_type,
                    doc_id=doc_id,
                    doc_hash=doc_hash,
                    extracted=extracted,
                    score_weight=1.0,
                    source="document",
                )
                session.add(row)
                session.commit()
                logger.info(
                    "Persisted metrics for doc_id=%s business=%s content_type=%s",
                    doc_id, self.business_id, self.content_type
                )
                return True

        except IntegrityError:
            # Race condition — another worker already inserted this hash
            logger.warning("Duplicate doc_hash on insert — race condition handled gracefully")
            return False

    # ------------------------------------------------------------------ #
    #  Feedback loop — called by Celery when a generation scores highly  #
    # ------------------------------------------------------------------ #

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def save_generation_feedback(
        self,
        generation_content: str,
        score_weight: float,
    ) -> bool:
        """
        Extract metrics from a high-scoring generation and add it to the
        knowledge base. score_weight reflects quality — human-approved
        content should carry a higher weight than auto-approved.
        """
        doc_hash = hashlib.sha256(generation_content.encode()).hexdigest()

        with get_db_session() as session:
            exists = session.query(BrandMetrics).filter_by(
                business_id=self.business_id,
                content_type=self.content_type,
                doc_hash=doc_hash,
            ).first()
            if exists:
                return False

        result = self._extraction_llm.invoke(
            METRICS_EXTRACTION.format(
                document=generation_content,
                content_type=self.content_type,
            )
        )

        try:
            raw = result.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            extracted = json.loads(raw.strip())
        except json.JSONDecodeError:
            logger.error("Extraction LLM returned invalid JSON — skipping persist")
            return False

        try:
            with get_db_session() as session:
                row = BrandMetrics(
                    business_id=self.business_id,
                    content_type=self.content_type,
                    doc_id=None,        # not sourced from an uploaded document
                    doc_hash=doc_hash,
                    extracted=extracted,
                    score_weight=score_weight,
                    source="generation",
                )
                session.add(row)
                session.commit()
                logger.info(
                    "Persisted generation feedback business=%s weight=%.2f",
                    self.business_id, score_weight
                )
                return True

        except IntegrityError:
            return False

    # ------------------------------------------------------------------ #
    #  Synthesis — assembles and caches the brand context                 #
    # ------------------------------------------------------------------ #

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def build_and_cache_context(self) -> str:
        with get_db_session() as session:
            rows = (
                session.query(BrandMetrics)
                .filter_by(
                    business_id=self.business_id,
                    content_type=self.content_type,
                )
                .order_by(BrandMetrics.created_at.asc())
                .all()
            )

        if not rows:
            logger.info(
                "No metric rows found for business=%s content_type=%s",
                self.business_id, self.content_type,
            )
            return ""

        # Pass the most recent N profiles in full to the synthesis LLM.
        # Older ones are already captured in previous synthesis passes.
        recent = rows[-MAX_RECENT_PROFILES:]

        profiles_block = self._format_profiles_for_synthesis(recent)

        result = self._synthesis_llm.invoke(
            METRICS_SYNTHESIS.format(
                business_id=self.business_id,
                content_type=self.content_type,
                total_documents=len(rows),
                profiles=profiles_block,
            )
        )

        context = result.content
    
        # Persist to Postgres
        with get_db_session() as session:
            brain = session.query(BrandBrain).filter_by(
                business_id=self.business_id,
                content_type=self.content_type,
            ).first()
            
            if brain:
                brain.synthesis_text = context
                brain.profile_count = len(rows)
                brain.last_synthesis_at = datetime.utcnow()
                brain.version += 1
            else:
                brain = BrandBrain(
                    business_id=self.business_id,
                    content_type=self.content_type,
                    synthesis_text=context,
                    profile_count=len(rows),
                )
                session.add(brain)
            session.commit()
        
        # Cache to Redis
        self._redis.set(self._cache_key, context, ex=CACHE_TTL)
        return context

    def _format_profiles_for_synthesis(self, rows: list) -> str:
        """
        Format metric rows into a structured block for the synthesis prompt.
        Each row becomes a clearly delimited section with its source and weight.
        """
        sections = []
        for i, row in enumerate(rows, 1):
            section = (
                f"## Profile {i} "
                f"(source: {row.source}, weight: {row.score_weight:.1f}, "
                f"date: {row.created_at.strftime('%Y-%m-%d')})\n"
                f"{json.dumps(row.extracted, indent=2)}"
            )
            sections.append(section)
        return "\n\n".join(sections)

    # ------------------------------------------------------------------ #
    #  Read path — called by writer and enforcer nodes                    #
    # ------------------------------------------------------------------ #

    def get_context(self) -> str:
        # 1. Try Redis
        cached = self._redis.get(self._cache_key)
        if cached:
            return cached
        
        # 2. Try Postgres brain
        with get_db_session() as session:
            brain = session.query(BrandBrain).filter_by(
                business_id=self.business_id,
                content_type=self.content_type,
            ).first()
            if brain:
                # Warm cache
                self._redis.set(self._cache_key, brain.synthesis_text, ex=CACHE_TTL)
                return brain.synthesis_text
        
        
        return self.build_and_cache_context()

    def invalidate_cache(self):
        """Force Redis cache eviction — next get_context() will rebuild."""
        self._redis.delete(self._cache_key)
        logger.info(
            "Cache invalidated for business=%s content_type=%s",
            self.business_id, self.content_type,
        )

    def delete_all(self):
        """Remove all metric rows and cache for this business + content_type."""
        with get_db_session() as session:
            session.query(BrandMetrics).filter_by(
                business_id=self.business_id,
                content_type=self.content_type,
            ).delete()
            session.commit()
        self.invalidate_cache()
        logger.info(
            "Deleted all metrics for business=%s content_type=%s",
            self.business_id, self.content_type,
        )
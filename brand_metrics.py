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
from prompts.metrics import (  # v5: asset consolidation rules, honest confidence, subset bias prevention
    PASS0_DOCUMENT_INVENTORY,      # NEW: extracts verbatim opening/closing + classification
    PASS1_STRUCTURAL_DNA,          # REVISED: enforces skeleton quality, detects canonical formula
    PASS2_ASSET_BANK,              # UNCHANGED
    PASS25_OPENING_CLOSING_ABSTRACTION,  # NEW: anti-overfitting gate — abstracts verbatim text into pure structure
    PASS3_PATTERN_CONSOLIDATION,   # NEW: cross-document canonical/variant/unique pattern detection
    PASS4_BEST_EXAMPLE_SELECTION,  # REVISED: scores Pass 2.5 abstractions (not verbatim text)
    METRICS_SYNTHESIS,             # REVISED: receives all 5 pass outputs
)

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
        run Pass 3 pattern consolidation and Pass 4 example selection,
        synthesize via LLM, and write the result to Redis and Postgres BrandBrain.
        Returns the synthesized context string.
        """
        ...

    @abstractmethod
    def get_context(self) -> str:
        """
        Return the brand context string for use by the writer/enforcer.
        Reads from Redis cache; falls back to Postgres BrandBrain;
        falls back to build_and_cache_context() if both are cold.
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
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _parse_json(self, raw: str) -> dict:
        """
        Strip markdown fences and parse JSON from an LLM response.
        Raises json.JSONDecodeError if the result is not valid JSON.
        """
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())

    def _run_extraction_passes(self, doc_content: str) -> dict:
        """
        Run Pass 0 (inventory), Pass 1 (structural DNA), Pass 2 (asset bank),
        and Pass 2.5 (opening/closing abstraction) on a single document.

        Returns a dict with all four outputs nested under their pass keys:
          {
            "inventory": { ...Pass 0 output... },
            "structural_dna": { ...Pass 1 output... },
            "asset_bank": { ...Pass 2 output... },
            "opening_closing_abstraction": { ...Pass 2.5 output... }
          }

        Raises json.JSONDecodeError if any pass returns invalid JSON.
        """
        # --- Pass 0: Document Inventory ---
        result_pass0 = self._extraction_llm.invoke(
            PASS0_DOCUMENT_INVENTORY.format(document=doc_content)
        )
        inventory = self._parse_json(result_pass0.content)
        structural_classification = inventory.get("structural_classification", "other")

        # --- Pass 1: Structural DNA (uses classification from Pass 0) ---
        result_pass1 = self._extraction_llm.invoke(
            PASS1_STRUCTURAL_DNA.format(
                document=doc_content,
                content_type=self.content_type,
                structural_classification=structural_classification,
            )
        )
        structural_dna = self._parse_json(result_pass1.content)

        # --- Pass 2: Asset Bank ---
        result_pass2 = self._extraction_llm.invoke(
            PASS2_ASSET_BANK.format(
                document=doc_content,
                content_type=self.content_type,
            )
        )
        asset_bank = self._parse_json(result_pass2.content)

        # --- Pass 2.5: Opening/Closing Structural Abstraction ---
        # This is the anti-overfitting gate. It converts verbatim opening/closing
        # into pure structural representations before they ever reach cross-document
        # scoring. No content-specific words survive this pass.
        opening_verbatim = inventory.get("opening", {}).get("text_verbatim", "")
        closing_verbatim = inventory.get("closing", {}).get("text_verbatim", "")

        result_pass25 = self._extraction_llm.invoke(
            PASS25_OPENING_CLOSING_ABSTRACTION.format(
                document_index=0,  # will be set during batch formatting
                content_type=self.content_type,
                structural_classification=structural_classification,
                opening_verbatim=opening_verbatim,
                closing_verbatim=closing_verbatim,
                structural_dna=json.dumps(structural_dna, indent=2),
            )
        )
        opening_closing_abstraction = self._parse_json(result_pass25.content)

        return {
            "inventory": inventory,
            "structural_dna": structural_dna,
            "asset_bank": asset_bank,
            "opening_closing_abstraction": opening_closing_abstraction,
        }

    def _format_structural_profiles(self, rows: list) -> str:
        """
        Format the Pass 1 structural DNA from each row into a labelled
        block for the synthesis LLM.
        Falls back to the flat extracted dict for rows created before
        the five-pass upgrade (backward compatible).
        """
        sections = []
        for i, row in enumerate(rows, 1):
            dna = row.extracted.get("structural_dna", row.extracted)
            section = (
                f"## Profile {i} "
                f"(source: {row.source}, weight: {row.score_weight:.1f}, "
                f"date: {row.created_at.strftime('%Y-%m-%d')})\n"
                f"{json.dumps(dna, indent=2)}"
            )
            sections.append(section)
        return "\n\n".join(sections)

    def _format_asset_banks(self, rows: list) -> str:
        """
        Format the Pass 2 asset banks from each row into a labelled
        block for the synthesis LLM.
        Rows without an asset_bank key (pre-upgrade) are silently skipped.
        """
        sections = []
        for i, row in enumerate(rows, 1):
            assets = row.extracted.get("asset_bank", {})
            if not assets:
                continue
            section = (
                f"## Asset Bank {i} "
                f"(source: {row.source}, weight: {row.score_weight:.1f}, "
                f"date: {row.created_at.strftime('%Y-%m-%d')})\n"
                f"{json.dumps(assets, indent=2)}"
            )
            sections.append(section)
        return "\n\n".join(sections)

    def _format_inventory_for_pass3(self, rows: list) -> str:
        """
        Format the Pass 0 inventory from each row for Pass 3 pattern consolidation.
        Includes structural classification and key metadata flags.
        """
        sections = []
        for i, row in enumerate(rows, 1):
            inv = row.extracted.get("inventory", {})
            # Build a condensed version for Pass 3 — only the structural DNA + classification
            dna = row.extracted.get("structural_dna", row.extracted)
            condensed = {
                "document_index": i,
                "content_type": inv.get("content_type", self.content_type),
                "structural_classification": inv.get("structural_classification", "other"),
                "structural_classification_note": inv.get("structural_classification_note", ""),
                "opening_metadata": {
                    "has_hook": inv.get("opening", {}).get("has_hook", False),
                    "has_social_proof_anchor": inv.get("opening", {}).get("has_social_proof_anchor", False),
                    "has_reframe": inv.get("opening", {}).get("has_reframe", False),
                    "has_reader_address": inv.get("opening", {}).get("has_reader_address", False),
                },
                "closing_metadata": {
                    "has_cta": inv.get("closing", {}).get("has_cta", False),
                    "has_reframe": inv.get("closing", {}).get("has_reframe", False),
                    "has_process_mention": inv.get("closing", {}).get("has_process_mention", False),
                    "has_soft_close": inv.get("closing", {}).get("has_soft_close", False),
                },
                "body_structure_preview": inv.get("body_structure_preview", {}),
                "structural_dna": dna,
            }
            sections.append(json.dumps(condensed, indent=2))
        return "\n\n".join(sections)

    def _format_abstractions_for_pass4(self, rows: list) -> str:
        """
        Format Pass 2.5 abstractions for Pass 4 scoring — NO verbatim text.
        These are pure structural representations with topic-independence scores.
        """
        sections = []
        for i, row in enumerate(rows, 1):
            abs_data = row.extracted.get("opening_closing_abstraction", {})
            # Update document_index to match batch position
            if "opening_abstraction" in abs_data:
                abs_data["document_index"] = i
            sections.append(json.dumps(abs_data, indent=2))
        return "\n\n".join(sections)

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
        """
        Run Pass 0 + Pass 1 + Pass 2 + Pass 2.5 on a document and persist
        the combined output as a single BrandMetrics row.

        The extracted column stores:
          {
            "inventory": { ...Pass 0 output... },
            "structural_dna": { ...Pass 1 output... },
            "asset_bank": { ...Pass 2 output... },
            "opening_closing_abstraction": { ...Pass 2.5 output... }
          }

        Idempotent — returns False without re-extracting if this document
        hash already exists for this business + content_type.
        """
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
                    doc_hash[:8], self.business_id,
                )
                return False

        # --- Run Pass 0, Pass 1, Pass 2, and Pass 2.5 ---
        try:
            extracted = self._run_extraction_passes(doc_content)
        except json.JSONDecodeError:
            logger.error(
                "Extraction LLM returned invalid JSON for doc_id=%s — skipping persist",
                doc_id,
            )
            return False

        # --- Persist new row ---
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
                    page_number=1,
                    total_pages=1,
                    page_hash=doc_hash,
                )
                session.add(row)
                session.commit()
                logger.info(
                    "Persisted metrics for doc_id=%s business=%s content_type=%s",
                    doc_id, self.business_id, self.content_type,
                )
                return True

        except IntegrityError:
            # Race condition — another worker already inserted this hash
            logger.warning("Duplicate doc_hash on insert — race condition handled gracefully")
            return False

    # ------------------------------------------------------------------ #
    #  Feedback loop — called by Celery when a generation scores highly   #
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

        Runs the same Pass 0 + Pass 1 + Pass 2 + Pass 2.5 extraction as
        extract_and_save() so that generation feedback enriches the brand
        profile with the same structure as document-sourced rows.
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

        try:
            extracted = self._run_extraction_passes(generation_content)
        except json.JSONDecodeError:
            logger.error(
                "Extraction LLM returned invalid JSON for generation feedback — skipping persist"
            )
            return False

        try:
            with get_db_session() as session:
                row = BrandMetrics(
                    business_id=self.business_id,
                    content_type=self.content_type,
                    doc_id=None,
                    doc_hash=doc_hash,
                    extracted=extracted,
                    score_weight=score_weight,
                    source="generation",
                    page_number=1,
                    total_pages=1,
                    page_hash=doc_hash,
                )
                session.add(row)
                session.commit()
                logger.info(
                    "Persisted generation feedback business=%s weight=%.2f",
                    self.business_id, score_weight,
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
        """
        Five-stage synthesis pipeline:

        Stage 1 — Load rows
          Fetch all BrandMetrics rows for this business + content_type,
          ordered oldest to newest. Pass only the most recent N profiles
          to the LLM — older ones are already baked into previous syntheses.

        Stage 2 — Pass 3: Cross-document pattern consolidation
          Compare all Pass 1 structural DNA profiles to identify canonical
          (shared >= 60%), variant (>= 2 but < 60%), and unique patterns.
          This produces the unified brand voice patterns that feed into synthesis.

        Stage 3 — Pass 4: Best example selection
          Score all document opening and closing ABSTRACTIONS from Pass 2.5
          (NOT verbatim text). Uses the canonical patterns from Pass 3 as
          the reference standard. Selects the best-scoring abstractions.

        Stage 4 — Synthesis
          Feed all five pass outputs (inventory, structural profiles, asset banks,
          pattern consolidation, example selection) into METRICS_SYNTHESIS to
          produce the final brand writing intelligence brief.

        Persists the brief to Postgres BrandBrain and caches in Redis.
        """
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

        recent = rows[-MAX_RECENT_PROFILES:]

        # --- Stage 2: Pass 3 — Cross-document pattern consolidation ---
        inventory_block = self._format_inventory_for_pass3(recent)

        try:
            result_pass3 = self._synthesis_llm.invoke(
                PASS3_PATTERN_CONSOLIDATION.format(
                    total_documents=len(recent),
                    structural_profiles=inventory_block,
                )
            )
            pattern_consolidation = self._parse_json(result_pass3.content)
        except json.JSONDecodeError:
            logger.warning(
                "Pass 3 returned invalid JSON — proceeding without pattern consolidation"
            )
            pattern_consolidation = {}

        # --- Stage 3: Pass 4 — Best example selection (scores abstractions, not verbatim) ---
        abstractions_block = self._format_abstractions_for_pass4(recent)
        canonical_patterns = json.dumps(
            pattern_consolidation.get("canonical_patterns", {}),
            indent=2,
        )

        try:
            result_pass4 = self._synthesis_llm.invoke(
                PASS4_BEST_EXAMPLE_SELECTION.format(
                    total_documents=len(recent),
                    canonical_patterns=canonical_patterns,
                    documents_with_abstractions=abstractions_block,
                )
            )
            example_selection = self._parse_json(result_pass4.content)
        except json.JSONDecodeError:
            logger.warning(
                "Pass 4 returned invalid JSON — proceeding without example selection"
            )
            example_selection = {}

        # --- Stage 4: Synthesis ---
        structural_profiles = self._format_structural_profiles(recent)
        asset_banks = self._format_asset_banks(recent)
        document_inventory = self._format_inventory_for_pass3(recent)

        result = self._synthesis_llm.invoke(
            METRICS_SYNTHESIS.format(
                business_id=self.business_id,
                content_type=self.content_type,
                total_documents=len(rows),
                document_inventory=document_inventory,
                structural_profiles=structural_profiles,
                asset_banks=asset_banks,
                pattern_consolidation=json.dumps(pattern_consolidation, indent=2),
                example_selection=json.dumps(example_selection, indent=2),
            )
        )

        context = result.content

        # --- Persist to Postgres BrandBrain ---
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

        # --- Cache to Redis ---
        self._redis.set(self._cache_key, context, ex=CACHE_TTL)
        logger.info(
            "Brand context built and cached for business=%s content_type=%s profiles=%d",
            self.business_id, self.content_type, len(rows),
        )
        return context

    # ------------------------------------------------------------------ #
    #  Read path — called by writer and enforcer nodes                    #
    # ------------------------------------------------------------------ #

    def get_context(self) -> str:
        """
        Three-level read path:
          1. Redis (hot cache, 24h TTL)
          2. Postgres BrandBrain (warm fallback, warms Redis on hit)
          3. Full rebuild via build_and_cache_context() (cold fallback)
        """
        # 1. Try Redis
        cached = self._redis.get(self._cache_key)
        if cached:
            return cached

        # 2. Try Postgres BrandBrain
        with get_db_session() as session:
            brain = session.query(BrandBrain).filter_by(
                business_id=self.business_id,
                content_type=self.content_type,
            ).first()
            if brain:
                # Warm the Redis cache
                self._redis.set(self._cache_key, brain.synthesis_text, ex=CACHE_TTL)
                return brain.synthesis_text

        # 3. Cold rebuild
        return self.build_and_cache_context()

    # ------------------------------------------------------------------ #
    #  Context parsing — called by writer node                            #
    # ------------------------------------------------------------------ #

    def get_parsed_context(self) -> dict:
        """
        Return the brand context parsed into named sections for direct
        injection into the WRITER_INITIAL and WRITER_REVISION templates.

        The synthesis brief uses # headers — this method splits on them
        and returns a dict keyed by section name.

        Writer node usage:
            ctx = metrics.get_parsed_context()
            prompt = WRITER_INITIAL.format(
                brand_name=ctx["brand_name"],
                voice_overview=ctx["brand_voice_overview"],
                intellectual_patterns=ctx["intellectual_patterns"],
                style_signature=ctx["style_signature"],
                tone_signature=ctx["tone_signature"],
                signature_constructions=ctx["signature_constructions"],
                opening_skeleton=ctx["opening_skeleton"],
                closing_skeleton=ctx["closing_skeleton"],
                section_pattern=ctx["section_pattern"],
                narrative_arc=ctx["narrative_arc"],
                asset_bank=ctx["brand_asset_bank"],
                generation_do=ctx["generation_do"],
                generation_dont=ctx["generation_dont"],
                # content-specific fields injected separately:
                topic=topic,
                content_type=content_type,
                research=research,
                approved=approved_angles,
                rejected=rejected_angles,
            )
        """
        raw = self.get_context()
        if not raw:
            return {}

        sections = {}
        current_key = None
        current_lines = []

        for line in raw.splitlines():
            if line.startswith("# "):
                # Save previous section
                if current_key:
                    sections[current_key] = "\n".join(current_lines).strip()
                # Start new section
                current_key = line[2:].strip().lower().replace(" ", "_")
                current_lines = []
            else:
                current_lines.append(line)

        # Save final section
        if current_key:
            sections[current_key] = "\n".join(current_lines).strip()

        # Extract opening and closing skeletons from STRUCTURE SIGNATURE
        structure = sections.get("structure_signature", "")
        sections["opening_skeleton"] = self._extract_skeleton_block(
            structure, "OPENING PATTERN"
        )
        sections["closing_skeleton"] = self._extract_skeleton_block(
            structure, "CLOSING PATTERN"
        )
        sections["section_pattern"] = self._extract_subsection(
            structure, "SECTION PATTERN"
        )
        sections["narrative_arc"] = self._extract_subsection(
            structure, "NARRATIVE ARC"
        )

        # Extract DO / DON'T from GENERATION INSTRUCTIONS
        gen = sections.get("generation_instructions", "")
        sections["generation_do"] = self._extract_subsection(gen, "DO")
        sections["generation_dont"] = self._extract_subsection(gen, "DON'T")

        # Extract brand name cleanly
        brand_name_raw = sections.get("brand_name", "")
        sections["brand_name"] = brand_name_raw.strip().splitlines()[0] if brand_name_raw else ""

        return sections

    def _extract_skeleton_block(self, text: str, header: str) -> str:
        """
        Extract the content between --- skeleton delimiters under a given
        header in the structure signature section.
        """
        if header not in text:
            return ""
        after_header = text.split(header, 1)[1]
        if "---" not in after_header:
            # No skeleton delimiters — return everything up to next header
            return self._extract_subsection(after_header, "")
        parts = after_header.split("---")
        # First --- opens the block, second --- closes it
        if len(parts) >= 3:
            return parts[1].strip()
        return ""

    def _extract_subsection(self, text: str, header: str) -> str:
        """
        Extract content under a subsection header up to the next
        all-caps subsection header or end of text.
        """
        if not header:
            return text.strip()
        if header not in text:
            return ""
        after = text.split(header, 1)[1]
        # Stop at the next all-caps header line
        lines = after.splitlines()
        result = []
        for line in lines:
            stripped = line.strip()
            # Detect next subsection — all caps line with optional colon
            if (
                stripped
                and stripped == stripped.upper()
                and len(stripped) > 3
                and stripped != header
                and result  # don't stop before we've collected anything
            ):
                break
            result.append(line)
        return "\n".join(result).strip()

    # ------------------------------------------------------------------ #
    #  Cache and data management                                          #
    # ------------------------------------------------------------------ #

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
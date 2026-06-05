import hashlib
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

from embedding_stategy import FastEmbedEmbedding
from chunking_stategy import get_chunking_strategy

@dataclass
class _IndexEntry:
    index: object
    doc_hashes: set[str] = field(default_factory=set)
    built_at: float = field(default_factory=time.monotonic)





class BrandRAG:
    """
    Retrieval-augmented generation scoped to a single (business_id, content_type).

    Thread-safe: uses a class-level lock so concurrent requests don't race
    on index construction, and never mutates global LlamaIndex Settings.

    Refresh strategy:
    - refresh(new_doc_content) → incremental, embeds only the new document
    - refresh()                → full rebuild, clears cache entirely
    """

    _cache: dict[tuple, _IndexEntry] = {}
    _cache_lock = threading.Lock()

    def __init__(
        self,
        business_id: str,
        content_type: str,
        embedding: FastEmbedEmbedding,
        index_ttl_seconds: int = 3600,
        similarity_top_k: int = 5,
    ):
        self.business_id = business_id
        self.content_type = content_type
        self.embedding = embedding
        self._llamaindex_embed = None
        self.index_ttl_seconds = index_ttl_seconds
        self.similarity_top_k = similarity_top_k
        self.chunking_strategy = get_chunking_strategy(content_type)
        self._postgres_uri = self._require_env("POSTGRES_URI")



    def query(self, topic: str) -> str:
        """Retrieve the most relevant passages for *topic*."""
        if not topic.strip():
            raise ValueError("Query topic must not be empty.")

        index = self._get_index().index
        retriever = index.as_retriever(similarity_top_k=self.similarity_top_k)

        try:
            results = self._retrieve_with_retry(retriever, topic)
        except Exception as exc:
            logger.error(
                "Retrieval failed for business_id=%s content_type=%s topic=%r: %s",
                self.business_id, self.content_type, topic, exc,
            )
            raise

        if not results:
            logger.warning(
                "No results for business_id=%s content_type=%s topic=%r",
                self.business_id, self.content_type, topic,
            )
            return ""

        logger.info(
            "Retrieved %d node(s) for business_id=%s content_type=%s topic=%r",
            len(results), self.business_id, self.content_type, topic,
        )
        return "\n\n".join(r.text for r in results)

    def refresh(self, new_doc_content: str = None) -> None:
        """
        Incremental refresh: only embeds and inserts the new document.
        Full refresh: clears cache entirely, rebuilds on next query.
        """
        if new_doc_content is None:
            # Full rebuild
            with self._cache_lock:
                self._cache.pop(self._cache_key(), None)
            logger.info(
                "Full cache cleared for business_id=%s content_type=%s",
                self.business_id, self.content_type,
            )
            return

        # Incremental — hash check first
        doc_hash = hashlib.md5(new_doc_content.encode()).hexdigest()

        with self._cache_lock:
            entry = self._cache.get(self._cache_key())

            if entry is not None and doc_hash in entry.doc_hashes:
                logger.info(
                    "Document already indexed for business_id=%s content_type=%s — skipping.",
                    self.business_id, self.content_type,
                )
                return

        # Embed and insert only the new document
        from llama_index.core import Document
        index_entry = self._get_index()
        index_entry.index.insert(Document(text=new_doc_content))
        index_entry.doc_hashes.add(doc_hash)

        logger.info(
            "Incremental refresh complete for business_id=%s content_type=%s",
            self.business_id, self.content_type,
        )



    def _cache_key(self) -> tuple:
        return (
            self.business_id,
            self.content_type,
            self.embedding.model,
            self.chunking_strategy.__class__.__name__,
        )

    def _get_index(self) -> _IndexEntry:
        key = self._cache_key()

        with self._cache_lock:
            entry = self._cache.get(key)
            if entry is not None:
                age = time.monotonic() - entry.built_at
                if self.index_ttl_seconds == 0 or age < self.index_ttl_seconds:
                    return entry
                logger.info(
                    "Index TTL expired (%.0fs) for business_id=%s content_type=%s — rebuilding.",
                    age, self.business_id, self.content_type,
                )

            # Track hashes of all docs going into the index
            docs, doc_hashes = self._load_docs()
            index = self._build(docs)
            entry = _IndexEntry(index=index, doc_hashes=doc_hashes)
            self._cache[key] = entry
            return entry
        
    
    def _sanitize_table_name(self, name: str) -> str:
        import re
        # Keep only alphanumeric and underscore
        return re.sub(r'[^a-z0-9_]', '_', name.lower())
        
    @property
    def llamaindex_embed(self):
        if self._llamaindex_embed is None:
            self._llamaindex_embed = self.embedding.to_llamaindex()
        return self._llamaindex_embed

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _build(self, docs):
        """Build (or load) the VectorStoreIndex. Retried up to 3 times."""
        from llama_index.core import VectorStoreIndex
        from llama_index.core.node_parser import SimpleNodeParser
        from llama_index.vector_stores.postgres import PGVectorStore

        

        node_parser = SimpleNodeParser.from_defaults(
            chunk_size=self.chunking_strategy.chunk_size,
            chunk_overlap=self.chunking_strategy.chunk_overlap,
            )
        

        parsed = urlparse(self._postgres_uri)
        vector_store = PGVectorStore.from_params(
            host=parsed.hostname,
            port=parsed.port or 5432,
            database=parsed.path.lstrip("/"),
            user=parsed.username,
            password=parsed.password,
            table_name = f"vectors_{self._sanitize_table_name(self.business_id)}_{self._sanitize_table_name(self.content_type)}",
            embed_dim=self.embedding.embed_dim,
            hybrid_search=True,
            hnsw_kwargs={
                "hnsw_m": 16,
                "hnsw_ef_construction": 64,
                "hnsw_ef_search": 40,
                "hnsw_dist_method": "vector_cosine_ops",
            },
        )

        if not docs:
            logger.info(
                "No source documents for business_id=%s content_type=%s; "
                "loading existing vector store.",
                self.business_id, self.content_type,
            )
            return VectorStoreIndex.from_vector_store(
                vector_store=vector_store,
                embed_model=self.llamaindex_embed,
            )

        logger.info(
            "Indexing %d document(s) for business_id=%s content_type=%s "
            "(self.chunking_strategy=%d, embed_dim=%d).",
            len(docs), self.business_id, self.content_type,
            self.chunking_strategy.__class__.__name__, self.embedding.embed_dim,
        )
        return VectorStoreIndex.from_documents(
            docs,
            vector_store=vector_store,
            embed_model=self.llamaindex_embed,
            transformations=[node_parser],
            show_progress=True,
        )

  

    @staticmethod
    def pdf_bytes_to_markdown(pdf_bytes: bytes) -> str:
        import tempfile
        from pymupdf4llm import to_markdown

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_bytes)
            temp_path = f.name

        try:
            return to_markdown(temp_path)
        finally:
            os.unlink(temp_path)
    
    def _load_docs(self) -> tuple[list, set[str]]:
        from llama_index.core import Document
        from database import get_db_session, BrandDocument

        with get_db_session() as session:
            rows = (
                session.query(BrandDocument)
                .filter_by(
                    business_id=self.business_id,
                    content_type=self.content_type,
                )
                .filter(BrandDocument.file_content.isnot(None))
                .all()
            )

        if not rows:
            logger.warning(
                "No documents found for business_id=%s content_type=%s.",
                self.business_id, self.content_type,
            )
            return [], set()

        docs = [Document(text=row.file_content) for row in rows]
        doc_hashes = {
            hashlib.md5(row.file_content.encode()).hexdigest()
            for row in rows
        }
        return docs, doc_hashes

    @staticmethod
    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _retrieve_with_retry(retriever, topic: str):
        return retriever.retrieve(topic)

    @staticmethod
    def _require_env(name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise EnvironmentError(
                f"Required environment variable '{name}' is not set."
            )
        return value
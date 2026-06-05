from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from abc import ABC, abstractmethod
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



class EmbeddingPort(ABC):
    """Adapter interface between your domain and LlamaIndex embedding models."""

    @property
    @abstractmethod
    def model(self) -> str: ...

    @property
    @abstractmethod
    def embed_dim(self) -> int:
        """Must match the dimension stored in PGVector."""
        ...

    @abstractmethod
    def to_llamaindex(self):
        """Return the LlamaIndex-compatible embedding model object."""
        ...




class FastEmbedEmbedding(EmbeddingPort):
    """BAAI/bge-small-en-v1.5 → 384 dims (local, no API key required)."""

    _DIM_MAP: dict[str, int] = {
        "BAAI/bge-small-en-v1.5": 384,
        "BAAI/bge-base-en-v1.5": 768,
        "BAAI/bge-large-en-v1.5": 1024,
    }

    def __init__(self, model: str = "BAAI/bge-small-en-v1.5"):
        if model not in self._DIM_MAP:
            raise ValueError(
                f"Unknown FastEmbed model '{model}'. "
                f"Known models: {list(self._DIM_MAP)}"
            )
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    @property
    def embed_dim(self) -> int:
        return self._DIM_MAP[self._model]

    def to_llamaindex(self):
        from llama_index.embeddings.fastembed import FastEmbedEmbedding
        return FastEmbedEmbedding(model_name=self._model)


class OpenAIEmbedding(EmbeddingPort):
    """OpenAI text-embedding-* models."""

    _DIM_MAP: dict[str, int] = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: str = "",
    ):
        if not api_key.strip():
            raise ValueError("OpenAI API key is required for OpenAIEmbedding.")
        if model not in self._DIM_MAP:
            raise ValueError(
                f"Unknown OpenAI embedding model '{model}'. "
                f"Known models: {list(self._DIM_MAP)}"
            )
        self._model = model
        self._api_key = api_key

    @property
    def model(self) -> str:
        return self._model

    @property
    def embed_dim(self) -> int:
        return self._DIM_MAP[self._model]

    def to_llamaindex(self):
        from llama_index.embeddings.openai import OpenAIEmbedding
        return OpenAIEmbedding(model=self._model, api_key=self._api_key)


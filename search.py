import os
import logging
from tavily import TavilyClient
from tenacity import retry, stop_after_attempt, wait_exponential
from abc import ABC, abstractmethod
logger = logging.getLogger(__name__)

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

_client = TavilyClient(api_key=TAVILY_API_KEY) if TAVILY_API_KEY else None


class SearchPort(ABC):
    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> str: ...

class TavilySearch(SearchPort):
    def __init__(self, api_key: str = ""):
        if not api_key.strip():
            raise ValueError("Tavily API key required")
        self._client = TavilyClient(api_key=api_key)

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=5),
        reraise=True
    )
    def search(self, query: str, max_results: int = 5) -> str:
        results = self._client.search(query, max_results=max_results)
        logger.info("Search completed for query=%r", query)
        return str(results)
from abc import ABC, abstractmethod
from typing import Dict, Any
import os
from config import model
class LLMModel(ABC):
    @property
    @abstractmethod
    def source(self) -> str: ...
    
    @property
    @abstractmethod
    def model(self) -> str: ...
    
    @property
    @abstractmethod
    def api_key(self) -> str: ...
    
    @property
    @abstractmethod
    def temperature(self) -> float: ...
    
    @property
    @abstractmethod
    def max_tokens(self) -> int: ...
    
    @property
    @abstractmethod
    def top_p(self) -> float: ...
    
    @abstractmethod
    def to_params(self) -> Dict[str, Any]: ...
    
    @abstractmethod
    def to_langchain(self): ...


class ChatGroq(LLMModel):
    def __init__(
        self,
        model: str = model,
        api_key: str = "",
        temperature: float = 0.7,
        max_tokens: int = 8192,
        top_p: float = 1.0
    ):
        if not api_key.strip():
            raise ValueError("Groq API key required")
        if not 0 <= temperature <= 2:
            raise ValueError("temperature must be 0-2")
        if not 0 < top_p <= 1:
            raise ValueError("top_p must be (0,1]")
        if not (1 <= max_tokens <= 131072):
            raise ValueError("max_tokens must be 1-131072")
        
        self._model = model
        self._api_key = api_key
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._top_p = top_p

    @property
    def source(self) -> str:
        return "ChatGroq"

    @property
    def model(self) -> str:
        return self._model

    @property
    def api_key(self) -> str:
        return self._api_key

    @property
    def temperature(self) -> float:
        return self._temperature

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    @property
    def top_p(self) -> float:
        return self._top_p

    def to_params(self) -> Dict[str, Any]:
        """API-ready params (excludes api_key for security)."""
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p
        }

    def to_langchain(self):
        from langchain_groq import ChatGroq as LangChainGroq
        return LangChainGroq(
            model=self._model,
            api_key=self._api_key,
            temperature=self._temperature,
            max_tokens=self._max_tokens
        )

    def __repr__(self) -> str:
        return f"ChatGroq(model='{self.model}', temp={self.temperature})"
    


# OpenAI class
class ChatOpenAI(LLMModel):
    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        top_p: float = 1.0
    ):
        if not api_key.strip():
            raise ValueError("OpenAI API key required")
        if not 0 <= temperature <= 2:
            raise ValueError("temperature must be 0-2")
        if not 0 < top_p <= 1:
            raise ValueError("top_p must be (0,1]")
        if not (1 <= max_tokens <= 128000):
            raise ValueError("max_tokens must be 1-128000")

        self._model = model
        self._api_key = api_key
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._top_p = top_p

    @property
    def source(self) -> str:
        return "ChatOpenAI"

    @property
    def model(self) -> str:
        return self._model

    @property
    def api_key(self) -> str:
        return self._api_key

    @property
    def temperature(self) -> float:
        return self._temperature

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    @property
    def top_p(self) -> float:
        return self._top_p

    def to_params(self) -> Dict[str, Any]:
        """API-ready params (excludes api_key for security)."""
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p
        }

    def to_langchain(self):
        from langchain_openai import ChatOpenAI as LangChainOpenAI
        return LangChainOpenAI(
            model=self._model,
            api_key=self._api_key,
            temperature=self._temperature,
            max_tokens=self._max_tokens
        )

    def __repr__(self) -> str:
        return f"ChatOpenAI(model='{self.model}', temp={self.temperature})"



class ChatOllama(LLMModel):
    def __init__(
        self,
        model: str = "mistral:7b",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.7,
        max_tokens: int = 8192,
        top_p: float = 1.0
    ):
        self._model = model
        self._base_url = base_url
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._top_p = top_p

    @property
    def source(self) -> str:
        return "ChatOllama"

    @property
    def model(self) -> str:
        return self._model

    @property
    def api_key(self) -> str:
        return ""

    @property
    def temperature(self) -> float:
        return self._temperature

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    @property
    def top_p(self) -> float:
        return self._top_p

    def to_params(self):
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

    def to_langchain(self):
        from langchain_ollama import ChatOllama as LangChainOllama
        return LangChainOllama(
            model=self._model,
            base_url=self._base_url,
            temperature=self._temperature,
            num_predict=self._max_tokens
        )

    def __repr__(self) -> str:
        return f"ChatOllama(model='{self.model}', temp={self.temperature})"

# Singleton for LLMs
class LLMSingleton:
    _instance = None

    @classmethod
    def get(cls, mode: str = "generation"):
        if cls._instance is None:
            cls._instance = ChatGroq(
                model="openai/gpt-oss-120b",
                api_key=os.getenv("GROQ_API_KEY", "")
            ).to_langchain()
        return cls._instance
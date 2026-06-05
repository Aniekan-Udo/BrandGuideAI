from abc import ABC, abstractmethod
from langchain.text_splitter import RecursiveCharacterTextSplitter


class ChunkingStrategy(ABC):
    @abstractmethod
    def chunk(self, text: str) -> list[str]:
        pass

    @property
    def chunk_size(self) -> int:
        return self.splitter._chunk_size

    @property
    def chunk_overlap(self) -> int:
        return self.splitter._chunk_overlap



class BlogChunking(ChunkingStrategy):
    """
    Paragraph-aware chunking for long-form blog content.
    Larger chunks preserve narrative context.
    """
    def __init__(self):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=100,
            separators=["\n\n", "\n", ".", " "]
        )

    def chunk(self, text: str) -> list[str]:
        return self.splitter.split_text(text)


class SocialChunking(ChunkingStrategy):
    """
    Small chunks for social media content.
    Social posts are short — minimal overlap needed.
    """
    def __init__(self):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=200,
            chunk_overlap=20,
            separators=["\n", ".", " "]
        )

    def chunk(self, text: str) -> list[str]:
        chunks = self.splitter.split_text(text)
        # if content is short enough, keep it whole
        if len(text) <= 200:
            return [text]
        return chunks


class AdChunking(ChunkingStrategy):
    """
    Sentence-level chunking for ad copy.
    Short, punchy chunks preserve the intent of each line.
    """
    def __init__(self):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=300,
            chunk_overlap=30,
            separators=[".\n", ".", "\n", " "]
        )

    def chunk(self, text: str) -> list[str]:
        return self.splitter.split_text(text)


class ProposalChunking(ChunkingStrategy):
    """
    Section-aware chunking for long proposal documents.
    Large chunks with high overlap preserve section continuity.
    """
    def __init__(self):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=150,
            separators=["\n\n\n", "\n\n", "\n", ".", " "]
        )

    def chunk(self, text: str) -> list[str]:
        return self.splitter.split_text(text)


# Registry — maps content_type to its strategy
# Add new content types here without touching anything else
CHUNKING_REGISTRY: dict[str, ChunkingStrategy] = {
    "blog":     BlogChunking(),
    "social":   SocialChunking(),
    "ad":       AdChunking(),
    "proposal": ProposalChunking(),
}


def get_chunking_strategy(content_type: str) -> ChunkingStrategy:
    """
    Returns the chunking strategy for the given content type.
    Raises ValueError if content_type is not registered.

    Usage:
        strategy = get_chunking_strategy("blog")
        chunks = strategy.chunk(doc_content)
    """
    strategy = CHUNKING_REGISTRY.get(content_type)
    if not strategy:
        raise ValueError(
            f"No chunking strategy found for content type: '{content_type}'. "
            f"Available types: {list(CHUNKING_REGISTRY.keys())}"
        )
    return strategy

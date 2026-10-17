from typing import Any, Protocol

from pydantic import BaseModel

from app.domain.graph import ApprovedControlPath
from app.domain.models import BaselineEdge, SeedBundle


class AIClient(Protocol):
    async def generate_structured(
        self, prompt_version: str, context: dict[str, Any], output_type: type[BaseModel]
    ) -> BaseModel: ...


class EmbeddingClient(Protocol):
    async def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...


class RegulatoryRepository(Protocol):
    def snapshot(self) -> SeedBundle: ...


class SearchRepository(Protocol):
    async def vector_search(self, embedding: tuple[float, ...], limit: int) -> tuple[str, ...]: ...

    async def lexical_search(self, query: str, limit: int) -> tuple[str, ...]: ...


class GraphRepository(Protocol):
    def approved_outgoing(self, node_id: str) -> tuple[BaselineEdge, ...]: ...

    def approved_control_paths(self, mandate_id: str) -> tuple[ApprovedControlPath, ...]: ...


class ObjectStorage(Protocol):
    async def read(self, object_key: str) -> bytes: ...

    async def write(self, object_key: str, content: bytes, content_type: str) -> str: ...

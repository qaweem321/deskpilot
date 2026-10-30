"""Help-center search: markdown docs split by section, embedded, stored in Qdrant."""

import hashlib
import math
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from qdrant_client import QdrantClient, models

COLLECTION = "kb"


class Embedder(Protocol):
    dim: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class FastEmbedder:
    """Multilingual sentence embeddings on CPU (ONNX), so Urdu questions find English docs."""

    def __init__(self, model: str) -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model)
        self.dim = len(next(iter(self._model.embed(["probe"]))))

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(list(texts))]


class HashEmbedder:
    """Tiny bag-of-words embedder for tests: deterministic, no model download."""

    dim = 256

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            for word in re.findall(r"\w+", text.lower()):
                vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dim] += 1  # noqa: S324
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


@dataclass(frozen=True)
class Passage:
    doc: str
    heading: str
    text: str
    score: float = 0.0


def split_markdown(path: Path) -> list[Passage]:
    """One passage per "## " section, prefixed with the page title so it stands on its own."""
    raw = path.read_text(encoding="utf-8")
    title_match = re.search(r"^# (.+)$", raw, re.M)
    title = title_match.group(1).strip() if title_match else path.stem
    sections = re.split(r"^## ", raw, flags=re.M)
    intro = re.sub(r"^# .+$", "", sections[0], flags=re.M).strip()
    passages = [Passage(path.name, title, intro)] if intro else []
    for section in sections[1:]:
        heading, _, body = section.partition("\n")
        passages.append(Passage(path.name, f"{title} › {heading.strip()}", body.strip()))
    return passages


class KnowledgeBase:
    def __init__(self, client: QdrantClient, embedder: Embedder) -> None:
        self.client = client
        self.embedder = embedder

    @classmethod
    def connect(cls, url: str, embedder: Embedder) -> "KnowledgeBase":
        client = QdrantClient(location=":memory:") if url == ":memory:" else QdrantClient(url=url)
        return cls(client, embedder)

    def ingest(self, folder: Path) -> int:
        """(Re)build the collection when the docs changed. Returns the number of passages."""
        passages = [p for f in sorted(folder.glob("*.md")) for p in split_markdown(f)]
        fingerprint = hashlib.sha256("".join(p.heading + p.text for p in passages).encode()).hexdigest()[:16]
        name = f"{COLLECTION}_{fingerprint}"
        if self.client.collection_exists(name):
            self._use(name)
            return len(passages)

        self.client.create_collection(
            name, vectors_config=models.VectorParams(size=self.embedder.dim, distance=models.Distance.COSINE)
        )
        vectors = self.embedder.embed([f"{p.heading}\n{p.text}" for p in passages])
        self.client.upsert(
            name,
            points=[
                models.PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{p.doc}#{p.heading}")),
                    vector=v,
                    payload={"doc": p.doc, "heading": p.heading, "text": p.text},
                )
                for p, v in zip(passages, vectors, strict=True)
            ],
        )
        self._use(name)
        # Drop collections from older versions of the docs.
        for c in self.client.get_collections().collections:
            if c.name.startswith(f"{COLLECTION}_") and c.name != name:
                self.client.delete_collection(c.name)
        return len(passages)

    def _use(self, name: str) -> None:
        self.collection = name

    def search(self, query: str, limit: int = 4, min_score: float = 0.0) -> list[Passage]:
        vector = self.embedder.embed([query])[0]
        hits = self.client.query_points(
            self.collection, query=vector, limit=limit, score_threshold=min_score
        ).points
        return [
            Passage(h.payload["doc"], h.payload["heading"], h.payload["text"], h.score)  # type: ignore[index]
            for h in hits
        ]

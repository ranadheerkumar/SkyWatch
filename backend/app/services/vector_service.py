import hashlib
import json
import logging
import math
import os
import re
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("ai-qa-engine.vector_service")

# Storage directory for local persistent ChromaDB collections
_DEFAULT_VECTOR_DIR = Path(__file__).resolve().parents[2] / "vector_store"
VECTOR_STORE_DIR = Path(os.getenv("AI_VECTOR_STORE_DIR", str(_DEFAULT_VECTOR_DIR)))
VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)

_chroma_client = None
_fastembed_model = None


def _get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        try:
            import chromadb
            from chromadb.config import Settings
            _chroma_client = chromadb.PersistentClient(
                path=str(VECTOR_STORE_DIR),
                settings=Settings(anonymized_telemetry=False),
            )
            logger.info("ChromaDB persistent client initialized at %s", VECTOR_STORE_DIR)
        except Exception as error:
            logger.warning("Unable to initialize ChromaDB persistent client: %s. Using in-memory fallback.", error)
            try:
                import chromadb
                _chroma_client = chromadb.EphemeralClient()
            except Exception:
                _chroma_client = None
    return _chroma_client


def _get_fastembed_model():
    global _fastembed_model
    if _fastembed_model is None:
        try:
            from fastembed import TextEmbedding
            # BAAI/bge-small-en-v1.5 is lightweight (33MB), high accuracy, fast on CPU
            _fastembed_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
            logger.info("FastEmbed local embedding model loaded successfully.")
        except Exception as error:
            logger.warning("FastEmbed local model load skipped (%s). Fallback embedding will be used.", error)
            _fastembed_model = False
    return _fastembed_model if _fastembed_model is not False else None


def _deterministic_hash_embedding(text: str, dimensions: int = 384) -> list[float]:
    """Fallback deterministic dense vectorizer using character n-grams and hashing."""
    vec = [0.0] * dimensions
    tokens = re.findall(r"\b\w+\b", (text or "").lower())
    if not tokens:
        return vec
    for token in tokens:
        idx = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % dimensions
        weight = 1.0 + (len(token) / 10.0)
        vec[idx] += weight
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


async def generate_embeddings(
    texts: list[str],
    *,
    api_key: str | None = None,
    base_url: str = "https://api.openai.com/v1",
) -> list[list[float]]:
    """
    Multi-tier embedding generator:
    1. Remote embedding API (when api_key provided and reachable)
    2. Local FastEmbed model (ONNX runtime, CPU-optimized)
    3. Resilient deterministic hash vectorizer fallback
    """
    if not texts:
        return []

    # Tier 1: Try OpenAI/Azure/Copilot Embeddings API if api_key is available
    if api_key and api_key.strip():
        try:
            clean_base = base_url.rstrip("/")
            endpoint = f"{clean_base}/embeddings"
            headers = {"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"}
            payload = {"input": texts[:32], "model": "text-embedding-3-small"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(endpoint, headers=headers, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    raw_embeddings = data.get("data", [])
                    if raw_embeddings and len(raw_embeddings) == len(texts):
                        return [item["embedding"] for item in raw_embeddings]
        except Exception as error:
            logger.debug("Remote embedding request fell back to local model: %s", error)

    # Tier 2: Local FastEmbed model (Offline, 384 dimensions)
    model = _get_fastembed_model()
    if model is not None:
        try:
            embeddings = list(model.embed(texts))
            return [list(map(float, vec)) for vec in embeddings]
        except Exception as error:
            logger.debug("FastEmbed generation failed (%s), using deterministic hash vectorizer.", error)

    # Tier 3: Deterministic vectorizer fallback
    return [_deterministic_hash_embedding(t) for t in texts]


class InMemoryCollection:
    """Lightweight in-memory vector collection fallback when ChromaDB is unavailable."""

    def __init__(self, name: str, metadata: dict[str, Any] | None = None):
        self.name = name
        self.metadata = metadata or {}
        self.items: dict[str, dict[str, Any]] = {}

    def count(self) -> int:
        return len(self.items)

    def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        metadatas = metadatas or [{}] * len(ids)
        for doc_id, emb, doc, meta in zip(ids, embeddings, documents, metadatas):
            self.items[doc_id] = {
                "id": doc_id,
                "embedding": emb,
                "document": doc,
                "metadata": meta,
            }

    def query(
        self,
        query_embeddings: list[list[float]],
        n_results: int = 5,
    ) -> dict[str, Any]:
        if not query_embeddings or not self.items:
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

        q_vec = query_embeddings[0]
        scored_items = []
        for item in self.items.values():
            i_vec = item["embedding"]
            dot = sum(a * b for a, b in zip(q_vec, i_vec))
            norm_q = math.sqrt(sum(a * a for a in q_vec)) or 1.0
            norm_i = math.sqrt(sum(b * b for b in i_vec)) or 1.0
            sim = dot / (norm_q * norm_i)
            dist = max(0.0, 1.0 - sim)
            scored_items.append((dist, item))

        scored_items.sort(key=lambda x: x[0])
        top_items = scored_items[:n_results]

        return {
            "ids": [[it["id"] for _, it in top_items]],
            "documents": [[it["document"] for _, it in top_items]],
            "metadatas": [[it["metadata"] for _, it in top_items]],
            "distances": [[d for d, _ in top_items]],
        }


_IN_MEMORY_COLLECTIONS: dict[str, InMemoryCollection] = {}


def purge_vector_store() -> None:
    """Purges all in-memory collections and deletes persistent ChromaDB storage."""
    global _chroma_client, _IN_MEMORY_COLLECTIONS
    _IN_MEMORY_COLLECTIONS.clear()
    if _chroma_client is not None:
        try:
            for coll in _chroma_client.list_collections():
                try:
                    _chroma_client.delete_collection(name=coll.name)
                except Exception:
                    pass
        except Exception as error:
            logger.debug("Error clearing Chroma collections: %s", error)
    _chroma_client = None
    if VECTOR_STORE_DIR.exists():
        import shutil
        for item in VECTOR_STORE_DIR.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                elif item.name != "chroma.sqlite3":
                    item.unlink(missing_ok=True)
            except Exception as error:
                logger.debug("Failed to remove vector store item %s: %s", item, error)


class VectorStoreService:
    """Application-scoped vector database service for documents, test cases, and healing memory."""

    def __init__(self, application_id: int):
        self.application_id = application_id
        self.client = _get_chroma_client()
        self._doc_collection_name = f"app_{application_id}_documents"
        self._case_collection_name = f"app_{application_id}_test_cases"
        self._healing_collection_name = f"app_{application_id}_healing_memory"

    def _get_collection(self, name: str):
        if self.client is None:
            return _IN_MEMORY_COLLECTIONS.setdefault(name, InMemoryCollection(name, {"application_id": self.application_id}))
        try:
            return self.client.get_or_create_collection(
                name=name,
                metadata={"application_id": self.application_id, "hnsw:space": "cosine"},
            )
        except Exception as error:
            logger.warning("Error getting collection %s: %s", name, error)
            return _IN_MEMORY_COLLECTIONS.setdefault(name, InMemoryCollection(name, {"application_id": self.application_id}))

    # ========================================================================
    # 1. Document Chunks (RAG Indexing & Semantic Retrieval)
    # ========================================================================

    async def index_document_chunks(self, chunks: list[dict[str, Any]]) -> int:
        """Indexes parsed document chunks with embeddings into the document collection."""
        if not chunks:
            return 0
        coll = self._get_collection(self._doc_collection_name)
        if coll is None:
            return 0

        texts = [c["text"] for c in chunks]
        embeddings = await generate_embeddings(texts)

        ids = [f"doc_{self.application_id}_{c.get('filename', 'doc')}_{c.get('index', i)}_{hashlib.md5(c['text'][:50].encode()).hexdigest()[:8]}" for i, c in enumerate(chunks)]
        metadatas = [
            {
                "filename": str(c.get("filename") or "document")[:100],
                "chunk_index": int(c.get("index", i)),
                "char_length": len(c["text"]),
            }
            for i, c in enumerate(chunks)
        ]

        try:
            coll.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )
            return len(chunks)
        except Exception as error:
            logger.warning("Failed to index document chunks into ChromaDB: %s", error)
            return 0

    async def query_relevant_document_chunks(
        self,
        query: str,
        *,
        top_k: int = 6,
        api_key: str | None = None,
    ) -> list[str]:
        """Performs semantic similarity search to retrieve the most relevant specification chunks."""
        if not query.strip():
            return []
        coll = self._get_collection(self._doc_collection_name)
        if coll is None:
            return []

        try:
            count = coll.count()
            if count == 0:
                return []
            query_embeddings = await generate_embeddings([query], api_key=api_key)
            results = coll.query(
                query_embeddings=query_embeddings,
                n_results=min(top_k, count),
            )
            docs = results.get("documents") or []
            return docs[0] if docs and len(docs) > 0 else []
        except Exception as error:
            logger.warning("Semantic document search query failed: %s", error)
            return []

    # ========================================================================
    # 2. Test Cases (Indexing, Semantic Search & Deduplication)
    # ========================================================================

    async def index_test_case(
        self,
        case_id: int,
        title: str,
        steps: str,
        expected_result: str | None = None,
        description: str | None = None,
    ) -> bool:
        """Indexes a test case for semantic deduplication and similarity retrieval."""
        coll = self._get_collection(self._case_collection_name)
        if coll is None:
            return False

        doc_content = f"Title: {title}\nDescription: {description or ''}\nSteps:\n{steps}\nExpected: {expected_result or ''}".strip()
        embeddings = await generate_embeddings([doc_content])
        try:
            coll.upsert(
                ids=[str(case_id)],
                embeddings=embeddings,
                documents=[doc_content],
                metadatas=[{"case_id": case_id, "title": title[:200]}],
            )
            return True
        except Exception as error:
            logger.warning("Failed to index test case %s into vector store: %s", case_id, error)
            return False

    async def find_duplicate_or_similar_cases(
        self,
        title: str,
        steps: str,
        *,
        top_k: int = 3,
        distance_threshold: float = 0.65,
    ) -> list[dict[str, Any]]:
        """Finds existing test cases in the workspace with high semantic overlap."""
        coll = self._get_collection(self._case_collection_name)
        if coll is None:
            return []

        try:
            count = coll.count()
            if count == 0:
                return []
            query_text = f"Title: {title}\nSteps:\n{steps}"
            embeddings = await generate_embeddings([query_text])
            results = coll.query(
                query_embeddings=embeddings,
                n_results=min(top_k, count),
            )
            matches = []
            distances = (results.get("distances") or [[]])[0]
            metadatas = (results.get("metadatas") or [[]])[0]
            ids = (results.get("ids") or [[]])[0]
            for case_id, dist, meta in zip(ids, distances, metadatas):
                if float(dist) <= distance_threshold:
                    matches.append({
                        "case_id": meta.get("case_id") or case_id,
                        "title": meta.get("title") or "",
                        "distance": round(float(dist), 4),
                        "similarity_score": round(max(0.0, 1.0 - float(dist)), 4),
                    })
            return matches
        except Exception as error:
            logger.warning("Semantic duplicate test case check failed: %s", error)
            return []

    # ========================================================================
    # 3. Self-Healing Experience Memory (Past Locator Repairs)
    # ========================================================================

    async def index_healing_repair(
        self,
        *,
        run_id: str,
        step_index: int,
        action: str,
        failed_selector: str,
        healed_selector: str,
        failure_message: str,
        reason: str | None = None,
        page_url: str | None = None,
    ) -> bool:
        """Stores successful Playwright locator repairs to accelerate future self-healing."""
        coll = self._get_collection(self._healing_collection_name)
        if coll is None:
            return False

        doc_content = (
            f"Action: {action}\n"
            f"Broken Selector: {failed_selector}\n"
            f"Failure Message: {failure_message}\n"
            f"Page URL: {page_url or ''}"
        ).strip()
        embeddings = await generate_embeddings([doc_content])
        repair_id = f"heal_{self.application_id}_{run_id}_{step_index}_{hashlib.md5(failed_selector.encode()).hexdigest()[:6]}"
        metadata = {
            "action": action[:40],
            "failed_selector": failed_selector[:200],
            "healed_selector": healed_selector[:200],
            "reason": (reason or "AI Healer repair")[:200],
            "page_url": (page_url or "")[:200],
        }
        try:
            coll.upsert(
                ids=[repair_id],
                embeddings=embeddings,
                documents=[doc_content],
                metadatas=[metadata],
            )
            logger.info("Indexed self-healing repair memory for selector '%s' -> '%s'", failed_selector, healed_selector)
            return True
        except Exception as error:
            logger.warning("Failed to index healing memory: %s", error)
            return False

    async def query_healing_memory(
        self,
        *,
        action: str,
        failed_selector: str,
        failure_message: str,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """Queries historical locator repairs for matching UI patterns."""
        coll = self._get_collection(self._healing_collection_name)
        if coll is None:
            return []

        try:
            count = coll.count()
            if count == 0:
                return []
            query_text = f"Action: {action}\nBroken Selector: {failed_selector}\nFailure Message: {failure_message}"
            embeddings = await generate_embeddings([query_text])
            results = coll.query(
                query_embeddings=embeddings,
                n_results=min(top_k, count),
            )
            metadatas = (results.get("metadatas") or [[]])[0]
            distances = (results.get("distances") or [[]])[0]
            matching_repairs = []
            for meta, dist in zip(metadatas, distances):
                if dist < 0.45:  # High semantic similarity match
                    matching_repairs.append({
                        "healed_selector": meta.get("healed_selector"),
                        "action": meta.get("action"),
                        "reason": meta.get("reason"),
                        "similarity": round(max(0.0, 1.0 - float(dist)), 3),
                    })
            return matching_repairs
        except Exception as error:
            logger.warning("Healing memory lookup failed: %s", error)
            return []

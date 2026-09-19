"""Continuous Adaptive Self-Learning Engine for AI QA Engine.

Learns from successful executions, self-healing events, and application interactions:
1. Learned Locator Repository (zero-latency optimal selector reuse across runs).
2. Route Timing & Settling Adaptation (adaptive DOM/network wait intervals).
3. Self-Learning Telemetry & Metrics.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from app.services.vector_service import _get_chroma_client, generate_embeddings

logger = logging.getLogger("ai-qa-engine.self_learning")

# In-memory fast LRU cache of learned selectors and entities per application:
# (app_id, action, normalized_target_key) -> LearnedLocator
_LEARNED_LOCATOR_CACHE: dict[tuple[int, str, str], LearnedLocator] = {}
_ROUTE_TIMING_CACHE: dict[tuple[int, str], RouteTimingMetric] = {}
_DISCOVERED_ENTITIES_CACHE: dict[tuple[int, str], list[str]] = {}


def clear_learning_cache() -> None:
    _LEARNED_LOCATOR_CACHE.clear()
    _ROUTE_TIMING_CACHE.clear()
    _DISCOVERED_ENTITIES_CACHE.clear()


def purge_all_learning_and_vector_cache() -> None:
    """Purges all in-memory LRU caches, route timings, discovered entities, and persistent vector databases."""
    clear_learning_cache()
    from app.services.vector_service import purge_vector_store
    purge_vector_store()


@dataclass
class LearnedLocator:
    app_id: int
    action: str
    target_key: str
    verified_selector: str
    confidence: float = 1.0
    hit_count: int = 1
    source: str = "execution"  # "execution" | "healer" | "vector_memory"
    last_used_at: float = field(default_factory=time.time)


@dataclass
class RouteTimingMetric:
    app_id: int
    route_pattern: str
    avg_load_time_ms: float
    sample_count: int = 1
    recommended_settle_ms: int = 300


def normalize_target_key(selector_or_label: str) -> str:
    """Normalizes a raw selector, label, or target description into a stable lookup key."""
    raw = (selector_or_label or "").strip()
    if raw.startswith("label="):
        raw = raw[6:]
    elif raw.startswith("text="):
        raw = raw[5:]
    elif raw.startswith("a:has-text(") or raw.startswith("button:has-text("):
        m = re.search(r"['\"]([^'\"]+)['\"]", raw)
        if m:
            raw = m.group(1)

    clean = re.sub(r"\b(filter|field|input|box|dropdown|select|button|link|the)\b", "", raw, flags=re.IGNORECASE)
    clean = re.sub(r"[^\w\s\-]", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip().lower()
    return clean or raw.lower().strip()


class SelfLearningEngine:
    """Application-scoped Self-Learning Engine providing fast-path locators and execution adaptation."""

    def __init__(self, application_id: int):
        self.application_id = application_id
        self._collection_name = f"app_{application_id}_learned_locators"

    def _get_collection(self):
        client = _get_chroma_client()
        if client is None:
            return None
        try:
            return client.get_or_create_collection(
                name=self._collection_name,
                metadata={"application_id": self.application_id, "hnsw:space": "cosine"},
            )
        except Exception as error:
            logger.debug("Chroma collection '%s' unavailable: %s", self._collection_name, error)
            return None

    def get_learned_locator(self, action: str, raw_selector: str) -> str | None:
        """
        Retrieves a verified, high-confidence resilient locator learned from previous runs.
        Returns immediately from in-memory cache if available.
        """
        target_key = normalize_target_key(raw_selector)
        if not target_key:
            return None

        cache_key = (self.application_id, action, target_key)
        if cache_key in _LEARNED_LOCATOR_CACHE:
            learned = _LEARNED_LOCATOR_CACHE[cache_key]
            learned.hit_count += 1
            learned.last_used_at = time.time()
            return learned.verified_selector

        # Check collection if not in local memory
        coll = self._get_collection()
        if coll is not None:
            try:
                item_id = f"loc_{self.application_id}_{action}_{hashlib.md5(target_key.encode()).hexdigest()[:10]}"
                res = coll.get(ids=[item_id])
                if res and res.get("metadatas") and len(res["metadatas"]) > 0:
                    meta = res["metadatas"][0]
                    verified_selector = meta.get("verified_selector")
                    if verified_selector:
                        learned = LearnedLocator(
                            app_id=self.application_id,
                            action=action,
                            target_key=target_key,
                            verified_selector=verified_selector,
                            confidence=float(meta.get("confidence", 1.0)),
                            hit_count=int(meta.get("hit_count", 1)) + 1,
                            source=str(meta.get("source", "persisted")),
                        )
                        _LEARNED_LOCATOR_CACHE[cache_key] = learned
                        return verified_selector
            except Exception as error:
                logger.debug("Error checking learned locator store: %s", error)

        return None

    def record_successful_locator(
        self,
        action: str,
        raw_selector: str,
        verified_selector: str,
        *,
        source: str = "execution",
        confidence: float = 1.0,
    ) -> None:
        """
        Learns and persists an effective locator for a given action and target.
        """
        if not verified_selector or not raw_selector:
            return
        target_key = normalize_target_key(raw_selector)
        if not target_key:
            return

        cache_key = (self.application_id, action, target_key)
        existing = _LEARNED_LOCATOR_CACHE.get(cache_key)

        if existing:
            existing.verified_selector = verified_selector
            existing.hit_count += 1
            existing.confidence = min(1.0, existing.confidence + 0.05)
            existing.last_used_at = time.time()
            existing.source = source
        else:
            _LEARNED_LOCATOR_CACHE[cache_key] = LearnedLocator(
                app_id=self.application_id,
                action=action,
                target_key=target_key,
                verified_selector=verified_selector,
                confidence=confidence,
                hit_count=1,
                source=source,
            )

        # Async persist in background/best-effort
        try:
            coll = self._get_collection()
            if coll is not None:
                item_id = f"loc_{self.application_id}_{action}_{hashlib.md5(target_key.encode()).hexdigest()[:10]}"
                coll.upsert(
                    ids=[item_id],
                    embeddings=_deterministic_hash_embedding(f"{action} {target_key}"),
                    documents=[f"{action} on {target_key} uses {verified_selector}"],
                    metadatas=[{
                        "action": action,
                        "target_key": target_key,
                        "verified_selector": verified_selector,
                        "source": source,
                        "confidence": confidence,
                        "hit_count": existing.hit_count if existing else 1,
                    }],
                )
        except Exception as error:
            logger.debug("Failed to persist learned locator: %s", error)

    def record_route_timing(self, route_url: str, duration_ms: float) -> None:
        """Learns route load latency to dynamically adjust wait budgets."""
        if not route_url or duration_ms <= 0:
            return
        route_pattern = re.sub(r"\d+", "{id}", urlparse(route_url).path.rstrip("/") or "/")
        cache_key = (self.application_id, route_pattern)
        existing = _ROUTE_TIMING_CACHE.get(cache_key)
        if existing:
            new_count = existing.sample_count + 1
            existing.avg_load_time_ms = ((existing.avg_load_time_ms * existing.sample_count) + duration_ms) / new_count
            existing.sample_count = new_count
            existing.recommended_settle_ms = int(min(2500, max(200, existing.avg_load_time_ms * 0.35)))
        else:
            _ROUTE_TIMING_CACHE[cache_key] = RouteTimingMetric(
                app_id=self.application_id,
                route_pattern=route_pattern,
                avg_load_time_ms=duration_ms,
                sample_count=1,
                recommended_settle_ms=int(min(2500, max(200, duration_ms * 0.35))),
            )

    def get_route_settle_budget(self, route_url: str) -> int:
        """Returns the learned recommended settle time in ms for this route."""
        route_pattern = re.sub(r"\d+", "{id}", urlparse(route_url).path.rstrip("/") or "/")
        cache_key = (self.application_id, route_pattern)
        metric = _ROUTE_TIMING_CACHE.get(cache_key)
        return metric.recommended_settle_ms if metric else 250

    def record_discovered_entities(self, entity_type: str, values: list[str]) -> None:
        """Records discovered live application entities (names, IDs, barcodes) into self-learning memory."""
        if not values:
            return
        norm_type = normalize_target_key(entity_type)
        cache_key = (self.application_id, norm_type)
        existing = _DISCOVERED_ENTITIES_CACHE.get(cache_key, [])
        combined = list(dict.fromkeys([*existing, *[v.strip() for v in values if v.strip()]]))[:50]
        _DISCOVERED_ENTITIES_CACHE[cache_key] = combined

        try:
            coll = self._get_entity_collection()
            if coll is not None:
                for val in values:
                    val_clean = val.strip()
                    if len(val_clean) < 2:
                        continue
                    item_id = f"ent_{self.application_id}_{norm_type}_{hashlib.md5(val_clean.encode()).hexdigest()[:8]}"
                    coll.upsert(
                        ids=[item_id],
                        embeddings=_deterministic_hash_embedding(f"{norm_type} {val_clean}"),
                        documents=[f"{norm_type}: {val_clean}"],
                        metadatas=[{"entity_type": norm_type, "value": val_clean}],
                    )
        except Exception as error:
            logger.debug("Failed to persist entity memory: %s", error)

    def get_discovered_entities(self, entity_type: str, limit: int = 10) -> list[str]:
        """Retrieves discovered live application entities for test data generation."""
        norm_type = normalize_target_key(entity_type)
        cache_key = (self.application_id, norm_type)
        cached = _DISCOVERED_ENTITIES_CACHE.get(cache_key)
        if cached:
            return cached[:limit]

        coll = self._get_entity_collection()
        if coll is not None:
            try:
                res = coll.get(where={"entity_type": norm_type}, limit=limit)
                if res and res.get("metadatas"):
                    items = [m.get("value") for m in res["metadatas"] if m.get("value")]
                    if items:
                        _DISCOVERED_ENTITIES_CACHE[cache_key] = items
                        return items[:limit]
            except Exception:
                pass

        # Try stripped base entity type (e.g. billing_address -> address, user_email -> email)
        base_entity = re.sub(r"^[a-z0-9]+[_\s-]", "", norm_type).strip()
        if base_entity and base_entity != norm_type:
            base_cached = _DISCOVERED_ENTITIES_CACHE.get((self.application_id, base_entity))
            if base_cached:
                return base_cached[:limit]
            if coll is not None:
                try:
                    res = coll.get(where={"entity_type": base_entity}, limit=limit)
                    if res and res.get("metadatas"):
                        items = [m.get("value") for m in res["metadatas"] if m.get("value")]
                        if items:
                            _DISCOVERED_ENTITIES_CACHE[(self.application_id, base_entity)] = items
                            return items[:limit]
                except Exception:
                    pass

        return []

    def _get_entity_collection(self):
        client = _get_chroma_client()
        if client is None:
            return None
        try:
            return client.get_or_create_collection(
                name=f"app_{self.application_id}_test_data_memory",
                metadata={"application_id": self.application_id, "hnsw:space": "cosine"},
            )
        except Exception:
            return None

    def harvest_text_signals(self, text_signals: str | list[str]) -> dict[str, list[str]]:
        """Harvests entity candidates from text, headings, or discovery strings synchronously."""
        harvested: dict[str, list[str]] = {}
        if isinstance(text_signals, list):
            text = " ".join(str(s) for s in text_signals if s)
        else:
            text = str(text_signals or "")

        if not text.strip():
            return harvested

        # Extract potential entities using regex patterns
        barcodes = list(dict.fromkeys(re.findall(r"\b\d{6,14}\b", text)))[:10]
        if barcodes:
            harvested["barcode"] = barcodes
            self.record_discovered_entities("barcode", barcodes)

        orders = list(dict.fromkeys(re.findall(r"\bORD[-_]?\d+\b", text, re.IGNORECASE)))[:10]
        if orders:
            harvested["order_id"] = orders
            self.record_discovered_entities("order_id", orders)

        statuses = list(dict.fromkeys(re.findall(r"\b(Active|Pending|Closed|Completed|Approved|Draft)\b", text, re.IGNORECASE)))[:6]
        if statuses:
            harvested["status"] = statuses
            self.record_discovered_entities("status", statuses)

        names = list(dict.fromkeys(re.findall(r"\b[A-Z][a-z]{2,12}\s+[A-Z][a-z]{2,12}\b", text)))[:10]
        if names:
            harvested["name"] = names
            self.record_discovered_entities("name", names)

        return harvested

    async def harvest_page_entities(self, page: Any) -> dict[str, list[str]]:
        """Harvests visible table cells, badge labels, form placeholders, and entities from the rendered DOM."""
        harvested: dict[str, list[str]] = {}
        try:
            raw_entities = await page.evaluate(
                """() => {
                    const result = {};

                    // 1. Scan structured tables dynamically based on header column names
                    document.querySelectorAll('table').forEach(table => {
                        const headers = Array.from(table.querySelectorAll('thead th, tr:first-child th')).map(th => {
                            const raw = (th.textContent || '').trim().toLowerCase().replace(/[^a-z0-9_]+/g, '_').replace(/^_+|_+$/g, '');
                            return raw || null;
                        });

                        table.querySelectorAll('tbody tr, tr:not(:first-child)').forEach(tr => {
                            const cells = tr.querySelectorAll('td');
                            cells.forEach((td, colIdx) => {
                                const text = (td.textContent || '').trim();
                                if (!text || text.length > 80 || text.includes('\\n')) return;

                                const colName = (headers[colIdx] && headers[colIdx].length >= 2) ? headers[colIdx] : null;
                                if (colName) {
                                    if (!result[colName]) result[colName] = [];
                                    result[colName].push(text);
                                }

                                // Generic value classification
                                if (/^\\d{6,14}$/.test(text)) {
                                    if (!result['id_code']) result['id_code'] = [];
                                    result['id_code'].push(text);
                                } else if (/^\\d{4}-\\d{2}-\\d{2}$/.test(text) || /^\\d{1,2}\\/\\d{1,2}\\/\\d{4}$/.test(text)) {
                                    if (!result['date']) result['date'] = [];
                                    result['date'].push(text);
                                }
                            });
                        });
                    });

                    // 2. Scan badges, card labels, and select options generically
                    document.querySelectorAll('.badge, .tag, .pill, [role=\"status\"], .card-title, select option').forEach(el => {
                        const text = (el.textContent || '').trim();
                        if (!text || text.length > 50 || text.startsWith('Select') || text.startsWith('-')) return;
                        if (['Active', 'Pending', 'Closed', 'Completed', 'Error', 'Contracted', 'Available', 'Hold', 'Draft', 'Approved'].includes(text)) {
                            if (!result['status']) result['status'] = [];
                            result['status'].push(text);
                        } else if (/^\\d{4}-\\d{2}-\\d{2}/.test(text)) {
                            if (!result['date']) result['date'] = [];
                            result['date'].push(text.slice(0, 10));
                        }
                    });

                    return result;
                }"""
            )
            if isinstance(raw_entities, dict):
                for k, vals in raw_entities.items():
                    if isinstance(vals, list) and vals:
                        unique_vals = list(dict.fromkeys(vals))[:20]
                        harvested[k] = unique_vals
                        self.record_discovered_entities(k, unique_vals)
        except Exception as err:
            logger.debug("Live entity harvesting skipped: %s", err)

        return harvested

    @classmethod
    def get_telemetry_metrics(cls, application_id: int) -> dict[str, Any]:
        """Returns live self-learning telemetry and metrics for an application."""
        app_locators = [
            loc for (a_id, _, _), loc in _LEARNED_LOCATOR_CACHE.items()
            if a_id == application_id
        ]
        app_routes = [
            rm for (a_id, _), rm in _ROUTE_TIMING_CACHE.items()
            if a_id == application_id
        ]

        total_hits = sum(loc.hit_count for loc in app_locators)
        healed_count = sum(1 for loc in app_locators if loc.source == "healer")

        return {
            "application_id": application_id,
            "total_learned_locators": len(app_locators),
            "total_locator_hits": total_hits,
            "healed_adaptations_retained": healed_count,
            "monitored_route_profiles": len(app_routes),
            "average_route_load_ms": round(sum(r.avg_load_time_ms for r in app_routes) / len(app_routes), 1) if app_routes else 0.0,
            "learning_engine_status": "active",
        }


def _deterministic_hash_embedding(text: str, dimensions: int = 384) -> list[float]:
    import math
    vec = [0.0] * dimensions
    tokens = re.findall(r"\b\w+\b", (text or "").lower())
    if not tokens:
        return vec
    for token in tokens:
        idx = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % dimensions
        vec[idx] += 1.0 + (len(token) / 10.0)
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]

from __future__ import annotations

import hashlib
import json
import math
import random
import sqlite3
from dataclasses import dataclass
from typing import Any

import numpy as np

from . import FEATURE_VERSION
from .db import json_loads
from .features import EXPLANATION_FEATURES, FEATURE_ORDER


@dataclass
class Candidate:
    photo_id: int
    source_dir: str
    link_key: str
    url: str
    image_path: str
    vector: np.ndarray
    raw: dict[str, float]
    summary: dict[str, Any]
    distance: float
    similarity: float
    shown_count: int
    feeling_score: float | None = None
    energy_score: float | None = None


def recommend(
    conn: sqlite3.Connection,
    query_vector: list[float],
    query_raw: dict[str, float],
    query_summary: dict[str, Any],
    session_id: str | None = None,
    seed_material: str = "",
    query_mood: tuple[float, float] | None = None,
) -> dict[str, Any]:
    stats = _load_stats(conn)
    candidates = _load_candidates(conn)
    if not candidates:
        return {"recommendations": [], "feature_summary": query_summary}

    query = np.asarray(query_vector, dtype=np.float64)
    qz = _zscore(query, stats["mean"], stats["std"])
    weights = stats["weights"]

    ranked: list[Candidate] = []
    for candidate in candidates:
        cz = _zscore(candidate.vector, stats["mean"], stats["std"])
        distance = _weighted_distance(qz, cz, weights)
        similarity = 1.0 / (1.0 + distance)
        ranked.append(
            Candidate(
                photo_id=candidate.photo_id,
                source_dir=candidate.source_dir,
                link_key=candidate.link_key,
                url=candidate.url,
                image_path=candidate.image_path,
                vector=candidate.vector,
                raw=candidate.raw,
                summary=candidate.summary,
                distance=distance,
                similarity=similarity,
                shown_count=candidate.shown_count,
                feeling_score=candidate.feeling_score,
                energy_score=candidate.energy_score,
            )
        )
    ranked.sort(key=lambda item: item.distance)

    selected: list[tuple[str, Candidate, float]] = []
    if query_mood is not None:
        mood_ranked = _rank_by_visual_and_mood(ranked, query_mood)
        selected.extend(mood_ranked[:2])
        opposite = _select_opposite_by_visual_and_mood(
            ranked,
            selected=[item for _, item, _ in selected],
            query_mood=query_mood,
        )
        if opposite is not None:
            selected.append(opposite)
    else:
        nearest = ranked[0]
        selected.append(("nearest", nearest, nearest.similarity))
        mood = _select_by_score(
            ranked,
            selected=[nearest],
            seed_material=seed_material,
            relevance_weight=0.75,
            diversity_weight=0.25,
            novelty_weight=0.0,
            random_weight=0.0,
            pool_size=min(24, len(ranked)),
        )
        if mood is not None:
            selected.append(("mood", mood[0], mood[1]))

        discovery = _select_by_score(
            ranked,
            selected=[item for _, item, _ in selected],
            seed_material=seed_material,
            relevance_weight=0.50,
            diversity_weight=0.28,
            novelty_weight=0.17,
            random_weight=0.05,
            pool_size=len(ranked),
        )
        if discovery is not None:
            selected.append(("discovery", discovery[0], discovery[1]))

    event_id = _save_event(conn, session_id, seed_material, query_vector, query_raw, query_summary)
    response_items = []
    for rank, (slot, candidate, final_score) in enumerate(selected, 1):
        _save_result(conn, event_id, candidate, slot, final_score, rank)
        response_items.append(_response_item(slot, candidate, query_raw, query_summary, final_score))
    conn.commit()

    return {
        "event_id": event_id,
        "feature_version": FEATURE_VERSION,
        "feature_summary": query_summary,
        "query_features": _query_features(query_raw),
        "recommendations": response_items,
    }


@dataclass
class LoadedCandidate:
    photo_id: int
    source_dir: str
    link_key: str
    url: str
    image_path: str
    vector: np.ndarray
    raw: dict[str, float]
    summary: dict[str, Any]
    shown_count: int
    feeling_score: float | None = None
    energy_score: float | None = None


def _load_stats(conn: sqlite3.Connection) -> dict[str, np.ndarray]:
    row = conn.execute(
        "SELECT mean_json, std_json, weight_json FROM feature_stats WHERE feature_version = ?",
        (FEATURE_VERSION,),
    ).fetchone()
    if row is None:
        raise RuntimeError("Feature stats are missing. Run scripts/import_dataset.py first.")
    return {
        "mean": np.asarray(json_loads(row["mean_json"]), dtype=np.float64),
        "std": np.asarray(json_loads(row["std_json"]), dtype=np.float64),
        "weights": np.asarray(json_loads(row["weight_json"]), dtype=np.float64),
    }


def _load_candidates(conn: sqlite3.Connection) -> list[LoadedCandidate]:
    rows = conn.execute(
        """
        SELECT
            p.id,
            p.source_dir,
            p.link_key,
            p.copied_image_path,
            t.url,
            f.vector_json,
            f.raw_json,
            f.summary_json,
            e.feeling_score,
            e.energy_score,
            COALESCE(SUM(CASE WHEN fb.action = 'shown' THEN 1 ELSE 0 END), 0) AS shown_count
        FROM photos p
        JOIN tracks t ON t.link_key = p.link_key
        JOIN image_features f ON f.photo_id = p.id
        LEFT JOIN photo_emotions e ON e.photo_id = p.id
        LEFT JOIN feedback fb ON fb.photo_id = p.id
        WHERE p.active = 1 AND f.feature_version = ?
        GROUP BY p.id
        ORDER BY p.id
        """,
        (FEATURE_VERSION,),
    ).fetchall()
    return [
        LoadedCandidate(
            photo_id=int(row["id"]),
            source_dir=str(row["source_dir"]),
            link_key=str(row["link_key"]),
            url=str(row["url"]),
            image_path=str(row["copied_image_path"]),
            vector=np.asarray(json_loads(row["vector_json"]), dtype=np.float64),
            raw={key: float(value) for key, value in json_loads(row["raw_json"]).items()},
            summary=json_loads(row["summary_json"]),
            shown_count=int(row["shown_count"]),
            feeling_score=float(row["feeling_score"]) if row["feeling_score"] is not None else None,
            energy_score=float(row["energy_score"]) if row["energy_score"] is not None else None,
        )
        for row in rows
    ]


def _zscore(vector: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    return (vector - mean) / np.maximum(std, 1e-6)


def _weighted_distance(a: np.ndarray, b: np.ndarray, weights: np.ndarray) -> float:
    diff = a - b
    return float(math.sqrt(float(np.sum(weights * diff * diff) / max(float(np.sum(weights)), 1e-6))))


def _select_by_score(
    ranked: list[Candidate],
    selected: list[Candidate],
    seed_material: str,
    relevance_weight: float,
    diversity_weight: float,
    novelty_weight: float,
    random_weight: float,
    pool_size: int,
) -> tuple[Candidate, float] | None:
    selected_ids = {item.photo_id for item in selected}
    selected_links = {item.link_key for item in selected}
    pool = [item for item in ranked[:pool_size] if item.photo_id not in selected_ids and item.link_key not in selected_links]
    if not pool:
        return None

    seed = int(hashlib.sha1(seed_material.encode("utf-8", errors="ignore")).hexdigest()[:12], 16)
    rng = random.Random(seed)

    best: tuple[Candidate, float] | None = None
    for item in pool:
        diversity = _diversity(item, selected)
        novelty = 1.0 / math.sqrt(1.0 + item.shown_count)
        jitter = rng.random()
        score = (
            relevance_weight * item.similarity
            + diversity_weight * diversity
            + novelty_weight * novelty
            + random_weight * jitter
        )
        if best is None or score > best[1]:
            best = (item, score)
    return best


def _rank_by_visual_and_mood(
    ranked: list[Candidate],
    query_mood: tuple[float, float],
    visual_weight: float = 0.65,
    mood_weight: float = 0.35,
) -> list[tuple[str, Candidate, float]]:
    scored: list[tuple[str, Candidate, float]] = []
    for item in ranked:
        if item.feeling_score is None or item.energy_score is None:
            mood_similarity = 0.0
        else:
            mood_similarity = _mood_similarity(query_mood, (float(item.feeling_score), float(item.energy_score)))
        score = visual_weight * item.similarity + mood_weight * mood_similarity
        scored.append(("nearest" if not scored else "mood", item, score))
    scored.sort(key=lambda row: row[2], reverse=True)
    return [
        ("nearest" if index == 0 else "mood", item, score)
        for index, (_, item, score) in enumerate(scored)
    ]


def _select_opposite_by_visual_and_mood(
    ranked: list[Candidate],
    selected: list[Candidate],
    query_mood: tuple[float, float],
    visual_weight: float = 0.65,
    mood_weight: float = 0.35,
) -> tuple[str, Candidate, float] | None:
    selected_ids = {item.photo_id for item in selected}
    selected_links = {item.link_key for item in selected}
    best: tuple[str, Candidate, float] | None = None
    for item in ranked:
        if item.photo_id in selected_ids or item.link_key in selected_links:
            continue
        if item.feeling_score is None or item.energy_score is None:
            mood_similarity = 0.0
        else:
            mood_similarity = _mood_similarity(query_mood, (float(item.feeling_score), float(item.energy_score)))
        combined_similarity = visual_weight * item.similarity + mood_weight * mood_similarity
        opposite_score = 1.0 - combined_similarity
        if best is None or opposite_score > best[2]:
            best = ("emotion_opposite", item, opposite_score)
    return best


def _select_by_mood(
    ranked: list[Candidate],
    selected: list[Candidate],
    query_mood: tuple[float, float],
    opposite: bool,
    visual_weight: float,
    mood_weight: float,
    pool_size: int,
) -> tuple[Candidate, float] | None:
    selected_ids = {item.photo_id for item in selected}
    selected_links = {item.link_key for item in selected}
    pool = [
        item
        for item in ranked[:pool_size]
        if item.photo_id not in selected_ids
        and item.link_key not in selected_links
        and item.feeling_score is not None
        and item.energy_score is not None
    ]
    if not pool:
        return _select_by_score(
            ranked,
            selected=selected,
            seed_material=f"{query_mood[0]}:{query_mood[1]}:{opposite}",
            relevance_weight=0.70 if not opposite else 0.45,
            diversity_weight=0.20,
            novelty_weight=0.05,
            random_weight=0.05,
            pool_size=pool_size,
        )

    target = (-query_mood[0], -query_mood[1]) if opposite else query_mood
    best: tuple[Candidate, float] | None = None
    for item in pool:
        mood_similarity = _mood_similarity(target, (float(item.feeling_score), float(item.energy_score)))
        score = visual_weight * item.similarity + mood_weight * mood_similarity
        if best is None or score > best[1]:
            best = (item, score)
    return best


def _mood_similarity(a: tuple[float, float], b: tuple[float, float]) -> float:
    distance = math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)
    return max(0.0, 1.0 - distance / math.sqrt(200.0))


def _diversity(item: Candidate, selected: list[Candidate]) -> float:
    if not selected:
        return 0.0
    distances = []
    for other in selected:
        raw_dist = float(np.linalg.norm(item.vector - other.vector))
        distances.append(raw_dist)
    min_distance = min(distances)
    return float(1.0 - math.exp(-min_distance / 2.0))


def _save_event(
    conn: sqlite3.Connection,
    session_id: str | None,
    seed_material: str,
    query_vector: list[float],
    query_raw: dict[str, float],
    query_summary: dict[str, Any],
) -> int:
    payload = {"vector": query_vector, "raw": query_raw, "summary": query_summary}
    cursor = conn.execute(
        """
        INSERT INTO recommendation_events
            (session_id, upload_image_sha1, upload_feature_json)
        VALUES (?, ?, ?)
        """,
        (session_id, seed_material[:40], json.dumps(payload, ensure_ascii=True, separators=(",", ":"))),
    )
    return int(cursor.lastrowid)


def _save_result(conn: sqlite3.Connection, event_id: int, candidate: Candidate, slot: str, final_score: float, rank: int) -> None:
    conn.execute(
        """
        INSERT INTO recommendation_results
            (event_id, photo_id, slot, distance, similarity, final_score, rank)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (event_id, candidate.photo_id, slot, candidate.distance, candidate.similarity, final_score, rank),
    )
    conn.execute(
        """
        INSERT INTO feedback
            (event_id, photo_id, link_key, action, value)
        VALUES (?, ?, ?, 'shown', 0)
        """,
        (event_id, candidate.photo_id, candidate.link_key),
    )


def _response_item(
    slot: str,
    candidate: Candidate,
    query_raw: dict[str, float],
    query_summary: dict[str, Any],
    final_score: float,
) -> dict[str, Any]:
    return {
        "slot": slot,
        "photo_id": candidate.photo_id,
        "source_dir": candidate.source_dir,
        "image_url": f"/api/photos/{candidate.photo_id}/image",
        "youtube_music_url": candidate.url,
        "distance": candidate.distance,
        "similarity": candidate.similarity,
        "final_score": final_score,
        "reason": _reason(query_raw, candidate.raw),
        "visualization": {
            "query": query_summary,
            "match": candidate.summary,
            "feature_compare": _feature_compare(query_raw, candidate.raw),
        },
    }


def _reason(query_raw: dict[str, float], item_raw: dict[str, float]) -> list[str]:
    pairs = []
    for key, label in EXPLANATION_FEATURES:
        diff = abs(float(query_raw.get(key, 0.0)) - float(item_raw.get(key, 0.0)))
        pairs.append((diff, label))
    pairs.sort(key=lambda pair: pair[0])
    return [f"{label} is close" for _, label in pairs[:4]]


def _feature_compare(query_raw: dict[str, float], item_raw: dict[str, float]) -> list[dict[str, Any]]:
    rows = []
    for key, label in EXPLANATION_FEATURES:
        q = float(query_raw.get(key, 0.0))
        x = float(item_raw.get(key, 0.0))
        closeness = max(0.0, 1.0 - abs(q - x))
        rows.append({"name": label, "query": q, "match": x, "closeness": closeness})
    rows.sort(key=lambda row: row["closeness"], reverse=True)
    return rows


def _query_features(query_raw: dict[str, float]) -> dict[str, float]:
    keys = [
        "brightness_mean",
        "saturation_mean",
        "warm_ratio",
        "blue_ratio",
        "gray_ratio",
        "dark_ratio",
        "contrast",
        "edge_density",
        "sky_blue",
        "sky_cloud",
        "sky_gray",
        "sky_warm",
        "sky_texture",
        "sky_clear",
    ]
    return {key: float(query_raw.get(key, 0.0)) for key in keys}

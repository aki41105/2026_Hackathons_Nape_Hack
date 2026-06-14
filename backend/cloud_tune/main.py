from __future__ import annotations

import hashlib
import os
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import FEATURE_VERSION
from .db import connect, init_db, json_dumps
from .features import extract_image_features
from .recommender import recommend


WORKSPACE = Path(os.environ.get("CLOUD_TUNE_WORKSPACE", "/home/ubuntu/workspace/cloud-tune"))
DB_PATH = Path(os.environ.get("CLOUD_TUNE_DB", WORKSPACE / "data" / "cloud_tune.sqlite3"))
UPLOAD_DIR = WORKSPACE / "data" / "uploads"
PHOTO_DIR = WORKSPACE / "data" / "photos"
TEST_QUERY_DIR = WORKSPACE / "data" / "test_queries"
APP_DIR = WORKSPACE / "app"
EMOTION_OPTIONS = (
    {"key": "sentimental", "label": "しみじみ", "feeling": -1, "energy": 1},
    {"key": "excited", "label": "わくわく", "feeling": 1, "energy": 1},
    {"key": "nostalgic", "label": "懐かしい", "feeling": -1, "energy": -1},
    {"key": "relaxed", "label": "のんびり", "feeling": 1, "energy": -1},
)
EMOTION_BY_KEY = {option["key"]: option for option in EMOTION_OPTIONS}
EMOTION_BY_LABEL = {option["label"]: option for option in EMOTION_OPTIONS}
EMOTION_LABELS = tuple(option["label"] for option in EMOTION_OPTIONS)


def clamp_score(value: object) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(-5.0, min(5.0, score))


def option_from_scores(feeling_score: float, energy_score: float) -> dict[str, object]:
    if feeling_score >= 0 and energy_score >= 0:
        return EMOTION_BY_KEY["excited"]
    if feeling_score >= 0 and energy_score < 0:
        return EMOTION_BY_KEY["relaxed"]
    if feeling_score < 0 and energy_score < 0:
        return EMOTION_BY_KEY["nostalgic"]
    return EMOTION_BY_KEY["sentimental"]


app = FastAPI(title="Cloud Tune API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    with connect(DB_PATH) as conn:
        init_db(conn)


@app.get("/health")
def health() -> dict[str, object]:
    return {"ok": True, "feature_version": FEATURE_VERSION}


@app.get("/")
def index() -> FileResponse:
    index_path = APP_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(index_path)


@app.get("/api/stats")
def stats() -> dict[str, object]:
    with connect(DB_PATH) as conn:
        photos = conn.execute("SELECT COUNT(*) AS count FROM photos WHERE active = 1").fetchone()["count"]
        tracks = conn.execute("SELECT COUNT(*) AS count FROM tracks").fetchone()["count"]
        feature_rows = conn.execute(
            "SELECT COUNT(*) AS count FROM image_features WHERE feature_version = ?",
            (FEATURE_VERSION,),
        ).fetchone()["count"]
    return {"photos": photos, "tracks": tracks, "features": feature_rows, "feature_version": FEATURE_VERSION}


@app.get("/api/library")
def library(limit: int = 120) -> dict[str, object]:
    limit = max(1, min(limit, 300))
    with connect(DB_PATH) as conn:
        init_db(conn)
        rows = conn.execute(
            """
            SELECT
                p.id,
                p.source_dir,
                p.created_at,
                t.url,
                e.emotion_key,
                e.emotion_label,
                e.feeling_score,
                e.energy_score
            FROM photos p
            JOIN tracks t ON t.link_key = p.link_key
            LEFT JOIN photo_emotions e ON e.photo_id = p.id
            WHERE p.active = 1
            ORDER BY p.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        count = conn.execute("SELECT COUNT(*) AS count FROM photos WHERE active = 1").fetchone()["count"]
    return {
        "count": count,
        "items": [
            {
                "photo_id": int(row["id"]),
                "source_dir": row["source_dir"],
                "created_at": row["created_at"],
                "youtube_music_url": row["url"],
                "image_url": f"/api/photos/{int(row['id'])}/image",
                "emotion_key": row["emotion_key"],
                "emotion_label": row["emotion_label"],
                "feeling_score": row["feeling_score"],
                "energy_score": row["energy_score"],
            }
            for row in rows
        ],
    }


@app.get("/api/annotations")
def annotations(limit: int = 300) -> dict[str, object]:
    limit = max(1, min(limit, 500))
    with connect(DB_PATH) as conn:
        init_db(conn)
        rows = conn.execute(
            """
            SELECT
                p.id,
                p.source_dir,
                p.created_at,
                t.url,
                e.emotion_key,
                e.emotion_label,
                e.feeling_score,
                e.energy_score
            FROM photos p
            JOIN tracks t ON t.link_key = p.link_key
            LEFT JOIN photo_emotions e ON e.photo_id = p.id
            WHERE p.active = 1
            ORDER BY p.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        count = conn.execute("SELECT COUNT(*) AS count FROM photos WHERE active = 1").fetchone()["count"]
    return {
        "count": count,
        "labels": list(EMOTION_LABELS),
        "emotion_options": [dict(option) for option in EMOTION_OPTIONS],
        "items": [
            {
                "photo_id": int(row["id"]),
                "source_dir": row["source_dir"],
                "created_at": row["created_at"],
                "youtube_music_url": row["url"],
                "image_url": f"/api/photos/{int(row['id'])}/image",
                "emotion_key": row["emotion_key"],
                "emotion_label": row["emotion_label"],
                "feeling_score": row["feeling_score"],
                "energy_score": row["energy_score"],
            }
            for row in rows
        ],
    }


@app.post("/api/photos/{photo_id}/emotion")
def set_photo_emotion(photo_id: int, payload: dict[str, object]) -> dict[str, object]:
    key = str(payload.get("emotion_key", "")).strip()
    label = str(payload.get("emotion_label", "")).strip()
    has_point = "feeling_score" in payload and "energy_score" in payload
    feeling_score = clamp_score(payload.get("feeling_score"))
    energy_score = clamp_score(payload.get("energy_score"))
    option = None
    if has_point:
        key = ""
        label = ""
    else:
        option = EMOTION_BY_KEY.get(key) if key else EMOTION_BY_LABEL.get(label)
        if option is None:
            raise HTTPException(status_code=400, detail="Invalid emotion label")
        key = str(option["key"])
        label = str(option["label"])
        feeling_score = float(option["feeling"]) * 3.0
        energy_score = float(option["energy"]) * 3.0
    with connect(DB_PATH) as conn:
        init_db(conn)
        row = conn.execute("SELECT id FROM photos WHERE id = ? AND active = 1", (photo_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Photo not found")
        conn.execute(
            """
            INSERT INTO photo_emotions (
                photo_id,
                emotion_key,
                emotion_label,
                feeling_score,
                energy_score,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(photo_id) DO UPDATE SET
                emotion_key = excluded.emotion_key,
                emotion_label = excluded.emotion_label,
                feeling_score = excluded.feeling_score,
                energy_score = excluded.energy_score,
                updated_at = CURRENT_TIMESTAMP
            """,
            (photo_id, key, label, feeling_score, energy_score),
        )
        conn.commit()
    return {
        "ok": True,
        "photo_id": photo_id,
        "emotion_key": key,
        "emotion_label": label,
        "feeling_score": feeling_score,
        "energy_score": energy_score,
    }


@app.get("/api/test-images")
def test_images() -> dict[str, object]:
    TEST_QUERY_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for path in sorted(
        TEST_QUERY_DIR.iterdir(),
        key=lambda item: item.stat().st_mtime if item.is_file() else 0,
        reverse=True,
    ):
        if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        items.append(
            {
                "name": path.name,
                "url": f"/api/test-images/{quote(path.name)}",
                "size": path.stat().st_size,
                "modified": path.stat().st_mtime,
            }
        )
    return {"items": items}


@app.get("/api/test-images/{filename}")
def test_image(filename: str) -> FileResponse:
    if Path(filename).name != filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = TEST_QUERY_DIR / filename
    if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(status_code=404, detail="Test image not found")
    return FileResponse(path)


@app.post("/api/recommend")
async def recommend_api(
    file: UploadFile = File(...),
    session_id: str | None = Form(None),
    feeling_score: float | None = Form(None),
    energy_score: float | None = Form(None),
) -> dict[str, object]:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload")
    digest = hashlib.sha1(data).hexdigest()
    suffix = _safe_suffix(file.filename)
    upload_path = UPLOAD_DIR / f"{digest}{suffix}"
    upload_path.write_bytes(data)

    try:
        features = extract_image_features(upload_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not process image: {exc}") from exc

    with connect(DB_PATH) as conn:
        init_db(conn)
        return recommend(
            conn=conn,
            query_vector=features.vector,
            query_raw=features.raw,
            query_summary=features.summary,
            session_id=session_id,
            seed_material=digest,
            query_mood=(
                clamp_score(feeling_score),
                clamp_score(energy_score),
            )
            if feeling_score is not None and energy_score is not None
            else None,
        )


@app.post("/api/register")
async def register_api(
    file: UploadFile = File(...),
    youtube_music_url: str = Form(...),
    feeling_score: float | None = Form(None),
    energy_score: float | None = Form(None),
) -> dict[str, object]:
    url = youtube_music_url.strip()
    link_key = _youtube_link_key(url)
    if not link_key:
        raise HTTPException(status_code=400, detail="YouTube Music link is invalid")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload")

    digest = hashlib.sha1(data).hexdigest()
    suffix = _safe_suffix(file.filename)
    token = f"{time.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    source_dir = f"user_upload_{token}_{digest[:8]}"
    image_path = PHOTO_DIR / f"{source_dir}{suffix}"
    image_path.write_bytes(data)

    try:
        features = extract_image_features(image_path)
    except Exception as exc:
        image_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Could not process image: {exc}") from exc

    with connect(DB_PATH) as conn:
        init_db(conn)
        conn.execute(
            """
            INSERT OR IGNORE INTO tracks (link_key, url, url_hash)
            VALUES (?, ?, ?)
            """,
            (link_key, url, hashlib.sha1(url.encode("utf-8")).hexdigest()),
        )
        cursor = conn.execute(
            """
            INSERT INTO photos
                (source_dir, source_image_path, copied_image_path, image_sha1, link_key, active)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (source_dir, str(image_path), str(image_path), digest, link_key),
        )
        photo_id = int(cursor.lastrowid)
        conn.execute(
            """
            INSERT INTO image_features
                (photo_id, feature_version, vector_json, raw_json, summary_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                photo_id,
                FEATURE_VERSION,
                json_dumps(features.vector),
                json_dumps(features.raw),
                json_dumps(features.summary),
            ),
        )
        if feeling_score is not None and energy_score is not None:
            conn.execute(
                """
                INSERT INTO photo_emotions (
                    photo_id,
                    emotion_key,
                    emotion_label,
                    feeling_score,
                    energy_score,
                    updated_at
                )
                VALUES (?, '', '', ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(photo_id) DO UPDATE SET
                    emotion_key = '',
                    emotion_label = '',
                    feeling_score = excluded.feeling_score,
                    energy_score = excluded.energy_score,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (photo_id, clamp_score(feeling_score), clamp_score(energy_score)),
            )
        conn.commit()

    return {
        "ok": True,
        "photo_id": photo_id,
        "image_url": f"/api/photos/{photo_id}/image",
        "youtube_music_url": url,
    }


@app.get("/api/photos/{photo_id}/image")
def photo_image(photo_id: int) -> FileResponse:
    with connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT copied_image_path FROM photos WHERE id = ? AND active = 1",
            (photo_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    path = Path(row["copied_image_path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image file not found")
    return FileResponse(path)


@app.post("/api/feedback")
def feedback(payload: dict[str, object]) -> dict[str, object]:
    action = str(payload.get("action", ""))
    if action not in {"clicked", "liked", "disliked", "skipped"}:
        raise HTTPException(status_code=400, detail="Invalid action")
    photo_id = int(payload.get("photo_id", 0))
    event_id = payload.get("event_id")
    value = int(payload.get("value", 0))
    session_id = payload.get("session_id")
    with connect(DB_PATH) as conn:
        row = conn.execute("SELECT link_key FROM photos WHERE id = ?", (photo_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Photo not found")
        conn.execute(
            """
            INSERT INTO feedback (event_id, photo_id, link_key, action, value, session_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, photo_id, row["link_key"], action, value, session_id),
        )
        conn.commit()
    return {"ok": True}


def _safe_suffix(filename: str | None) -> str:
    if not filename:
        return ".jpg"
    suffix = Path(filename).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return suffix
    return ".jpg"


def _youtube_link_key(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host != "music.youtube.com":
        return None
    key = parse_qs(parsed.query).get("v", [""])[0]
    key = key.strip()
    if not key or len(key) > 64:
        return None
    return key


app.mount("/static", StaticFiles(directory=APP_DIR), name="static")

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tracks (
            link_key TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            url_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_dir TEXT NOT NULL UNIQUE,
            source_image_path TEXT NOT NULL,
            copied_image_path TEXT NOT NULL,
            image_sha1 TEXT NOT NULL,
            link_key TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (link_key) REFERENCES tracks(link_key)
        );

        CREATE INDEX IF NOT EXISTS idx_photos_link_key ON photos(link_key);

        CREATE TABLE IF NOT EXISTS photo_emotions (
            photo_id INTEGER PRIMARY KEY,
            emotion_key TEXT,
            emotion_label TEXT NOT NULL,
            feeling_score REAL,
            energy_score REAL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (photo_id) REFERENCES photos(id)
        );

        CREATE TABLE IF NOT EXISTS image_features (
            photo_id INTEGER PRIMARY KEY,
            feature_version TEXT NOT NULL,
            vector_json TEXT NOT NULL,
            raw_json TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            computed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (photo_id) REFERENCES photos(id)
        );

        CREATE TABLE IF NOT EXISTS feature_stats (
            feature_version TEXT PRIMARY KEY,
            mean_json TEXT NOT NULL,
            std_json TEXT NOT NULL,
            weight_json TEXT NOT NULL,
            feature_order_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS recommendation_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            upload_image_sha1 TEXT,
            upload_image_path TEXT,
            upload_feature_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS recommendation_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            photo_id INTEGER NOT NULL,
            slot TEXT NOT NULL,
            distance REAL,
            similarity REAL,
            final_score REAL,
            rank INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (event_id) REFERENCES recommendation_events(id),
            FOREIGN KEY (photo_id) REFERENCES photos(id)
        );

        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER,
            photo_id INTEGER NOT NULL,
            link_key TEXT NOT NULL,
            action TEXT NOT NULL,
            value INTEGER,
            session_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (event_id) REFERENCES recommendation_events(id),
            FOREIGN KEY (photo_id) REFERENCES photos(id)
        );
        """
    )
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(photo_emotions)").fetchall()
    }
    if "emotion_key" not in columns:
        conn.execute("ALTER TABLE photo_emotions ADD COLUMN emotion_key TEXT")
    if "feeling_score" not in columns:
        conn.execute("ALTER TABLE photo_emotions ADD COLUMN feeling_score REAL")
    if "energy_score" not in columns:
        conn.execute("ALTER TABLE photo_emotions ADD COLUMN energy_score REAL")
    conn.execute(
        """
        UPDATE photo_emotions
        SET
            emotion_key = CASE emotion_label
                WHEN 'わくわく' THEN 'excited'
                WHEN 'のんびり' THEN 'relaxed'
                WHEN '懐かしい' THEN 'nostalgic'
                WHEN 'しみじみ' THEN 'sentimental'
                ELSE emotion_key
            END,
            feeling_score = CASE emotion_label
                WHEN 'わくわく' THEN 3.0
                WHEN 'のんびり' THEN 3.0
                WHEN '懐かしい' THEN -3.0
                WHEN 'しみじみ' THEN -3.0
                ELSE feeling_score
            END,
            energy_score = CASE emotion_label
                WHEN 'わくわく' THEN 3.0
                WHEN 'のんびり' THEN -3.0
                WHEN '懐かしい' THEN -3.0
                WHEN 'しみじみ' THEN 3.0
                ELSE energy_score
            END
        WHERE emotion_key IS NULL OR emotion_key = ''
        """
    )
    conn.execute(
        """
        UPDATE photo_emotions
        SET
            feeling_score = CASE emotion_key
                WHEN 'excited' THEN 3.0
                WHEN 'relaxed' THEN 3.0
                WHEN 'nostalgic' THEN -3.0
                WHEN 'sentimental' THEN -3.0
                ELSE feeling_score
            END,
            energy_score = CASE emotion_key
                WHEN 'excited' THEN 3.0
                WHEN 'relaxed' THEN -3.0
                WHEN 'nostalgic' THEN -3.0
                WHEN 'sentimental' THEN 3.0
                ELSE energy_score
            END
        WHERE feeling_score IS NULL OR energy_score IS NULL
        """
    )
    conn.commit()


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def json_loads(value: str) -> Any:
    return json.loads(value)

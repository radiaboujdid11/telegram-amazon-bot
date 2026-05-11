"""
Database - SQLite
Handles users, search history, stats, and preferences
"""

import sqlite3
import json
from typing import List, Dict, Optional


class Database:
    def __init__(self, db_path: str = "shopping_bot.db"):
        self.db_path = db_path
        self._init()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id     INTEGER PRIMARY KEY,
                    username    TEXT,
                    first_name  TEXT,
                    language    TEXT DEFAULT 'fr',
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS search_history (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id      INTEGER NOT NULL,
                    product_name TEXT NOT NULL,
                    results_json TEXT,
                    search_date  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id     INTEGER PRIMARY KEY,
                    prefs_json  TEXT NOT NULL DEFAULT '{}',
                    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );

                CREATE INDEX IF NOT EXISTS idx_search_user ON search_history(user_id);
                CREATE INDEX IF NOT EXISTS idx_search_date ON search_history(search_date);
            """)

    def save_user(self, user_id: int, username, first_name):
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO users (user_id, username, first_name)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username    = excluded.username,
                    first_name  = excluded.first_name,
                    last_active = CURRENT_TIMESTAMP
            """, (user_id, username, first_name))

    def get_user(self, user_id: int):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    def save_search(self, user_id: int, product_name: str, results=None):
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO search_history (user_id, product_name, results_json)
                VALUES (?, ?, ?)
            """, (user_id, product_name, json.dumps(results) if results else None))

    def get_user_history(self, user_id: int, limit: int = 10):
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT product_name, search_date
                FROM search_history
                WHERE user_id = ?
                ORDER BY search_date DESC
                LIMIT ?
            """, (user_id, limit)).fetchall()
            return [dict(r) for r in rows]

    def save_user_preferences(self, user_id: int, prefs: dict):
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO user_preferences (user_id, prefs_json)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    prefs_json = excluded.prefs_json,
                    updated_at = CURRENT_TIMESTAMP
            """, (user_id, json.dumps(prefs)))

    def get_user_preferences(self, user_id: int):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT prefs_json FROM user_preferences WHERE user_id = ?", (user_id,)
            ).fetchone()
            return json.loads(row["prefs_json"]) if row else None

    def get_user_stats(self, user_id: int) -> dict:
        with self._connect() as conn:
            stats = conn.execute("""
                SELECT COUNT(*) AS total_searches, COUNT(DISTINCT product_name) AS unique_products
                FROM search_history WHERE user_id = ?
            """, (user_id,)).fetchone()
            user = conn.execute(
                "SELECT created_at FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            return {
                "total_searches":  stats["total_searches"],
                "unique_products": stats["unique_products"],
                "member_since":    user["created_at"][:10] if user else "?",
            }

    def get_global_stats(self) -> dict:
        with self._connect() as conn:
            row = conn.execute("""
                SELECT
                    (SELECT COUNT(*) FROM users)          AS total_users,
                    (SELECT COUNT(*) FROM search_history) AS total_searches
            """).fetchone()
            return dict(row)

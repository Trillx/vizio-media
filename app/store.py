"""Small SQLite store. Each operation closes its own connection."""

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "vizio-media.sqlite3"
        with self.connection() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS progress (
                    title_id TEXT PRIMARY KEY,
                    position REAL NOT NULL,
                    duration REAL NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS diagnostics (
                    id INTEGER PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS profiles (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, pin_hash TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS owner (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1), password_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, kind TEXT NOT NULL, profile_id TEXT,
                    expires_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS service_config (
                    service TEXT PRIMARY KEY, sealed TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS accounts (
                    profile_id TEXT NOT NULL REFERENCES profiles(id), service TEXT NOT NULL,
                    sealed TEXT NOT NULL, display_name TEXT NOT NULL, expires_at REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'connected',
                    PRIMARY KEY(profile_id, service)
                );
                CREATE TABLE IF NOT EXISTS oauth_flows (
                    id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, service TEXT NOT NULL,
                    sealed TEXT NOT NULL, state TEXT NOT NULL, expires_at REAL NOT NULL,
                    interval REAL NOT NULL, next_poll REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS playback (
                    profile_id TEXT NOT NULL, title_id TEXT NOT NULL,
                    position REAL NOT NULL, duration REAL NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(profile_id, title_id)
                );
                CREATE TABLE IF NOT EXISTS catalog_cache (
                    key TEXT PRIMARY KEY, payload TEXT NOT NULL, expires_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS flow_profile ON oauth_flows(profile_id, service);
                CREATE TABLE IF NOT EXISTS watching_titles (
                    profile_id TEXT NOT NULL, media_id TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(profile_id, media_id)
                );
            """)
            connection.execute("INSERT OR IGNORE INTO profiles(id, name) VALUES ('household', 'Household')")
            connection.execute("""INSERT OR IGNORE INTO playback(profile_id,title_id,position,duration,updated_at)
                SELECT 'household',title_id,position,duration,updated_at FROM progress""")

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def progress(self, title_id: str) -> dict:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT title_id, position, duration, updated_at FROM progress WHERE title_id = ?",
                (title_id,),
            ).fetchone()
        return dict(row) if row else {"title_id": title_id, "position": 0, "duration": 0}

    def save_progress(self, title_id: str, position: float, duration: float) -> dict:
        with self.connection() as connection:
            connection.execute("""
                INSERT INTO progress (title_id, position, duration) VALUES (?, ?, ?)
                ON CONFLICT(title_id) DO UPDATE SET position = excluded.position,
                    duration = excluded.duration, updated_at = CURRENT_TIMESTAMP
            """, (title_id, position, duration))
        return self.progress(title_id)

    def log(self, session_id: str, kind: str, payload: dict):
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO diagnostics (session_id, kind, payload) VALUES (?, ?, ?)",
                (session_id, kind, json.dumps(payload, ensure_ascii=True)),
            )
            connection.execute(
                "DELETE FROM diagnostics WHERE id NOT IN (SELECT id FROM diagnostics ORDER BY id DESC LIMIT 500)"
            )

    def diagnostics(self) -> list[dict]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM diagnostics ORDER BY id DESC LIMIT 100"
            ).fetchall()
        return [dict(row, payload=json.loads(row["payload"])) for row in rows]

    def profiles(self) -> list[dict]:
        with self.connection() as connection:
            rows = connection.execute("SELECT id,name,pin_hash FROM profiles ORDER BY created_at,id").fetchall()
        return [{"id": row["id"], "name": row["name"], "requires_pin": bool(row["pin_hash"])} for row in rows]

    def profile(self, profile_id: str) -> dict | None:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        return dict(row) if row else None

    def create_profile(self, name: str, pin_hash: str | None) -> str:
        profile_id = uuid.uuid4().hex
        with self.connection() as connection:
            if connection.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] >= 12:
                raise ValueError("This installation supports up to twelve household profiles.")
            connection.execute("INSERT INTO profiles(id,name,pin_hash) VALUES (?,?,?)", (profile_id,name,pin_hash))
        return profile_id

    def update_profile(self, profile_id: str, name: str, pin_hash: str | None):
        with self.connection() as connection:
            connection.execute("UPDATE profiles SET name=?,pin_hash=? WHERE id=?", (name,pin_hash,profile_id))
            connection.execute("DELETE FROM sessions WHERE profile_id=?", (profile_id,))

    def delete_profile(self, profile_id: str):
        if profile_id == "household":
            raise ValueError("The Household profile cannot be deleted.")
        with self.connection() as connection:
            for table in ("accounts","oauth_flows","playback","sessions","watching_titles"):
                connection.execute(f"DELETE FROM {table} WHERE profile_id=?", (profile_id,))
            connection.execute("DELETE FROM profiles WHERE id=?", (profile_id,))

    def owner_hash(self) -> str | None:
        with self.connection() as connection:
            row = connection.execute("SELECT password_hash FROM owner WHERE singleton=1").fetchone()
        return row[0] if row else None

    def setup_owner(self, password_hash: str):
        with self.connection() as connection:
            connection.execute("INSERT INTO owner(singleton,password_hash) VALUES (1,?)", (password_hash,))

    def add_session(self, token_hash: str, kind: str, profile_id: str | None, expires_at: float):
        with self.connection() as connection:
            connection.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))
            connection.execute("INSERT INTO sessions VALUES (?,?,?,?)", (token_hash,kind,profile_id,expires_at))
            connection.execute("DELETE FROM sessions WHERE rowid NOT IN (SELECT rowid FROM sessions ORDER BY expires_at DESC LIMIT 200)")

    def session(self, token_hash: str, kind: str) -> dict | None:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM sessions WHERE token_hash=? AND kind=? AND expires_at>?", (token_hash,kind,time.time())).fetchone()
        return dict(row) if row else None

    def drop_session(self, token_hash: str):
        with self.connection() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))

    def config(self, service: str) -> str | None:
        with self.connection() as connection:
            row = connection.execute("SELECT sealed FROM service_config WHERE service=?", (service,)).fetchone()
        return row[0] if row else None

    def save_config(self, service: str, sealed: str):
        with self.connection() as connection:
            connection.execute("INSERT INTO service_config VALUES (?,?) ON CONFLICT(service) DO UPDATE SET sealed=excluded.sealed", (service,sealed))
            connection.execute("DELETE FROM catalog_cache")

    def delete_config(self, service: str):
        with self.connection() as connection:
            connection.execute("DELETE FROM service_config WHERE service=?", (service,))
            connection.execute("DELETE FROM catalog_cache")

    def account(self, profile_id: str, service: str) -> dict | None:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM accounts WHERE profile_id=? AND service=?", (profile_id,service)).fetchone()
        return dict(row) if row else None

    def save_account(self, profile_id: str, service: str, sealed: str, display_name: str, expires_at: float, *, flow_id: str | None = None):
        with self.connection() as connection:
            connection.execute("""INSERT INTO accounts VALUES (?,?,?,?,?,'connected')
                ON CONFLICT(profile_id,service) DO UPDATE SET sealed=excluded.sealed,
                display_name=excluded.display_name,expires_at=excluded.expires_at,status='connected'""",
                (profile_id,service,sealed,display_name,expires_at))
            if flow_id:
                connection.execute("UPDATE oauth_flows SET state='connected',sealed='' WHERE id=?", (flow_id,))

    def mark_account(self, profile_id: str, service: str, status: str):
        with self.connection() as connection:
            connection.execute("UPDATE accounts SET status=? WHERE profile_id=? AND service=?", (status,profile_id,service))

    def unlink(self, profile_id: str, service: str):
        with self.connection() as connection:
            connection.execute("DELETE FROM accounts WHERE profile_id=? AND service=?", (profile_id,service))
            connection.execute("DELETE FROM oauth_flows WHERE profile_id=? AND service=?", (profile_id,service))

    def linked_count(self, service: str) -> int:
        with self.connection() as connection:
            return connection.execute("SELECT COUNT(*) FROM accounts WHERE service=?", (service,)).fetchone()[0]

    def pending_count(self, service: str) -> int:
        with self.connection() as connection:
            return connection.execute("SELECT COUNT(*) FROM oauth_flows WHERE service=? AND state='pending' AND expires_at>?", (service,time.time())).fetchone()[0]

    def sealed_values(self) -> list[str]:
        with self.connection() as connection:
            rows=connection.execute("SELECT sealed FROM service_config UNION ALL SELECT sealed FROM accounts UNION ALL SELECT sealed FROM oauth_flows WHERE sealed != ''").fetchall()
        return [row[0] for row in rows]

    def flow(self, flow_id: str) -> dict | None:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM oauth_flows WHERE id=?", (flow_id,)).fetchone()
        return dict(row) if row else None

    def pending_flow(self, profile_id: str, service: str) -> dict | None:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM oauth_flows WHERE profile_id=? AND service=? AND state='pending' AND expires_at>? ORDER BY expires_at DESC LIMIT 1", (profile_id,service,time.time())).fetchone()
        return dict(row) if row else None

    def save_flow(self, flow: dict):
        with self.connection() as connection:
            connection.execute("DELETE FROM oauth_flows WHERE expires_at<?", (time.time()-86400,))
            connection.execute("""INSERT INTO oauth_flows VALUES (:id,:profile_id,:service,:sealed,:state,:expires_at,:interval,:next_poll)
                ON CONFLICT(id) DO UPDATE SET sealed=excluded.sealed,state=excluded.state,
                next_poll=excluded.next_poll,interval=excluded.interval""", flow)
            connection.execute("DELETE FROM oauth_flows WHERE rowid NOT IN (SELECT rowid FROM oauth_flows ORDER BY expires_at DESC LIMIT 500)")

    def playback(self, profile_id: str, title_id: str) -> dict:
        with self.connection() as connection:
            row = connection.execute("SELECT title_id,position,duration,updated_at FROM playback WHERE profile_id=? AND title_id=?", (profile_id,title_id)).fetchone()
        return dict(row) if row else {"title_id": title_id, "position": 0, "duration": 0}

    def save_playback(self, profile_id: str, title_id: str, position: float, duration: float) -> dict:
        with self.connection() as connection:
            connection.execute("""INSERT INTO playback(profile_id,title_id,position,duration) VALUES (?,?,?,?)
                ON CONFLICT(profile_id,title_id) DO UPDATE SET position=excluded.position,duration=excluded.duration,updated_at=CURRENT_TIMESTAMP""", (profile_id,title_id,position,duration))
        return self.playback(profile_id,title_id)

    def remember_watching(self, profile_id: str, media_id: str, title: dict):
        with self.connection() as connection:
            connection.execute("""INSERT INTO watching_titles VALUES (?,?,?)
                ON CONFLICT(profile_id,media_id) DO UPDATE SET payload=excluded.payload""",
                (profile_id,media_id,json.dumps(title)))
            connection.execute("""DELETE FROM watching_titles WHERE profile_id=? AND media_id NOT IN
                (SELECT title_id FROM playback WHERE profile_id=? ORDER BY updated_at DESC LIMIT 200)
                AND media_id != ?""", (profile_id,profile_id,media_id))

    def continue_watching(self, profile_id: str):
        with self.connection() as connection:
            rows=connection.execute("""SELECT w.media_id,w.payload,p.position,p.duration FROM watching_titles w
                JOIN playback p ON p.profile_id=w.profile_id AND p.title_id=w.media_id
                WHERE w.profile_id=? AND p.position>1 AND p.position<p.duration-2
                ORDER BY p.updated_at DESC LIMIT 20""", (profile_id,)).fetchall()
        return [{**json.loads(row["payload"]),"watching_id":row["media_id"],
                 "progress":{"position":row["position"],"duration":row["duration"]}} for row in rows]

    def cached(self, key: str, *, stale: bool = False):
        with self.connection() as connection:
            row = connection.execute("SELECT payload,expires_at FROM catalog_cache WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row and (stale or row[1]>time.time()) else None

    def cache(self, key: str, payload, ttl: int = 21600):
        with self.connection() as connection:
            connection.execute("INSERT INTO catalog_cache VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,expires_at=excluded.expires_at", (key,json.dumps(payload),time.time()+ttl))
            connection.execute("DELETE FROM catalog_cache WHERE rowid NOT IN (SELECT rowid FROM catalog_cache ORDER BY expires_at DESC LIMIT 1000)")

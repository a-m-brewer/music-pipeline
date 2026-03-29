import json
import sqlite3
from collections.abc import Generator
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Optional

from music_pipeline.models import IdentificationResult, SourceResult, TrackTags


class FileStatus(StrEnum):
    PENDING = "pending"
    IDENTIFIED = "identified"
    APPROVED = "approved"
    MOVED = "moved"
    DISCARDED = "discarded"
    SKIPPED = "skipped"
    ERROR = "error"


SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    confidence INTEGER,
    identified_tags TEXT,
    sources_used TEXT,
    source_results TEXT,
    reasoning TEXT,
    destination_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL,
    file_id INTEGER,
    timestamp TEXT NOT NULL,
    tokens_used INTEGER DEFAULT 0,
    FOREIGN KEY (file_id) REFERENCES files(id)
);

CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
CREATE INDEX IF NOT EXISTS idx_files_file_path ON files(file_path);
CREATE INDEX IF NOT EXISTS idx_api_calls_service ON api_calls(service);
"""


class StateDB:
    def __init__(self, db_path: str = "pipeline_state.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(SCHEMA)
        # Migrate existing DBs that predate the source_results column
        try:
            self.conn.execute("ALTER TABLE files ADD COLUMN source_results TEXT")
            self.conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists

    def close(self):
        self.conn.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # --- File operations ---

    def add_file(self, file_path: str) -> int:
        """Add a file to track. Returns the file ID. Skips if already exists."""
        now = self._now()
        try:
            cursor = self.conn.execute(
                "INSERT INTO files (file_path, status, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (file_path, FileStatus.PENDING, now, now),
            )
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            row = self.conn.execute(
                "SELECT id FROM files WHERE file_path = ?", (file_path,)
            ).fetchone()
            return row["id"]

    def get_file(self, file_path: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM files WHERE file_path = ?", (file_path,)
        ).fetchone()
        return dict(row) if row else None

    def get_file_by_id(self, file_id: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM files WHERE id = ?", (file_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_files_by_status(self, status: FileStatus) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM files WHERE status = ? ORDER BY id", (status,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_non_pending_paths(self) -> set[str]:
        """Return paths of all files that are NOT pending (already processed or errored)."""
        rows = self.conn.execute(
            "SELECT file_path FROM files WHERE status != ?", (FileStatus.PENDING,)
        ).fetchall()
        return {row["file_path"] for row in rows}

    def add_files_batch(self, file_paths: list[str]) -> None:
        """Add multiple files in a single transaction. Skips already-existing paths."""
        now = self._now()
        self.conn.executemany(
            "INSERT OR IGNORE INTO files (file_path, status, created_at, updated_at) VALUES (?, ?, ?, ?)",
            [(p, FileStatus.PENDING, now, now) for p in file_paths],
        )
        self.conn.commit()

    def count_pending(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) as count FROM files WHERE status = ?", (FileStatus.PENDING,)
        ).fetchone()
        return row["count"]

    def get_pending_files(self) -> list[dict]:
        return self.get_files_by_status(FileStatus.PENDING)

    def iter_pending_files(self) -> Generator[dict, None, None]:
        """Stream pending files from DB without loading all into memory."""
        cursor = self.conn.execute(
            "SELECT * FROM files WHERE status = ? ORDER BY id", (FileStatus.PENDING,)
        )
        for row in cursor:
            yield dict(row)

    def get_identified_files(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM files WHERE status = ? ORDER BY confidence DESC, id ASC",
            (FileStatus.IDENTIFIED,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_album_siblings(self, album: str, album_artist: str, exclude_path: str) -> list[dict]:
        """Return identified files for the same album/album_artist, excluding the current file."""
        rows = self.conn.execute(
            """SELECT * FROM files
               WHERE status = ?
                 AND file_path != ?
                 AND LOWER(json_extract(identified_tags, '$.album')) = LOWER(?)
                 AND LOWER(json_extract(identified_tags, '$.album_artist')) = LOWER(?)
               ORDER BY json_extract(identified_tags, '$.track_number'), id""",
            (FileStatus.IDENTIFIED, exclude_path, album, album_artist)
        ).fetchall()
        return [dict(r) for r in rows]

    def update_status(self, file_path: str, status: FileStatus):
        self.conn.execute(
            "UPDATE files SET status = ?, updated_at = ? WHERE file_path = ?",
            (status, self._now(), file_path),
        )
        self.conn.commit()

    def save_identification(
        self, file_path: str, result: IdentificationResult
    ):
        """Save identification result for a file."""
        source_results_json = json.dumps([
            {"source": r.source, "confidence": r.confidence, "tags": r.tags.to_dict()}
            for r in result.source_results
        ])
        self.conn.execute(
            """UPDATE files SET
                status = ?,
                confidence = ?,
                identified_tags = ?,
                sources_used = ?,
                source_results = ?,
                reasoning = ?,
                updated_at = ?
            WHERE file_path = ?""",
            (
                FileStatus.IDENTIFIED,
                result.confidence,
                json.dumps(result.tags.to_dict()),
                json.dumps(result.sources_used),
                source_results_json,
                result.reasoning,
                self._now(),
                file_path,
            ),
        )
        self.conn.commit()

    def save_destination(self, file_path: str, destination_path: str):
        self.conn.execute(
            "UPDATE files SET destination_path = ?, updated_at = ? WHERE file_path = ?",
            (destination_path, self._now(), file_path),
        )
        self.conn.commit()

    def load_identification(self, file_path: str) -> Optional[IdentificationResult]:
        """Load a saved identification result."""
        row = self.get_file(file_path)
        if not row or not row.get("identified_tags"):
            return None

        tags_dict = json.loads(row["identified_tags"])
        sources = json.loads(row["sources_used"]) if row.get("sources_used") else []
        source_results_raw = json.loads(row["source_results"]) if row.get("source_results") else []
        source_results = [
            SourceResult(
                source=sr["source"],
                confidence=sr["confidence"],
                tags=TrackTags(**sr["tags"]),
            )
            for sr in source_results_raw
        ]

        return IdentificationResult(
            tags=TrackTags(**tags_dict),
            confidence=row.get("confidence", 0),
            reasoning=row.get("reasoning", ""),
            sources_used=sources,
            source_results=source_results,
        )

    # --- API call tracking ---

    def log_api_call(self, service: str, file_id: Optional[int] = None, tokens_used: int = 0):
        self.conn.execute(
            "INSERT INTO api_calls (service, file_id, timestamp, tokens_used) VALUES (?, ?, ?, ?)",
            (service, file_id, self._now(), tokens_used),
        )
        self.conn.commit()

    # --- Stats ---

    def get_stats(self) -> dict:
        stats = {}
        rows = self.conn.execute(
            "SELECT status, COUNT(*) as count FROM files GROUP BY status"
        ).fetchall()
        for row in rows:
            stats[row["status"]] = row["count"]

        total = self.conn.execute("SELECT COUNT(*) as count FROM files").fetchone()
        stats["total"] = total["count"]

        api_rows = self.conn.execute(
            "SELECT service, COUNT(*) as count, SUM(tokens_used) as total_tokens FROM api_calls GROUP BY service"
        ).fetchall()
        stats["api_calls"] = {
            row["service"]: {"count": row["count"], "tokens": row["total_tokens"] or 0}
            for row in api_rows
        }

        return stats

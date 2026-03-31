"""Persistent attribute library — SQLite-backed memory for fake values (SESSION-01)."""
from __future__ import annotations

import pathlib
import sqlite3

DEFAULT_DB = pathlib.Path(__file__).parent.parent / "enigma_library.db"


class AttributeLibrary:
    """Stores and retrieves fake values across masking sessions.

    Same original value always gets the same fake — even in different files.
    """

    def __init__(self, db_path: str | pathlib.Path | None = None) -> None:
        self.db_path = str(db_path or DEFAULT_DB)
        self._init_db()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS text_mappings (
                    normalized_value TEXT PRIMARY KEY,
                    fake_value       TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS numeric_mappings (
                    column_name TEXT PRIMARY KEY,
                    coefficient REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS column_log (
                    column_name TEXT PRIMARY KEY
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS column_classifications (
                    column_name TEXT PRIMARY KEY,
                    verdict     TEXT NOT NULL
                )
            """)

    @staticmethod
    def _norm(value: str) -> str:
        """Normalize value for consistent lookup."""
        import unicodedata
        import re
        s = unicodedata.normalize("NFC", str(value))
        s = re.sub(r'["\u201c\u201d\u00ab\u00bb\u2018\u2019\']', "", s)
        return re.sub(r"\s+", " ", s).strip().upper()

    # ------------------------------------------------------------------
    # Text mappings
    # ------------------------------------------------------------------

    def lookup(self, column_name: str, original_value: str) -> str | None:
        """Return stored fake for original_value, or None if not seen before."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT fake_value FROM text_mappings WHERE normalized_value = ?",
                (self._norm(original_value),),
            ).fetchone()
        return row[0] if row else None

    def lookup_fuzzy(
        self, original_value: str, threshold: int = 85
    ) -> str | None:
        """Fuzzy lookup: find the closest stored value and return its fake.

        Uses token_sort_ratio so word order differences (e.g. "Иван Петров"
        vs "Петров Иван") and abbreviations are handled correctly.
        Returns None if no match exceeds the threshold.
        """
        try:
            from rapidfuzz import process, fuzz
        except ImportError:
            return None

        query = self._norm(original_value)
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT normalized_value, fake_value FROM text_mappings"
            ).fetchall()

        if not rows:
            return None

        candidates = {r[0]: r[1] for r in rows}
        match = process.extractOne(
            query,
            candidates.keys(),
            scorer=fuzz.token_sort_ratio,
            score_cutoff=threshold,
        )
        if match:
            return candidates[match[0]]
        return None

    def save(self, column_name: str, original_value: str, fake_value: str) -> None:
        """Persist a new original → fake mapping and log the column."""
        norm = self._norm(original_value)
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO text_mappings (normalized_value, fake_value) VALUES (?, ?)",
                (norm, fake_value),
            )
            conn.execute(
                "INSERT OR IGNORE INTO column_log (column_name) VALUES (?)",
                (column_name,),
            )

    # ------------------------------------------------------------------
    # Numeric mappings
    # ------------------------------------------------------------------

    def lookup_numeric(self, column_name: str) -> float | None:
        """Return stored coefficient for column, or None."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT coefficient FROM numeric_mappings WHERE column_name = ?",
                (column_name,),
            ).fetchone()
        return row[0] if row else None

    def save_numeric(self, column_name: str, coefficient: float) -> None:
        """Persist a coefficient for a numeric column."""
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO numeric_mappings (column_name, coefficient) VALUES (?, ?)",
                (column_name, coefficient),
            )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_known_columns(self) -> list[str]:
        """Return list of column names that have been masked at least once."""
        with self._conn() as conn:
            rows = conn.execute("SELECT column_name FROM column_log").fetchall()
        return [r[0] for r in rows]

    # ------------------------------------------------------------------
    # Column classifications (AI verdicts)
    # ------------------------------------------------------------------

    def save_classification(self, column_name: str, verdict: str) -> None:
        """Persist AI verdict for a column. Does not overwrite if already exists."""
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO column_classifications (column_name, verdict) VALUES (?, ?)",
                (column_name, verdict),
            )

    def lookup_classification(self, column_name: str) -> str | None:
        """Return stored verdict for column ('required'/'recommended'/'safe'), or None."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT verdict FROM column_classifications WHERE column_name = ?",
                (column_name,),
            ).fetchone()
        return row[0] if row else None

    def get_all_classifications(self) -> dict[str, str]:
        """Return all stored column classifications as {column_name: verdict}."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT column_name, verdict FROM column_classifications"
            ).fetchall()
        return {r[0]: r[1] for r in rows}

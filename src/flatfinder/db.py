"""SQLite-Speicher. Bewusst ohne ORM - zwei Tabellen, klarer SQL, gut zu reviewen.

Die beiden Tabellen sind die Nahtstelle zwischen den Tracks:
  listings      gehoert Track A (schreibt), Track B liest
  applications  gehoert Track B
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .models import Application, ApplicationStatus, Listing, ListingStatus

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    key           TEXT PRIMARY KEY,
    fingerprint   TEXT NOT NULL,
    source        TEXT NOT NULL,
    status        TEXT NOT NULL,
    score         INTEGER,
    seen_at       TEXT NOT NULL,
    payload       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_listings_fp     ON listings(fingerprint);
CREATE INDEX IF NOT EXISTS idx_listings_status ON listings(status);
CREATE INDEX IF NOT EXISTS idx_listings_seen   ON listings(seen_at DESC);

CREATE TABLE IF NOT EXISTS applications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_key   TEXT NOT NULL REFERENCES listings(key),
    status        TEXT NOT NULL,
    decision      TEXT,
    decided_at    TEXT,
    message_text  TEXT,
    message_model TEXT,
    sent_via      TEXT,
    sent_at       TEXT,
    error         TEXT,
    messenger_ref TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_app_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_app_ref    ON applications(messenger_ref);
-- Eine Bewerbung pro Objekt. Verhindert, dass ein Vermieter zweimal
-- angeschrieben wird, wenn ein Adapter dasselbe Objekt erneut liefert.
CREATE UNIQUE INDEX IF NOT EXISTS idx_app_listing_unique ON applications(listing_key);
"""


class Store:
    def __init__(self, path: str | Path = "data/flatfinder.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
        finally:
            conn.close()

    # ---------- Listings (Track A) ----------

    def is_known(self, listing: Listing) -> bool:
        """Kennen wir das Objekt schon - auch von einer anderen Quelle?"""
        with self._conn() as c:
            row = c.execute(
                "SELECT 1 FROM listings WHERE key = ? OR fingerprint = ? LIMIT 1",
                (listing.key, listing.fingerprint),
            ).fetchone()
        return row is not None

    def upsert(self, listing: Listing) -> None:
        with self._conn() as c:
            c.execute(
                """INSERT INTO listings (key, fingerprint, source, status, score, seen_at, payload)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                       status = excluded.status,
                       score  = excluded.score,
                       payload = excluded.payload""",
                (listing.key, listing.fingerprint, listing.source, listing.status,
                 listing.score, listing.seen_at.isoformat(), listing.model_dump_json()),
            )

    def get(self, key: str) -> Listing | None:
        with self._conn() as c:
            row = c.execute("SELECT payload FROM listings WHERE key = ?", (key,)).fetchone()
        return Listing.model_validate_json(row["payload"]) if row else None

    def recent(self, limit: int = 50, status: ListingStatus | None = None) -> list[Listing]:
        q = "SELECT payload FROM listings"
        args: list = []
        if status:
            q += " WHERE status = ?"
            args.append(str(status))
        q += " ORDER BY seen_at DESC LIMIT ?"
        args.append(limit)
        with self._conn() as c:
            rows = c.execute(q, args).fetchall()
        return [Listing.model_validate_json(r["payload"]) for r in rows]

    # ---------- Applications (Track B) ----------

    def create_application(self, listing_key: str) -> Application | None:
        """Legt eine Bewerbung an. Gibt None zurueck, wenn es fuer dieses
        Objekt schon eine gibt - doppeltes Anschreiben ist der schlimmste Bug,
        den dieses Tool haben kann."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as c:
            try:
                cur = c.execute(
                    """INSERT INTO applications (listing_key, status, created_at)
                       VALUES (?, ?, ?)""",
                    (listing_key, ApplicationStatus.PENDING, now),
                )
            except sqlite3.IntegrityError:
                return None
            app_id = cur.lastrowid
        return self.get_application(app_id)

    def get_application(self, app_id: int) -> Application | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
        return _row_to_app(row) if row else None

    def application_for_listing(self, listing_key: str) -> Application | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM applications WHERE listing_key = ?", (listing_key,)
            ).fetchone()
        return _row_to_app(row) if row else None

    def update_application(self, app: Application) -> None:
        with self._conn() as c:
            c.execute(
                """UPDATE applications SET
                       status=?, decision=?, decided_at=?, message_text=?, message_model=?,
                       sent_via=?, sent_at=?, error=?, messenger_ref=?
                   WHERE id=?""",
                (app.status, app.decision,
                 app.decided_at.isoformat() if app.decided_at else None,
                 app.message_text, app.message_model, app.sent_via,
                 app.sent_at.isoformat() if app.sent_at else None,
                 app.error, app.messenger_ref, app.id),
            )

    def pending_applications(self) -> list[Application]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM applications WHERE status = ? ORDER BY created_at",
                (ApplicationStatus.PENDING,),
            ).fetchall()
        return [_row_to_app(r) for r in rows]

    def applications(self, limit: int = 100) -> list[Application]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM applications ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row_to_app(r) for r in rows]


def _row_to_app(row: sqlite3.Row) -> Application:
    d = dict(row)
    for f in ("decided_at", "sent_at", "created_at"):
        if d.get(f):
            d[f] = datetime.fromisoformat(d[f])
    return Application.model_validate(d)

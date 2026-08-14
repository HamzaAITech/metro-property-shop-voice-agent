import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "leads.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
            call_id TEXT PRIMARY KEY,
            customer_name TEXT,
            phone_number TEXT,
            requirement_summary TEXT,
            visit_preference TEXT,
            language TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return conn


def save_lead(call_id: str, lead: dict) -> None:
    """Insert or update a lead, keyed by call_id — safe to call more than once per call."""
    conn = _get_conn()
    with conn:
        conn.execute(
            """
            INSERT INTO leads
                (call_id, customer_name, phone_number, requirement_summary, visit_preference, language, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(call_id) DO UPDATE SET
                customer_name = excluded.customer_name,
                phone_number = excluded.phone_number,
                requirement_summary = excluded.requirement_summary,
                visit_preference = excluded.visit_preference,
                language = excluded.language,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                call_id,
                lead.get("customer_name"),
                lead.get("phone_number"),
                lead.get("requirement_summary"),
                lead.get("visit_preference", ""),
                lead.get("language"),
            ),
        )
    conn.close()


def list_leads() -> list[dict]:
    conn = _get_conn()
    cur = conn.execute(
        """
        SELECT call_id, customer_name, phone_number, requirement_summary,
               visit_preference, language, updated_at
        FROM leads ORDER BY updated_at DESC
        """
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    conn.close()
    return rows

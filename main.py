import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from extractor import WEEKDAYS, clean_lines, keyword_extract, llm_extract

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "memory.db"
MAX_CHARS = 200_000          # reject absurdly large pastes
MAX_LINES = 5_000

app = FastAPI(title="MemoryLayer")

@contextmanager
def db():
    """Connection that commits on success, rolls back on error and always closes."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _fix_legacy_deadline(value, created_at):
    """Old rows stored raw words like 'friday'. Turn them into YYYY-MM-DD, or None."""
    if not value or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    try:
        base = datetime.strptime((created_at or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    v = value.strip().lower()
    if v in ("today", "tonight", "eod"):
        return base.isoformat()
    if v == "tomorrow":
        return (base + timedelta(days=1)).isoformat()
    if v in WEEKDAYS:
        return (base + timedelta(days=(WEEKDAYS.index(v) - base.weekday()) % 7 or 7)).isoformat()
    return None


def setup_database():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                owner TEXT,
                deadline TEXT,
                source_text TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # upgrade databases created by older versions
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(memories)")]
        for col in ("group_name", "sender"):
            if col not in cols:
                conn.execute(f"ALTER TABLE memories ADD COLUMN {col} TEXT")
        conn.execute("UPDATE memories SET group_name='Ungrouped' WHERE group_name IS NULL OR group_name=''")

        for r in conn.execute("SELECT id, deadline, created_at FROM memories").fetchall():
            fixed = _fix_legacy_deadline(r["deadline"], r["created_at"])
            if fixed != r["deadline"]:
                conn.execute("UPDATE memories SET deadline=? WHERE id=?", (fixed, r["id"]))

        # remove duplicates left by the old, weaker check, then enforce uniqueness in the DB
        conn.execute("""
            DELETE FROM memories WHERE id NOT IN (
                SELECT MIN(id) FROM memories
                GROUP BY platform, kind, group_name, COALESCE(sender, ''), source_text)
        """)
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_memory
            ON memories (platform, kind, group_name, COALESCE(sender, ''), source_text)
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS ix_memory_group ON memories (group_name, id)")


setup_database()


class ConversationInput(BaseModel):
    platform: str
    conversation: str
    group: Optional[str] = None     
    today: Optional[str] = None     


def _parse_today(value):
    if not value:
        return None
    try:
        d = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None
    return d if abs((d - date.today()).days) <= 2 else None  


@app.post("/api/process")
def process_conversation(data: ConversationInput):
    platform = data.platform.lower()
    if platform != "whatsapp":
        raise HTTPException(status_code=400, detail="Unsupported platform")
    if len(data.conversation) > MAX_CHARS:
        raise HTTPException(status_code=413, detail=f"Conversation too long (max {MAX_CHARS:,} characters)")

    group = " ".join((data.group or "").split())[:60] or "Ungrouped"
    lines = clean_lines(data.conversation)
    if not lines:
        raise HTTPException(status_code=400, detail="Conversation is empty")
    if len(lines) > MAX_LINES:
        raise HTTPException(status_code=413, detail=f"Too many messages (max {MAX_LINES:,})")

    today = _parse_today(data.today)
    method, reason = "llm", None
    try:
        extracted = llm_extract(lines, today=today)
    except Exception as e:  
        reason = str(e)[:200]
        print(f"[MemoryLayer] LLM extraction failed ({reason}); using keyword fallback")
        method = "keyword-fallback"
        extracted = keyword_extract(lines, today=today)

    new = 0
    with db() as conn:
        for m in extracted:
            m["platform"] = platform
            m["group_name"] = group
            cur = conn.execute(
                """INSERT OR IGNORE INTO memories
                   (platform, kind, title, owner, deadline, source_text, group_name, sender)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (platform, m["kind"], m["title"], m["owner"], m["deadline"],
                 m["source_text"], group, m["sender"]),
            )
            m["is_new"] = cur.rowcount == 1
            new += cur.rowcount

    return {
        "message": "Conversation processed successfully",
        "method": method,
        "fallback_reason": reason,
        "count": len(extracted),   
        "new": new,               
        "memories": extracted,
    }


@app.get("/api/memories")
def get_memories(group: Optional[str] = None,
                 kind: Optional[str] = Query(None, pattern="^(Decision|Task)$"),
                 limit: int = Query(1000, ge=1, le=5000),
                 offset: int = Query(0, ge=0)):
    sql, args = "SELECT * FROM memories WHERE 1=1", []
    if group:
        sql += " AND group_name=?"; args.append(group)
    if kind:
        sql += " AND kind=?"; args.append(kind)
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    with db() as conn:
        return [dict(r) for r in conn.execute(sql, (*args, limit, offset)).fetchall()]


@app.delete("/api/memories")
def clear_memories(group: Optional[str] = None, all: bool = False):
    """Delete every memory of one chat (?group=NAME) or everything (?all=true)."""
    if not group and not all:
        raise HTTPException(status_code=400, detail="Pass group=NAME or all=true")
    with db() as conn:
        if group:
            n = conn.execute("DELETE FROM memories WHERE group_name=?", (group,)).rowcount
        else:
            n = conn.execute("DELETE FROM memories").rowcount
    return {"deleted": n}


@app.delete("/api/memories/{memory_id}")
def delete_memory(memory_id: int):
    with db() as conn:
        if conn.execute("DELETE FROM memories WHERE id=?", (memory_id,)).rowcount == 0:
            raise HTTPException(status_code=404, detail="Memory not found")
    return {"deleted": memory_id}


app.mount("/", StaticFiles(directory=BASE_DIR / "static", html=True), name="static")

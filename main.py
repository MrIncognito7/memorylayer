
from pathlib import Path
import sqlite3
import re

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "memory.db"

app = FastAPI(title="MemoryLayer")


# DATABASE CONNECTION
def get_connection():
    return sqlite3.connect(DB_PATH)


# CREATE DATABASE TABLE
def setup_database():
    with get_connection() as conn:
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


setup_database()


# INPUT MODEL
class ConversationInput(BaseModel):
    platform: str
    conversation: str


# KEYWORDS FOR EXTRACTION
DECISION_WORDS = [
    "let's use",
    "lets use",
    "agreed",
    "final decision",
    "we decided",
    "decided to",
    "we will go with"
]

TASK_WORDS = [
    "i'll",
    "i will",
    "will handle",
    "please complete",
    "please handle",
    "need to",
    "can you"
]

DAYS = (
    "monday|tuesday|wednesday|thursday|"
    "friday|saturday|sunday|today|tomorrow"
)


# EXTRACT INFORMATION FROM A MESSAGE
def extract_memory(speaker, message, platform):
    text = message.lower()

    kind = None

    if any(word in text for word in DECISION_WORDS):
        kind = "Decision"

    elif any(word in text for word in TASK_WORDS):
        kind = "Task"

    if not kind:
        return None

    # DETECT DEADLINES
    deadline_match = re.search(
        rf"\b(?:by|before|on)\s+({DAYS})\b",
        text
    )

    deadline = (
        deadline_match.group(1)
        if deadline_match
        else None
    )

    # DETECT OWNER
    owner = None

    if re.search(r"\b(i'll|i will)\b", text):
        owner = speaker

    return {
        "platform": platform,
        "kind": kind,
        "title": message,
        "owner": owner,
        "deadline": deadline,
        "source_text": message
    }


# API: PROCESS CONVERSATION
@app.post("/api/process")
def process_conversation(data: ConversationInput):

    platform = data.platform.lower()

    if platform not in ["whatsapp", "instagram"]:
        return {"error": "Unsupported platform"}

    lines = [
        line.strip()
        for line in data.conversation.splitlines()
        if line.strip()
    ]

    extracted = []

    with get_connection() as conn:

        for line in lines:

            # DETECT SPEAKER AND MESSAGE
            match = re.match(
                r"^([^:]{1,40}):\s*(.*)$",
                line
            )

            if match:
                speaker = match.group(1).strip()
                message = match.group(2).strip()

            else:
                speaker = "Unknown"
                message = line

            memory = extract_memory(
                speaker,
                message,
                platform
            )

            if memory:

                conn.execute("""
                    INSERT INTO memories
                    (platform, kind, title, owner, deadline, source_text)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    memory["platform"],
                    memory["kind"],
                    memory["title"],
                    memory["owner"],
                    memory["deadline"],
                    memory["source_text"]
                ))

                extracted.append(memory)

    return {
        "message": "Conversation processed successfully",
        "count": len(extracted),
        "memories": extracted
    }


# API: GET ALL MEMORIES
@app.get("/api/memories")
def get_memories():

    with get_connection() as conn:

        conn.row_factory = sqlite3.Row

        rows = conn.execute("""
            SELECT * FROM memories
            ORDER BY id DESC
        """).fetchall()

    return [dict(row) for row in rows]


# SERVE FRONTEND
app.mount(
    "/",
    StaticFiles(
        directory=BASE_DIR / "static",
        html=True
    ),
    name="static"
)

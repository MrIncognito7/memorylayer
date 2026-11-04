"""
MemoryLayer extraction logic (no web framework, no database).

Used by main.py (the API) and try.py (standalone test), so there is one
prompt and one set of rules.

  clean_lines(text)           -> list of "Speaker: message" lines
  llm_extract(lines)          -> memories via Groq (raises on any failure)
  keyword_extract(lines)      -> memories via simple rules (offline fallback)

Every memory is a dict:
  kind         "Decision" | "Task"
  title        short summary
  sender       who wrote the message (taken from the transcript, not guessed)
  owner        who is responsible, or None
  deadline     "YYYY-MM-DD", or None
  source_text  the original message (without the "Speaker:" prefix)
"""
import difflib
import json
import os
import re
from datetime import date, datetime, timedelta

GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
CHUNK_LINES = 80      # lines per LLM call
CHUNK_OVERLAP = 5     # shared lines between chunks so replies keep context


# ------------------------------------------------------------ PARSING
# Matches WhatsApp prefixes like "12/03/24, 10:15 - " or "[12/03/24, 10:15:30 AM] ".
# \s also covers the narrow no-break space newer exports put before AM/PM.
TIMESTAMP_RE = re.compile(
    r"^\[?\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4},?\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:[APap]\.?[Mm]\.?)?\]?\s*[-\u2013]?\s*"
)
SPEAKER_RE = re.compile(r"^([^:]{1,40}):\s*(.*)$")
INVISIBLE_RE = re.compile(r"[\u200e\u200f\u202a-\u202e\ufeff]")
SKIP_MESSAGE_RE = re.compile(
    r"^(<media omitted>|<attached:.*>|image omitted|video omitted|audio omitted|sticker omitted|"
    r"gif omitted|document omitted|this message was deleted|you deleted this message|"
    r"null|missed (voice|video) call)$",
    re.I,
)
MAX_SPEAKER_WORDS = 5


def parse_line(line):
    """'Sam: hi' -> ('Sam', 'hi').  Lines without a speaker -> (None, line)."""
    m = SPEAKER_RE.match(line)
    if not m:
        return None, line
    speaker, message = m.group(1).strip(), m.group(2).strip()
    # "Meet at 5:30" is not a speaker called "Meet at 5"; neither is a sentence ending in ":"
    if (not speaker or re.search(r"[?!.,;]", speaker) or len(speaker.split()) > MAX_SPEAKER_WORDS
            or (speaker[-1:].isdigit() and message[:1].isdigit())):
        return None, line
    return speaker, message


def parse_chat(text):
    """Raw chat text -> list of (speaker_or_None, message).

    Handles WhatsApp exports (Android and iOS formats, 12/24-hour clocks) and
    plain pasted "Speaker: message" text. In an export, a line without a
    timestamp continues the previous message, so multi-line messages stay whole,
    and system lines (no speaker) are dropped.
    """
    raw = [INVISIBLE_RE.sub("", ln).strip() for ln in text.splitlines()]
    raw = [ln for ln in raw if ln]
    is_export = sum(1 for ln in raw if TIMESTAMP_RE.match(ln)) >= max(1, len(raw) // 3)

    messages = []   # [speaker, message]
    for ln in raw:
        ts = TIMESTAMP_RE.match(ln)
        if is_export and not ts:
            if messages:
                messages[-1][1] += " " + ln          # continuation line
            continue
        body = TIMESTAMP_RE.sub("", ln, count=1).strip() if ts else ln
        speaker, message = parse_line(body)
        if ts and speaker is None:
            continue                                   # system notice in an export
        messages.append([speaker, message])

    out = []
    for speaker, message in messages:
        message = message.strip()
        if message and not SKIP_MESSAGE_RE.match(message):
            out.append((speaker, message))
    return out


def clean_lines(text):
    """Raw chat -> list of 'Speaker: message' lines (one per message)."""
    return [f"{sp}: {msg}" if sp else msg for sp, msg in parse_chat(text)]


# ------------------------------------------------------------- PROMPT
SYSTEM_PROMPT = """You analyse chat transcripts and extract DECISIONS and TASKS.

INPUT
Each line is "Speaker: message". The speaker is the person who wrote that message. "You" is the person using the app.

OUTPUT
Return ONLY a JSON object (no prose, no markdown) of exactly this shape:
{"memories": [
  {"kind": "Decision" or "Task",
   "title": "short clear summary",
   "sender": "who wrote source_text",
   "owner": "person responsible, or null",
   "deadline": "YYYY-MM-DD or null",
   "source_text": "the message, copied exactly"}
]}
If nothing qualifies, return {"memories": []}.

FIELD RULES
- source_text: copy ONE message exactly as written, without the "Speaker:" prefix. It must be the message that actually states the decision or task. If a short reply such as "agreed", "sure" or "ok" confirms an earlier proposal, use the PROPOSAL message as source_text, not the reply.
- sender: the speaker who wrote source_text, spelled exactly as in the transcript.
- owner: the person responsible for doing it.
    "I'll do X" -> the owner is the sender.
    "Can you do X, Rahul?" or "Rahul, please do X" -> the owner is Rahul; the sender is whoever asked.
    Use null when nobody is clearly responsible. For Decisions the owner is normally null.
- deadline: resolve it using today's date (given below).
    "tomorrow" = today + 1 day. "today", "tonight", "EOD" = today.
    A weekday name means the NEXT upcoming such day (if today is that weekday, use the same weekday next week).
    "the 20th" = the next 20th that is not in the past. A date without a year = its next occurrence.
    Ignore clock times. Vague phrases ("soon", "next week", "ASAP") -> null. Never invent a deadline.
- title: under 12 words, self-contained and in English, e.g. "Set up the Postgres server", never "I'll do it". Names stay as written.

WHAT COUNTS
- Decision: the group chose or fixed something ("let's go with Postgres", "we decided to launch on the 20th", "final decision: React").
- Task: someone committed to doing something ("I'll send the notes"), or someone was clearly asked to do something ("please finish the slides before Tuesday", "can you share the docs?").

IGNORE
- Small talk, jokes, greetings, reactions (lol, ok, thanks, emoji).
- Questions that commit nobody ("which database are we using?").
- Ideas nobody accepted ("maybe we could...", "what if...", "I think X").
- Anything rejected, retracted or cancelled ("I didn't agree", "scratch that", "never mind").
- Work reported as already finished ("done", "I already sent it").
- System lines ("Messages and calls are end-to-end encrypted", "<Media omitted>", "joined using this group's invite link").
Never output the same item twice. If something was changed later, output only the latest version. When unsure, leave it out.

LANGUAGE
Transcripts may mix languages (for example Hinglish). Understand them, write titles in English, and keep source_text exactly as written.

EXAMPLE (in this example today is Thursday 2026-03-12)
Transcript:
Sam: morning team, which database are we using?
Priya: I think Postgres, SQLite won't scale
Sam: ok let's go with Postgres
Priya: agreed
Rahul: I'll set up the server by Monday
Sam: can you share the API docs with Priya tomorrow, Rahul?
Rahul: sure
Priya: lol this weather
Output:
{"memories": [
  {"kind": "Decision", "title": "Use Postgres as the database", "sender": "Sam", "owner": null, "deadline": null, "source_text": "ok let's go with Postgres"},
  {"kind": "Task", "title": "Set up the server", "sender": "Rahul", "owner": "Rahul", "deadline": "2026-03-16", "source_text": "I'll set up the server by Monday"},
  {"kind": "Task", "title": "Share the API docs with Priya", "sender": "Sam", "owner": "Rahul", "deadline": "2026-03-13", "source_text": "can you share the API docs with Priya tomorrow, Rahul?"}
]}

TODAY
Today is __WEEKDAY__ __TODAY__.
"""


def build_prompt(today=None):
    today = today or date.today()
    return (
        SYSTEM_PROMPT
        .replace("__TODAY__", today.isoformat())
        .replace("__WEEKDAY__", today.strftime("%A"))
    )


# -------------------------------------------------- RESULT CLEAN-UP
def _null(value):
    if value is None:
        return None
    value = str(value).strip()
    return None if value.lower() in ("", "null", "none", "n/a", "unknown") else value


def _valid_date(value):
    value = _null(value)
    if not value:
        return None
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return value
    except ValueError:
        return None


def _norm(text):
    return " ".join(re.sub(r"[^\w\s]", "", text.lower()).split())


def _build_index(lines):
    index = []
    for line in lines:
        speaker, message = parse_line(line)
        if message:
            index.append((speaker, message, _norm(message)))
    return index


def _find_line(source, sender_hint, index):
    """Find the transcript line a model-returned source_text came from.
    Returns (speaker, message) or None. Uses the hint to break ties."""
    src = source.strip()
    speakers = {sp for sp, _, _ in index if sp}
    m = SPEAKER_RE.match(src)
    if m and m.group(1).strip() in speakers:        # model kept the "Sam: " prefix
        src = m.group(2).strip()
    n = _norm(src)
    if not n:
        return None

    def pick(cands):
        if not cands:
            return None
        if sender_hint:
            for sp, msg, _ in cands:
                if sp and sp.lower() == sender_hint.lower():
                    return sp, msg
        return cands[0][0], cands[0][1]

    exact = [e for e in index if e[2] == n]
    if exact:
        return pick(exact)
    if len(n) >= 8:
        contains = [e for e in index if len(e[2]) >= 8 and (n in e[2] or e[2] in n)]
        if contains:
            return pick(contains)
    close = difflib.get_close_matches(n, [e[2] for e in index], n=1, cutoff=0.75)
    if close:
        return pick([e for e in index if e[2] == close[0]])
    return None


def _clean_item(item, index):
    kind = str(item.get("kind", "")).strip().capitalize()
    if kind not in ("Decision", "Task"):
        return None
    source = _null(item.get("source_text")) or _null(item.get("title"))
    if not source:
        return None

    hint = _null(item.get("sender"))
    speakers = {sp for sp, _, _ in index if sp}
    match = _find_line(source, hint, index)
    if match:
        sender, source = match                      # the transcript is the authority
    else:
        if speakers:
            return None                              # matches nothing in the chat: invented by the model
        sender = None

    return {
        "kind": kind,
        "title": _null(item.get("title")) or source,
        "sender": sender,
        "owner": _null(item.get("owner")),
        "deadline": _valid_date(item.get("deadline")),
        "source_text": source,
    }


# ---------------------------------------------------- LLM EXTRACTION
def _ask_groq(client, system, chunk):
    """One chunk -> list of raw items. Retries once on malformed output only."""
    last = None
    for _ in range(2):
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": "\n".join(chunk)},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        try:
            data = json.loads(resp.choices[0].message.content)
            items = data if isinstance(data, list) else data.get("memories", [])
            return [i for i in items if isinstance(i, dict)]
        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            last = e
    raise ValueError(f"model returned invalid JSON: {last}")


def llm_extract(lines, today=None):
    """Extract memories with Groq. Raises on any failure (caller falls back)."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set")

    from groq import Groq  # imported lazily so the app still runs without it

    client = Groq(api_key=api_key)
    system = build_prompt(today)
    index = _build_index(lines)

    results = []
    step = max(1, CHUNK_LINES - CHUNK_OVERLAP)
    for start in range(0, len(lines), step):
        chunk = lines[start:start + CHUNK_LINES]
        for item in _ask_groq(client, system, chunk):
            cleaned = _clean_item(item, index)
            if cleaned:
                results.append(cleaned)
        if start + CHUNK_LINES >= len(lines):
            break

    # chunks overlap, so drop exact repeats
    seen, unique = set(), []
    for r in results:
        key = (r["kind"], r["source_text"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


# ------------------------------------------------- KEYWORD FALLBACK
DECISION_RE = re.compile(
    r"\b(let'?s (?:use|go with|do|pick|choose|stick (?:with|to))|we(?:'ll| will) go with|"
    r"final decision|we decided|(?:i|we) decided to|decided to|it'?s decided|going with)\b", re.I)
CONFIRM_RE = re.compile(
    r"^(agreed|i agree|sounds good|sure|ok(?:ay)?|done deal|fine by me|works for me|deal)\b[\s.!]*$", re.I)
TASK_RE = re.compile(
    r"\b(i'll|i will|i can take|i'm going to|will handle|will do|please (?:complete|handle|send|share|finish|update|review|prepare)|"
    r"need(?:s)? to be (?:done|completed|finished)|(?:needs?|has|have) to be (?:done|completed|finished)|"
    r"can you|could you|please)\b", re.I)
SELF_TASK_RE = re.compile(r"\b(i'll|i will|i can take|i'm going to)\b", re.I)
NEGATION_RE = re.compile(
    r"\b(didn'?t|did not|don'?t|do not|not agree|never ?mind|scratch that|cancel(?:led)?|"
    r"already (?:done|sent|finished)|no longer|won'?t|can'?t)\b", re.I)
IDEA_RE = re.compile(r"\b(maybe|what if|i think|perhaps|should we|how about|if we)\b", re.I)
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DAYS = "|".join(WEEKDAYS) + "|today|tonight|tomorrow|eod"
EXPLICIT_DEADLINE_RE = re.compile(rf"\b(?:by|before|on|till|until)\s+({DAYS})\b|\b(tomorrow|tonight|eod)\b", re.I)


def resolve_day(word, today=None):
    """'friday' -> next upcoming Friday as YYYY-MM-DD; 'tomorrow' -> today + 1."""
    today = today or date.today()
    word = word.lower()
    if word in ("today", "tonight", "eod"):
        return today.isoformat()
    if word == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    ahead = (WEEKDAYS.index(word) - today.weekday()) % 7 or 7
    return (today + timedelta(days=ahead)).isoformat()


def keyword_extract(lines, today=None):
    """Crude offline extractor. A bare "agreed" is ignored (the proposal it
    confirms is saved on its own), as are questions-as-ideas and retractions."""
    results, seen = [], set()
    for line in lines:
        speaker, message = parse_line(line)
        text = message.strip()

        kind, src_speaker, src_text = None, speaker, text
        if NEGATION_RE.search(text) or IDEA_RE.search(text):
            pass
        elif CONFIRM_RE.match(text):
            pass                                        # a bare "agreed" says nothing on its own; the proposal is saved
        elif DECISION_RE.search(text):
            kind = "Decision"
        elif TASK_RE.search(text):
            kind = "Task"
        if not kind:
            continue

        key = (kind, src_text)
        if key in seen:
            continue
        seen.add(key)
        d = EXPLICIT_DEADLINE_RE.search(text.lower())
        word = (d.group(1) or d.group(2)) if d else None
        owner = src_speaker if src_speaker and SELF_TASK_RE.search(text) and kind == "Task" else None
        results.append({
            "kind": kind,
            "title": src_text[:80],
            "sender": src_speaker,
            "owner": owner,
            "deadline": resolve_day(word, today) if word else None,
            "source_text": src_text,
        })
    return results

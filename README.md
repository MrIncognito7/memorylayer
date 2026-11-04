# MemoryLayer

Paste a WhatsApp chat and MemoryLayer pulls out the *decisions* and *tasks*: who said it, who owns it, and the deadline. Everything is saved and organised by chat.

The app has two views you can flip between with the small toggle in the top-right corner:

- *WhatsApp*: a full-screen, dark-mode WhatsApp-style chat clone with sample chats you can type into.
- *MemoryLayer*: the prototype, where you paste or import a chat, process it, and browse the saved memories.

## How it works

1. WhatsApp timestamps are stripped, so lines become Name: message. Multi-line messages, media placeholders and system notices in exports are handled.
2. The chat is sent to an LLM on Groq (free tier) with a detailed prompt: definitions, ownership rules, date rules, things to ignore, and a worked example. It returns structured JSON.
3. *The sender is taken from the chat itself.* The model only points at a message. The app finds that message in the transcript and uses the real speaker, so a wrong or invented name from the model never reaches the database. Items that match nothing in the chat are dropped, and invalid dates are discarded.
4. If the LLM is unavailable (no key, no network, rate limit), a keyword extractor takes over. The status line in the UI says which one was used.
5. Results are saved in SQLite (memory.db, created on first run), grouped by chat name. The same message is never saved twice within a chat.

## Run it

Requires Python 3.10 or newer.

bash
pip install -r requirements.txt

# free key from https://console.groq.com
export GROQ_API_KEY=your_key_here          # Windows PowerShell: $env:GROQ_API_KEY="your_key_here"

uvicorn main:app --reload


Open http://127.0.0.1:8000

- Set the key in the same terminal that starts uvicorn. Never put it in code or commit it.
- Optional: GROQ_MODEL overrides the model (default openai/gpt-oss-120b).
- Without a key the app still works, using the keyword fallback.
- Open the app through the server URL above. If you open index.html directly from disk, there is no backend and the page runs in a browser-only demo mode (results are not saved).

## Using the app

*WhatsApp view*
- Pick a chat from the list, read it, and type messages in the box at the bottom. Messages live only in the page and are lost on refresh.

*MemoryLayer view*
1. Get a conversation into the box in one of three ways:
   - paste it,
   - click *Use current WhatsApp chat* to load the chat you had open in the WhatsApp view,
   - click *Import .txt* to load a WhatsApp export file.
2. The *Chat name* field is filled in automatically by the last two options. You can also type one.
3. Click *Process conversation*. The status line reads Method: AI extraction or keyword fallback.

Reading the results:
- Each memory card shows its type (*Decision* or *Task*), who sent the message, the owner, and the deadline.
- *Extracted memories* shows the latest run. Faded cards were already saved earlier.
- *All saved memories* is grouped by chat. Each group collapses and shows its decision and task counts. Memories without a chat name go under Ungrouped.
- Filter by Decision or Task with the chips.
- Delete one memory with ✕, a whole chat with *Clear chat* on its group header, or everything with *Clear all*. Each asks for confirmation.

## API

| Method | Path | Body / query | Returns |
|---|---|---|---|
| POST | /api/process | {"platform": "whatsapp", "conversation": "...", "group": "Project Team"} (group optional) | method (llm or keyword-fallback), count (found), new (newly saved), memories |
| GET | /api/memories | query: group, kind (Decision/Task), limit, offset | saved memories, newest first |
| DELETE | /api/memories | query: group=NAME or all=true | {"deleted": count}; 400 if neither is given |
| DELETE | /api/memories/{id} | none | {"deleted": id} or 404 |

Each memory has: kind, title, sender, owner, deadline (YYYY-MM-DD), source_text, group_name, platform.

- Optional today (YYYY-MM-DD) in the process request lets the browser pass its local date so "tomorrow" is right in any timezone.
- Responses include fallback_reason when the keyword fallback ran.
- Errors: 400 unsupported platform or empty conversation, 413 over 200,000 characters or 5,000 messages.

## Project layout


main.py            FastAPI backend and SQLite storage
extractor.py       the Groq prompt, sender matching, validation, keyword fallback
requirements.txt   dependencies
static/
  index.html       both views (WhatsApp and MemoryLayer)
  script.js        chat clone, toggle, processing, saved-memory UI
  style.css        dark WhatsApp-green theme
  chat-bg.png      chat background used in both views
memory.db          created on first run (git-ignored)


The prompt lives in extractor.py (SYSTEM_PROMPT). Edit it there to tune results.

## Privacy

With a Groq key set, pasted chats are sent to Groq's API for extraction. Without a key, extraction is keyword-based and nothing leaves your machine. memory.db holds your chat content, so it is git-ignored. Don't commit it.

## Upgrading an existing database

Older memory.db files are upgraded automatically on startup: missing columns are added, duplicates removed, and word deadlines like friday converted to real dates. To start fresh, delete memory.db and restart the server.

## Known limits

- WhatsApp only. The API rejects other platforms.
- The keyword fallback is crude: it ignores bare replies like "agreed" and saves the proposal instead, but misses anything phrased unusually.
- Multi-line messages are supported for WhatsApp exports (lines without a timestamp continue the previous message). In plain pasted text each line is one message.
- The WhatsApp view is a mock: chats are sample data and nothing you type there is stored.
- No login: anyone who can reach the server sees all memories. Run it locally.
- Extraction quality depends on the model. A larger model on Groq gives better owners and dates.
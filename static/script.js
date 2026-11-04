
function setView(view) {
    document.body.dataset.view = view;
    try { localStorage.setItem("ml_view", view); } catch (_) {}
    if (view === "memorylayer") loadMemories();
}
function toggleView() {
    setView(document.body.dataset.view === "whatsapp" ? "memorylayer" : "whatsapp");
}

/* ===================== WHATSAPP (basic clone) ===================== */
const chats = [
    {
        id: 1, name: "Project Team", members: "Alex, Rahul, You", color: "#128c7e",
        messages: [
            { from: "Alex",  text: "Let's use React for the frontend.", time: "11:55 am" },
            { from: "Rahul", text: "Agreed, final decision then.", time: "11:57 am" },
            { from: "me",    text: "I'll handle the dashboard by Friday.", time: "12:00 pm" },
            { from: "Rahul", text: "Backend needs to be completed by Monday.", time: "12:01 pm" },
            { from: "Alex",  text: "Can you share the API doc tomorrow?", time: "12:03 pm" },
        ]
    },
    {
        id: 2, name: "Office Work", members: "Priya, Sam, You", color: "#a0522d",
        messages: [
            { from: "Priya", text: "We decided to move the review to Wednesday.", time: "Yesterday" },
            { from: "Sam",   text: "I will send the notes today.", time: "Yesterday" },
            { from: "me",    text: "Please complete the slides before Tuesday.", time: "Yesterday" },
        ]
    },
    {
        id: 3, name: "Friends", members: "Mia, Dev, You", color: "#3b6fb6",
        messages: [
            { from: "Mia", text: "Movie on Saturday?", time: "Monday" },
            { from: "Dev", text: "See you tomorrow!", time: "Monday" },
        ]
    },
];
let activeChat = chats[0];

const $ = id => document.getElementById(id);
const initials = n => n.split(/\s+/).map(w => w[0]).join("").slice(0, 2).toUpperCase();
const nowTime = () => new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }).toLowerCase();

function waRenderList() {
    const q = $("waSearch").value.toLowerCase();
    $("waList").innerHTML = "";
    chats.filter(c => c.name.toLowerCase().includes(q)).forEach(c => {
        const last = c.messages[c.messages.length - 1];
        const el = document.createElement("button");
        el.className = "wa-item" + (c === activeChat ? " selected" : "");
        el.onclick = () => { activeChat = c; waRenderList(); waRenderChat(); };
        el.innerHTML = `<div class="wa-avatar" style="background:${c.color}"></div>
            <div class="wa-item-body">
                <div class="top"><strong></strong><small></small></div>
                <p></p>
            </div>`;
        el.querySelector(".wa-avatar").textContent = initials(c.name);
        el.querySelector("strong").textContent = c.name;
        el.querySelector("small").textContent = last ? last.time : "";
        el.querySelector("p").textContent = last ? (last.from === "me" ? "You: " : "") + last.text : "";
        $("waList").appendChild(el);
    });
}
function waFilter() { waRenderList(); }

function waRenderChat() {
    $("waName").textContent = activeChat.name;
    $("waMembers").textContent = activeChat.members;
    $("waAvatar").textContent = initials(activeChat.name);
    $("waAvatar").style.background = activeChat.color;
    const box = $("waMessages");
    box.innerHTML = '<div class="wa-date"><span>Today</span></div>';
    const group = activeChat.members.split(",").length > 2;
    activeChat.messages.forEach(m => {
        const b = document.createElement("div");
        b.className = "wa-bubble " + (m.from === "me" ? "out" : "in");
        if (m.from !== "me" && group) {
            const s = document.createElement("span");
            s.className = "sender"; s.textContent = m.from; b.appendChild(s);
        }
        const t = document.createElement("span"); t.textContent = m.text;
        const tm = document.createElement("time"); tm.textContent = m.time;
        b.append(t, tm);
        box.appendChild(b);
    });
    box.scrollTop = box.scrollHeight;
}

function waSend() {
    const input = $("waInput");
    const text = input.value.trim();
    if (!text) return;
    activeChat.messages.push({ from: "me", text, time: nowTime() });
    input.value = "";
    waRenderChat(); waRenderList();
}
$("waInput").addEventListener("keydown", e => { if (e.key === "Enter") waSend(); });

/* Current WhatsApp chat as "Speaker: message" text */
function currentChatAsText() {
    return activeChat.messages
        .map(m => `${m.from === "me" ? "You" : m.from}: ${m.text}`).join("\n");
}

/* ===================== MEMORYLAYER PROTOTYPE ===================== */
let allMemories = [];
let kindFilter = "all";

function useCurrentChat() {
    $("pasteText").value = currentChatAsText();
    $("groupName").value = activeChat.name;
    $("platform").value = "whatsapp";
    setStatus(`Loaded "${activeChat.name}" from the WhatsApp view. Hit Process.`);
}
function clearPaste() { $("pasteText").value = ""; setStatus(""); }
function setStatus(msg, type = "") {
    const s = $("status");
    s.textContent = msg;
    s.className = "status " + type;
}

/* Turn exported WhatsApp lines into "Speaker: message" (same as backend expects) */
function normaliseChat(text) {
    return text.split(/\r?\n/).map(line => {
        const t = line.trim();
        if (!t) return "";
        const m = t.match(/^\[?\d{1,2}[/-]\d{1,2}[/-]\d{2,4},?\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s?[ap]m)?\]?\s+-?\s*([^:]+):\s?(.*)$/i);
        return m ? `${m[1].trim()}: ${m[2]}` : t;
    }).filter(Boolean).join("\n");
}

const WEEKDAYS = ["sunday","monday","tuesday","wednesday","thursday","friday","saturday"];
const isoDate = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
function resolveDay(word) {
    const d = new Date();
    word = word.toLowerCase();
    if (word === "tomorrow") d.setDate(d.getDate() + 1);
    else if (WEEKDAYS.includes(word)) d.setDate(d.getDate() + ((WEEKDAYS.indexOf(word) - d.getDay() + 7) % 7 || 7));
    return isoDate(d);
}

/* Offline fallback: mirrors main.py so the prototype still demos without a backend */
function localExtract(conversation, platform) {
    const DECISION = ["let's use", "lets use", "agreed", "final decision", "we decided", "decided to", "we will go with"];
    const TASK = ["i'll", "i will", "will handle", "please complete", "please handle", "need to", "can you"];
    const DAYS = "monday|tuesday|wednesday|thursday|friday|saturday|sunday|today|tomorrow";
    const NEG = /\b(didn'?t|did not|don'?t|not agree|never ?mind|scratch that|maybe|what if|i think)\b/;
    const out = [];
    conversation.split("\n").forEach(line => {
        const m = line.match(/^([^:]{1,40}):\s*(.*)$/);
        const speaker = m ? m[1].trim() : null;
        const message = m ? m[2].trim() : line;
        const lower = message.toLowerCase();
        let kind = null;
        if (NEG.test(lower) || /^(agreed|sure|ok|okay)[.! ]*$/.test(lower)) return;
        if (DECISION.some(w => lower.includes(w))) kind = "Decision";
        else if (TASK.some(w => lower.includes(w))) kind = "Task";
        if (!kind) return;
        const d = lower.match(new RegExp(`\\b(?:by|before|on)\\s+(${DAYS})\\b`));
        out.push({
            platform, kind, title: message, source_text: message,
            sender: speaker,
            deadline: d ? resolveDay(d[1]) : null,
            owner: speaker && /\b(i'll|i will)\b/.test(lower) ? speaker : null,
        });
    });
    return out;
}

function memCard(mem) {
    const el = document.createElement("article");
    el.className = "mem " + mem.kind.toLowerCase() + (mem.is_new === false ? " seen" : "");
    const head = document.createElement("div");
    head.className = "mem-head";
    const badge = document.createElement("span");
    badge.className = "badge"; badge.textContent = mem.kind;
    const from = document.createElement("small");
    from.className = "sender";
    from.textContent = mem.sender ? "Sent by " + mem.sender : "";
    head.append(badge, from);
    if (mem.id != null) {
        const del = document.createElement("button");
        del.className = "mem-del"; del.type = "button"; del.title = "Delete this memory"; del.textContent = "✕";
        del.onclick = () => deleteMemory(mem.id);
        head.appendChild(del);
    }
    const title = document.createElement("p");
    title.textContent = mem.title;
    const meta = document.createElement("div");
    meta.className = "mem-meta";
    if (mem.owner) { const o = document.createElement("span"); o.textContent = "👤 " + mem.owner; meta.appendChild(o); }
    if (mem.deadline) { const d = document.createElement("span"); d.textContent = "⏰ " + mem.deadline; meta.appendChild(d); }
    el.append(head, title);
    if (meta.children.length) el.appendChild(meta);
    return el;
}

function renderResults(list) {
    const box = $("results");
    box.innerHTML = "";
    $("resultHint").textContent = list.length
        ? `${list.length} ${list.length === 1 ? "memory" : "memories"} found in the latest run.`
        : "No decisions or tasks found in that conversation.";
    list.forEach(m => box.appendChild(memCard(m)));
}

const collapsedGroups = new Set();
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

function renderSaved() {
    const box = $("saved");
    box.innerHTML = "";
    const list = allMemories.filter(m => kindFilter === "all" || m.kind === kindFilter);
    $("savedCount").textContent = allMemories.length;
    $("clearAllBtn").hidden = !allMemories.length;
    if (!list.length) {
        box.innerHTML = '<p class="empty">Nothing here yet. Paste a chat above to create memories.</p>';
        return;
    }

    // group by chat name; groups with the newest memory come first, "Ungrouped" last
    const groups = new Map();
    list.forEach(m => {
        const name = m.group_name || "Ungrouped";
        if (!groups.has(name)) groups.set(name, []);
        groups.get(name).push(m);
    });
    const ordered = [...groups.entries()].sort((a, b) => (a[0] === "Ungrouped") - (b[0] === "Ungrouped"));

    ordered.forEach(([name, items]) => {
        const decisions = items.filter(m => m.kind === "Decision").length;
        const tasks = items.length - decisions;

        const det = document.createElement("details");
        det.className = "group";
        det.open = !collapsedGroups.has(name);
        det.addEventListener("toggle", () => {
            if (det.open) collapsedGroups.delete(name); else collapsedGroups.add(name);
        });

        const sum = document.createElement("summary");
        const nameEl = document.createElement("span");
        nameEl.className = "group-name"; nameEl.textContent = name;
        const meta = document.createElement("span");
        meta.className = "group-meta";
        meta.textContent = [decisions && plural(decisions, "decision"), tasks && plural(tasks, "task")]
            .filter(Boolean).join(" · ");
        const clr = document.createElement("button");
        clr.className = "group-clear"; clr.type = "button"; clr.textContent = "Clear chat";
        clr.title = `Delete all memories from "${name}"`;
        // inside <summary>: stop the click from toggling the group open/closed
        clr.onclick = e => { e.preventDefault(); e.stopPropagation(); clearMemories(name); };
        sum.append(nameEl, meta, clr);

        const grid = document.createElement("div");
        grid.className = "mem-list grid";
        items.forEach(m => grid.appendChild(memCard(m)));

        det.append(sum, grid);
        box.appendChild(det);
    });
}

async function loadMemories() {
    try {
        const r = await fetch("/api/memories");
        if (!r.ok) throw new Error();
        allMemories = await r.json();
    } catch (_) { /* backend offline: keep whatever is in memory */ }
    renderSaved();
}

async function deleteMemory(id) {
    if (!confirm("Delete this memory?")) return;
    try {
        const r = await fetch(`/api/memories/${id}`, { method: "DELETE" });
        if (!r.ok && r.status !== 404) throw new Error();
        allMemories = allMemories.filter(m => m.id !== id);
        renderSaved();
    } catch (_) { setStatus("Could not delete that memory (is the server running?).", "err"); }
}

async function clearMemories(group) {
    const msg = group
        ? `Delete ALL saved memories from "${group}"? This cannot be undone.`
        : "Delete ALL saved memories from every chat? This cannot be undone.";
    if (!confirm(msg)) return;
    try {
        const url = group ? `/api/memories?group=${encodeURIComponent(group)}` : "/api/memories?all=true";
        const r = await fetch(url, { method: "DELETE" });
        if (!r.ok) throw new Error();
        const { deleted } = await r.json();
        allMemories = allMemories.filter(m => group ? (m.group_name || "Ungrouped") !== group : false);
        renderSaved();
        setStatus(`Deleted ${deleted} ${deleted === 1 ? "memory" : "memories"}${group ? ` from "${group}"` : ""}.`, "ok");
    } catch (_) { setStatus("Could not clear memories (is the server running?).", "err"); }
}

async function processChat() {
    const platform = $("platform").value;
    const group = $("groupName").value.trim();
    const text = $("pasteText").value;
    if (!text.trim()) { setStatus("Paste a conversation first.", "err"); return; }

    const btn = $("processBtn");
    btn.disabled = true;
    setStatus("Processing conversation…");

    try {
        let r;
        try {
            r = await fetch("/api/process", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ platform, conversation: text, group, today: isoDate(new Date()) }),
            });
        } catch (_) {
            // Network failure only (server not running): offline demo mode
            const found = localExtract(normaliseChat(text), platform);
            found.forEach(f => { f.group_name = group || "Ungrouped"; });
            renderResults(found);
            allMemories = found.slice().reverse().concat(allMemories);
            renderSaved();
            setStatus(`Backend not reachable, ran in demo mode (${found.length} found, not saved to database).`, "warn");
            return;
        }

        if (!r.ok) {
            // The server answered with an error: show it instead of hiding it
            let detail = "";
            try { const j = await r.json(); if (typeof j.detail === "string") detail = j.detail; } catch (_) {}
            setStatus(`Server error (${r.status}): ${detail || "request failed"}`, "err");
            return;
        }

        const data = await r.json();
        renderResults(data.memories);
        const viaAI = data.method === "llm";
        setStatus(
            `Done! ${data.count} found, ${data.new} new saved. Method: ${viaAI ? "AI extraction" : "keyword fallback (" + (data.fallback_reason || "AI unavailable") + ")"}.`,
            viaAI ? "ok" : "warn"
        );
        await loadMemories();
    } finally {
        btn.disabled = false;
    }
}

async function importChat(event) {
    const file = event.target.files[0];
    if (!file) return;
    $("pasteText").value = await file.text();
    $("groupName").value = file.name.replace(/\.txt$/i, "").replace(/^WhatsApp Chat with /i, "").trim();
    $("platform").value = "whatsapp";
    event.target.value = "";
    setStatus(`Imported ${file.name}. Hit Process.`);
}

$("kindFilter").addEventListener("click", e => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    document.querySelectorAll("#kindFilter .chip").forEach(c => c.classList.remove("active"));
    chip.classList.add("active");
    kindFilter = chip.dataset.kind;
    renderSaved();
});

/* ===================== INIT ===================== */
waRenderList();
waRenderChat();
let savedView = "whatsapp";
try { savedView = localStorage.getItem("ml_view") === "memorylayer" ? "memorylayer" : "whatsapp"; } catch (_) {}
setView(savedView);


async function processConversation() {

    const platform =
        document.getElementById("platform").value;

    const conversation =
        document.getElementById("conversation").value;

    const status =
        document.getElementById("status");

    const button =
        document.getElementById("processBtn");


    if (!conversation.trim()) {

        status.textContent =
            "Please paste a conversation first.";

        return;
    }


    button.disabled = true;

    status.textContent =
        "Processing conversation...";


    try {

        const response = await fetch("/api/process", {

            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                platform: platform,
                conversation: conversation
            })

        });


        if (!response.ok) {
            throw new Error("Server returned an error.");
        }


        const data = await response.json();


        status.textContent =
            `Successfully extracted ${data.count} memories.`;


        await loadMemories();


    } catch (error) {

        status.textContent =
            "Could not connect to the backend. Check whether the server is running.";

        console.error(error);

    } finally {

        button.disabled = false;

    }

}


// LOAD MEMORIES FROM DATABASE
async function loadMemories() {

    const response =
        await fetch("/api/memories");

    const memories =
        await response.json();

    const container =
        document.getElementById("memories");


    container.innerHTML = "";


    if (memories.length === 0) {

        container.innerHTML =
            '<p class="empty">No memories extracted yet.</p>';

        return;
    }


    memories.forEach(memory => {

        const card =
            document.createElement("div");

        card.className = "memory-card";


        const heading =
            document.createElement("h3");

        heading.textContent =
            memory.kind.toUpperCase();


        const content =
            document.createElement("p");

        content.textContent =
            memory.title;


        const details =
            document.createElement("small");

        details.textContent =
            `${memory.platform} | Owner: ${memory.owner || "Not confirmed"} | Deadline: ${memory.deadline || "Not detected"}`;


        card.append(
            heading,
            content,
            details
        );

        container.appendChild(card);

    });

}


// LOAD SAVED MEMORIES WHEN PAGE OPENS
loadMemories();

function buildCaseViewer(text) {
    const viewer = document.getElementById("caseViewer");
    const lines = text.split("\n");
    viewer.innerHTML = lines.map((line, i) =>
        `<div class="line" id="line-${i+1}"><span class="line-num">${i+1}</span>${escapeHtml(line)}</div>`
    ).join("");
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

// matches patterns like "Line 9", "Lines 9-10", "【Line 34-36】", etc.
function linkifyCitations(text) {
    return text.replace(/(?:【)?Lines?\s*(\d+)(?:\s*\p{Pd}\s*(?:Lines?\s*)?(\d+))?(?:】)?/giu, (match, start, end) => {
        const citation = end ? `Lines ${start}-${end}` : `Line ${start}`;
        return `<span class="citation-link" onclick="jumpToLine('${citation}')">${match}</span>`;
    });
}

function jumpToLine(citationStr) {
    document.querySelectorAll(".line.highlighted").forEach(el => el.classList.remove("highlighted"));

    // split on commas to handle multiple separate citations like "Lines 10-11, Line 58"
    const groups = citationStr.split(",");
    let firstEl = null;

    groups.forEach(group => {
        const nums = group.match(/\d+/g);
        if (!nums) return;

        const start = parseInt(nums[0]);
        const end = nums[1] ? parseInt(nums[1]) : start;

        for (let i = start; i <= end; i++) {
            const el = document.getElementById(`line-${i}`);
            if (el) {
                el.classList.add("highlighted");
                if (!firstEl) firstEl = el;
            }
        }
    });

    if (firstEl) firstEl.scrollIntoView({ behavior: "smooth", block: "center" });
}

let uploadedFileContents = []; // [{name: "file1.txt", text: "..."}]

async function readFiles(fileList) {
    const contents = [];
    for (const file of fileList) {
        const text = await file.text();
        contents.push({ name: file.name, text: text });
    }
    return contents;
}

async function analyze() {
    const fileInput = document.getElementById("caseFiles");
    if (fileInput.files.length === 0) return;

    document.getElementById("analyzeBtn").disabled = true;
    document.getElementById("loading").style.display = "block";
    document.getElementById("dashboard").innerHTML = "";

    uploadedFileContents = await readFiles(fileInput.files);

    const res = await fetch("/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ files: uploadedFileContents })
    });
    const data = await res.json();

    document.getElementById("loading").style.display = "none";
    document.getElementById("analyzeBtn").disabled = false;

    if (data.error) {
        document.getElementById("dashboard").innerHTML = "<p>Error: " + data.error + "</p>";
        return;
    }

    renderDashboard(data.guidelines);
    renderContradictions(data.contradictions || []);
    buildCaseViewer(data.combined_text);
    document.getElementById("chatSection").style.display = "block";
}

function renderDashboard(guidelines) {
    const dashboard = document.getElementById("dashboard");
    dashboard.innerHTML = "";

    guidelines.forEach((g, i) => {
        const card = document.createElement("div");
        card.className = "card " + g.risk;

        let detailsHtml = "";
        if (g.evidence && g.evidence !== "No relevant information found") {
            detailsHtml += `<div><b>Evidence:</b> ${g.evidence} <span class="citation-link" onclick="jumpToLine('${g.citations}')">(${g.citations})</span></div>`;
        }
        if (g.unclear) {
            detailsHtml += `<div style="margin-top:6px;"><b>Unclear:</b> ${g.unclear}</div>`;
        }
        if (g.followup) {
            detailsHtml += `<div style="margin-top:6px;"><b>Follow-up:</b> ${g.followup}</div>`;
        }
        if (!detailsHtml) detailsHtml = "<div>No relevant information found.</div>";

        card.innerHTML = `
            <div class="card-header expandable" onclick="toggleDetails(${i})">
                <span class="card-title">${g.letter} — ${g.name}</span>
                <span class="badge ${g.risk}">${g.risk}</span>
            </div>
            <div class="details" id="details-${i}">${detailsHtml}</div>
        `;
        dashboard.appendChild(card);
    });
}

function renderContradictions(contradictions) {
    let container = document.getElementById("contradictions");
    if (!container) {
        container = document.createElement("div");
        container.id = "contradictions";
        document.getElementById("dashboard").insertAdjacentElement("beforebegin", container);
    }

    if (contradictions.length === 0) {
        container.innerHTML = "";
        return;
    }

    container.innerHTML = "<h3 style='color:#ea4335;'>⚠ Cross-Source Contradictions</h3>" +
        contradictions.map(c => `
            <div class="card red" style="margin-bottom:10px;">
                <div class="card-header"><span class="card-title">${c.summary}</span></div>
                <div class="card-body">${c.detail} <span class="citation-link" onclick="jumpToLine('${c.citations}')">(${c.citations})</span></div>
            </div>
        `).join("");
}

function toggleDetails(i) {
    document.getElementById(`details-${i}`).classList.toggle("open");
}

let chatHistory = [];

async function askQuestion() {
    const question = document.getElementById("chatQuestion").value;
    const caseText = document.getElementById("caseText").value;
    if (!question.trim()) return;

    const res = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: "case_text=" + encodeURIComponent(caseText) +
              "&question=" + encodeURIComponent(question) +
              "&history=" + encodeURIComponent(JSON.stringify(chatHistory))
    });
    const data = await res.json();

    const answer = data.answer || ("Error: " + data.error);

    // only saving successful answers to history so a failed call doesn't pollute later context
    if (data.answer) {
        chatHistory.push({ question: question, answer: data.answer });
    }

    const historyDiv = document.getElementById("chatHistory");
    historyDiv.innerHTML += `<div class="chat-turn"><div class="chat-q">Q: ${question}</div><div>${linkifyCitations(answer)}</div></div>`;
    document.getElementById("chatQuestion").value = "";
}
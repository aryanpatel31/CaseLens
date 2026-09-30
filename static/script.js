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

let selectedFiles = []; // File objects currently selected

const dropZone = document.getElementById("dropZone");
const fileInput = document.getElementById("caseFiles");
const fileListDiv = document.getElementById("fileList");

dropZone.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", () => {
    addFiles(Array.from(fileInput.files));
});

dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
});

dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("dragover");
});

dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    addFiles(Array.from(e.dataTransfer.files));
});

function addFiles(newFiles) {
    newFiles.forEach(f => {
        if (!selectedFiles.some(existing => existing.name === f.name)) {
            selectedFiles.push(f);
        }
    });
    renderFileList();
}

function removeFile(name) {
    selectedFiles = selectedFiles.filter(f => f.name !== name);
    renderFileList();
}

function renderFileList() {
    fileListDiv.innerHTML = selectedFiles.map(f =>
        `<span class="file-chip">${f.name} <span class="remove-file" onclick="event.stopPropagation(); removeFile('${f.name}')">✕</span></span>`
    ).join("");
}

async function analyze() {
    if (selectedFiles.length === 0) return;

    document.getElementById("analyzeBtn").disabled = true;
    document.getElementById("loading").style.display = "block";
    document.getElementById("dashboard").innerHTML = "";

    const stopAnimation = animateLoadingSteps();

    uploadedFileContents = await readFiles(selectedFiles);

    const res = await fetch("/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ files: uploadedFileContents })
    });
    const data = await res.json();

    stopAnimation();
    document.getElementById("loading").style.display = "none";
    document.getElementById("analyzeBtn").disabled = false;

    if (data.error) {
        document.getElementById("dashboard").innerHTML = "<p>Error: " + data.error + "</p>";
        return;
    }

    renderDashboard(data.guidelines);
    renderContradictions(data.contradictions || []);
    renderVerification(data.verification_flags || []);
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

function renderVerification(flags) {
    let container = document.getElementById("verification");
    if (!container) {
        container = document.createElement("div");
        container.id = "verification";
        document.getElementById("dashboard").insertAdjacentElement("beforebegin", container);
    }

    if (flags.length === 0) {
        container.innerHTML = `<div style="color:#34a853; font-size:13px; margin-bottom:10px;">✓ Verifier agent found no issues with citations or ratings.</div>`;
        return;
    }

    container.innerHTML = "<h3 style='color:#fbbc04;'>⚠ Verifier Flags</h3>" +
        flags.map(f => `<div class="card yellow" style="margin-bottom:8px;"><div class="card-body"><b>Guideline ${f.letter}:</b> ${f.issue}</div></div>`).join("");
}

function toggleDetails(i) {
    document.getElementById(`details-${i}`).classList.toggle("open");
}

let chatHistory = [];

async function askQuestion() {
    const question = document.getElementById("chatQuestion").value;
    if (!question.trim()) return;
    if (uploadedFileContents.length === 0) {
        alert("Please analyze a case first.");
        return;
    }

    const res = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            files: uploadedFileContents,
            question: question,
            history: chatHistory
        })
    });
    const data = await res.json();

    const answer = data.answer || ("Error: " + data.error);

    if (data.answer) {
        chatHistory.push({ question: question, answer: data.answer });
    }

    const historyDiv = document.getElementById("chatHistory");
    historyDiv.innerHTML += `<div class="chat-turn"><div class="chat-q">Q: ${question}</div><div>${linkifyCitations(answer)}</div></div>`;
    document.getElementById("chatQuestion").value = "";
}

function animateLoadingSteps() {
    const steps = ["step-redact", "step-analyst", "step-reconciler", "step-verifier"];
    let current = 0;

    steps.forEach(id => document.getElementById(id).classList.remove("active", "done"));

    function advance() {
        if (current > 0) {
            document.getElementById(steps[current - 1]).classList.remove("active");
            document.getElementById(steps[current - 1]).classList.add("done");
        }
        if (current < steps.length) {
            document.getElementById(steps[current]).classList.add("active");
            current++;
            loadingTimer = setTimeout(advance, current === 1 ? 500 : 13000);
        }
    }
    advance();
    return () => clearTimeout(loadingTimer); // returns a stop function
}
let currentJobId = null;
let statusTimer = null;
let previewTimer = null;

const form = document.getElementById("job-form");
const startBtn = document.getElementById("start-btn");
const stopBtn = document.getElementById("stop-btn");
const progressPanel = document.getElementById("progress-panel");
const statusLine = document.getElementById("status-line");
const errorBanner = document.getElementById("error-banner");
const locationProgress = document.getElementById("location-progress");
const locationCount = document.getElementById("location-count");
const enrichProgress = document.getElementById("enrich-progress");
const enrichCount = document.getElementById("enrich-count");
const matchesCount = document.getElementById("matches-count");
const downloadsBox = document.getElementById("downloads");
const previewBody = document.getElementById("preview-body");

const dlLinks = {
  "leads_filtered.csv": document.getElementById("dl-filtered"),
  "leads.csv": document.getElementById("dl-leads"),
};

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  startBtn.disabled = true;
  startBtn.textContent = "Starting...";

  const payload = {
    search_term: document.getElementById("search_term").value,
    locations: document.getElementById("locations").value,
    radius_miles: document.getElementById("radius_miles").value,
    min_reviews: document.getElementById("min_reviews").value,
    website_filter: document.getElementById("website_filter").value,
  };

  const res = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();

  startBtn.disabled = false;
  startBtn.textContent = "Start search";

  if (!res.ok) {
    alert(data.error || "Failed to start job.");
    return;
  }

  currentJobId = data.job_id;
  progressPanel.classList.remove("hidden");
  errorBanner.classList.add("hidden");
  downloadsBox.classList.add("hidden");
  previewBody.innerHTML = "";
  stopBtn.disabled = false;
  stopBtn.textContent = "Stop";
  startPolling();
});

stopBtn.addEventListener("click", async () => {
  if (!currentJobId) return;
  stopBtn.disabled = true;
  stopBtn.textContent = "Stopping...";
  await fetch(`/api/jobs/${currentJobId}/stop`, { method: "POST" });
});

function startPolling() {
  clearInterval(statusTimer);
  clearInterval(previewTimer);
  pollStatus();
  pollPreview();
  statusTimer = setInterval(pollStatus, 2000);
  previewTimer = setInterval(pollPreview, 5000);
}

async function pollStatus() {
  if (!currentJobId) return;
  const res = await fetch(`/api/jobs/${currentJobId}/status`);
  const s = await res.json();

  statusLine.textContent = s.message || s.phase || "";

  const locTotal = s.location_total || 0;
  const locIndex = s.location_index || 0;
  locationProgress.max = Math.max(locTotal, 1);
  locationProgress.value = locIndex;
  locationCount.textContent = `${locIndex} / ${locTotal}`;

  const enrTotal = s.enrich_total || 0;
  const enrIndex = s.enrich_index || 0;
  enrichProgress.max = Math.max(enrTotal, 1);
  enrichProgress.value = enrIndex;
  enrichCount.textContent = `${enrIndex} / ${enrTotal}`;

  matchesCount.textContent = s.matches_found || 0;

  const files = s.files || [];
  if (files.length > 0) {
    downloadsBox.classList.remove("hidden");
    for (const [name, el] of Object.entries(dlLinks)) {
      if (files.includes(name)) {
        el.href = `/api/jobs/${currentJobId}/download/${name}`;
        el.classList.remove("hidden");
      }
    }
  }

  if (["done", "error", "stopped"].includes(s.phase)) {
    clearInterval(statusTimer);
    clearInterval(previewTimer);
    stopBtn.disabled = true;
    if (s.phase === "error") {
      errorBanner.textContent = "Error: " + (s.error || "unknown error");
      errorBanner.classList.remove("hidden");
    }
    pollPreview();
  }
}

async function pollPreview() {
  if (!currentJobId) return;
  const res = await fetch(`/api/jobs/${currentJobId}/preview`);
  const data = await res.json();
  const rows = data.rows || [];

  previewBody.innerHTML = "";
  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(row.name || "")}</td>
      <td>${escapeHtml(row.search_location || "")}</td>
      <td>${escapeHtml(row.rating || "")}</td>
      <td>${escapeHtml(row.review_count || "")}</td>
      <td>${row.has_website === "True" ? "Yes" : "No"}</td>
      <td>${escapeHtml(row.address || "")}</td>
      <td>${escapeHtml(row.phone || "")}</td>
    `;
    previewBody.appendChild(tr);
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

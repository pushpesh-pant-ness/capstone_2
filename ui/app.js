const state = { currentIncidentId: null, pollHandle: null, incidents: [], filter: "" };

function severityBadgeClass(sev) {
  if (sev === "P1") return "badge-critical";
  if (sev === "P2") return "badge-warning";
  if (sev === "P3") return "badge-info";
  return "badge-neutral";
}

function statusBadgeClass(status) {
  if (["resolved"].includes(status)) return "badge-ok";
  if (["escalated"].includes(status)) return "badge-critical";
  if (["pending_approval", "remediating", "investigating"].includes(status)) return "badge-warning";
  return "badge-neutral";
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function badge(text, cls) {
  return `<span class="badge ${cls}">${escapeHtml(text)}</span>`;
}

function formatStatus(status) {
  return (status ?? "-").replace(/_/g, " ");
}

function formatTime(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function renderIncidentList() {
  const container = document.getElementById("incident-list");
  const term = state.filter.trim().toLowerCase();
  const incidents = state.incidents.filter((incident) => {
    if (!term) return true;
    return (
      (incident.title ?? "").toLowerCase().includes(term) ||
      (incident.service_name ?? "").toLowerCase().includes(term)
    );
  });

  document.getElementById("incident-count").textContent = state.incidents.length;

  if (incidents.length === 0) {
    container.innerHTML = `<div class="list-empty">${
      state.incidents.length === 0 ? "No incidents yet." : "No incidents match your filter."
    }</div>`;
    return;
  }

  container.innerHTML = "";
  for (const incident of incidents) {
    const card = document.createElement("div");
    card.className = "incident-card" + (incident.incident_id === state.currentIncidentId ? " active" : "");
    card.innerHTML = `
      <div class="incident-card-title">${escapeHtml(incident.title)}</div>
      <div class="incident-card-meta">
        <span class="incident-card-service">${escapeHtml(incident.service_name ?? "unknown service")}</span>
        ${badge(incident.severity ?? "-", severityBadgeClass(incident.severity))}
      </div>
      <div class="incident-card-footer">
        ${badge(formatStatus(incident.status), statusBadgeClass(incident.status))}
        <span class="incident-card-time">${formatTime(incident.detected_at)}</span>
      </div>
    `;
    card.addEventListener("click", () => openIncident(incident.incident_id));
    container.appendChild(card);
  }
}

async function loadIncidents() {
  const res = await fetch("/incidents");
  state.incidents = await res.json();
  renderIncidentList();
}

function renderAuditEntry(entry) {
  const el = document.createElement("div");
  el.className = "step";
  const header = document.createElement("div");
  header.className = "step-header";
  header.innerHTML = `<span>${escapeHtml(entry.actor)} — ${escapeHtml(entry.action_type)}</span><span class="step-time">${escapeHtml(formatTime(entry.created_at))}</span>`;
  const body = document.createElement("pre");
  body.className = "code-block";
  body.hidden = true;
  body.textContent = JSON.stringify(entry.payload, null, 2);
  header.addEventListener("click", () => (body.hidden = !body.hidden));
  el.appendChild(header);
  el.appendChild(body);
  return el;
}

async function refreshIncidentDetail(incidentId) {
  const res = await fetch(`/incidents/${incidentId}`);
  const incident = await res.json();
  document.getElementById("detail-title").textContent = `${incident.title}`;
  document.getElementById("detail-meta").innerHTML = `
    ${badge(incident.severity ?? "-", severityBadgeClass(incident.severity))}
    ${badge(formatStatus(incident.status), statusBadgeClass(incident.status))}
    <span class="incident-card-time">${escapeHtml(incident.service_name ?? "")} · detected ${escapeHtml(formatTime(incident.detected_at))}</span>
  `;
  document.getElementById("evidence-text").textContent = JSON.stringify(incident.evidence, null, 2);
  document.getElementById("rca-text").textContent =
    incident.root_cause_summary
      ? `${incident.root_cause_summary} (confidence: ${incident.confidence_score ?? "-"})`
      : "Root cause analysis pending…";

  const similarList = document.getElementById("similar-list");
  similarList.innerHTML = "";
  for (const s of incident.similar_incident_ids ?? []) {
    const li = document.createElement("li");
    li.textContent = s;
    similarList.appendChild(li);
  }

  const approvalPanel = document.getElementById("approval-panel");
  const outcomePanel = document.getElementById("outcome-panel");

  if (incident.status === "pending_approval") {
    approvalPanel.hidden = false;
    document.getElementById("plan-text").textContent = JSON.stringify(incident.remediation_plan, null, 2);
  } else {
    approvalPanel.hidden = true;
  }

  if (["resolved", "escalated"].includes(incident.status)) {
    outcomePanel.hidden = false;
    const reasonLine = incident.escalation_reason ? `Escalation reason: ${incident.escalation_reason}\n` : "";
    document.getElementById("outcome-text").textContent =
      `Status: ${incident.status}\n${reasonLine}${JSON.stringify(incident.validation_result, null, 2)}`;
  } else {
    outcomePanel.hidden = true;
  }

  const auditRes = await fetch(`/incidents/${incidentId}/audit`);
  const auditEntries = await auditRes.json();
  const auditLog = document.getElementById("audit-log");
  auditLog.innerHTML = "";
  for (const entry of auditEntries) {
    auditLog.appendChild(renderAuditEntry(entry));
  }

  const idx = state.incidents.findIndex((i) => i.incident_id === incidentId);
  if (idx >= 0) state.incidents[idx] = { ...state.incidents[idx], ...incident };
  renderIncidentList();
}

function openIncident(incidentId) {
  state.currentIncidentId = incidentId;
  document.getElementById("empty-state").hidden = true;
  document.getElementById("incident-detail-section").hidden = false;
  refreshIncidentDetail(incidentId);
  renderIncidentList();
  if (state.pollHandle) clearInterval(state.pollHandle);
  state.pollHandle = setInterval(() => refreshIncidentDetail(incidentId), 4000);
}

async function submitDecision(path) {
  const actor = document.getElementById("actor-name").value || "demo-user";
  const reason = document.getElementById("reason-text").value || undefined;
  const body = path === "approve" ? { approved_by: actor, comment: reason } : { rejected_by: actor, reason };
  await fetch(`/incidents/${state.currentIncidentId}/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  refreshIncidentDetail(state.currentIncidentId);
}

document.getElementById("approve-btn").addEventListener("click", () => submitDecision("approve"));
document.getElementById("reject-btn").addEventListener("click", () => submitDecision("reject"));
document.getElementById("incident-search").addEventListener("input", (e) => {
  state.filter = e.target.value;
  renderIncidentList();
});

loadIncidents();
setInterval(loadIncidents, 5000);


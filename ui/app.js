const state = { currentIncidentId: null, pollHandle: null };

function severityClass(sev) {
  if (sev === "P1") return "sev-critical";
  if (sev === "P2") return "sev-warning";
  return "";
}

async function loadIncidents() {
  const res = await fetch("/incidents");
  const incidents = await res.json();
  const tbody = document.getElementById("incident-table-body");
  tbody.innerHTML = "";
  for (const incident of incidents) {
    const tr = document.createElement("tr");
    tr.className = "incident-row";
    tr.innerHTML = `
      <td>${incident.title}</td>
      <td>${incident.service_name ?? "-"}</td>
      <td class="${severityClass(incident.severity)}">${incident.severity ?? "-"}</td>
      <td>${incident.status}</td>
      <td>${incident.detected_at ?? ""}</td>
    `;
    tr.addEventListener("click", () => openIncident(incident.incident_id));
    tbody.appendChild(tr);
  }
}

function renderAuditEntry(entry) {
  const el = document.createElement("div");
  el.className = "step";
  const header = document.createElement("div");
  header.className = "step-header";
  header.innerHTML = `<span>${entry.actor} — ${entry.action_type}</span><span>${entry.created_at ?? ""}</span>`;
  const body = document.createElement("pre");
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
  document.getElementById("detail-title").textContent = `${incident.title} — ${incident.service_name ?? ""}`;
  document.getElementById("evidence-text").textContent = JSON.stringify(incident.evidence, null, 2);
  document.getElementById("rca-text").textContent =
    `${incident.root_cause_summary ?? "(pending)"} (confidence: ${incident.confidence_score ?? "-"})`;

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
    document.getElementById("outcome-text").textContent =
      `Status: ${incident.status}\n${JSON.stringify(incident.validation_result, null, 2)}`;
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
}

function openIncident(incidentId) {
  state.currentIncidentId = incidentId;
  document.getElementById("incident-detail-section").hidden = false;
  refreshIncidentDetail(incidentId);
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

loadIncidents();
setInterval(loadIncidents, 5000);

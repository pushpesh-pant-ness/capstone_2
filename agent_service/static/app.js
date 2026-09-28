const state = { currentIncidentId: null, eventSource: null };

async function loadFaults() {
  const res = await fetch("/faults");
  const faults = await res.json();
  const container = document.getElementById("fault-list");
  container.innerHTML = "";
  for (const fault of faults) {
    const card = document.createElement("div");
    card.className = "fault-card";
    card.innerHTML = `
      <span class="fid">${fault.id}</span>
      <span class="fdesc">${fault.expected_root_cause}</span>
      <button data-action="trigger" data-id="${fault.id}">Trigger</button>
      <button data-action="clear" data-id="${fault.id}" class="clear">Clear</button>
    `;
    container.appendChild(card);
  }
  container.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const { action, id } = btn.dataset;
      btn.disabled = true;
      try {
        await fetch(`/faults/${id}/${action}`, { method: "POST" });
      } finally {
        btn.disabled = false;
      }
    });
  });
}

function severityClass(sev) {
  if (sev === "critical") return "sev-critical";
  if (sev === "warning") return "sev-warning";
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
      <td>${incident.alert_name}</td>
      <td>${incident.service_name ?? "-"}</td>
      <td class="${severityClass(incident.severity)}">${incident.severity ?? "-"}</td>
      <td>${incident.status}</td>
      <td>${incident.created_at ?? ""}</td>
    `;
    tr.addEventListener("click", () => openIncident(incident.id));
    tbody.appendChild(tr);
  }
}

function renderStep(step) {
  const el = document.createElement("div");
  el.className = `step ${step.status}`;
  const header = document.createElement("div");
  header.className = "step-header";
  header.innerHTML = `<span>${step.node_name} — ${step.status}</span><span>${new Date((step.timestamp ?? Date.now() / 1000) * 1000).toLocaleTimeString()}</span>`;
  const body = document.createElement("pre");
  body.hidden = true;
  body.textContent = JSON.stringify(
    {
      input: step.input,
      output: step.output,
      llm_prompt: step.llm_prompt,
      llm_response: step.llm_response,
      tool_calls: step.tool_calls,
      error: step.error,
    },
    null,
    2
  );
  header.addEventListener("click", () => (body.hidden = !body.hidden));
  el.appendChild(header);
  el.appendChild(body);
  return el;
}

async function refreshIncidentHeader(incidentId) {
  const res = await fetch(`/incidents/${incidentId}`);
  const data = await res.json();
  const incident = data.incident;
  document.getElementById("detail-title").textContent = `${incident.alert_name} — ${incident.service_name ?? ""}`;

  const approvalPanel = document.getElementById("approval-panel");
  const outcomePanel = document.getElementById("outcome-panel");

  if (incident.status === "awaiting_approval") {
    approvalPanel.hidden = false;
    document.getElementById("approval-plan-text").textContent = `Plan: ${incident.remediation_plan ?? "(pending)"}\nRoot cause: ${incident.root_cause ?? ""}`;
  } else {
    approvalPanel.hidden = true;
  }

  if (["resolved", "escalated"].includes(incident.status)) {
    outcomePanel.hidden = false;
    document.getElementById("outcome-text").textContent = `Status: ${incident.status} | Outcome: ${incident.outcome ?? "-"}`;
  } else {
    outcomePanel.hidden = true;
  }

  return incident;
}

function openIncident(incidentId) {
  state.currentIncidentId = incidentId;
  document.getElementById("incident-detail-section").hidden = false;
  document.getElementById("timeline").innerHTML = "";

  if (state.eventSource) state.eventSource.close();

  refreshIncidentHeader(incidentId);

  const es = new EventSource(`/incidents/${incidentId}/stream`);
  es.onmessage = (evt) => {
    const step = JSON.parse(evt.data);
    document.getElementById("timeline").appendChild(renderStep(step));
    refreshIncidentHeader(incidentId);
  };
  state.eventSource = es;
}

async function submitDecision(path) {
  const actor = document.getElementById("actor-name").value || "demo-user";
  const body = path === "approve" ? { approved_by: actor } : { rejected_by: actor };
  await fetch(`/incidents/${state.currentIncidentId}/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  refreshIncidentHeader(state.currentIncidentId);
}

document.getElementById("approve-btn").addEventListener("click", () => submitDecision("approve"));
document.getElementById("reject-btn").addEventListener("click", () => submitDecision("reject"));

loadFaults();
loadIncidents();
setInterval(loadIncidents, 5000);
document.getElementById("conn-status").textContent = "ready";

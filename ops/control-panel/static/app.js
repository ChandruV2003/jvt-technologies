const statusGrid = document.querySelector("#status-grid");
const pendingDecisions = document.querySelector("#pending-decisions");
const nextActions = document.querySelector("#next-actions");
const quickLinks = document.querySelector("#quick-links");
const leadList = document.querySelector("#lead-list");
const draftList = document.querySelector("#draft-list");
const sentList = document.querySelector("#sent-list");
const inboxList = document.querySelector("#inbox-list");
const messageViewer = document.querySelector("#message-viewer");
const refreshButton = document.querySelector("#refresh-all");
const sendPromptButton = document.querySelector("#send-prompt");
const promptBox = document.querySelector("#model-prompt");
const responseBox = document.querySelector("#model-response");
const profileSelect = document.querySelector("#model-profile");
const includeStatusBox = document.querySelector("#include-status");

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return response.json();
}

function tile(label, value) {
  return `
    <div class="status-tile">
      <div class="status-label">${label}</div>
      <strong>${value}</strong>
    </div>
  `;
}

function renderStatus(status) {
  const leadCounts = status.lead_counts || {};
  const queueCounts = status.queue_counts || {};
  const inboxCounts = status.inbox_counts || {};
  const decisionCounts = status.decision_counts || {};
  statusGrid.innerHTML = [
    tile("New leads", leadCounts.new || 0),
    tile("Sent leads", leadCounts.sent || 0),
    tile("Draft packets", queueCounts.draft || 0),
    tile("Pending decisions", decisionCounts.pending || 0),
    tile("Inbox new", inboxCounts.new || 0),
    tile("Approved packets", queueCounts.approved || 0),
    tile("Replied threads", queueCounts.replied || 0),
    tile("Sent packets", queueCounts.sent || 0),
  ].join("");
}

function renderQuickLinks(status) {
  const panelUrls = status.panel_urls || {};
  const siteUrls = status.site_urls || {};
  const links = [
    { label: "Tailnet panel", href: panelUrls.tailscale, detail: "Remote ops access over Tailscale" },
    { label: "Local panel", href: panelUrls.local, detail: "Local-only control surface" },
    { label: "Public site", href: siteUrls.public, detail: "Live JVT Technologies website" },
    { label: "Company roadmap", href: "https://github.com/ChandruV2003/jvt-technologies", detail: "Repo and working source of truth" },
  ].filter((item) => item.href);

  quickLinks.innerHTML = links
    .map((item) => `
      <a class="quick-link" href="${item.href}" target="_blank" rel="noreferrer">
        <strong>${item.label}</strong>
        <span class="meta">${item.detail}</span>
      </a>
    `)
    .join("");
}

function renderPending(items) {
  if (!items.length) {
    pendingDecisions.innerHTML = `<div class="list-item"><h3>No pending decisions</h3><p class="meta">The system is clear right now.</p></div>`;
    return;
  }

  pendingDecisions.innerHTML = items
    .map((item) => `
      <article class="list-item">
        <h3>${item.title}</h3>
        <p class="meta">${item.category} · risk ${item.risk}</p>
        <p>${item.recommended_action}</p>
        <div class="chips">
          ${(item.options || []).map((option) => `<span class="chip">${option}</span>`).join("")}
        </div>
        <div class="decision-actions">
          <button class="button small" data-transition="${item.stem}" data-state="approved">Approve</button>
          <button class="button small secondary" data-transition="${item.stem}" data-state="rejected">Reject</button>
          <button class="button small secondary" data-transition="${item.stem}" data-state="executed">Mark Executed</button>
        </div>
      </article>
    `)
    .join("");
}

function renderNextActions(items) {
  if (!items.length) {
    nextActions.innerHTML = `<div class="list-item"><h3>No queued actions</h3></div>`;
    return;
  }

  nextActions.innerHTML = items
    .map((item) => `
      <article class="list-item">
        <h3>${item.title}</h3>
        <p class="meta">${item.kind || "task"}</p>
        <p>${item.detail}</p>
      </article>
    `)
    .join("");
}

function renderLeads(items) {
  if (!items.length) {
    leadList.innerHTML = `<div class="list-item"><h3>No leads found</h3></div>`;
    return;
  }

  leadList.innerHTML = items
    .map((lead) => `
      <article class="list-item">
        <h3>${lead.company_name}</h3>
        <p class="meta">${lead.practice_area || "No practice area"} · fit ${lead.fit_score || 0}</p>
        <p>${lead.city_state || "No location"}${lead.public_email ? ` · ${lead.public_email}` : ""}</p>
        <div class="chips">
          <span class="chip">${lead.outreach_status || "unknown"}</span>
          <span class="chip">${lead.follow_up_status || "none"}</span>
        </div>
      </article>
    `)
    .join("");
}

function packetMeta(item, queueLabel) {
  const recipient = item.recipient_email ? ` · ${item.recipient_email}` : "";
  const sentAt = item.sent_at ? ` · ${item.sent_at}` : "";
  return `${queueLabel}${recipient}${sentAt}`;
}

function renderPacketList(container, items, queueLabel, emptyTitle, emptyDetail) {
  const renderPacket = (item) => `
    <article class="list-item">
      <h3>${item.company_name || item.stem || "Packet"}</h3>
      <p class="meta">${packetMeta(item, queueLabel)}</p>
      <p>${item.subject || item.title || "No subject"}</p>
      <div class="decision-actions">
        <button class="button small secondary" data-open-packet="${item.stem}" data-queue="${queueLabel}">View</button>
      </div>
    </article>
  `;

  container.innerHTML = items.length
    ? items.slice(0, 6).map((item) => renderPacket(item)).join("")
    : `<div class="list-item"><h3>${emptyTitle}</h3><p class="meta">${emptyDetail}</p></div>`;
}

function renderPacketViewer(detail) {
  const metadata = detail.metadata || {};
  const recipient = metadata.recipient_email || "No recipient";
  const subject = metadata.subject || "No subject";
  const body = detail.text_body || detail.review_body || "No body available.";
  const queue = detail.queue || "unknown";
  const sentAt = metadata.sent_at || metadata.generated_at || "Unknown time";

  messageViewer.innerHTML = `
    <article class="list-item viewer-card">
      <h3>${subject}</h3>
      <p class="meta">${queue} · ${recipient} · ${sentAt}</p>
      <div class="chips">
        <span class="chip">${metadata.company_name || "No company"}</span>
        <span class="chip">${metadata.reply_to_email || "No reply-to"}</span>
      </div>
      <pre class="viewer-body">${body}</pre>
    </article>
  `;
}

function renderInbox(items) {
  if (!items.length) {
    inboxList.innerHTML = `<div class="list-item"><h3>No imported inbox items</h3><p class="meta">When new mail is imported, it will show here.</p></div>`;
    return;
  }

  inboxList.innerHTML = items
    .map((item) => `
      <article class="list-item">
        <h3>${item.subject || "No subject"}</h3>
        <p class="meta">${item.from || "Unknown sender"} · ${item.triage_bucket || "review"}</p>
        <p>${item.snippet || ""}</p>
      </article>
    `)
    .join("");
}

async function refreshAll() {
  const [status, decisions, leads, outreach, inbox] = await Promise.all([
    request("/api/status"),
    request("/api/decisions"),
    request("/api/leads?limit=8"),
    request("/api/outreach/recent?limit=6"),
    request("/api/inbox/recent?limit=6"),
  ]);

  renderStatus(status);
  renderQuickLinks(status);
  renderPending(decisions.pending || []);
  renderNextActions(status.next_actions || []);
  renderLeads(leads.items || []);
  renderPacketList(draftList, outreach.draft || [], "draft", "No draft packets", "Generate or review a new packet and it will show up here.");
  renderPacketList(sentList, outreach.sent || [], "sent", "No sent packets", "When reviewed outreach goes out, it will show up here.");
  renderInbox(inbox.items || []);

  const defaultPacket = (outreach.sent || [])[0] || (outreach.draft || [])[0];
  if (defaultPacket) {
    try {
      const detail = await request(`/api/outreach/${(outreach.sent || []).length ? "sent" : "draft"}/${defaultPacket.stem}`);
      renderPacketViewer(detail);
    } catch (error) {
      messageViewer.innerHTML = `<div class="list-item"><h3>Viewer load failed</h3><p class="meta">${error.message}</p></div>`;
    }
  } else {
    messageViewer.innerHTML = `<div class="list-item"><h3>No packet selected</h3><p class="meta">Choose a draft or sent packet to inspect its subject, recipient, and body.</p></div>`;
  }
}

async function handleDecisionTransition(event) {
  const button = event.target.closest("[data-transition]");
  if (!button) return;

  const stem = button.dataset.transition;
  const state = button.dataset.state;
  const note = window.prompt(`Optional note for ${state}:`, "") || "";

  await request(`/api/decisions/${stem}/transition`, {
    method: "POST",
    body: JSON.stringify({ state, note }),
  });
  await refreshAll();
}

async function handlePrompt() {
  const prompt = promptBox.value.trim();
  if (!prompt) return;

  responseBox.textContent = "Thinking locally...";
  const payload = {
    prompt,
    profile: profileSelect.value,
    include_status_context: includeStatusBox.checked,
  };
  try {
    const response = await request("/api/model/respond", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    responseBox.textContent = response.response;
  } catch (error) {
    responseBox.textContent = `Request failed: ${error.message}`;
  }
}

async function handlePacketOpen(event) {
  const button = event.target.closest("[data-open-packet]");
  if (!button) return;

  const stem = button.dataset.openPacket;
  const queue = button.dataset.queue;
  try {
    const detail = await request(`/api/outreach/${queue}/${stem}`);
    renderPacketViewer(detail);
  } catch (error) {
    messageViewer.innerHTML = `<div class="list-item"><h3>Viewer load failed</h3><p class="meta">${error.message}</p></div>`;
  }
}

refreshButton.addEventListener("click", refreshAll);
sendPromptButton.addEventListener("click", handlePrompt);
pendingDecisions.addEventListener("click", handleDecisionTransition);
draftList.addEventListener("click", handlePacketOpen);
sentList.addEventListener("click", handlePacketOpen);

promptBox.value = "Give me a concise operator summary of the current JVT state and the best next action.";
refreshAll().catch((error) => {
  responseBox.textContent = `Initial load failed: ${error.message}`;
});

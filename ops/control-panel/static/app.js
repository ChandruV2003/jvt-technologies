const statusGrid = document.querySelector("#status-grid");
const pendingDecisions = document.querySelector("#pending-decisions");
const nextActions = document.querySelector("#next-actions");
const agentList = document.querySelector("#agent-list");
const waveList = document.querySelector("#wave-list");
const leadList = document.querySelector("#lead-list");
const draftList = document.querySelector("#draft-list");
const reviewList = document.querySelector("#review-list");
const approvedList = document.querySelector("#approved-list");
const sentList = document.querySelector("#sent-list");
const inboxList = document.querySelector("#inbox-list");
const messageViewer = document.querySelector("#message-viewer");
const watchdogGrid = document.querySelector("#watchdog-grid");
const watchdogFindings = document.querySelector("#watchdog-findings");
const ownedOpsGrid = document.querySelector("#owned-ops-grid");
const ownedOpsDetail = document.querySelector("#owned-ops-detail");
const agentInteropGrid = document.querySelector("#agent-interop-grid");
const agentHandoffList = document.querySelector("#agent-handoff-list");
const agentLaunchList = document.querySelector("#agent-launch-list");
const orchestratorGrid = document.querySelector("#orchestrator-grid");
const orchestratorLanes = document.querySelector("#orchestrator-lanes");
const orchestratorWorkItems = document.querySelector("#orchestrator-work-items");
const followupGrid = document.querySelector("#followup-grid");
const followupList = document.querySelector("#followup-list");
const readinessGrid = document.querySelector("#readiness-grid");
const readinessDetail = document.querySelector("#readiness-detail");
const voiceStatusGrid = document.querySelector("#voice-status-grid");
const voiceIntakeList = document.querySelector("#voice-intake-list");
const revenueRecommendation = document.querySelector("#revenue-recommendation");
const revenueList = document.querySelector("#revenue-list");
const cryptoLabGrid = document.querySelector("#crypto-lab-grid");
const cryptoLabDetail = document.querySelector("#crypto-lab-detail");
const refreshButton = document.querySelector("#refresh-all");
const refreshCryptoLabButton = document.querySelector("#refresh-crypto-lab");
const prepareTodayWaveButton = document.querySelector("#prepare-today-wave");
const prepareTomorrowWaveButton = document.querySelector("#prepare-tomorrow-wave");
const sendApprovedBatchButton = document.querySelector("#send-approved-batch");
const sendPromptButton = document.querySelector("#send-prompt");
const promptBox = document.querySelector("#model-prompt");
const responseBox = document.querySelector("#model-response");
const profileSelect = document.querySelector("#model-profile");
const includeStatusBox = document.querySelector("#include-status");

let pendingSendRequest = null;

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    let detail = "";
    try {
      const payload = await response.json();
      detail = payload.detail || JSON.stringify(payload);
    } catch {
      detail = await response.text();
    }
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
  const agentSummary = status.agent_summary || {};
  const queueCounts = status.queue_counts || {};
  const inboxCounts = status.inbox_counts || {};
  const inboxBuckets = status.inbox_buckets || {};
  const decisionCounts = status.decision_counts || {};
  const currentWaveCounts = (status.current_wave || {}).packet_counts || {};
  const approvedBacklog = status.approved_backlog || {};
  const sentBreakdown = status.sent_packet_breakdown || {};
  const voice = status.voice_agent || {};
  const agentInterop = status.agent_interop || {};
  const orchestrator = status.orchestrator || {};
  const ownedOps = status.owned_ops || {};
  const tcpPressure = status.tcp_pressure || {};
  const autoSend = status.auto_send || {};
  const operatorAlerts = status.operator_alerts || {};
  const inboxNeedsReview = Number(inboxBuckets.direct || 0) + Number(inboxBuckets.review || 0);
  const inboxImported = Object.values(inboxCounts).reduce((sum, value) => sum + Number(value || 0), 0);
  statusGrid.innerHTML = [
    tile("Total leads", Object.values(leadCounts).reduce((sum, value) => sum + Number(value || 0), 0)),
    tile("New leads", leadCounts.new || 0),
    tile("Active agents", agentSummary.active || 0),
    tile("Agent interop", agentInterop.ok ? "ok" : "check"),
    tile("Growth OS", orchestrator.generated_at ? (orchestrator.ok ? "ready" : "attention") : "missing"),
    tile("TCP pressure", tcpPressure.severity || "unknown"),
    tile("Auto-send", autoSend.status || "unknown"),
    tile("Operator alerts", operatorAlerts.active_count || 0),
    tile("Sent today", `${autoSend.sent_today_total || 0}/${autoSend.daily_total_cap || "?"}`),
    tile("Follow-ups today", `${autoSend.sent_today_followup || 0}/${autoSend.daily_followup_cap || "?"}`),
    tile("Cap mode", (autoSend.cap_adjustments || []).length ? "dynamic" : "base"),
    tile("Owned infra", ownedOps.ok ? "ok" : "check"),
    tile("Backlog approved", approvedBacklog.count || queueCounts.approved || 0),
    tile("Latest wave review", currentWaveCounts.review || 0),
    tile("Latest wave approved", currentWaveCounts.approved || 0),
    tile("Latest wave sent", currentWaveCounts.sent || 0),
    tile("Draft packets", queueCounts.draft || 0),
    tile("Pending decisions", decisionCounts.pending || 0),
    tile("Inbox needs review", inboxNeedsReview),
    tile("Inbox imported", inboxImported),
    tile("Ready packets", approvedBacklog.count || queueCounts.approved || 0),
    tile("Replied threads", queueCounts.replied || 0),
    tile("Prospect sends", sentBreakdown.prospect || 0),
    tile("Sent queue items", queueCounts.sent || 0),
    tile("Voice intake", voice.intake_count || 0),
  ].join("");
}

function renderOwnedOps(ownedOps) {
  if (!ownedOpsGrid || !ownedOpsDetail) return;

  ownedOpsGrid.innerHTML = [
    tile("Overall", ownedOps.ok ? "ok" : "attention"),
    tile("Debian", ownedOps.debian_reachable ? "reachable" : "offline"),
    tile("Backup target", ownedOps.backup_target || "unknown"),
    tile("Latest backup", ownedOps.debian_latest_backup || "unknown"),
    tile("Backup age", formatAge(ownedOps.last_backup_age_seconds)),
    tile("Tunnel", ownedOps.cloudflare_tunnel || "unknown"),
    tile("UPS", String(ownedOps.m4_ups || "").includes("100%") ? "100%" : "check"),
    tile("Second backup", ownedOps.second_backup_target || "paused"),
  ].join("");

  const findings = ownedOps.findings || [];
  const findingMarkup = findings.length
    ? findings
        .map((finding) => `
          <article class="list-item attention-item">
            <h3>Owned infra finding</h3>
            <p>${escapeHtml(finding)}</p>
          </article>
        `)
        .join("")
    : `
      <article class="list-item healthy-item">
        <h3>Owned infra checks are clean</h3>
        <p class="meta">M4, Cloudflare tunnel, Debian ops, UPS, and Debian-local backup are reporting healthy.</p>
      </article>
    `;

  ownedOpsDetail.innerHTML = `
    <article class="list-item owned-ops-summary">
      <h3>Current owned topology</h3>
      <p>M4 runs app/voice/tunnel. Debian is the ops node and local backup target. TrueNAS is intentionally excluded.</p>
      <div class="chips">
        <span class="chip">Disk: ${escapeHtml(ownedOps.debian_disk || "unknown")}</span>
        <span class="chip">Memory: ${escapeHtml(ownedOps.debian_mem || "unknown")}</span>
        <span class="chip">Load: ${escapeHtml(ownedOps.debian_load || "unknown")}</span>
      </div>
      <p class="meta">${escapeHtml(ownedOps.last_backup_line || "No backup log line found.")}</p>
      <p class="meta">${escapeHtml(ownedOps.m4_ups || "UPS status unavailable.")}</p>
    </article>
    ${findingMarkup}
  `;
}

function renderAgentInterop(agentInterop) {
  if (!agentInteropGrid || !agentHandoffList || !agentLaunchList) return;

  const summary = agentInterop.summary || {};
  const handoffs = agentInterop.handoffs || [];
  const launchd = agentInterop.launchd || {};
  agentInteropGrid.innerHTML = [
    tile("Overall", agentInterop.ok ? "ok" : "attention"),
    tile("Findings", agentInterop.finding_count || 0),
    tile("State age", formatAge(agentInterop.state_age_seconds)),
    tile("Launch agents", `${summary.clean_launch_agents || 0}/${summary.registered_launch_agents || 0}`),
    tile("Manifests", summary.agent_manifests || 0),
    tile("Handoffs", `${summary.handoffs_ok || 0}/${summary.handoffs_total || handoffs.length || 0}`),
  ].join("");

  if (!handoffs.length) {
    agentHandoffList.innerHTML = `
      <div class="list-item attention-item">
        <h3>No handoff check has run</h3>
        <p class="meta">Run ops/agent-control/agent_interop_check.py on the Mac mini.</p>
      </div>
    `;
  } else {
    agentHandoffList.innerHTML = handoffs
      .map((item) => `
        <article class="list-item ${item.ok ? "healthy-item" : "attention-item"}">
          <div class="wave-card-head">
            <div>
              <h3>${escapeHtml(item.name || "Agent handoff")}</h3>
              <p class="meta">${escapeHtml(item.source || "source")} -> ${escapeHtml(item.target || "target")} · ${escapeHtml(item.status || "unknown")}</p>
            </div>
            <span class="chip">${item.ok ? "ready" : "needs check"}</span>
          </div>
          <p>${escapeHtml(item.evidence || "No evidence recorded.")}</p>
          ${item.next_step ? `<p class="meta"><strong>Next:</strong> ${escapeHtml(item.next_step)}</p>` : ""}
        </article>
      `)
      .join("");
  }

  const launchItems = Object.values(launchd);
  agentLaunchList.innerHTML = launchItems.length
    ? launchItems
        .map((item) => `
          <span class="chip ${item.ok ? "chip-good" : "chip-warn"}">
            ${escapeHtml(item.label || "launch-agent")}: ${item.running ? "running" : item.ok ? "clean" : "check"}
          </span>
        `)
        .join("")
    : `<span class="chip chip-warn">No launchd snapshot found</span>`;
}

function renderOrchestrator(orchestrator) {
  if (!orchestratorGrid || !orchestratorLanes || !orchestratorWorkItems) return;

  const quotas = orchestrator.quotas || {};
  const policy = orchestrator.policy || {};
  const checkin = orchestrator.checkin || {};
  const lanes = orchestrator.lanes || [];
  const workItems = orchestrator.work_items || [];
  orchestratorGrid.innerHTML = [
    tile("Overall", orchestrator.generated_at ? (orchestrator.ok ? "ready" : "attention") : "missing"),
    tile("Mode", policy.mode || "unknown"),
    tile("State age", formatAge(orchestrator.state_age_seconds)),
    tile("Check-in", checkin.generated_at ? formatAge(checkin.state_age_seconds) : "missing"),
    tile("Safe actions", checkin.safe_action_count || 0),
    tile("Initial today", `${quotas.initial_sends_today || 0}/${quotas.daily_initial_send_cap || 0}`),
    tile("Follow-ups today", `${quotas.followup_sends_today || 0}/${quotas.daily_followup_send_cap || 0}`),
    tile("Approved", quotas.approved_backlog || 0),
    tile("Review", quotas.review_backlog || 0),
    tile("Send gate", quotas.operator_send_ready ? "operator-ready" : "held"),
  ].join("");

  if (!lanes.length) {
    orchestratorLanes.innerHTML = `
      <div class="list-item attention-item">
        <h3>No orchestrator lanes loaded</h3>
        <p class="meta">Run ops/agent-control/orchestrator.py on the Mac mini.</p>
      </div>
    `;
  } else {
    orchestratorLanes.innerHTML = lanes
      .map((lane) => {
        const metrics = Object.entries(lane.metrics || {})
          .slice(0, 4)
          .map(([key, value]) => `<span class="chip">${escapeHtml(key)}: ${escapeHtml(value)}</span>`)
          .join("");
        const isAttention = ["attention", "approval-required", "needs-input"].includes(String(lane.status || ""));
        return `
          <article class="list-item lane-card ${isAttention ? "attention-item" : "healthy-item"}">
            <div class="wave-card-head">
              <div>
                <h3>${escapeHtml(lane.title || "Lane")}</h3>
                <p class="meta">${escapeHtml(lane.status || "unknown")}</p>
              </div>
              <span class="chip">${escapeHtml(lane.slug || "lane")}</span>
            </div>
            <p>${escapeHtml(lane.summary || "No lane summary.")}</p>
            <p class="meta"><strong>Next:</strong> ${escapeHtml(lane.next_step || "No next step.")}</p>
            ${metrics ? `<div class="chips">${metrics}</div>` : ""}
          </article>
        `;
      })
      .join("");
  }

  if (!workItems.length) {
    orchestratorWorkItems.innerHTML = `
      <div class="list-item healthy-item">
        <h3>No ranked work items</h3>
        <p class="meta">${escapeHtml(quotas.ramp_recommendation || "No orchestrator recommendation loaded.")}</p>
      </div>
    `;
    return;
  }

  orchestratorWorkItems.innerHTML = workItems
    .slice(0, 10)
    .map((item) => `
      <article class="list-item work-item-card">
        <div class="wave-card-head">
          <div>
            <h3>P${escapeHtml(item.priority)} · ${escapeHtml(item.title || "Work item")}</h3>
            <p class="meta">${escapeHtml(item.lane || "orchestrator")} · ${escapeHtml(item.automation_level || "stage-only")}</p>
          </div>
          <span class="chip">${escapeHtml(item.id || "work")}</span>
        </div>
        <p>${escapeHtml(item.detail || "")}</p>
        <p class="meta"><strong>Action:</strong> ${escapeHtml(item.recommended_action || "")}</p>
        ${(item.blocked_by || []).length ? `<p class="meta"><strong>Blocked by:</strong> ${escapeHtml((item.blocked_by || []).join(", "))}</p>` : ""}
      </article>
    `)
    .join("");
}

function formatAge(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value)) return "unknown";
  if (value < 90) return `${Math.round(value)}s`;
  if (value < 7200) return `${Math.round(value / 60)}m`;
  return `${Math.round(value / 3600)}h`;
}

function renderWatchdog(watchdog) {
  if (!watchdogGrid || !watchdogFindings) return;

  const http = watchdog.http || {};
  const launchd = watchdog.launchd || {};
  const serviceBoard = watchdog.service_board || {};
  const trader = watchdog.trader || {};
  const traderDebian = trader.debian || {};
  const tcpPressure = (window.latestStatus || {}).tcp_pressure || {};
  const autoSend = (window.latestStatus || {}).auto_send || {};
  const runningAgents = Object.values(launchd).filter((item) => item && item.ok).length;
  watchdogGrid.innerHTML = [
    tile("Overall", watchdog.ok ? "ok" : "attention"),
    tile("Findings", watchdog.finding_count || 0),
    tile("State age", formatAge(watchdog.state_age_seconds)),
    tile("Site", (http.public_site || {}).ok ? "200" : "check"),
    tile("Control", (http.control_panel || {}).ok ? "200" : "check"),
    tile("Voice", (http.voice_intake || {}).ok ? "200" : "check"),
    tile("Launch agents", runningAgents),
    tile("Trader report", traderDebian.ok ? formatAge(traderDebian.offline_report_age_seconds) : "check"),
    tile("Trader mode", traderDebian.offline_mode || "unknown"),
    tile("TCP", tcpPressure.severity || "unknown"),
    tile("TIME_WAIT", tcpPressure.time_wait || 0),
    tile("Mbuf", tcpPressure.mbuf_network_percent ? `${tcpPressure.mbuf_network_percent}%` : "unknown"),
    tile("Auto-send", autoSend.status || "unknown"),
    tile("Sent/cap", `${autoSend.sent_today_total || 0}/${autoSend.daily_total_cap || "?"}`),
    tile("Follow-up cap", `${autoSend.sent_today_followup || 0}/${autoSend.daily_followup_cap || "?"}`),
    tile("Cap adjust", (autoSend.cap_adjustments || [])[0] || "none"),
  ].join("");

  const findings = watchdog.findings || [];
  if (!findings.length) {
    watchdogFindings.innerHTML = `
      <div class="list-item healthy-item">
        <h3>No active watchdog findings</h3>
        <p class="meta">Service board: ${escapeHtml(serviceBoard.wedge_count || 0)} wedge(s), ${escapeHtml(serviceBoard.next_count || 0)} next action(s).</p>
      </div>
    `;
    return;
  }
  watchdogFindings.innerHTML = findings
    .map((finding) => {
      const title =
        typeof finding === "object"
          ? `${finding.severity || "finding"} · ${finding.area || "watchdog"}`
          : "Watchdog finding";
      const message =
        typeof finding === "object"
          ? finding.message || JSON.stringify(finding)
          : finding;
      return `
        <article class="list-item attention-item">
          <h3>${escapeHtml(title)}</h3>
          <p>${escapeHtml(message)}</p>
        </article>
      `;
    })
    .join("");
}

function renderFollowups(followups) {
  if (!followupGrid || !followupList) return;

  followupGrid.innerHTML = [
    tile("Eligible older sends", followups.eligible_count || 0),
    tile("Review follow-ups", followups.review_queue || 0),
    tile("Approved follow-ups", followups.approved_queue || 0),
    tile("Sent follow-ups", followups.sent_followups || 0),
    tile("Prospect sends 24h", followups.prospect_sent_last_24h || 0),
    tile("Min age", `${followups.min_age_days || 0}d`),
    tile("Last staged", followups.latest_report_written_count || 0),
    tile("Report time", followups.latest_report_generated_at ? "present" : "none"),
  ].join("");

  const items = followups.eligible_sample || [];
  if (!items.length) {
    followupList.innerHTML = `
      <div class="list-item healthy-item">
        <h3>No immediate unstaged follow-up candidates</h3>
        <p class="meta">Either recent sends are still too new, or eligible prospects already have a staged/sent follow-up.</p>
      </div>
    `;
    return;
  }
  followupList.innerHTML = items
    .map((item) => `
      <article class="list-item">
        <h3>${escapeHtml(item.company_name || item.stem || "Prospect")}</h3>
        <p class="meta">${escapeHtml(item.recipient_email || "No recipient")} · sent ${escapeHtml(item.sent_at || "unknown")}</p>
        <p>${escapeHtml(item.subject || "No subject")}</p>
      </article>
    `)
    .join("");
}

function renderBusinessReadiness(readiness) {
  if (!readinessGrid || !readinessDetail) return;

  const opportunities = readiness.opportunity_manager || {};
  const voice = readiness.voice_readiness || {};
  const trader = readiness.paper_trader || {};
  const source = readiness.source_hygiene || {};
  const resources = readiness.system_resources || {};
  const resourceFindings = resources.findings || [];
  const traderFindings = trader.findings || [];

  readinessGrid.innerHTML = [
    tile("Overall", readiness.ok ? "ok" : "attention"),
    tile("Active opportunities", opportunities.active_count || 0),
    tile("Need response", opportunities.response_needed_count || 0),
    tile("Voice demo", voice.demo_ready ? "ready" : "not ready"),
    tile("Voice live", voice.live_ready ? "ready" : "gated"),
    tile("Paper trader", trader.ok ? (trader.mode || "ok") : "check"),
    tile("Trader findings", traderFindings.length || 0),
    tile("Dirty source", source.status_count || 0),
    tile("M4 resources", resources.ok ? "ok" : "attention"),
    tile("Resource findings", resourceFindings.length || 0),
  ].join("");

  const topActions = opportunities.top_next_actions || [];
  const findings = readiness.findings || [];
  readinessDetail.innerHTML = `
    <article class="list-item ${readiness.ok ? "healthy-item" : "attention-item"}">
      <div class="wave-card-head">
        <div>
          <h3>${readiness.ok ? "No readiness blockers" : "Readiness findings"}</h3>
          <p class="meta">${escapeHtml(readiness.generated_at || "unknown time")} · ${escapeHtml(readiness.guardrail || "")}</p>
        </div>
        <span class="chip">${escapeHtml(readiness.ok ? "ok" : "review")}</span>
      </div>
      <div class="chips">
        ${(findings.length ? findings : ["No current findings."]).slice(0, 6).map((item) => `<span class="chip ${readiness.ok ? "chip-good" : "chip-warn"}">${escapeHtml(item)}</span>`).join("")}
      </div>
    </article>
    <article class="list-item">
      <h3>Opportunity next actions</h3>
      ${
        topActions.length
          ? topActions.slice(0, 5).map((item) => `
              <p><strong>${escapeHtml(item.account_name || "Unknown")}</strong>: ${escapeHtml(item.next_action || "Review manually.")}</p>
              <p class="meta">${escapeHtml(item.stage || "stage")} · ${escapeHtml(item.service_name || "service")} · ${escapeHtml(item.contact_email || "no contact")}</p>
            `).join("")
          : `<p class="meta">No active opportunity response is pending.</p>`
      }
    </article>
  `;
}

function renderAgents(items) {
  if (!items.length) {
    agentList.innerHTML = `<div class="list-item"><h3>No agent registry loaded</h3><p class="meta">Add manifests under ops/agent-control/agents to populate this view.</p></div>`;
    return;
  }

  agentList.innerHTML = items
    .map((item) => `
      <article class="list-item agent-card">
        <h3>${item.name}</h3>
        <p class="meta">${item.role || "agent"} · ${item.runtime_status || "unknown"} · ${item.mode || "unknown"}</p>
        <p>${item.summary || "No summary available."}</p>
        <div class="chips">
          <span class="chip">approval: ${item.approval_boundary || "n/a"}</span>
          ${(item.metrics || []).map((metric) => `<span class="chip">${metric.label}: ${metric.value}</span>`).join("")}
        </div>
      </article>
    `)
    .join("");
}

function localDateIso(daysFromToday = 0) {
  const date = new Date();
  date.setDate(date.getDate() + daysFromToday);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderWaves(items) {
  if (!items.length) {
    waveList.innerHTML = `<div class="list-item"><h3>No prepared waves</h3><p class="meta">Use Prepare Today or Prepare Tomorrow to stage personalized outreach into review.</p></div>`;
    return;
  }

  waveList.innerHTML = items
    .map((wave) => {
      const counts = wave.packet_counts || {};
      const reviewCount = counts.review || 0;
      const approvedCount = counts.approved || 0;
      const sentCount = counts.sent || 0;
      const missingCount = counts.missing || 0;
      const leadNames = (wave.selected_leads || [])
        .slice(0, 4)
        .map((lead) => lead.company_name)
        .filter(Boolean);
      const firstPacket = (wave.packets || []).find((packet) => packet.queue !== "missing") || {};
      const packetLines = (wave.packets || [])
        .map((packet) => {
          const queue = packet.queue || "missing";
          const canApprove = queue === "review";
          const canSend = queue === "approved";
          return `
            <li>
              <div>
                <strong>${escapeHtml(packet.company_name || packet.stem)}</strong>
                <small>${escapeHtml(packet.recipient_email || "No recipient")} · ${escapeHtml(packet.subject || "No subject")}</small>
              </div>
              <div class="packet-line-actions">
                <span>${escapeHtml(queue)}</span>
                ${queue !== "missing" ? `<button class="button tiny secondary" data-open-packet="${escapeHtml(packet.stem)}" data-queue="${escapeHtml(queue)}">Preview</button>` : ""}
                ${canApprove ? `<button class="button tiny" data-transition-packet="${escapeHtml(packet.stem)}" data-from-queue="review" data-to-queue="approved">Approve</button>` : ""}
                ${canSend ? `<button class="button tiny" data-send-packet="${escapeHtml(packet.stem)}">Send</button>` : ""}
              </div>
            </li>
          `;
        })
        .join("");
      return `
        <article class="list-item wave-card">
          <div class="wave-card-head">
            <div>
              <h3>${wave.scheduled_date || "Unscheduled"} · ${wave.name || wave.stem}</h3>
              <p class="meta">${reviewCount} need review · ${approvedCount} ready · ${sentCount} sent</p>
            </div>
            <span class="chip">${wave.stem}</span>
          </div>
          <p>${leadNames.length ? leadNames.join(", ") : "No selected lead summary available."}${(wave.selected_leads || []).length > 4 ? "..." : ""}</p>
          ${packetLines ? `<ul class="packet-lines">${packetLines}</ul>` : ""}
          <div class="chips">
            <span class="chip">review ${reviewCount}</span>
            <span class="chip">approved ${approvedCount}</span>
            <span class="chip">sent ${sentCount}</span>
            ${missingCount ? `<span class="chip">missing ${missingCount}</span>` : ""}
          </div>
          <div class="decision-actions">
            ${firstPacket.stem ? `<button class="button small secondary" data-review-wave="${wave.stem}" data-first-stem="${firstPacket.stem}" data-first-queue="${firstPacket.queue}">Review Packets</button>` : ""}
            <button class="button small" data-approve-wave="${wave.stem}" data-review-count="${reviewCount}" ${reviewCount ? "" : "disabled"}>Approve Reviewed Wave</button>
            <button class="button small" data-send-wave="${wave.stem}" data-approved-count="${approvedCount}" ${approvedCount ? "" : "disabled"}>Send Approved</button>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderPending(items) {
  if (!items.length) {
    pendingDecisions.innerHTML = `<div class="list-item"><h3>No non-outreach decisions</h3><p class="meta">Outreach approvals now live in Outreach Command above.</p></div>`;
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

function transitionButtons(queueLabel, item) {
  if (queueLabel === "review") {
    return `
      <button class="button small" data-transition-packet="${item.stem}" data-from-queue="review" data-to-queue="approved">Approve Packet</button>
      <button class="button small secondary" data-transition-packet="${item.stem}" data-from-queue="review" data-to-queue="draft">Return to Draft</button>
    `;
  }
  if (queueLabel === "approved") {
    return `
      <button class="button small" data-send-packet="${item.stem}">Send Packet</button>
      <button class="button small secondary" data-transition-packet="${item.stem}" data-from-queue="approved" data-to-queue="review">Back to Review</button>
    `;
  }
  return "";
}

function renderPacketList(container, items, queueLabel, emptyTitle, emptyDetail, displayLimit = 8) {
  const renderPacket = (item) => `
    <article class="list-item">
      <h3>${escapeHtml(item.company_name || item.stem || "Packet")}</h3>
      <p class="meta">${escapeHtml(packetMeta(item, queueLabel))}</p>
      <p>${escapeHtml(item.subject || item.title || "No subject")}</p>
      <div class="decision-actions">
        <button class="button small secondary" data-open-packet="${escapeHtml(item.stem)}" data-queue="${escapeHtml(queueLabel)}">Preview</button>
        ${transitionButtons(queueLabel, item)}
      </div>
    </article>
  `;

  container.innerHTML = items.length
    ? items.slice(0, displayLimit).map((item) => renderPacket(item)).join("")
    : `<div class="list-item"><h3>${emptyTitle}</h3><p class="meta">${emptyDetail}</p></div>`;
}

function renderPacketViewer(detail) {
  const metadata = detail.metadata || {};
  const recipient = metadata.recipient_email || "No recipient";
  const subject = metadata.subject || "No subject";
  const body = detail.text_body || detail.review_body || "No body available.";
  const htmlBody = detail.html_body || "";
  const queue = detail.queue || "unknown";
  const sentAt = metadata.sent_at || metadata.generated_at || "Unknown time";
  const htmlPreview = htmlBody
    ? `<iframe class="html-preview" sandbox="" srcdoc="${escapeHtml(htmlBody)}"></iframe>`
    : `<div class="empty-preview">No HTML body found for this packet.</div>`;

  messageViewer.innerHTML = `
    <article class="list-item viewer-card">
      <h3>${escapeHtml(subject)}</h3>
      <p class="meta">${escapeHtml(queue)} · ${escapeHtml(recipient)} · ${escapeHtml(sentAt)}</p>
      <div class="chips">
        <span class="chip">${escapeHtml(metadata.company_name || "No company")}</span>
        <span class="chip">${escapeHtml(metadata.reply_to_email || "No reply-to")}</span>
      </div>
      <div class="viewer-split">
        <section>
          <div class="viewer-subhead">HTML rendering</div>
          ${htmlPreview}
        </section>
        <section>
          <div class="viewer-subhead">Plain-text fallback</div>
          <pre class="viewer-body">${escapeHtml(body)}</pre>
        </section>
      </div>
    </article>
  `;
}

function focusViewer() {
  messageViewer.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderSendConfirmation(requestConfig) {
  const count = Number(requestConfig.count || requestConfig.stems?.length || 0);
  pendingSendRequest = requestConfig;

  const targetLabel = requestConfig.type === "wave"
    ? `wave ${requestConfig.waveStem}`
    : `${count} approved packet${count === 1 ? "" : "s"}`;
  const packetList = requestConfig.stems?.length
    ? `<p class="meta">${requestConfig.stems.map((stem) => escapeHtml(stem)).join(", ")}</p>`
    : "";

  messageViewer.innerHTML = `
    <article class="list-item viewer-card send-confirmation">
      <h3>Final send confirmation</h3>
      <p>This will send ${count} real prospect email${count === 1 ? "" : "s"} from JVT Technologies LLC.</p>
      <p class="meta">Target: ${escapeHtml(targetLabel)}</p>
      ${packetList}
      <div class="decision-actions">
        <button class="button" data-confirm-send>Confirm Send ${count}</button>
        <button class="button secondary" data-cancel-send>Cancel</button>
      </div>
    </article>
  `;
  focusViewer();
}

function renderInbox(items) {
  if (!items.length) {
    inboxList.innerHTML = `<div class="list-item"><h3>No imported inbox items</h3><p class="meta">When new mail is imported, it will show here.</p></div>`;
    return;
  }

  inboxList.innerHTML = items
    .map((item) => `
      <article class="list-item">
        <h3>${escapeHtml(item.subject || "No subject")}</h3>
        <p class="meta">${escapeHtml(item.from || "Unknown sender")} · ${escapeHtml(item.triage_bucket || "review")} · ${escapeHtml(item.triage_action || "review")}</p>
        <p>${escapeHtml(item.snippet || "")}</p>
        <div class="decision-actions">
          <button class="button small secondary" data-inbox-transition="${escapeHtml(item.stem || "")}" data-target-state="reviewed">Mark Reviewed</button>
          <button class="button small secondary" data-inbox-transition="${escapeHtml(item.stem || "")}" data-target-state="closed">Close</button>
        </div>
      </article>
    `)
    .join("");
}

function renderVoice(voice) {
  if (!voiceStatusGrid || !voiceIntakeList) {
    return;
  }

  voiceStatusGrid.innerHTML = [
    tile("Mode", voice.status || "unknown"),
    tile("Dry run", voice.dry_run ? "yes" : "no"),
    tile("OpenAI key", voice.has_openai_key ? "set" : "missing"),
    tile("Phone provider", voice.phone_provider_configured ? "set" : "not set"),
    tile("Webhook", voice.public_base_url ? "public" : "missing"),
    tile("Intake packets", voice.intake_count || 0),
  ].join("");

  const recent = voice.recent_intake || [];
  if (!recent.length) {
    voiceIntakeList.innerHTML = `
      <div class="list-item">
        <h3>No voice intake yet</h3>
        <p class="meta">${escapeHtml(voice.next_step || "Run a dry-run intake or connect a phone provider when ready.")}</p>
        <p class="meta">Live gates: ${escapeHtml(Object.entries(voice.live_ready_gates || {}).map(([key, value]) => `${key}=${value ? "yes" : "no"}`).join(" · "))}</p>
      </div>
    `;
    return;
  }

  voiceIntakeList.innerHTML = recent
    .map((item) => `
      <article class="list-item">
        <h3>${escapeHtml(item.company || item.caller_name || item.call_id || "Voice intake")}</h3>
        <p class="meta">${escapeHtml(item.source || "voice")} · ${escapeHtml(item.captured_at || "unknown time")}</p>
        <p>${escapeHtml(item.workflow || item.notes || item.transcript || "No summary captured yet.")}</p>
      </article>
    `)
    .join("");
}

function renderRevenue(revenue) {
  if (!revenueRecommendation || !revenueList) {
    return;
  }

  revenueRecommendation.textContent = revenue.recommendation || "No adjacent revenue recommendation loaded yet.";
  const items = revenue.items || [];
  if (!items.length) {
    revenueList.innerHTML = `
      <div class="list-item">
        <h3>No revenue opportunities loaded</h3>
        <p class="meta">The heartbeat will populate strategy/revenue-opportunities.json as research matures.</p>
      </div>
    `;
    return;
  }

  revenueList.innerHTML = items
    .map((item) => `
      <article class="list-item opportunity-card">
        <div class="wave-card-head">
          <div>
            <h3>${escapeHtml(item.rank || "")}. ${escapeHtml(item.service_line || "Service line")}</h3>
            <p class="meta">${escapeHtml(item.target_customer || "Target customer TBD")} · ${escapeHtml(item.delivery_complexity || "complexity TBD")}</p>
          </div>
          <span class="chip">${escapeHtml(item.pricing_hypothesis || "pricing TBD")}</span>
        </div>
        <p><strong>Pain:</strong> ${escapeHtml(item.pain || "Not defined.")}</p>
        <p><strong>Offer:</strong> ${escapeHtml(item.offer || "Not defined.")}</p>
        <p class="meta"><strong>Risk:</strong> ${escapeHtml(item.risk || "Not defined.")}</p>
        <p class="meta"><strong>Next:</strong> ${escapeHtml(item.next_validation_step || "No validation step set.")}</p>
      </article>
    `)
    .join("");
}

function money(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "n/a";
  return `$${number.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function renderCryptoLab(cryptoLab) {
  if (!cryptoLabGrid || !cryptoLabDetail) {
    return;
  }

  const prices = cryptoLab.prices_usd || {};
  cryptoLabGrid.innerHTML = [
    tile("Overall", cryptoLab.ok ? "ready" : "missing"),
    tile("Report age", formatAge(cryptoLab.state_age_seconds)),
    tile("Power rate", cryptoLab.electricity_usd_per_kwh ? `${money(cryptoLab.electricity_usd_per_kwh)}/kWh` : "unknown"),
    tile("Best PoW net/mo", money(cryptoLab.best_pow_net_monthly_usd)),
    tile("Best PoS net/mo", money(cryptoLab.best_staking_monthly_usd)),
    tile("Best compute net/mo", money(cryptoLab.best_compute_monthly_usd)),
    tile("BTC", money(prices.bitcoin)),
    tile("ETH", money(prices.ethereum)),
    tile("XMR", money(prices.monero)),
  ].join("");

  const powRows = (cryptoLab.proof_of_work || []).slice(0, 3);
  const stakeRows = (cryptoLab.proof_of_stake || []).slice(0, 2);
  const computeRows = (cryptoLab.compute_market || []).slice(0, 2);
  const rowMarkup = (rows, valueKey) => rows
    .map((item) => `
      <span class="chip ${Number(item[valueKey] || 0) > 0 ? "chip-good" : "chip-warn"}">
        ${escapeHtml(item.name || item.id || "scenario")}: ${money(item[valueKey])}
      </span>
    `)
    .join("");

  cryptoLabDetail.innerHTML = `
    <article class="list-item crypto-verdict">
      <div class="wave-card-head">
        <div>
          <h3>Current lab verdict</h3>
          <p class="meta">${escapeHtml(cryptoLab.generated_at || "No report time")} · ${escapeHtml(cryptoLab.html_path || "No HTML report path")}</p>
        </div>
        <span class="chip">${cryptoLab.html_exists ? "HTML ready" : "HTML missing"}</span>
      </div>
      <p>${escapeHtml(cryptoLab.verdict || "No verdict available.")}</p>
      <p class="meta">${escapeHtml(cryptoLab.guardrail || "")}</p>
    </article>
    <article class="list-item">
      <h3>Scenario comparison</h3>
      <div class="chips">${rowMarkup(powRows, "net_monthly_usd")}</div>
      <div class="chips">${rowMarkup(stakeRows, "risk_adjusted_monthly_usd")}</div>
      <div class="chips">${rowMarkup(computeRows, "net_monthly_usd")}</div>
    </article>
  `;
}

async function handleCryptoLabRefresh() {
  if (!refreshCryptoLabButton) return;
  try {
    refreshCryptoLabButton.disabled = true;
    refreshCryptoLabButton.textContent = "Refreshing...";
    const result = await request("/api/crypto-lab/refresh", {
      method: "POST",
      body: JSON.stringify({}),
    });
    renderCryptoLab(result.crypto_lab || {});
  } catch (error) {
    cryptoLabDetail.innerHTML = `<div class="list-item attention-item"><h3>Crypto lab refresh failed</h3><p class="meta">${escapeHtml(error.message)}</p></div>`;
  } finally {
    refreshCryptoLabButton.disabled = false;
    refreshCryptoLabButton.textContent = "Refresh Lab";
  }
}

async function handleInboxTransition(event) {
  const button = event.target.closest("[data-inbox-transition]");
  if (!button) return;

  const stem = button.dataset.inboxTransition;
  const targetState = button.dataset.targetState;
  if (!stem || !targetState) return;

  try {
    button.disabled = true;
    button.textContent = targetState === "closed" ? "Closing..." : "Marking...";
    await request(`/api/inbox/${stem}/transition`, {
      method: "POST",
      body: JSON.stringify({ target_state: targetState }),
    });
    await refreshAll();
  } catch (error) {
    messageViewer.innerHTML = `<div class="list-item"><h3>Inbox update failed</h3><p class="meta">${escapeHtml(error.message)}</p></div>`;
    focusViewer();
  }
}

async function refreshAll() {
  const [status, decisions, agents, waves, leads, outreach, inbox] = await Promise.all([
    request("/api/status"),
    request("/api/decisions"),
    request("/api/agents"),
    request("/api/outreach/waves?limit=8"),
    request("/api/leads?limit=8"),
    request("/api/outreach/recent?limit=20"),
    request("/api/inbox/recent?limit=6"),
  ]);

  window.latestStatus = status;
  renderStatus(status);
  renderWatchdog(status.watchdog || {});
  renderOwnedOps(status.owned_ops || {});
  renderAgentInterop(status.agent_interop || {});
  renderOrchestrator(status.orchestrator || {});
  renderBusinessReadiness(status.business_readiness || {});
  renderFollowups(status.follow_up_pipeline || {});
  renderPending(decisions.pending || []);
  renderNextActions(status.next_actions || []);
  renderAgents(agents.items || []);
  renderWaves(waves.items || []);
  renderLeads(leads.items || []);
  renderPacketList(draftList, outreach.draft || [], "draft", "No draft packets", "Generate or review a new packet and it will show up here.");
  renderPacketList(reviewList, outreach.review || [], "review", "No review packets", "When the next outreach wave is staged, it will show up here for approval.");
  renderPacketList(approvedList, outreach.approved || [], "approved", "No ready-to-send packets", "Approve reviewed packets first. Sending still requires a final confirmation.", 20);
  renderPacketList(sentList, outreach.sent || [], "sent", "No sent packets", "When reviewed outreach goes out, it will show up here.");
  renderInbox(inbox.items || []);
  renderVoice(status.voice_agent || {});
  renderRevenue(status.revenue_opportunities || {});
  renderCryptoLab(status.crypto_lab || {});

  const defaultPacket =
    (outreach.approved || [])[0] ||
    (outreach.review || [])[0] ||
    (outreach.sent || [])[0] ||
    (outreach.draft || [])[0];
  if (defaultPacket) {
    try {
      const queue =
        (outreach.approved || []).length ? "approved" :
        (outreach.review || []).length ? "review" :
        (outreach.sent || []).length ? "sent" :
        "draft";
      const detail = await request(`/api/outreach/${queue}/${defaultPacket.stem}`);
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
    focusViewer();
  } catch (error) {
    messageViewer.innerHTML = `<div class="list-item"><h3>Viewer load failed</h3><p class="meta">${error.message}</p></div>`;
    focusViewer();
  }
}

async function handleWaveReview(event) {
  const button = event.target.closest("[data-review-wave]");
  if (!button) return;

  const stem = button.dataset.firstStem;
  const queue = button.dataset.firstQueue;
  if (!stem || !queue) return;

  messageViewer.innerHTML = `<div class="list-item"><h3>Loading packet</h3><p class="meta">Opening the first packet in this wave.</p></div>`;
  focusViewer();
  try {
    const detail = await request(`/api/outreach/${queue}/${stem}`);
    renderPacketViewer(detail);
  } catch (error) {
    messageViewer.innerHTML = `<div class="list-item"><h3>Viewer load failed</h3><p class="meta">${error.message}</p></div>`;
  }
}

async function handlePacketTransition(event) {
  const button = event.target.closest("[data-transition-packet]");
  if (!button) return;

  const stem = button.dataset.transitionPacket;
  const fromQueue = button.dataset.fromQueue;
  const toQueue = button.dataset.toQueue;
  const confirmed = window.confirm(`Move ${stem} from ${fromQueue} to ${toQueue}?`);
  if (!confirmed) return;

  try {
    messageViewer.innerHTML = `<div class="list-item"><h3>Updating packet</h3><p class="meta">Moving ${stem} to ${toQueue}.</p></div>`;
    focusViewer();
    await request(`/api/outreach/${fromQueue}/${stem}/transition`, {
      method: "POST",
      body: JSON.stringify({ target_state: toQueue }),
    });
    await refreshAll();
  } catch (error) {
    messageViewer.innerHTML = `<div class="list-item"><h3>Queue update failed</h3><p class="meta">${error.message}</p></div>`;
    focusViewer();
  }
}

async function sendPackets(stems) {
  if (!stems.length) return;
  renderSendConfirmation({
    type: "packets",
    stems,
    count: stems.length,
  });
}

async function executePendingSend() {
  if (!pendingSendRequest) {
    messageViewer.innerHTML = `<div class="list-item"><h3>No pending send</h3><p class="meta">Click Send Approved or Send Ready Packets first.</p></div>`;
    focusViewer();
    return;
  }

  const sendRequest = pendingSendRequest;
  pendingSendRequest = null;

  try {
    const endpoint = sendRequest.type === "wave"
      ? `/api/outreach/waves/${sendRequest.waveStem}/send`
      : "/api/outreach/send";
    const body = sendRequest.type === "wave"
      ? { confirmed: true }
      : { stems: sendRequest.stems || [], confirmed: true };

    messageViewer.innerHTML = `<div class="list-item"><h3>Sending approved packets</h3><p class="meta">The M4 is sending now. Keep this page open until the result appears.</p></div>`;
    focusViewer();

    const result = await request(endpoint, {
      method: "POST",
      body: JSON.stringify(body),
    });
    const sentCount = result.sent_count || 0;
    messageViewer.innerHTML = `<div class="list-item"><h3>Send complete</h3><p class="meta">${sentCount} packet${sentCount === 1 ? "" : "s"} sent.</p></div>`;
    await refreshAll();
  } catch (error) {
    messageViewer.innerHTML = `<div class="list-item"><h3>Send failed</h3><p class="meta">${error.message}</p></div>`;
    focusViewer();
  }
}

async function handleSendConfirmation(event) {
  const confirmButton = event.target.closest("[data-confirm-send]");
  const cancelButton = event.target.closest("[data-cancel-send]");
  if (confirmButton) {
    confirmButton.disabled = true;
    confirmButton.textContent = "Sending...";
    await executePendingSend();
    return;
  }
  if (cancelButton) {
    pendingSendRequest = null;
    messageViewer.innerHTML = `<div class="list-item"><h3>Send cancelled</h3><p class="meta">No prospect emails were sent.</p></div>`;
    focusViewer();
  }
}

async function handlePacketSend(event) {
  const button = event.target.closest("[data-send-packet]");
  if (!button) return;
  await sendPackets([button.dataset.sendPacket]);
}

async function handleApprovedBatchSend() {
  try {
    const outreach = await request("/api/outreach/recent?limit=20");
    const stems = (outreach.approved || []).map((item) => item.stem);
    if (!stems.length) {
      messageViewer.innerHTML = `<div class="list-item"><h3>No approved packets</h3><p class="meta">Move one or more packets into approved before sending.</p></div>`;
      return;
    }
    await sendPackets(stems);
  } catch (error) {
    messageViewer.innerHTML = `<div class="list-item"><h3>Batch load failed</h3><p class="meta">${error.message}</p></div>`;
  }
}

async function prepareWave(daysFromToday) {
  const packetDate = localDateIso(daysFromToday);
  const label = daysFromToday === 0 ? "today" : "tomorrow";
  messageViewer.innerHTML = `<div class="list-item"><h3>Preparing ${label}'s wave</h3><p class="meta">The M4 is selecting leads and generating personalized packets.</p></div>`;
  try {
    const result = await request("/api/outreach/waves/prepare", {
      method: "POST",
      body: JSON.stringify({ packet_date: packetDate, limit: 10 }),
    });
    const wave = result.wave || {};
    messageViewer.innerHTML = `<div class="list-item"><h3>Wave prepared</h3><p class="meta">${wave.scheduled_date || packetDate} · ${wave.total_packets || 0} packets staged for review.</p></div>`;
    await refreshAll();
  } catch (error) {
    messageViewer.innerHTML = `<div class="list-item"><h3>Wave prep failed</h3><p class="meta">${error.message}</p></div>`;
  }
}

async function handleWaveApprove(event) {
  const button = event.target.closest("[data-approve-wave]");
  if (!button) return;

  const waveStem = button.dataset.approveWave;
  const reviewCount = Number(button.dataset.reviewCount || 0);
  const confirmed = window.confirm(`Move ${reviewCount} reviewed packet${reviewCount === 1 ? "" : "s"} from this wave into approved?`);
  if (!confirmed) return;

  try {
    button.disabled = true;
    button.textContent = "Approving...";
    messageViewer.innerHTML = `<div class="list-item"><h3>Approving wave</h3><p class="meta">Moving reviewed packets into Ready to Send. This does not send email.</p></div>`;
    focusViewer();
    const result = await request(`/api/outreach/waves/${waveStem}/approve`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    await refreshAll();
    messageViewer.innerHTML = `<div class="list-item"><h3>Wave approved</h3><p class="meta">${result.moved_count || 0} packet${result.moved_count === 1 ? "" : "s"} moved into Ready to Send. Use Send Approved only after final confirmation.</p></div>`;
    focusViewer();
  } catch (error) {
    button.disabled = false;
    button.textContent = "Approve Reviewed Wave";
    messageViewer.innerHTML = `<div class="list-item"><h3>Wave approval failed</h3><p class="meta">${error.message}</p></div>`;
    focusViewer();
  }
}

async function handleWaveSend(event) {
  const button = event.target.closest("[data-send-wave]");
  if (!button) return;

  const waveStem = button.dataset.sendWave;
  const approvedCount = Number(button.dataset.approvedCount || 0);
  if (!approvedCount) {
    messageViewer.innerHTML = `<div class="list-item"><h3>No approved packets</h3><p class="meta">Approve this wave before sending.</p></div>`;
    focusViewer();
    return;
  }
  renderSendConfirmation({
    type: "wave",
    waveStem,
    count: approvedCount,
  });
}

refreshButton.addEventListener("click", refreshAll);
refreshCryptoLabButton?.addEventListener("click", handleCryptoLabRefresh);
prepareTodayWaveButton.addEventListener("click", () => prepareWave(0));
prepareTomorrowWaveButton.addEventListener("click", () => prepareWave(1));
sendApprovedBatchButton.addEventListener("click", handleApprovedBatchSend);
sendPromptButton.addEventListener("click", handlePrompt);
pendingDecisions.addEventListener("click", handleDecisionTransition);
waveList.addEventListener("click", handlePacketOpen);
waveList.addEventListener("click", handleWaveReview);
waveList.addEventListener("click", handleWaveApprove);
waveList.addEventListener("click", handleWaveSend);
waveList.addEventListener("click", handlePacketTransition);
waveList.addEventListener("click", handlePacketSend);
draftList.addEventListener("click", handlePacketOpen);
reviewList.addEventListener("click", handlePacketOpen);
reviewList.addEventListener("click", handlePacketTransition);
approvedList.addEventListener("click", handlePacketOpen);
approvedList.addEventListener("click", handlePacketTransition);
approvedList.addEventListener("click", handlePacketSend);
sentList.addEventListener("click", handlePacketOpen);
messageViewer.addEventListener("click", handleSendConfirmation);
inboxList.addEventListener("click", handleInboxTransition);

promptBox.value = "Give me a concise operator summary of the current JVT state and the best next action.";
refreshAll().catch((error) => {
  responseBox.textContent = `Initial load failed: ${error.message}`;
});

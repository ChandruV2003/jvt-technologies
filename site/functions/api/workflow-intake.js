const SERVICE_LABELS = {
  "ai-voice-intake": "AI receptionist / intake",
  "meeting-to-action": "Meeting-to-action packets",
  "inbox-document-triage": "Inbox / document triage",
  "workflow-automation": "Workflow cleanup / automation",
  "private-doc-intel": "Private document assistant",
  "document-generation": "Document generation",
  "managed-ai-ops": "Managed AI operations",
};

const SERVICE_ALIASES = new Map([
  ...Object.keys(SERVICE_LABELS).map((slug) => [slug, slug]),
  ["ai receptionist", "ai-voice-intake"],
  ["voice intake", "ai-voice-intake"],
  ["intake", "ai-voice-intake"],
  ["meeting", "meeting-to-action"],
  ["meeting notes", "meeting-to-action"],
  ["meeting-to-action packets", "meeting-to-action"],
  ["inbox", "inbox-document-triage"],
  ["document triage", "inbox-document-triage"],
  ["inbox triage", "inbox-document-triage"],
  ["workflow", "workflow-automation"],
  ["workflow cleanup", "workflow-automation"],
  ["automation", "workflow-automation"],
  ["document assistant", "private-doc-intel"],
  ["private document assistant", "private-doc-intel"],
  ["knowledge assistant", "private-doc-intel"],
  ["document generation", "document-generation"],
  ["managed ai ops", "managed-ai-ops"],
  ["not sure", "managed-ai-ops"],
]);

const EMAIL_RE = /^[A-Z0-9._%+\-']+@[A-Z0-9.\-]+\.[A-Z]{2,63}$/i;
const SUBMISSION_ID_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{10,79}$/;
const PLACEHOLDER_RE = /^(test|example|sample|placeholder|todo|tbd|n\/a|na|none|unknown|your name|your company|company|first last|john doe|jane doe|asdf|qwerty)$/i;
const PLACEHOLDER_EMAIL_DOMAINS = new Set(["example.com", "example.org", "example.net", "test.com", "test.org", "invalid", "localhost"]);
const FREE_MAIL_DOMAINS = new Set(["aol.com", "gmail.com", "hotmail.com", "icloud.com", "live.com", "mail.com", "me.com", "msn.com", "outlook.com", "proton.me", "protonmail.com", "yahoo.com"]);
const BLOCKED_LOCAL_PARTS = new Set(["admin", "career", "careers", "employment", "example", "hr", "jobs", "marketing", "no-reply", "noreply", "recruiting", "resumes", "seo", "support", "talent", "test", "user", "webmaster"]);
const ATTACHMENT_KEYS = new Set(["attachment", "attachments", "document", "documents", "file", "files", "upload", "uploads", "resume"]);
const MAX_BODY_BYTES = 16 * 1024;
const RATE_LIMIT_WRITES = 60;
const RATE_LIMIT_TTL_SECONDS = 2 * 60 * 60;
const EVENT_TTL_SECONDS = 90 * 24 * 60 * 60;
const SUBMISSION_TTL_SECONDS = 365 * 24 * 60 * 60;
const SENSITIVE_PATTERNS = [
  /\b(password|passcode|secret|api[_ -]?key|token|credential)s?\s*(?:is|=|:)\s*\S+/i,
  /\b\d{3}-\d{2}-\d{4}\b/,
  /\b(?:\d[ -]*?){13,19}\b/,
  /\b(?:routing number|bank account(?: number)?|card number|cvv)\s*(?:is|=|:)\s*\S+/i,
  /\b(attached|attachment|uploaded|uploading)\b/i,
];

function jsonResponse(payload, status = 200, origin = "") {
  const headers = {
    "content-type": "application/json; charset=utf-8",
    "access-control-allow-headers": "content-type",
    "access-control-allow-methods": "POST, OPTIONS",
    "vary": "Origin",
  };
  if (origin) headers["access-control-allow-origin"] = origin;
  return new Response(JSON.stringify(payload, null, 2), {
    status,
    headers,
  });
}

function cleanText(value, limit = 1000) {
  return String(value || "").replace(/\s+/g, " ").trim().slice(0, limit);
}

function cleanEmail(value) {
  return cleanText(value, 254).toLowerCase();
}

function cleanSubmissionId(value) {
  const raw = cleanText(value, 100);
  return SUBMISSION_ID_RE.test(raw) ? raw : "";
}

function normalizeUrl(value) {
  const raw = cleanText(value, 500);
  if (!raw) return "";
  try {
    const parsed = new URL(raw);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? `${parsed.origin}${parsed.pathname}` : "";
  } catch {
    return "";
  }
}

function allowedOrigin(request) {
  const requestOrigin = new URL(request.url).origin;
  const origin = cleanText(request.headers.get("origin"), 300);
  if (origin && origin !== requestOrigin) {
    throw validationError("origin_not_allowed", "This form only accepts same-site requests.", 403);
  }
  return origin || requestOrigin;
}

function serviceSlug(value) {
  return SERVICE_ALIASES.get(cleanText(value, 120).toLowerCase()) || "";
}

function sourceAttribution(payload) {
  const sourceUrl = normalizeUrl(payload.source_url || payload.page_url);
  let params = new URLSearchParams();
  let pagePath = cleanText(payload.page_path, 240);
  if (sourceUrl) {
    const parsed = new URL(sourceUrl);
    params = parsed.searchParams;
    pagePath = pagePath || parsed.pathname;
  }
  const param = (name) => cleanText(payload[name] || params.get(name), 160);
  return {
    source: cleanText(payload.source || "public-site-workflow-intake", 80),
    source_url: sourceUrl,
    page_path: pagePath,
    referrer: normalizeUrl(payload.referrer),
    utm_source: param("utm_source"),
    utm_medium: param("utm_medium"),
    utm_campaign: param("utm_campaign"),
    utm_term: param("utm_term"),
    utm_content: param("utm_content"),
  };
}

async function sha256(value) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function validationError(code, message, status = 400) {
  const error = new Error(message);
  error.code = code;
  error.status = status;
  return error;
}

function rejectUnsafePayload(payload) {
  const keys = Object.keys(payload).map((key) => key.toLowerCase());
  if (keys.some((key) => ATTACHMENT_KEYS.has(key))) {
    throw validationError("attachments_not_allowed", "Do not upload or attach files through this form.");
  }
  const text = ["name", "company", "problem_description", "preferred_next_step", "notes"]
    .map((key) => cleanText(payload[key], 1400))
    .join(" ");
  if (SENSITIVE_PATTERNS.some((pattern) => pattern.test(text))) {
    throw validationError("sensitive_details_not_allowed", "Describe the workflow without credentials, payment data, health details, or attachments.");
  }
}

function validateBusinessEmail(email) {
  if (!EMAIL_RE.test(email)) {
    throw validationError("invalid_email", "Use a valid public business email address.");
  }
  const [local, domain] = email.split("@");
  if (domain === "jvt-technologies.com" || email === "hello@jvt-technologies.com") {
    throw validationError("internal_email", "Use a non-JVT public business email address.");
  }
  if (PLACEHOLDER_EMAIL_DOMAINS.has(domain) || domain.endsWith(".invalid")) {
    throw validationError("placeholder_email", "Use a real public business email address.");
  }
  if (BLOCKED_LOCAL_PARTS.has(local) || local.startsWith("no-reply") || local.startsWith("noreply")) {
    throw validationError("blocked_email", "Use a person or shared public business inbox, not a system address.");
  }
  if (FREE_MAIL_DOMAINS.has(domain)) {
    throw validationError("personal_email", "Use a public business email address for the company.");
  }
}

async function validateSubmission(payload) {
  rejectUnsafePayload(payload);
  const submissionId = cleanSubmissionId(payload.submission_id);
  const name = cleanText(payload.name, 100);
  const email = cleanEmail(payload.public_business_email || payload.email);
  const company = cleanText(payload.company, 140);
  const slug = serviceSlug(payload.workflow_type || payload.service_interest);
  const problem = cleanText(payload.problem_description, 1400);
  const preferredNextStep = cleanText(payload.preferred_next_step, 80).toLowerCase();

  if (!submissionId) throw validationError("invalid_submission_id", "Refresh the page and try again.");
  if (!name || name.length < 2 || PLACEHOLDER_RE.test(name)) throw validationError("invalid_name", "Use your real name.");
  if (!company || company.length < 2 || PLACEHOLDER_RE.test(company)) throw validationError("invalid_company", "Use the company name.");
  validateBusinessEmail(email);
  if (!slug) throw validationError("invalid_service_interest", "Choose the workflow type that is closest to the problem.");
  if (problem.length < 35 || PLACEHOLDER_RE.test(problem)) {
    throw validationError("short_problem_description", "Describe the workflow problem in one or two short sentences.");
  }
  const dedupeKey = await sha256(`${email}|${company.toLowerCase()}|${slug}|${problem.toLowerCase().replace(/\s+/g, " ")}`);
  return {
    submission_id: submissionId,
    contact: { name, email, company },
    service_slug: slug,
    service_interest: SERVICE_LABELS[slug],
    problem_description: problem,
    preferred_next_step: ["email", "call", "demo", "scope", "not-sure"].includes(preferredNextStep) ? preferredNextStep : "",
    dedupe_key: dedupeKey,
    attribution: sourceAttribution(payload),
  };
}

async function parseBody(request) {
  const declaredLength = Number(request.headers.get("content-length") || 0);
  if (declaredLength > MAX_BODY_BYTES) {
    throw validationError("request_too_large", "Keep the workflow note under 16 KB.", 413);
  }
  const body = await request.arrayBuffer();
  if (body.byteLength > MAX_BODY_BYTES) {
    throw validationError("request_too_large", "Keep the workflow note under 16 KB.", 413);
  }
  const bodyText = new TextDecoder().decode(body);
  const contentType = (request.headers.get("content-type") || "").split(";")[0].trim().toLowerCase();
  if (contentType.startsWith("multipart/")) {
    throw validationError("attachments_not_allowed", "File uploads are not accepted.", 415);
  }
  if (!contentType || contentType === "application/json") {
    try {
      return JSON.parse(bodyText || "{}");
    } catch {
      throw validationError("invalid_json", "Request body must be valid JSON.");
    }
  }
  if (contentType === "application/x-www-form-urlencoded") {
    return Object.fromEntries(new URLSearchParams(bodyText).entries());
  }
  throw validationError("unsupported_content_type", "Submit JSON or form data only.", 415);
}

async function enforceRateLimit(request, env) {
  const address = cleanText(request.headers.get("cf-connecting-ip") || "unknown", 100);
  const hour = new Date().toISOString().slice(0, 13);
  const key = `rate:${await sha256(`${address}|${hour}`)}`;
  const current = Number(await env.JVT_CONVERSION_INTAKE.get(key) || 0);
  if (current >= RATE_LIMIT_WRITES) {
    throw validationError("rate_limited", "Too many form requests. Try again later.", 429);
  }
  await env.JVT_CONVERSION_INTAKE.put(key, String(current + 1), { expirationTtl: RATE_LIMIT_TTL_SECONDS });
}

async function handleEvent(payload, env, eventType) {
  const submissionId = cleanSubmissionId(payload.submission_id);
  if (!submissionId) throw validationError("invalid_submission_id", "Missing form session identifier.");
  const now = new Date().toISOString();
  const key = `event:${eventType}:${submissionId}`;
  const existing = await env.JVT_CONVERSION_INTAKE.get(key, "json");
  if (existing) {
    return jsonResponse({ ok: true, event_type: eventType, submission_id: submissionId, already_seen: true });
  }
  const record = {
    schema_version: 1,
    event_type: eventType,
    submission_id: submissionId,
    created_at: now,
    attribution: sourceAttribution(payload),
    service_slug: serviceSlug(payload.service_interest || payload.workflow_type),
    metrics_countable: true,
  };
  await env.JVT_CONVERSION_INTAKE.put(key, JSON.stringify(record), { expirationTtl: EVENT_TTL_SECONDS });
  await env.JVT_CONVERSION_INTAKE.put(
    `event-log:${now}:${eventType}:${submissionId}`,
    JSON.stringify(record),
    { expirationTtl: EVENT_TTL_SECONDS },
  );
  return jsonResponse({ ok: true, event_type: eventType, submission_id: submissionId, already_seen: false });
}

async function handleSubmission(payload, env) {
  const normalized = await validateSubmission(payload);
  const now = new Date().toISOString();
  const submissionKey = `submission:${normalized.submission_id}`;
  const existing = await env.JVT_CONVERSION_INTAKE.get(submissionKey, "json");
  if (existing) {
    if (existing.dedupe_key !== normalized.dedupe_key) {
      throw validationError("conflicting_submission_id", "This form session has conflicting submission data.", 409);
    }
    return jsonResponse({
      ok: true,
      submission_id: existing.submission_id,
      status: existing.status || "qualified",
      duplicate: Boolean(existing.duplicate),
      idempotent: true,
      message: "Already received. No duplicate work was created.",
    });
  }

  const dedupeKey = `dedupe:${normalized.dedupe_key}`;
  const duplicateOf = await env.JVT_CONVERSION_INTAKE.get(dedupeKey);
  const duplicate = Boolean(duplicateOf && duplicateOf !== normalized.submission_id);
  const record = {
    schema_version: 1,
    source: "public-site-workflow-intake",
    submission_id: normalized.submission_id,
    dedupe_key: normalized.dedupe_key,
    status: duplicate ? "duplicate" : "qualified",
    qualified: !duplicate,
    duplicate,
    duplicate_of: duplicateOf || "",
    metrics_countable: !duplicate,
    created_at: now,
    updated_at: now,
    contact: normalized.contact,
    service_slug: normalized.service_slug,
    service_interest: normalized.service_interest,
    problem_description: normalized.problem_description,
    preferred_next_step: normalized.preferred_next_step,
    attribution: normalized.attribution,
    guardrail: "Internal first-party intake only. No prospect email, public post, purchase, account change, financial action, or external commitment was made.",
  };
  if (!duplicate) {
    await env.JVT_CONVERSION_INTAKE.put(
      dedupeKey,
      normalized.submission_id,
      { expirationTtl: SUBMISSION_TTL_SECONDS },
    );
  }
  await env.JVT_CONVERSION_INTAKE.put(
    submissionKey,
    JSON.stringify(record),
    { expirationTtl: SUBMISSION_TTL_SECONDS },
  );
  await env.JVT_CONVERSION_INTAKE.put(`event-log:${now}:submission:${normalized.submission_id}`, JSON.stringify({
    event_type: "submission",
    submission_id: normalized.submission_id,
    status: record.status,
    qualified: record.qualified,
    duplicate: record.duplicate,
    service_slug: record.service_slug,
    created_at: now,
  }), { expirationTtl: SUBMISSION_TTL_SECONDS });
  return jsonResponse({
    ok: true,
    submission_id: record.submission_id,
    status: record.status,
    qualified: record.qualified,
    duplicate: record.duplicate,
    idempotent: false,
    message: duplicate ? "Already received. No duplicate work was created." : "Received. JVT will review this before any external follow-up.",
  });
}

export async function onRequestOptions({ request }) {
  try {
    const origin = allowedOrigin(request);
    return jsonResponse({ ok: true }, 200, origin);
  } catch (error) {
    return jsonResponse({ ok: false, error: error.code, message: error.message }, error.status || 403);
  }
}

export async function onRequestPost({ request, env }) {
  if (!env.JVT_CONVERSION_INTAKE) {
    return jsonResponse({ ok: false, error: "missing_binding", message: "Cloudflare KV binding JVT_CONVERSION_INTAKE is required." }, 500);
  }
  try {
    const origin = allowedOrigin(request);
    await enforceRateLimit(request, env);
    const payload = await parseBody(request);
    const eventType = cleanText(payload.event_type, 40).toLowerCase();
    if (eventType === "view" || eventType === "start") {
      const response = await handleEvent(payload, env, eventType);
      response.headers.set("access-control-allow-origin", origin);
      response.headers.set("vary", "Origin");
      return response;
    }
    const response = await handleSubmission(payload, env);
    response.headers.set("access-control-allow-origin", origin);
    response.headers.set("vary", "Origin");
    return response;
  } catch (error) {
    return jsonResponse({
      ok: false,
      error: error.code || "invalid_request",
      message: error.message || "Could not capture the workflow intake.",
    }, error.status || 400);
  }
}

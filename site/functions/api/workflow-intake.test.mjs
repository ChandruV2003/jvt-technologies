import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

const sourceUrl = new URL("./workflow-intake.js", import.meta.url);
const source = await fs.readFile(sourceUrl, "utf8");
const worker = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);

class MockKv {
  constructor() {
    this.values = new Map();
    this.options = new Map();
  }

  async get(key, mode) {
    const value = this.values.get(key);
    if (value === undefined) return null;
    return mode === "json" ? JSON.parse(value) : value;
  }

  async put(key, value, options = {}) {
    this.values.set(key, value);
    this.options.set(key, options);
  }
}

function validPayload(id = "wfintake_worker_test_alpha") {
  return {
    submission_id: id,
    name: "Avery Morgan",
    public_business_email: "avery@rivercitydentalops.com",
    company: "River City Dental Ops",
    service_interest: "ai-voice-intake",
    problem_description: "We miss patient appointment calls and need a clean callback packet for the office team.",
    preferred_next_step: "email",
    source_url: "https://jvt-technologies.com/?utm_source=test",
  };
}

function request(payload, headers = {}) {
  return new Request("https://jvt-technologies.com/api/workflow-intake", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "origin": "https://jvt-technologies.com",
      "cf-connecting-ip": "192.0.2.10",
      ...headers,
    },
    body: JSON.stringify(payload),
  });
}

test("accepts an ordinary healthcare workflow and expires retained records", async () => {
  const kv = new MockKv();
  const response = await worker.onRequestPost({
    request: request(validPayload()),
    env: { JVT_CONVERSION_INTAKE: kv },
  });
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.qualified, true);
  assert.ok(kv.options.get(`submission:${body.submission_id}`).expirationTtl);
});

test("rejects cross-origin, oversized, and concrete sensitive values", async () => {
  const kv = new MockKv();
  const crossOrigin = await worker.onRequestPost({
    request: request(validPayload(), { origin: "https://attacker.example" }),
    env: { JVT_CONVERSION_INTAKE: kv },
  });
  assert.equal(crossOrigin.status, 403);

  const oversized = await worker.onRequestPost({
    request: request(validPayload(), { "content-length": "20000" }),
    env: { JVT_CONVERSION_INTAKE: kv },
  });
  assert.equal(oversized.status, 413);

  const sensitivePayload = validPayload("wfintake_worker_test_sensitive");
  sensitivePayload.problem_description = "Please use 123-45-6789 to find the record in our current workflow.";
  const sensitive = await worker.onRequestPost({
    request: request(sensitivePayload),
    env: { JVT_CONVERSION_INTAKE: kv },
  });
  assert.equal(sensitive.status, 400);
  assert.equal((await sensitive.json()).error, "sensitive_details_not_allowed");
});

test("same submission is idempotent and write rate is bounded", async () => {
  const kv = new MockKv();
  const first = await worker.onRequestPost({
    request: request(validPayload()),
    env: { JVT_CONVERSION_INTAKE: kv },
  });
  const second = await worker.onRequestPost({
    request: request(validPayload()),
    env: { JVT_CONVERSION_INTAKE: kv },
  });
  assert.equal(first.status, 200);
  assert.equal((await second.json()).idempotent, true);

  const rateKey = [...kv.values.keys()].find((key) => key.startsWith("rate:"));
  kv.values.set(rateKey, "60");
  const limited = await worker.onRequestPost({
    request: request(validPayload("wfintake_worker_test_limited")),
    env: { JVT_CONVERSION_INTAKE: kv },
  });
  assert.equal(limited.status, 429);
});

test("client rotates the submission id after success", async () => {
  const appSource = await fs.readFile(new URL("../../app.js", import.meta.url), "utf8");
  assert.match(appSource, /let submissionId = getSubmissionId\(\)/);
  assert.match(appSource, /const rotateSubmissionId = \(\) =>/);
  assert.match(appSource, /intakeForm\.reset\(\);\s*rotateSubmissionId\(\);/);
});

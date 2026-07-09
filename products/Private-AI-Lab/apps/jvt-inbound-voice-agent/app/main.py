from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape as xml_escape

import httpx
import websockets
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field


APP_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = APP_ROOT / "data"
CALL_ROOT = DATA_ROOT / "calls"
INTAKE_ROOT = DATA_ROOT / "intake"
VOICE_QUALITY_ROOT = APP_ROOT / "voice-quality"
VOICE_QUALITY_SAMPLES = VOICE_QUALITY_ROOT / "samples"
VOICE_QUALITY_SCRIPTS = VOICE_QUALITY_ROOT / "scripts"
VOICE_QUALITY_RENDERS = VOICE_QUALITY_ROOT / "renders"
VOICE_QUALITY_SCORECARDS = VOICE_QUALITY_ROOT / "scorecards"
VOICE_QUALITY_SCRIPT_PACK = VOICE_QUALITY_SCRIPTS / "chandru-style-script-pack.json"

OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime"
DEFAULT_PROMPT = """
You are JVT Technologies LLC's inbound AI receptionist.

Start by saying you are JVT's AI assistant. Never claim to be human.
Your job is to answer basic questions and collect enough information for a human follow-up.

JVT builds private AI systems for document-heavy work: private document assistants, cited answers over internal files, intake triage, workflow automation, and implementation pilots.

Keep responses short and conversational. Ask one question at a time.
If the caller provides a name, email, phone number, company name, or appointment detail, repeat it back and ask for confirmation.

Collect:
- caller name
- company
- email
- phone
- document-heavy workflow or admin problem
- industry
- timeline
- preferred callback window

Do not provide legal, tax, financial, medical, or investment advice.
Do not promise exact pricing, delivery dates, or project acceptance.
Do not accept confidential client documents over the phone.
If the caller asks for a commitment, say a person from JVT will review and follow up.
""".strip()

DEFAULT_VOICE_SAMPLE_SCRIPTS: List[Dict[str, str]] = [
    {
        "id": "warm-intro",
        "title": "Warm JVT intro",
        "category": "baseline",
        "text": "Hey, this is Chandru from JVT Technologies. The simplest way to explain what we do is this: we take repetitive office workflows and turn them into reviewed AI-assisted systems.",
    },
    {
        "id": "what-jvt-does",
        "title": "What JVT does",
        "category": "baseline",
        "text": "JVT is focused on practical AI systems for document-heavy teams. Not gimmicks. Intake, inbox triage, meeting notes, draft replies, and internal knowledge tools that still keep a person in the loop.",
    },
    {
        "id": "law-firm-safe-start",
        "title": "Law firm safe starting point",
        "category": "offer",
        "text": "For a law firm, I would not start with anything risky. I would start with intake, document triage, and follow-up drafts that a person reviews before anything goes out.",
    },
    {
        "id": "inbox-triage",
        "title": "Inbox triage explanation",
        "category": "offer",
        "text": "The inbox triage version is simple. We classify the message, pull out the actual request, flag anything missing, and prepare a draft response. Nothing sends unless a person reviews it.",
    },
    {
        "id": "meeting-to-action",
        "title": "Meeting-to-action explanation",
        "category": "offer",
        "text": "For meeting-to-action packets, the point is to stop losing decisions and follow-ups after calls. We turn the transcript into decisions, owners, missing items, and a clean follow-up draft.",
    },
    {
        "id": "ai-receptionist",
        "title": "AI receptionist explanation",
        "category": "offer",
        "text": "The AI receptionist is not there to pretend to be a person. It discloses that it is JVT's AI assistant, asks one question at a time, captures the request, and hands off anything sensitive.",
    },
    {
        "id": "written-outline",
        "title": "Offer written outline",
        "category": "follow-up",
        "text": "If easier, I can send a short written outline first instead of scheduling a call. Either path is fine on my end.",
    },
    {
        "id": "short-demo",
        "title": "Offer short demo",
        "category": "follow-up",
        "text": "The simplest next step would be a short walkthrough. Fifteen minutes is enough to show what the workflow looks like and decide if it is worth going deeper.",
    },
    {
        "id": "scope-boundary",
        "title": "Scope boundary",
        "category": "guardrail",
        "text": "I do not want the AI making commitments. The point is to capture the right information, keep the workflow moving, and hand off anything sensitive to a real person.",
    },
    {
        "id": "human-review",
        "title": "Human review boundary",
        "category": "guardrail",
        "text": "I can capture that, but Chandru would need to review it before we commit to scope, pricing, or a delivery timeline.",
    },
    {
        "id": "slow-down",
        "title": "Natural correction",
        "category": "cadence",
        "text": "Let me slow down and say that differently. The goal is not to replace the person who owns the workflow. The goal is to remove the repetitive back-and-forth around it.",
    },
    {
        "id": "email-spelling",
        "title": "Spelling an email",
        "category": "cadence",
        "text": "Could you spell the email address for me? I want to make sure I capture it correctly before I send anything over.",
    },
    {
        "id": "uncertain-handoff",
        "title": "Uncertain handoff",
        "category": "guardrail",
        "text": "I am not going to guess on that. I would rather capture the context and have a person review it than give you a half-answer.",
    },
    {
        "id": "farr-reply",
        "title": "Farr-style reply",
        "category": "reply",
        "text": "Thanks for the quick reply. The simplest next step would be a short walkthrough of what this could look like for intake, document triage, and reviewed response drafts.",
    },
    {
        "id": "pricing-soft",
        "title": "Pricing soft answer",
        "category": "guardrail",
        "text": "Pricing depends on the workflow and how much review is needed. I can give a starting range, but I would not want to quote final scope without looking at the actual process.",
    },
    {
        "id": "confidential-docs",
        "title": "Confidential document boundary",
        "category": "guardrail",
        "text": "Please do not send confidential client documents yet. For the first pass, a sample workflow or redacted example is enough to show whether the system makes sense.",
    },
    {
        "id": "quick-yes",
        "title": "Natural short yes",
        "category": "cadence",
        "text": "Yes, exactly. That is the kind of workflow where the small repetitive steps add up fast.",
    },
    {
        "id": "quick-no",
        "title": "Natural short no",
        "category": "cadence",
        "text": "No, I would not automate that part yet. I would keep that as a human decision and only automate the prep around it.",
    },
    {
        "id": "screen-share",
        "title": "Screen-share setup",
        "category": "demo",
        "text": "If we do a screen share, I can keep it focused. First the current workflow, then the proposed AI-assisted flow, then the exact point where a person reviews the output.",
    },
    {
        "id": "closing",
        "title": "Soft close",
        "category": "follow-up",
        "text": "If that sounds useful, I can send the outline and a couple of times that work. If not, no pressure at all.",
    },
]


class TestIntakeRequest(BaseModel):
    caller_name: str = ""
    company: str = ""
    email: str = ""
    phone: str = ""
    workflow: str = ""
    notes: str = ""


class CallRecord(BaseModel):
    call_id: str
    mode: str
    started_at: str
    ended_at: Optional[str] = None
    call_sid: str = ""
    stream_sid: str = ""
    media_events: int = 0
    transcript_fragments: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


app = FastAPI(title="JVT Inbound Voice Agent", version="0.1.0")


def truthy(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def env_value(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def realtime_model() -> str:
    return env_value("OPENAI_REALTIME_MODEL", "gpt-realtime")


def realtime_voice() -> str:
    return env_value("OPENAI_REALTIME_VOICE", "marin")


def response_engine() -> str:
    return env_value("JVT_VOICE_RESPONSE_ENGINE", "local-model-router").lower()


def local_audio_bridge_ready() -> bool:
    return truthy(env_value("JVT_VOICE_LOCAL_AUDIO_BRIDGE_READY", "0")) and local_audio_bridge_health().get("ok") is True


def local_audio_bridge_url() -> str:
    return env_value("JVT_VOICE_LOCAL_AUDIO_BRIDGE_URL", "ws://127.0.0.1:8761/twilio-media")


def local_audio_bridge_health_url() -> str:
    return env_value("JVT_VOICE_LOCAL_AUDIO_BRIDGE_HEALTH_URL", "http://127.0.0.1:8761/health")


def local_audio_bridge_health() -> Dict[str, Any]:
    url = local_audio_bridge_health_url()
    if not url:
        return {"ok": False, "error": "No local audio bridge health URL configured."}
    try:
        response = httpx.get(url, timeout=2.5)
        payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        return {
            "ok": response.status_code == 200 and bool(payload.get("ok", payload.get("ready", False))),
            "status_code": response.status_code,
            "url": url,
            "payload": payload,
        }
    except Exception as exc:
        return {"ok": False, "url": url, "error": str(exc)}


def dry_run_enabled() -> bool:
    if truthy(env_value("JVT_VOICE_DRY_RUN", "1")):
        return True
    return response_engine() in {"openai", "openai-realtime"} and not bool(env_value("OPENAI_API_KEY"))


def phone_provider_configured() -> bool:
    return truthy(env_value("JVT_VOICE_PHONE_PROVIDER_CONFIGURED", "0"))


def public_base_url() -> str:
    return env_value("JVT_VOICE_PUBLIC_BASE_URL").rstrip("/")


def media_stream_url() -> str:
    base_url = public_base_url()
    if not base_url:
        return ""
    if base_url.startswith("https://"):
        base_url = f"wss://{base_url.removeprefix('https://')}"
    elif base_url.startswith("http://"):
        base_url = f"ws://{base_url.removeprefix('http://')}"
    return f"{base_url}/twilio/media-stream"


def ensure_data_dirs() -> None:
    CALL_ROOT.mkdir(parents=True, exist_ok=True)
    INTAKE_ROOT.mkdir(parents=True, exist_ok=True)


def ensure_voice_quality_dirs() -> None:
    for path in (
        VOICE_QUALITY_ROOT,
        VOICE_QUALITY_SAMPLES,
        VOICE_QUALITY_SCRIPTS,
        VOICE_QUALITY_RENDERS,
        VOICE_QUALITY_SCORECARDS,
    ):
        path.mkdir(parents=True, exist_ok=True)
    if not VOICE_QUALITY_SCRIPT_PACK.exists():
        VOICE_QUALITY_SCRIPT_PACK.write_text(
            json.dumps(
                {
                    "generated_at": utc_now(),
                    "purpose": "Chandru-approved JVT voice sample script pack for voice-quality evaluation.",
                    "scripts": DEFAULT_VOICE_SAMPLE_SCRIPTS,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def load_voice_scripts() -> List[Dict[str, str]]:
    ensure_voice_quality_dirs()
    try:
        payload = json.loads(VOICE_QUALITY_SCRIPT_PACK.read_text(encoding="utf-8"))
        scripts = payload.get("scripts")
        if isinstance(scripts, list):
            return [
                {key: str(item.get(key, "")) for key in ("id", "title", "category", "text")}
                for item in scripts
                if isinstance(item, dict) and item.get("id") and item.get("text")
            ]
    except Exception:
        pass
    return DEFAULT_VOICE_SAMPLE_SCRIPTS


def voice_sample_summary() -> List[Dict[str, Any]]:
    ensure_voice_quality_dirs()
    items: List[Dict[str, Any]] = []
    for path in sorted(VOICE_QUALITY_SAMPLES.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        payload["metadata_path"] = str(path)
        items.append(payload)
    return items


def request_ip_candidates(request: Request) -> set[str]:
    host = (request.client.host if request.client else "") or ""
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    real_ip = request.headers.get("x-real-ip", "").strip()
    return {item for item in (host, forwarded, real_ip) if item}


def request_is_local(request: Request) -> bool:
    return bool(request_ip_candidates(request) & {"127.0.0.1", "::1", "localhost"})


def request_is_tailnet(request: Request) -> bool:
    tailnet_networks = (
        ipaddress.ip_network("100.64.0.0/10"),
        ipaddress.ip_network("fd7a:115c:a1e0::/48"),
    )
    for candidate in request_ip_candidates(request):
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if any(address in network for network in tailnet_networks):
            return True
    return False


def voice_recorder_write_allowed(request: Request) -> bool:
    if truthy(env_value("JVT_VOICE_RECORDER_ALLOW_REMOTE", "0")):
        return True
    if truthy(env_value("JVT_VOICE_RECORDER_ALLOW_TAILSCALE", "0")) and request_is_tailnet(request):
        return True
    return request_is_local(request)


def voice_recorder_read_allowed(request: Request) -> bool:
    if truthy(env_value("JVT_VOICE_RECORDER_ALLOW_REMOTE", "0")):
        return True
    return request_is_local(request) or request_is_tailnet(request)


def media_extension(content_type: str) -> str:
    normalized = content_type.lower()
    if "wav" in normalized:
        return "wav"
    if "mp4" in normalized or "m4a" in normalized:
        return "m4a"
    if "ogg" in normalized:
        return "ogg"
    return "webm"


def voice_quality_html() -> str:
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>JVT Voice Sample Recorder</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #050706;
      --panel: rgba(17, 24, 21, 0.88);
      --panel-2: rgba(31, 40, 35, 0.92);
      --line: rgba(255, 255, 255, 0.11);
      --text: #f6efe3;
      --muted: #b9b0a3;
      --gold: #f1c37b;
      --teal: #42d6c5;
      --blue: #668cff;
      --red: #ff7d68;
      font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--text);
      background:
        radial-gradient(circle at 20% 0%, rgba(66, 214, 197, 0.18), transparent 32rem),
        radial-gradient(circle at 90% 10%, rgba(241, 195, 123, 0.16), transparent 30rem),
        linear-gradient(135deg, #050706 0%, #0a1110 52%, #050706 100%);
      min-height: 100vh;
    }
    .shell { width: min(1180px, calc(100vw - 32px)); margin: 0 auto; padding: 42px 0 64px; }
    .hero {
      border: 1px solid var(--line);
      border-radius: 34px;
      padding: clamp(24px, 4vw, 52px);
      background: linear-gradient(145deg, rgba(18, 27, 24, 0.96), rgba(10, 14, 13, 0.86));
      box-shadow: 0 28px 90px rgba(0, 0, 0, 0.42);
    }
    .eyebrow { color: var(--gold); font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.22em; font-weight: 800; }
    h1 { margin: 14px 0 12px; font-size: clamp(2.35rem, 7vw, 5.8rem); line-height: 0.94; letter-spacing: -0.07em; }
    .lead { max-width: 780px; color: var(--muted); font-size: clamp(1.05rem, 2vw, 1.35rem); line-height: 1.7; }
    .grid { display: grid; grid-template-columns: 360px 1fr; gap: 18px; margin-top: 20px; }
    .card {
      border: 1px solid var(--line);
      border-radius: 26px;
      background: var(--panel);
      padding: 22px;
      box-shadow: 0 18px 60px rgba(0, 0, 0, 0.22);
    }
    .sticky { position: sticky; top: 18px; align-self: start; }
    .metric { display: flex; justify-content: space-between; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--line); }
    .metric:last-child { border-bottom: 0; }
    .metric span { color: var(--muted); }
    .metric strong { color: var(--text); }
    .script-list { display: grid; gap: 14px; }
    .script {
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 20px;
      background: var(--panel-2);
    }
    .script h2 { margin: 0 0 8px; font-size: 1.2rem; letter-spacing: -0.03em; }
    .script p { color: var(--text); line-height: 1.72; font-size: 1.08rem; }
    .tag { display: inline-flex; color: var(--teal); border: 1px solid rgba(66, 214, 197, 0.32); border-radius: 999px; padding: 5px 9px; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.12em; }
    .actions { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-top: 14px; }
    button, a.download {
      appearance: none;
      border: 0;
      border-radius: 999px;
      padding: 11px 16px;
      color: #07100f;
      background: var(--gold);
      font-weight: 800;
      cursor: pointer;
      text-decoration: none;
    }
    button.secondary, a.download { background: rgba(255,255,255,0.1); color: var(--text); border: 1px solid var(--line); }
    button.danger { background: var(--red); }
    button:disabled { opacity: 0.45; cursor: not-allowed; }
    audio { width: 100%; margin-top: 12px; }
    .status { color: var(--muted); font-size: 0.92rem; }
    .notice { border-left: 3px solid var(--teal); padding-left: 12px; color: var(--muted); line-height: 1.6; }
    .warn { border-left-color: var(--gold); }
    .saved { color: var(--teal); }
    .error { color: var(--red); }
    .input-control { display: grid; gap: 8px; margin: 16px 0; color: var(--muted); font-size: 0.9rem; }
    select {
      width: 100%;
      color: var(--text);
      background: rgba(255,255,255,0.08);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 10px 12px;
    }
    @media (max-width: 860px) { .grid { grid-template-columns: 1fr; } .sticky { position: static; } }
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <p class="eyebrow">JVT Voice Quality</p>
      <h1>Record the voice sample pack.</h1>
      <p class="lead">Use a quiet room, the same mic, and your normal speaking style. The goal is cadence, phrasing, pauses, corrections, and pronunciation. This recorder saves samples locally to the M4 for review.</p>
    </section>
    <section class="grid">
      <aside class="card sticky">
        <p class="eyebrow">Recording Rules</p>
        <div class="notice">
          Record only Chandru-approved speech. Do not use this to clone anyone else. Keep future JVT call flows disclosed as AI-assisted.
        </div>
        <div class="metric"><span>Mic access</span><strong id="micState">not started</strong></div>
        <div class="metric"><span>Scripts</span><strong id="scriptCount">0</strong></div>
        <div class="metric"><span>Saved takes</span><strong id="savedCount">0</strong></div>
        <div class="metric"><span>Write mode</span><strong id="writeMode">checking</strong></div>
        <div class="metric"><span>Input device</span><strong id="inputDevice">not selected</strong></div>
        <div class="metric"><span>Sample rate</span><strong id="sampleRate">target 192 kHz</strong></div>
        <label class="input-control">
          Audio input
          <select id="inputSelect">
            <option value="">Detect after mic permission</option>
          </select>
        </label>
        <button class="secondary" id="refreshDevices">Refresh audio devices</button>
        <p class="notice warn">Best setup: KVM into the M4 and open <code>http://127.0.0.1:8066/voice-quality</code>. Browser microphone recording is most reliable on localhost.</p>
        <p class="notice">Preferred input: Universal Audio Volt 276 / UA-276 input 1 with the SM7dB. The recorder requests 192 kHz, but Chrome/macOS may grant a lower actual sample rate; the granted settings are shown and saved with each take. For guaranteed input-1-only capture, use the local Mac Volt bridge helper.</p>
        <button id="startMic">Start mic</button>
      </aside>
      <section class="script-list" id="scripts"></section>
    </section>
  </main>
  <script>
    const state = {
      stream: null,
      activeRecorder: null,
      chunks: {},
      blobs: {},
      mimeType: "audio/webm",
      inputLabel: "",
      audioSettings: {}
    };

    const $ = (id) => document.getElementById(id);
    const setText = (id, value) => { $(id).textContent = value; };
    const preferredInputPatterns = [/volt\\s*276/i, /ua[-\\s]?276/i, /universal\\s+audio/i, /volt/i];
    const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => {
      if (char === "&") return "&amp;";
      if (char === "<") return "&lt;";
      if (char === ">") return "&gt;";
      if (char === '"') return "&quot;";
      return "&#39;";
    });

    function supportedMimeType() {
      const choices = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
      return choices.find((item) => window.MediaRecorder && MediaRecorder.isTypeSupported(item)) || "";
    }

    function preferredInput(devices) {
      return devices.find((device) => preferredInputPatterns.some((pattern) => pattern.test(device.label || "")));
    }

    function audioConstraints(deviceId = "") {
      const audio = {
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
        channelCount: { ideal: 1 },
        sampleRate: { ideal: 192000 },
        sampleSize: { ideal: 24 }
      };
      if (deviceId) audio.deviceId = { exact: deviceId };
      return { audio };
    }

    function updateAudioSettings() {
      const track = state.stream?.getAudioTracks?.()[0];
      const settings = track?.getSettings?.() || {};
      state.inputLabel = track?.label || settings.label || "browser default";
      state.audioSettings = settings;
      setText("inputDevice", state.inputLabel);
      setText("sampleRate", settings.sampleRate ? `${settings.sampleRate} Hz` : "not reported");
    }

    async function listInputs(selectPreferred = true) {
      if (!navigator.mediaDevices?.enumerateDevices) return [];
      const devices = await navigator.mediaDevices.enumerateDevices();
      const inputs = devices.filter((device) => device.kind === "audioinput");
      const currentValue = $("inputSelect").value;
      const preferred = preferredInput(inputs);
      $("inputSelect").innerHTML = [
        `<option value="">Browser default microphone</option>`,
        ...inputs.map((device, index) => {
          const label = device.label || `Audio input ${index + 1}`;
          return `<option value="${escapeHtml(device.deviceId)}">${escapeHtml(label)}</option>`;
        })
      ].join("");
      if (selectPreferred && preferred) {
        $("inputSelect").value = preferred.deviceId;
        setText("inputDevice", preferred.label);
      } else if (currentValue && inputs.some((device) => device.deviceId === currentValue)) {
        $("inputSelect").value = currentValue;
      }
      return inputs;
    }

    async function startMic() {
      if (!navigator.mediaDevices?.getUserMedia) {
        setText("micState", "unsupported");
        return;
      }
      state.stream?.getTracks?.().forEach((track) => track.stop());
      await listInputs(false);
      const selectedDeviceId = $("inputSelect").value;
      state.stream = await navigator.mediaDevices.getUserMedia(audioConstraints(selectedDeviceId));
      let inputs = await listInputs(true);
      const preferred = preferredInput(inputs);
      const currentLabel = state.stream.getAudioTracks()[0]?.label || "";
      if (preferred && preferred.deviceId !== selectedDeviceId && !preferredInputPatterns.some((pattern) => pattern.test(currentLabel))) {
        state.stream.getTracks().forEach((track) => track.stop());
        $("inputSelect").value = preferred.deviceId;
        state.stream = await navigator.mediaDevices.getUserMedia(audioConstraints(preferred.deviceId));
      }
      state.mimeType = supportedMimeType();
      updateAudioSettings();
      setText("micState", "ready");
      document.querySelectorAll("[data-record]").forEach((button) => button.disabled = false);
    }

    function renderScripts(scripts, samples) {
      const counts = samples.reduce((acc, sample) => {
        acc[sample.script_id] = (acc[sample.script_id] || 0) + 1;
        return acc;
      }, {});
      $("scripts").innerHTML = scripts.map((script, index) => `
        <article class="script" data-script="${script.id}">
          <span class="tag">${String(index + 1).padStart(2, "0")} · ${script.category}</span>
          <h2>${script.title}</h2>
          <p>${script.text}</p>
          <div class="actions">
            <button data-record="${script.id}" disabled>Record</button>
            <button class="danger" data-stop="${script.id}" disabled>Stop</button>
            <button class="secondary" data-save="${script.id}" disabled>Save take</button>
            <a class="download" data-download="${script.id}" hidden>Download local copy</a>
            <span class="status" data-status="${script.id}">${counts[script.id] || 0} saved take(s)</span>
          </div>
          <audio data-audio="${script.id}" controls hidden></audio>
        </article>
      `).join("");

      document.querySelectorAll("[data-record]").forEach((button) => {
        button.addEventListener("click", () => record(button.dataset.record));
      });
      document.querySelectorAll("[data-stop]").forEach((button) => {
        button.addEventListener("click", () => stop(button.dataset.stop));
      });
      document.querySelectorAll("[data-save]").forEach((button) => {
        button.addEventListener("click", () => saveTake(button.dataset.save));
      });
      if (state.stream) {
        document.querySelectorAll("[data-record]").forEach((button) => button.disabled = false);
      }
    }

    function setScriptStatus(id, text, kind = "") {
      const el = document.querySelector(`[data-status="${id}"]`);
      if (!el) return;
      el.textContent = text;
      el.className = `status ${kind}`;
    }

    function record(id) {
      if (!state.stream) return;
      if (state.activeRecorder && state.activeRecorder.state === "recording") {
        state.activeRecorder.stop();
      }
      state.chunks[id] = [];
      const options = state.mimeType ? { mimeType: state.mimeType } : {};
      const recorder = new MediaRecorder(state.stream, options);
      state.activeRecorder = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) state.chunks[id].push(event.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(state.chunks[id], { type: state.mimeType || "audio/webm" });
        state.blobs[id] = blob;
        const url = URL.createObjectURL(blob);
        const audio = document.querySelector(`[data-audio="${id}"]`);
        const download = document.querySelector(`[data-download="${id}"]`);
        audio.src = url;
        audio.hidden = false;
        download.href = url;
        download.download = `${id}-${new Date().toISOString().replaceAll(":", "").slice(0, 15)}.webm`;
        download.hidden = false;
        document.querySelector(`[data-save="${id}"]`).disabled = false;
        setScriptStatus(id, "recorded; listen back, then save", "saved");
      };
      recorder.start();
      document.querySelector(`[data-record="${id}"]`).disabled = true;
      document.querySelector(`[data-stop="${id}"]`).disabled = false;
      setScriptStatus(id, "recording...");
    }

    function stop(id) {
      if (state.activeRecorder && state.activeRecorder.state === "recording") {
        state.activeRecorder.stop();
      }
      document.querySelector(`[data-record="${id}"]`).disabled = false;
      document.querySelector(`[data-stop="${id}"]`).disabled = true;
    }

    async function saveTake(id) {
      const blob = state.blobs[id];
      if (!blob) return;
      setScriptStatus(id, "saving...");
      const response = await fetch(`/api/voice-quality/samples/${encodeURIComponent(id)}?mime_type=${encodeURIComponent(blob.type || "audio/webm")}`, {
        method: "POST",
        headers: {
          "Content-Type": blob.type || "audio/webm",
          "X-JVT-Input-Device": state.inputLabel || "",
          "X-JVT-Audio-Settings": JSON.stringify(state.audioSettings || {})
        },
        body: blob
      });
      if (!response.ok) {
        const detail = await response.text();
        setScriptStatus(id, `save failed: ${detail}`, "error");
        return;
      }
      const payload = await response.json();
      setScriptStatus(id, `saved take ${payload.take_number}`, "saved");
      await load();
    }

    async function load() {
      const response = await fetch("/api/voice-quality/status");
      const payload = await response.json();
      setText("scriptCount", payload.scripts.length);
      setText("savedCount", payload.samples.length);
      setText("writeMode", payload.write_allowed ? "local write enabled" : "read-only remote");
      renderScripts(payload.scripts, payload.samples);
      await listInputs(false);
    }

    $("startMic").addEventListener("click", () => startMic().catch((err) => {
      setText("micState", "blocked");
      console.error(err);
    }));
    $("refreshDevices").addEventListener("click", () => listInputs(true).catch(console.error));

    load().catch(console.error);
  </script>
</body>
</html>
""".strip()


def safe_stem(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80] or "voice-intake"


def unique_json_path(directory: Path, stem: str) -> Path:
    path = directory / f"{stem}.json"
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = directory / f"{stem}-{index}.json"
        if not candidate.exists():
            return candidate
    return directory / f"{stem}-{uuid.uuid4().hex[:8]}.json"


def write_call_record(record: CallRecord) -> Path:
    ensure_data_dirs()
    timestamp = record.started_at[:19].replace(":", "").replace("-", "")
    path = unique_json_path(CALL_ROOT, f"{timestamp}-{safe_stem(record.call_id)}")
    try:
        payload = record.model_dump()
    except AttributeError:
        payload = record.dict()
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def write_intake_packet(payload: Dict[str, Any]) -> Path:
    ensure_data_dirs()
    timestamp = utc_now()[:19].replace(":", "").replace("-", "")
    label = payload.get("company") or payload.get("caller_name") or payload.get("call_id") or "voice-intake"
    path = unique_json_path(INTAKE_ROOT, f"{timestamp}-{safe_stem(str(label))}")
    payload["captured_at"] = payload.get("captured_at") or utc_now()
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def recent_json(directory: Path, limit: int = 8) -> List[Dict[str, Any]]:
    if not directory.exists():
        return []
    items: List[Dict[str, Any]] = []
    for path in sorted(directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        payload["path"] = str(path)
        payload["stem"] = path.stem
        items.append(payload)
    return items


def status_payload() -> Dict[str, Any]:
    ensure_data_dirs()
    has_openai_key = bool(env_value("OPENAI_API_KEY"))
    engine = response_engine()
    openai_required = engine in {"openai", "openai-realtime"}
    live_audio_backend_ready = (openai_required and has_openai_key) or (engine in {"local-audio-bridge", "local-realtime"} and local_audio_bridge_ready())
    public_url = public_base_url()
    stream_url = media_stream_url()
    dry_run = dry_run_enabled()
    provider_ready = phone_provider_configured()
    live_ready = live_audio_backend_ready and bool(public_url) and bool(stream_url) and provider_ready and not dry_run
    return {
        "status": "live-ready" if live_ready else "dry-run" if dry_run else "configured-needs-provider",
        "dry_run": dry_run,
        "has_openai_key": has_openai_key,
        "openai_required": openai_required,
        "response_engine": engine,
        "local_model_router_url": env_value("JVT_MODEL_ROUTER_URL", "http://127.0.0.1:8760"),
        "local_audio_bridge_url": local_audio_bridge_url(),
        "local_audio_bridge_health_url": local_audio_bridge_health_url(),
        "local_audio_bridge_health": local_audio_bridge_health(),
        "local_audio_bridge_ready": local_audio_bridge_ready(),
        "live_audio_backend_ready": live_audio_backend_ready,
        "model": realtime_model(),
        "voice": realtime_voice(),
        "public_base_url": public_url,
        "media_stream_url": stream_url,
        "phone_provider_configured": provider_ready,
        "live_ready": live_ready,
        "live_ready_gates": {
            "openai_api_key": has_openai_key,
            "openai_required": openai_required,
            "local_audio_bridge_ready": local_audio_bridge_ready(),
            "live_audio_backend_ready": live_audio_backend_ready,
            "public_https_base_url": bool(public_url) and public_url.startswith("https://"),
            "media_stream_url": bool(stream_url) and stream_url.startswith("wss://"),
            "dry_run_disabled": not dry_run,
            "phone_provider_confirmed": provider_ready,
        },
        "twilio_webhook_path": "/twilio/inbound",
        "call_count": len(list(CALL_ROOT.glob("*.json"))),
        "intake_count": len(list(INTAKE_ROOT.glob("*.json"))),
        "recent_intake": recent_json(INTAKE_ROOT, limit=5),
        "updated_at": utc_now(),
    }


def twiml_response(message: str, stream_url: str = "") -> str:
    say = f"<Say voice=\"Polly.Joanna\">{xml_escape(message)}</Say>"
    if not stream_url:
        return f'<?xml version="1.0" encoding="UTF-8"?><Response>{say}</Response>'
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"{say}"
        "<Connect>"
        f"<Stream url=\"{xml_escape(stream_url)}\" />"
        "</Connect>"
        "</Response>"
    )


async def connect_openai():
    headers = {"Authorization": f"Bearer {env_value('OPENAI_API_KEY')}"}
    url = f"{OPENAI_REALTIME_URL}?model={realtime_model()}"
    try:
        return await websockets.connect(url, additional_headers=headers)
    except TypeError:
        return await websockets.connect(url, extra_headers=headers)


async def configure_openai_session(openai_ws: Any) -> None:
    event = {
        "type": "session.update",
        "session": {
            "type": "realtime",
            "model": realtime_model(),
            "instructions": DEFAULT_PROMPT,
            "output_modalities": ["audio"],
            "audio": {
                "input": {
                    "format": {"type": "audio/pcmu"},
                    "turn_detection": {
                        "type": "server_vad",
                        "interrupt_response": True,
                        "create_response": True,
                    },
                },
                "output": {
                    "format": {"type": "audio/pcmu"},
                    "voice": realtime_voice(),
                },
            },
        },
    }
    await openai_ws.send(json.dumps(event))


async def connect_local_audio_bridge():
    url = local_audio_bridge_url()
    return await websockets.connect(url)


def is_local_bridge_engine() -> bool:
    return response_engine() in {"local-audio-bridge", "local-realtime"}


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "app": "jvt-inbound-voice-agent", "generated_at": utc_now()}


@app.get("/api/status")
def api_status() -> Dict[str, Any]:
    return status_payload()


@app.get("/voice-quality")
def voice_quality_page(request: Request) -> Response:
    if not voice_recorder_read_allowed(request):
        raise HTTPException(status_code=403, detail="Voice recorder is available only on localhost or Tailnet.")
    ensure_voice_quality_dirs()
    return Response(content=voice_quality_html(), media_type="text/html")


@app.get("/api/voice-quality/status")
def voice_quality_status(request: Request) -> Dict[str, Any]:
    if not voice_recorder_read_allowed(request):
        raise HTTPException(status_code=403, detail="Voice recorder is available only on localhost or Tailnet.")
    scripts = load_voice_scripts()
    samples = voice_sample_summary()
    return {
        "status": "ok",
        "recorder_url": "/voice-quality",
        "write_allowed": voice_recorder_write_allowed(request),
        "write_policy": "localhost plus Tailnet when JVT_VOICE_RECORDER_ALLOW_TAILSCALE=1; public remote writes stay blocked",
        "tailnet_request": request_is_tailnet(request),
        "script_pack": str(VOICE_QUALITY_SCRIPT_PACK),
        "samples_dir": str(VOICE_QUALITY_SAMPLES),
        "scripts": scripts,
        "samples": samples,
        "updated_at": utc_now(),
    }


@app.post("/api/voice-quality/samples/{script_id}")
async def save_voice_sample(script_id: str, request: Request, mime_type: str = "") -> Dict[str, Any]:
    if not voice_recorder_write_allowed(request):
        raise HTTPException(
            status_code=403,
            detail="Voice sample uploads are only allowed from localhost or approved Tailnet clients.",
        )

    scripts_by_id = {script["id"]: script for script in load_voice_scripts()}
    script = scripts_by_id.get(script_id)
    if not script:
        raise HTTPException(status_code=404, detail="Unknown voice sample script.")

    body = await request.body()
    if len(body) < 1024:
        raise HTTPException(status_code=400, detail="Recording is too small to save.")
    if len(body) > 80 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Recording is too large to save.")

    ensure_voice_quality_dirs()
    existing = [item for item in voice_sample_summary() if item.get("script_id") == script_id]
    take_number = len(existing) + 1
    content_type = mime_type or request.headers.get("content-type") or "audio/webm"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    audio_path = VOICE_QUALITY_SAMPLES / f"{safe_stem(script_id)}-take-{take_number:02d}-{timestamp}.{media_extension(content_type)}"
    metadata_path = audio_path.with_suffix(".json")
    audio_path.write_bytes(body)

    metadata: Dict[str, Any] = {
        "script_id": script_id,
        "script_title": script.get("title", ""),
        "script_category": script.get("category", ""),
        "script_text": script.get("text", ""),
        "take_number": take_number,
        "content_type": content_type,
        "bytes": len(body),
        "audio_path": str(audio_path),
        "metadata_path": str(metadata_path),
        "recorded_at": utc_now(),
        "source": "jvt-local-voice-quality-recorder",
        "review_status": "needs-human-review",
    }
    input_device = request.headers.get("x-jvt-input-device") or ""
    audio_settings_raw = request.headers.get("x-jvt-audio-settings") or ""
    if input_device:
        metadata["input_device"] = input_device
    if audio_settings_raw:
        try:
            metadata["browser_audio_settings"] = json.loads(audio_settings_raw)
        except json.JSONDecodeError:
            metadata["browser_audio_settings_raw"] = audio_settings_raw[:1000]
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return {"status": "saved", **metadata}


@app.get("/api/intake")
def api_intake(limit: int = 8) -> Dict[str, Any]:
    return {"items": recent_json(INTAKE_ROOT, limit=limit)}


@app.post("/api/test-intake")
def api_test_intake(request: TestIntakeRequest) -> Dict[str, Any]:
    payload = {
        "source": "manual-test",
        "caller_name": request.caller_name,
        "company": request.company,
        "email": request.email,
        "phone": request.phone,
        "workflow": request.workflow,
        "notes": request.notes,
        "captured_at": utc_now(),
    }
    path = write_intake_packet(payload)
    return {"status": "created", "path": str(path), "item": payload}


@app.post("/twilio/inbound")
async def twilio_inbound() -> Response:
    stream_url = media_stream_url()
    if dry_run_enabled() or not stream_url:
        message = (
            "Thanks for calling JVT Technologies. I am JVT's AI assistant. "
            "Voice intake is in setup mode right now. Please email hello at JVT dash technologies dot com, "
            "and Chandru will review your message."
        )
        return Response(content=twiml_response(message), media_type="application/xml")

    message = (
        "Thanks for calling JVT Technologies. I am JVT's AI assistant. "
        "I can answer basic questions and capture details for a human follow up."
    )
    return Response(content=twiml_response(message, stream_url), media_type="application/xml")


@app.websocket("/twilio/media-stream")
async def twilio_media_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    record = CallRecord(
        call_id=str(uuid.uuid4()),
        mode="dry-run" if dry_run_enabled() else "realtime",
        started_at=utc_now(),
    )

    if dry_run_enabled():
        try:
            while True:
                raw = await websocket.receive_text()
                event = json.loads(raw)
                event_name = event.get("event")
                if event_name == "start":
                    start = event.get("start") or {}
                    record.stream_sid = str(start.get("streamSid") or "")
                    record.call_sid = str(start.get("callSid") or "")
                elif event_name == "media":
                    record.media_events += 1
                elif event_name == "stop":
                    break
        except WebSocketDisconnect:
            pass
        finally:
            record.ended_at = utc_now()
            write_call_record(record)
        return

    if is_local_bridge_engine():
        try:
            bridge_ws = await connect_local_audio_bridge()
        except Exception as exc:
            record.errors.append(f"local_audio_bridge_connect_failed: {exc}")
            record.ended_at = utc_now()
            write_call_record(record)
            await websocket.close()
            return

        async def twilio_to_bridge() -> None:
            try:
                while True:
                    raw = await websocket.receive_text()
                    event = json.loads(raw)
                    event_name = event.get("event")
                    if event_name == "start":
                        start = event.get("start") or {}
                        record.stream_sid = str(start.get("streamSid") or "")
                        record.call_sid = str(start.get("callSid") or "")
                    elif event_name == "media":
                        record.media_events += 1
                    elif event_name == "stop":
                        await bridge_ws.send(raw)
                        break
                    await bridge_ws.send(raw)
            except WebSocketDisconnect:
                pass
            finally:
                await bridge_ws.close()

        async def bridge_to_twilio() -> None:
            try:
                async for raw in bridge_ws:
                    event = json.loads(raw)
                    event_type = str(event.get("type") or event.get("event") or "")
                    transcript = event.get("transcript") or event.get("text")
                    if transcript:
                        record.transcript_fragments.append(str(transcript))
                    if event.get("event") == "media":
                        await websocket.send_json(event)
                    elif event_type == "media" and record.stream_sid and event.get("payload"):
                        await websocket.send_json({
                            "event": "media",
                            "streamSid": record.stream_sid,
                            "media": {"payload": event.get("payload")},
                        })
                    elif event_type in {"error", "bridge.error"}:
                        record.errors.append(json.dumps(event))
            except Exception as exc:
                record.errors.append(f"local_audio_bridge_stream_failed: {exc}")

        try:
            await asyncio.gather(twilio_to_bridge(), bridge_to_twilio())
        finally:
            record.ended_at = utc_now()
            write_call_record(record)
            if record.transcript_fragments:
                write_intake_packet({
                    "source": "voice-call-local-bridge",
                    "call_id": record.call_id,
                    "call_sid": record.call_sid,
                    "transcript": " ".join(record.transcript_fragments).strip(),
                    "captured_at": record.ended_at or utc_now(),
                })
        return

    try:
        openai_ws = await connect_openai()
        await configure_openai_session(openai_ws)
    except Exception as exc:
        record.errors.append(f"openai_connect_failed: {exc}")
        record.ended_at = utc_now()
        write_call_record(record)
        await websocket.close()
        return

    async def twilio_to_openai() -> None:
        try:
            while True:
                raw = await websocket.receive_text()
                event = json.loads(raw)
                event_name = event.get("event")
                if event_name == "start":
                    start = event.get("start") or {}
                    record.stream_sid = str(start.get("streamSid") or "")
                    record.call_sid = str(start.get("callSid") or "")
                elif event_name == "media":
                    media = event.get("media") or {}
                    payload = media.get("payload")
                    if payload:
                        record.media_events += 1
                        await openai_ws.send(json.dumps({
                            "type": "input_audio_buffer.append",
                            "audio": payload,
                        }))
                elif event_name == "stop":
                    break
        except WebSocketDisconnect:
            pass
        finally:
            await openai_ws.close()

    async def openai_to_twilio() -> None:
        try:
            async for raw in openai_ws:
                event = json.loads(raw)
                event_type = str(event.get("type") or "")
                if event_type in {"response.output_audio.delta", "response.audio.delta"} and record.stream_sid:
                    delta = event.get("delta")
                    if delta:
                        await websocket.send_json({
                            "event": "media",
                            "streamSid": record.stream_sid,
                            "media": {"payload": delta},
                        })
                elif event_type.endswith("transcript.delta"):
                    delta = event.get("delta")
                    if delta:
                        record.transcript_fragments.append(str(delta))
                elif event_type.endswith("transcription.completed"):
                    transcript = event.get("transcript")
                    if transcript:
                        record.transcript_fragments.append(str(transcript))
                elif event_type == "error":
                    record.errors.append(json.dumps(event))
        except Exception as exc:
            record.errors.append(f"openai_stream_failed: {exc}")

    try:
        await asyncio.gather(twilio_to_openai(), openai_to_twilio())
    finally:
        record.ended_at = utc_now()
        write_call_record(record)
        if record.transcript_fragments:
            write_intake_packet({
                "source": "voice-call",
                "call_id": record.call_id,
                "call_sid": record.call_sid,
                "transcript": " ".join(record.transcript_fragments).strip(),
                "captured_at": record.ended_at or utc_now(),
            })

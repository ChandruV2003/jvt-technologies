# JVT Local Model Runtime

This is the current local-model path for JVT autonomous operations.

## Runtime

- Primary host: M4 Mac mini, `jvt-m4`
- Primary HTTP endpoint: `http://127.0.0.1:11435`
- Primary runtime: MLX / `mlx_lm.server`
- Primary model: `mlx-community/Qwen3-8B-4bit`
- Primary model path:
  `/Users/c.s.d.v.r.s./.cache/huggingface/hub/models--mlx-community--Qwen3-8B-4bit/snapshots/545dc4251c05440727734bcd94334791f6ab0192`
- Keepalive script:
  `/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/ops/agent-control/run_m4_mlx_model_server_foreground.sh`
- LaunchAgent installer:
  `/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/ops/agent-control/install_m4_mlx_model_server_launch_agent.sh`
- Keepalive cadence: M4 LaunchAgent `KeepAlive`

Fallback:

- Host: Debian Mac mini, `macmini-i7-debian`
- Tailnet HTTP endpoint: `http://100.94.111.27:11434`
- Runtime: Ollama
- Model: `qwen2.5:1.5b`

Opportunistic large local model:

- Host: Chandru's M4 Max MacBook Pro
- Tailnet HTTP endpoint: `http://100.90.245.45:8770`
- Runtime: Ollama behind the guarded JVT MacBook proxy
- Model: `qwen2.5:14b`
- Gate endpoint: `http://100.90.245.45:8769/health`
- Proxy script:
  `/Users/chandruv/.jvt/model-worker/jvt_macbook_ollama_proxy.py`
- Proxy LaunchAgent:
  `/Users/chandruv/Library/LaunchAgents/com.jvt.macbook-ollama-proxy.plist`
- Power/model gate:
  `/Users/chandruv/Library/LaunchAgents/com.jvt.macbook-model-gate.plist`

The MacBook backend is only allowed when the gate reports AC power, at least
80% battery, and a 140W charger. If the gate blocks or the MacBook is offline,
the router falls back to the M4 MLX backend.

## Model Router

- Router endpoint: `http://127.0.0.1:8760`
- Router config:
  `/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/ops/agent-control/config/model-router.json`
- Default backend: `m4-mlx`
- Large-model routes: `strategy`, `deep_research`, `product_spec`, and
  `code_planning` route to `macbook-large-local` when available.
- Lightweight routes: `triage`, `lead_scoring`, `outreach_copy`, and
  `status_summary` stay on `m4-mlx`.
- Health check:
  `curl "http://127.0.0.1:8760/health?refresh=1"`

## Active Director Model

- Model: `mlx-community/Qwen3-8B-4bit`
- AI Director env:
  - `JVT_MLX_HOST=http://127.0.0.1:11435`
  - `JVT_MLX_MODEL=mlx-community/Qwen3-8B-4bit`
  - `JVT_AI_DIRECTOR_TIMEOUT_SECONDS=180`
  - `JVT_AI_DIRECTOR_NUM_PREDICT=220`

The AI Director and packet reviewer prefer the M4 MLX endpoint. Debian Ollama is
fallback only.

`mlx-community/gpt-oss-20b-MXFP4-Q4` is cached and can run on the M4, but the
first structured-output test took about 130 seconds and hit the token limit.
Do not use it as the default approval worker until it has a separate tuned
adjudicator prompt/runtime.

## Supervisor Wiring

The Debian JVT supervisor task `ai-director` injects the environment above and
then runs:

```bash
python3 ops/agent-control/ai_director.py --write-tasks
```

The AI Director still enforces the deterministic guardrails and task allowlist.
The local model is advisory: it adds operational reasoning, but it does not get
permission to spend money, trade live, mine, stake, submit applications, post
publicly, or send outside quality gates and caps.

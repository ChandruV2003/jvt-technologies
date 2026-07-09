# How JVT Runs Local Agents On The Mac Mini

JVT's local agents are not a single magic app. They are a practical stack:

1. **A Mac that stays online**
   - The M4 Mac Mini is the always-on host.
   - It owns the JVT repo, lead database, outreach queues, dashboard, and local model files.

2. **Small scripts with clear responsibilities**
   - `lead-pipeline/run_auto_research.sh` finds and scores new leads.
   - `outreach/tools/run_daily_wave_prep.sh` creates review-only outreach waves.
   - mailbox and demo services have their own launch scripts.
   - Each script can run by itself from the terminal, which makes debugging straightforward.

3. **macOS LaunchAgents for scheduling**
   - LaunchAgents are macOS user-level background jobs.
   - They restart at login and run on a schedule or interval.
   - Active JVT jobs live in `~/Library/LaunchAgents/com.jvt.*.plist`.

4. **Queues instead of uncontrolled autonomy**
   - Low-risk work runs automatically: research, scoring, draft generation, health checks.
   - Higher-risk work pauses in queues: outbound email, pricing changes, infrastructure changes.
   - Prospect emails stay in `outreach/queue/review` until moved to `approved` and confirmed.

5. **A dashboard for human-in-the-loop control**
   - The control panel runs locally on the M4 and is exposed through Tailscale.
   - It shows agents, leads, waves, queues, and local model responses.
   - The dashboard can approve/send a wave, but it still asks for confirmation before real email goes out.

6. **Local models for review work**
   - The M4 has local MLX models available for fast/strong/reviewer profiles.
   - These are useful for summarization, QA, and screening.
   - They are not the only intelligence in the system; deterministic scripts still enforce hard rules.

## Current JVT Local Agents

- `com.jvt.control-panel`: local dashboard/API.
- `com.jvt.lead-research`: recurring lead research and scoring.
- `com.jvt.daily-wave-prep`: prepares daily outreach waves for review.
- `com.jvt.mailbox-listener`: imports and watches mailbox state.
- `com.jvt.private-doc-intel-demo`: keeps the demo backend available.

## Core Safety Rule

The system can prepare work unattended, but it should not send real third-party prospect emails unattended. That final action affects outside parties, deliverability, brand reputation, and legal compliance, so it remains a human-confirmed step.

## How To Explain It In One Sentence

We built a local operations stack on an always-on Mac Mini: macOS LaunchAgents run scoped agent scripts, local models help with review and QA, and a dashboard keeps the human in control of anything that can affect customers, prospects, or infrastructure.

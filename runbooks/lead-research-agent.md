# Lead Research Agent

This is the Mac Mini-native recurring lead research worker for JVT.

## What it does

- rotates through a conservative set of public search queries
- fetches real firm websites and contact paths
- extracts public emails when available
- scores fit for JVT's current offer
- writes a dated CSV tranche into `lead-pipeline/data/`
- updates `lead-pipeline/data/jvt_leads.sqlite3`
- generates draft outreach packets for the strongest new leads
- never sends outreach automatically

## Files

- `lead-pipeline/tools/auto_research.py`
- `lead-pipeline/run_auto_research.sh`
- `lead-pipeline/install_launch_agent.sh`
- `lead-pipeline/state/auto-research-state.json`
- `lead-pipeline/state/auto-research-status.md`

## Schedule

The launch agent runs at load and then every 6 hours.

## Guardrails

- only real public companies
- only visible public contact paths
- only conservative fit scoring
- only draft generation, no autonomous sends
- dedupe against the existing lead database by company and website

## Manual checks

Run once manually:

```bash
/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/lead-pipeline/run_auto_research.sh
```

Install the launch agent:

```bash
/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/lead-pipeline/install_launch_agent.sh
```

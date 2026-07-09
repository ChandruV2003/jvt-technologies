#!/usr/bin/env bash
set -euo pipefail

ROOT="${JVT_CLIENT_DOCS_ROOT:-$HOME/Documents/JVT-Technologies}"
REPO_ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies"
NEW_WORKSPACE="${REPO_ROOT}/client-work/tools/new_client_workspace.sh"
SLUG=""
CLIENT_NAME=""
CONTACT_EMAIL=""
CONTACT_NAME=""
WEBSITE=""
VERTICAL="voice-agent"
NOTES=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --slug)
      SLUG="${2:-}"
      shift 2
      ;;
    --client-name)
      CLIENT_NAME="${2:-}"
      shift 2
      ;;
    --contact-email)
      CONTACT_EMAIL="${2:-}"
      shift 2
      ;;
    --contact-name)
      CONTACT_NAME="${2:-}"
      shift 2
      ;;
    --website)
      WEBSITE="${2:-}"
      shift 2
      ;;
    --vertical)
      VERTICAL="${2:-}"
      shift 2
      ;;
    --notes)
      NOTES="${2:-}"
      shift 2
      ;;
    --root)
      ROOT="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "${SLUG}" ]]; then
  echo "Usage: $0 --slug client-slug [--client-name 'Client Name'] [--vertical dental-office]" >&2
  exit 1
fi

"${NEW_WORKSPACE}" \
  --slug "${SLUG}" \
  --root "${ROOT}" \
  --client-name "${CLIENT_NAME}" \
  --contact-name "${CONTACT_NAME}" \
  --contact-email "${CONTACT_EMAIL}" \
  --website "${WEBSITE}" \
  --service-line "AI receptionist / voice intake" \
  --pipeline-stage "discovery" \
  --notes "${NOTES}"

CLIENT_ROOT="${ROOT}/30-active-clients/${SLUG}"
TODAY="$(date +%F)"

cp "${REPO_ROOT}/client-work/templates/voice-agent-pilot-checklist.md" "${CLIENT_ROOT}/01-intake/voice-agent-pilot-checklist.md"

cat > "${CLIENT_ROOT}/01-intake/voice-agent-pilot-plan.md" <<PLAN
# Voice Agent Pilot Plan

- created: ${TODAY}
- client: ${CLIENT_NAME}
- vertical: ${VERTICAL}
- service line: AI receptionist / voice intake
- status: discovery

## First Workflow

Describe the first inbound call workflow to automate.

## Approved Caller Types

- routine request:
- urgent escalation:
- existing customer/patient/client:
- wrong-fit:

## Scenario Pack

- source:
- dry-run report:
- staff review notes:

## Approval Gates

- disclosure approved:
- escalation language approved:
- data handling approved:
- SOW approved:
- phone provider approved:
- live webhook approved:
PLAN

cat > "${CLIENT_ROOT}/04-deliverables/voice-agent-pilot-readme.md" <<README
# Voice Agent Pilot Deliverables

This folder should hold only polished, client-shareable outputs:

- dry-run scenario report
- staff intake packet sample
- approved call script
- escalation map
- final implementation notes
README

echo "Created voice-agent pilot workspace at ${CLIENT_ROOT}"

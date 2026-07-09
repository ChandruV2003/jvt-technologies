#!/usr/bin/env bash
set -euo pipefail

ROOT="${JVT_CLIENT_DOCS_ROOT:-$HOME/Documents/JVT-Technologies}"
TEMPLATE_ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/client-work/templates/client-workspace-template"
REGISTRY_SCRIPT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/client-work/tools/register_client.py"
SLUG=""
CLIENT_NAME=""
CONTACT_EMAIL=""
CONTACT_NAME=""
WEBSITE=""
SERVICE_LINE=""
LEAD_ID=""
PIPELINE_STAGE="active"
NOTES=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --slug)
      SLUG="${2:-}"
      shift 2
      ;;
    --root)
      ROOT="${2:-}"
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
    --service-line)
      SERVICE_LINE="${2:-}"
      shift 2
      ;;
    --lead-id)
      LEAD_ID="${2:-}"
      shift 2
      ;;
    --pipeline-stage)
      PIPELINE_STAGE="${2:-}"
      shift 2
      ;;
    --notes)
      NOTES="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "${SLUG}" ]]; then
  echo "Usage: $0 --slug client-slug [--client-name 'Client Name'] [--contact-email email] [--website https://example.com]" >&2
  exit 1
fi

CLIENT_ROOT="${ROOT}/30-active-clients/${SLUG}"
TODAY="$(date +%F)"

mkdir -p \
  "${CLIENT_ROOT}/00-admin" \
  "${CLIENT_ROOT}/00-admin/contracts" \
  "${CLIENT_ROOT}/01-intake" \
  "${CLIENT_ROOT}/02-source-documents" \
  "${CLIENT_ROOT}/03-working-files" \
  "${CLIENT_ROOT}/04-deliverables" \
  "${CLIENT_ROOT}/05-meetings" \
  "${CLIENT_ROOT}/06-billing" \
  "${CLIENT_ROOT}/07-archive"

if [[ -d "${TEMPLATE_ROOT}" ]]; then
  rsync -a "${TEMPLATE_ROOT}/" "${CLIENT_ROOT}/"
fi

if [[ -n "${CLIENT_NAME}" && -x "${REGISTRY_SCRIPT}" ]]; then
  python3 "${REGISTRY_SCRIPT}" \
    --csv "${ROOT}/00-admin/client-registry.csv" \
    upsert \
    --slug "${SLUG}" \
    --name "${CLIENT_NAME}" \
    --pipeline-stage "${PIPELINE_STAGE}" \
    --lead-id "${LEAD_ID}" \
    --primary-contact-name "${CONTACT_NAME}" \
    --primary-contact-email "${CONTACT_EMAIL}" \
    --website "${WEBSITE}" \
    --service-line "${SERVICE_LINE}" \
    --start-date "${TODAY}" \
    --last-activity-date "${TODAY}" \
    --workspace-path "${CLIENT_ROOT}" \
    --notes "${NOTES}"
fi

echo "Created client workspace at ${CLIENT_ROOT}"

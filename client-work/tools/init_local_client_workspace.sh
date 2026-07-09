#!/usr/bin/env bash
set -euo pipefail

ROOT="${JVT_CLIENT_DOCS_ROOT:-$HOME/Documents/JVT-Technologies}"
TEMPLATE_ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/client-work/templates"
SHARED_TEMPLATE_DEST="${ROOT}/_shared-templates/repo-templates"
REGISTRY_CSV="${ROOT}/00-admin/client-registry.csv"

mkdir -p \
  "${ROOT}/00-admin/formation" \
  "${ROOT}/00-admin/tax" \
  "${ROOT}/00-admin/banking" \
  "${ROOT}/00-admin/contracts" \
  "${ROOT}/00-admin/insurance" \
  "${ROOT}/00-admin/policies" \
  "${ROOT}/10-leads/discovery-notes" \
  "${ROOT}/10-leads/proposals" \
  "${ROOT}/10-leads/closed-lost" \
  "${ROOT}/20-intake/pending" \
  "${ROOT}/20-intake/qualified" \
  "${ROOT}/20-intake/rejected" \
  "${ROOT}/30-active-clients" \
  "${ROOT}/40-deliverables" \
  "${ROOT}/90-archive" \
  "${SHARED_TEMPLATE_DEST}"

if [[ -d "${TEMPLATE_ROOT}" ]]; then
  rsync -a --delete "${TEMPLATE_ROOT}/" "${SHARED_TEMPLATE_DEST}/"
fi

cat > "${ROOT}/README.txt" <<EOF
JVT Technologies local client workspace

This folder is for real operating material on the Mac mini.

- Do not put this folder under Git.
- Store real client intake, source documents, working files, deliverables, and billing support here.
- Keep reusable scripts and templates in the repo at:
  /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/client-work
- The canonical local client registry is:
  ${REGISTRY_CSV}

Top-level layout:
- 00-admin: formation, tax, banking, contracts, insurance, policy records
- 10-leads: discovery notes, proposals, and lost leads
- 20-intake: pending, qualified, rejected intake packets
- 30-active-clients: one folder per active client
- 40-deliverables: shared exported deliverables if needed
- 90-archive: completed client archives
EOF

if [[ ! -f "${REGISTRY_CSV}" ]]; then
  cat > "${REGISTRY_CSV}" <<EOF
client_slug,client_name,pipeline_stage,lead_id,primary_contact_name,primary_contact_email,website,service_line,intake_date,start_date,last_activity_date,workspace_path,notes
EOF
fi

echo "Initialized local client workspace at ${ROOT}"

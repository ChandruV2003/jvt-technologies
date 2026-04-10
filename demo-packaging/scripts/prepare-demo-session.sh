#!/bin/zsh

set -euo pipefail

PROJECT_ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/Private-AI-Lab/apps/private-doc-intel-demo"
WEBSITE_ROOT="/Users/c.s.d.v.r.s./Developer/Control-Host/Private-AI-Lab/JVT-Technologies/site"

cat <<EOF
JVT Technologies demo prep

1. Start the backend:
   cd "$PROJECT_ROOT/backend"
   source .venv/bin/activate
   uvicorn app.main:app --reload

2. Preview the site locally if needed:
   cd "$WEBSITE_ROOT"
   python3 -m http.server 8080

3. Open these URLs:
   http://127.0.0.1:8080
   http://127.0.0.1:8000/demo

4. Use synthetic sample documents from:
   /Users/c.s.d.v.r.s./Developer/Control-Host/Private-AI-Lab/JVT-Technologies/demo-packaging/sample-documents

5. Recommended questions:
   - What does the billing policy say about disputed invoices?
   - What confidentiality obligations survive termination?
EOF

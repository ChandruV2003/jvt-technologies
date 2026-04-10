# Private AI Lab

`Private-AI-Lab` is now a product and R&D area inside the broader `JVT Technologies` workspace on `m4-mac-mini`.

## Layout

- `infra`: local infrastructure definitions, reverse-proxy plans, deployment glue
- `apps`: first-party product and demo applications
- `clients`: isolated client-specific workspaces
- `shared`: shared templates, schemas, and reusable components
- `runbooks`: implementation notes, deployment checklists, and operating procedures
- `staging`: scratch space for safe temporary work

## First Focus

The first scaffold in this workspace is a local-first private document intelligence demo for law firms and other document-heavy teams. The initial goal is a narrow path:

1. ingest uploaded documents
2. chunk and index them locally
3. retrieve grounded passages
4. answer with citations
5. keep secrets and client data out of source control

## Repo Split

- business-facing JVT assets live in the parent repo at `/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies`
- the active product app keeps its own repo at `apps/private-doc-intel-demo`

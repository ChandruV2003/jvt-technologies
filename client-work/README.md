# Client Work

Use this area for client-work templates, intake checklists, and local-workspace scaffolding that sit beside, but not inside, the shared `JVT Technologies` business assets.

## Working Split

- keep reusable templates and setup scripts in this repo
- keep real client documents and delivery files out of Git in a local-only documents workspace on the Mac mini
- keep the canonical client registry in the local-only documents workspace, not in Git

Recommended local-only path on the Mac mini:

- `/Users/c.s.d.v.r.s./Documents/JVT-Technologies`

Canonical client registry path on the Mac mini:

- `/Users/c.s.d.v.r.s./Documents/JVT-Technologies/00-admin/client-registry.csv`

## Recommended Pattern

- one folder per client engagement
- separate discovery notes, deployment notes, and deliverables
- keep reusable product and sales assets in the sibling `brand`, `site`, `demo-packaging`, `lead-pipeline`, and `outreach` areas
- when a lead becomes real intake or active work, create a workspace and upsert the client registry entry at the same time

## Local Workspace Scripts

Initialize the shared local documents workspace:

```bash
/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/client-work/tools/init_local_client_workspace.sh
```

Create a new client workspace under that documents root:

```bash
/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/client-work/tools/new_client_workspace.sh --slug example-client
```

Create a new client workspace and register it:

```bash
/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/client-work/tools/new_client_workspace.sh \
  --slug example-client \
  --client-name "Example Client" \
  --contact-email team@example.com \
  --website https://example.com \
  --service-line "Private document intelligence"
```

Create a voice-agent pilot workspace and register it:

```bash
/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/client-work/tools/new_voice_agent_pilot.sh \
  --slug example-dental-office \
  --client-name "Example Dental Office" \
  --contact-email office@example.com \
  --website https://example.com \
  --vertical dental-office
```

Register or update a client without creating a workspace:

```bash
python3 /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/client-work/tools/register_client.py upsert \
  --slug example-client \
  --name "Example Client"
```

List the client registry:

```bash
python3 /Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/client-work/tools/register_client.py list
```

## Included Templates

- `templates/client-intake-checklist.md`
- `templates/banking-setup-checklist.md`
- `templates/discovery-intake-form.md`
- `templates/client-service-agreement-template.md`
- `templates/statement-of-work-template.md`
- `templates/invoice-template.md`
- `templates/privacy-and-data-handling-addendum-template.md`
- `templates/client-workspace-template/`
- `templates/voice-agent-pilot-checklist.md`

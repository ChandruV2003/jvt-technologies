# JVT Technologies Demo Script

## Goal

Show a prospect that JVT Technologies can deliver a private, grounded document assistant for internal document workflows.

## Recommended Length

- short live version: 4 to 6 minutes
- video-ready version: 60 to 90 seconds

## Demo Arc

1. set context
2. upload realistic internal documents
3. ask a workflow-relevant question
4. show cited answer output
5. reinforce privacy and deployment options

## Opening

“JVT Technologies builds private AI systems for document-heavy teams. This demo shows a private document assistant that can ingest internal documents, answer grounded questions with citations, and run in a controlled local-first setup.”

## Live Flow

### Step 1. Explain the use case

- mention the document type
- mention the internal team that uses it
- mention the time cost of manual search today
- state clearly that the sample set is synthetic and safe for demo use

### Step 2. Upload documents

- show that the system accepts common business formats
- explain that ingestion creates searchable chunks and stores traceable references
- keep the upload set to three or four short documents so the demo stays tight

### Step 3. Ask grounded questions

Use one operational question first, not a broad theoretical one.

Examples:

- “What does the billing policy say about disputed invoices?”
- “What confidentiality obligations survive termination?”
- “Which documents describe retention requirements?”

### Step 4. Show citations

- point to the cited chunk references
- highlight that the operator can verify the answer against source text
- note the provider mode used
- if time allows, repeat the same question in `mlx-local` mode to reinforce the local answer path

### Step 5. Close with deployment story

- local-first if privacy and control matter most
- configurable provider path if the client wants a different model strategy
- pilot first, then production hardening

## Best One-Pass Sequence

1. open the JVT site
2. switch to the demo UI
3. upload `sample-engagement-terms.txt`, `sample-billing-policy.txt`, and `sample-records-retention-policy.txt`
4. ask: “What does the billing policy say about disputed invoices?”
5. hold on the answer and citations
6. ask: “What confidentiality obligations survive termination?”
7. close with privacy and pilot language

## Close

“The important point is not just that the system answers. It answers with traceable support and can be deployed in a way that fits the client’s privacy and infrastructure requirements.”

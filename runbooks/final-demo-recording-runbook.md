# Final Demo Recording Runbook

## Goal

Capture one clean, silent JVT Technologies product demo that can later receive narration or captions.

## Chosen Recording Path

- start the backend in a fresh recording run
- load only the recommended three-document recording pack
- drive Chromium with Playwright for the browser sequence
- export the browser session directly as a silent video artifact
- keep the clip to roughly 40 to 45 seconds raw, then extend to 60 to 90 seconds only if you add intro/outro or narration

## Commands

One-command capture:

```bash
/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/demo-packaging/scripts/capture-silent-demo.sh
```

Manual backend start if needed:

```bash
/Users/c.s.d.v.r.s./Developer/Control-Host/JVT-Technologies/demo-packaging/scripts/start-recording-demo.sh
```

## Best Single Take

1. show the JVT site hero
2. switch to the demo UI
3. show the reset and sample-pack controls
4. load the sample pack
5. show the indexed document list
6. click the `Billing disputes` preset
7. generate the answer in `mlx-local` mode
8. hold on the cited answer and citations
9. end on the site CTA or contact section

## Suggested Intro Text

`JVT Technologies builds private AI systems for document-heavy teams. This demo shows a private document assistant answering from uploaded documents with citations.`

## Suggested Outro Text

`The system is designed for private internal use, grounded answers, and deployment choices that fit privacy-sensitive teams.`

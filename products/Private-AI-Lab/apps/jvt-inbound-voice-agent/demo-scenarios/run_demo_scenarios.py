#!/usr/bin/env python3

from __future__ import annotations

import json
import argparse
import urllib.request
from pathlib import Path


API_URL = "http://127.0.0.1:8066/api/test-intake"
SCENARIOS = Path(__file__).with_name("ai-receptionist-scenarios.json")
OUT = Path(__file__).with_name("latest-demo-run.json")


def post_json(api_url: str, payload: dict[str, str]) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        api_url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "JVT-DemoScenario/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run voice-agent dry-run intake scenarios against the local JVT voice app.")
    parser.add_argument("--scenarios", type=Path, default=SCENARIOS)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--api-url", default=API_URL)
    args = parser.parse_args()

    data = json.loads(args.scenarios.read_text())
    results = []
    for scenario in data["scenarios"]:
        payload = {key: scenario[key] for key in ["caller_name", "company", "email", "phone", "workflow", "notes"]}
        result = post_json(args.api_url, payload)
        results.append(
            {
                "id": scenario["id"],
                "status": result.get("status"),
                "path": result.get("path"),
            }
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "scenario_file": str(args.scenarios),
                "api_url": args.api_url,
                "results": results,
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps({"results": results}, indent=2))


if __name__ == "__main__":
    main()

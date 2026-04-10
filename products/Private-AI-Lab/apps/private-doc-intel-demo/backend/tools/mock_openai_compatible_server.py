from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class MockHandler(BaseHTTPRequestHandler):
    server_version = "MockOpenAICompatible/0.1"

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler naming
        if self.path != "/v1/chat/completions":
            self.send_error(404, "Not Found")
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length).decode("utf-8")
        payload = json.loads(body)
        prompt = payload["messages"][-1]["content"]
        chunk_ids = re.findall(r"chunk_id:\s*([a-z0-9]+)", prompt)
        question_match = re.search(r"Question:\s*(.+)", prompt)
        question = question_match.group(1).strip() if question_match else "the question"

        answer_payload = {
            "answer": f"Mock provider answer for {question}. The response is grounded in the supplied retrieved chunks.",
            "citations": chunk_ids[:2],
            "confidence": 0.72,
            "note": "Mock OpenAI-compatible provider response for local plumbing tests.",
        }
        response_payload = {
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(answer_payload),
                    },
                    "finish_reason": "stop",
                }
            ],
        }
        response_body = json.dumps(response_payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003 - stdlib signature
        return


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 11435), MockHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

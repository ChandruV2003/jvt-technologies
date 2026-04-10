def planned_pipeline_steps() -> list[str]:
    return [
        "receive upload",
        "extract PDF, DOCX, and TXT content",
        "chunk extracted text with stable source offsets",
        "store documents and chunks in sqlite",
        "retrieve chunks through sqlite fts",
        "generate an answer through a pluggable provider path",
        "fallback to extractive citations when no model is active",
    ]

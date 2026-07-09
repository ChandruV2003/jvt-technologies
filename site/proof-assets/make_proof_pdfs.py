#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path


OUT_DIR = Path(__file__).resolve().parent


def escape_pdf(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def wrap(text: str, width: int = 76) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def make_pdf(path: Path, title: str, kicker: str, sections: list[tuple[str, list[str]]]) -> None:
    commands: list[str] = []
    y = 750
    commands.append("0.05 0.13 0.11 rg 0 0 612 792 re f")
    commands.append("0.86 0.75 0.54 rg 42 724 118 22 re f")
    commands.append("0.97 0.95 0.91 rg /F2 10 Tf 48 731 Td (" + escape_pdf(kicker.upper()) + ") Tj")
    commands.append("0.97 0.95 0.91 rg /F2 28 Tf 42 682 Td (" + escape_pdf(title) + ") Tj")
    y = 635
    for heading, lines in sections:
        commands.append(f"0.09 0.62 0.55 rg 42 {y} 10 10 re f")
        commands.append(f"0.97 0.95 0.91 rg /F2 15 Tf 62 {y - 1} Td (" + escape_pdf(heading) + ") Tj")
        y -= 25
        commands.append("0.80 0.78 0.72 rg /F1 10.5 Tf")
        for item in lines:
            for line in wrap(item):
                commands.append(f"52 {y} Td (" + escape_pdf(line) + ") Tj")
                commands.append(f"-52 {-14} Td")
                y -= 14
            y -= 4
        y -= 10
    commands.append("0.86 0.75 0.54 rg /F2 10 Tf 42 42 Td (JVT Technologies LLC | hello@jvt-technologies.com | jvt-technologies.com) Tj")
    stream = "BT\n" + "\n".join(commands) + "\nET\n"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}endstream",
    ]
    output = ["%PDF-1.4\n"]
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(sum(len(part.encode("latin-1")) for part in output))
        output.append(f"{index} 0 obj\n{obj}\nendobj\n")
    xref_offset = sum(len(part.encode("latin-1")) for part in output)
    output.append(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.append(f"{offset:010d} 00000 n \n")
    output.append(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n")
    path.write_bytes("".join(output).encode("latin-1"))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    make_pdf(
        OUT_DIR / "ai-receptionist-intake-proof.pdf",
        "AI Receptionist Intake Proof",
        "Dry-run demo",
        [
            ("Target customer", ["Solo and small offices that miss calls or lose intake context after hours."]),
            ("Pain", ["Calls arrive with urgency, missing fields, and questions staff should review before answering."]),
            ("Offer", ["Inbound AI intake that discloses itself, captures caller details, and routes a human-reviewed packet."]),
            ("Proof", ["Three synthetic scenarios: missed sales call, existing-client admin request, and wrong-fit caller with financial-advice guardrails."]),
            ("Pricing test", ["$500 setup plus $250/month support. Usage and phone-provider costs billed separately after approval."]),
            ("Next validation", ["Use the public demo page with phone-heavy businesses and measure demo replies."]),
        ],
    )
    make_pdf(
        OUT_DIR / "meeting-to-action-proof.pdf",
        "Meeting-To-Action Packet Proof",
        "Synthetic demo",
        [
            ("Target customer", ["Consultants, agencies, CPA firms, advisors, and operators with recurring client calls."]),
            ("Pain", ["Decisions, owners, missing documents, and client follow-ups get buried in transcripts and notes."]),
            ("Offer", ["Turn a call recording or transcript into summary, decisions, task owners, open questions, and a follow-up draft."]),
            ("Proof", ["Synthetic transcript excerpt converted into a decision packet with owner, missing-info, and client email sections."]),
            ("Pricing test", ["$75 per packet or $300/month for a small recurring meeting workflow."]),
            ("Next validation", ["Run five real non-sensitive meetings and score time saved, accuracy, and usefulness."]),
        ],
    )
    make_pdf(
        OUT_DIR / "inbox-document-triage-proof.pdf",
        "Inbox And Document Triage Proof",
        "Synthetic demo",
        [
            ("Target customer", ["Shared-inbox-heavy law, accounting, insurance, property, and operations teams."]),
            ("Pain", ["Client requests, attachments, notices, vendor messages, and noise land together with no reliable review queue."]),
            ("Offer", ["Classify inbound messages, extract the real ask, flag missing details, create a task queue, and draft reviewable replies."]),
            ("Proof", ["Synthetic public sample backed by JVT's internal mailbox run: 1,795 imported items triaged into direct, system, promotional, personal, and test buckets."]),
            ("Pricing test", ["$1,500 setup plus $500/month support for one shared inbox and one review workflow."]),
            ("Next validation", ["Use the public proof page with admin-heavy offices and measure replies asking for a pilot scope."]),
        ],
    )


if __name__ == "__main__":
    main()

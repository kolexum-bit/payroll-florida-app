from __future__ import annotations


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def create_pay_stub_pdf_bytes(lines: list[str]) -> bytes:
    commands = []
    commands.extend([
        "0.97 0.97 0.97 rg",
        "72 742 468 28 re f",
        "0 0 0 rg",
    ])
    commands.extend(["BT", "/F1 12 Tf"])
    y = 760
    for line in lines:
        if line.startswith("[") and line.endswith("]"):
            commands.extend([
                "ET",
                "0.9 0.9 0.9 rg",
                f"72 {y - 4} 468 16 re f",
                "0 0 0 rg",
                "BT",
                "/F1 11 Tf",
            ])
        commands.append(f"1 0 0 1 72 {y} Tm ({_escape(line)}) Tj")
        y -= 18
        if y < 40:
            break
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", errors="replace")

    objs: list[bytes] = []
    objs.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
    objs.append(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
    objs.append(
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n"
    )
    objs.append(b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")
    objs.append(f"5 0 obj << /Length {len(stream)} >> stream\n".encode("latin-1") + stream + b"\nendstream endobj\n")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objs:
        offsets.append(len(out))
        out.extend(obj)
    xref_start = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n".encode("latin-1"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("latin-1"))
    out.extend(
        f"trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode("latin-1")
    )
    return bytes(out)

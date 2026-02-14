from __future__ import annotations

import struct
import zlib
from pathlib import Path


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _parse_png(path: Path) -> dict | None:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None

    idx = 8
    width = height = bit_depth = color_type = interlace = None
    idat = bytearray()
    while idx + 8 <= len(data):
        length = int.from_bytes(data[idx:idx + 4], "big")
        chunk_type = data[idx + 4:idx + 8]
        chunk_data = data[idx + 8:idx + 8 + length]
        idx += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _comp, _filter, interlace = struct.unpack(">IIBBBBB", chunk_data
            )
        elif chunk_type == b"IDAT":
            idat.extend(chunk_data)
        elif chunk_type == b"IEND":
            break

    if not width or not height or bit_depth != 8 or interlace != 0:
        return None

    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error:
        return None
    bpp = {0: 1, 2: 3, 6: 4}.get(color_type)
    if bpp is None:
        return None
    row_len = width * bpp
    out = bytearray()
    prev = bytearray(row_len)
    p = 0
    for _ in range(height):
        filter_type = raw[p]
        p += 1
        row = bytearray(raw[p:p + row_len])
        p += row_len
        for i in range(row_len):
            left = row[i - bpp] if i >= bpp else 0
            up = prev[i]
            up_left = prev[i - bpp] if i >= bpp else 0
            if filter_type == 1:
                row[i] = (row[i] + left) & 0xFF
            elif filter_type == 2:
                row[i] = (row[i] + up) & 0xFF
            elif filter_type == 3:
                row[i] = (row[i] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                pval = left + up - up_left
                pa = abs(pval - left)
                pb = abs(pval - up)
                pc = abs(pval - up_left)
                pr = left if pa <= pb and pa <= pc else (up if pb <= pc else up_left)
                row[i] = (row[i] + pr) & 0xFF
        prev = row
        if color_type == 0:
            for i in range(width):
                g = row[i]
                out.extend((g, g, g))
        elif color_type == 2:
            out.extend(row)
        elif color_type == 6:
            for i in range(0, len(row), 4):
                out.extend(row[i:i + 3])

    return {
        "width": width,
        "height": height,
        "filter": "FlateDecode",
        "data": zlib.compress(bytes(out)),
    }


def _parse_jpeg(path: Path) -> dict | None:
    data = path.read_bytes()
    if not data.startswith(b"\xff\xd8"):
        return None
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        i += 2
        if marker in (0xD8, 0xD9):
            continue
        seg_len = int.from_bytes(data[i:i + 2], "big")
        if marker in (0xC0, 0xC2):
            h = int.from_bytes(data[i + 3:i + 5], "big")
            w = int.from_bytes(data[i + 5:i + 7], "big")
            return {"width": w, "height": h, "filter": "DCTDecode", "data": data}
        i += seg_len
    return None


def _load_image(path: str | None) -> dict | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return _parse_png(p) or _parse_jpeg(p)


def _build_pdf(commands: list[str], image: dict | None = None) -> bytes:
    stream = "\n".join(commands).encode("latin-1", errors="replace")

    objs: list[bytes] = []
    objs.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
    objs.append(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
    resources = b"/Font << /F1 4 0 R >>"
    if image:
        resources += b" /XObject << /Im1 6 0 R >>"
    objs.append(
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << " + resources + b" >> /Contents 5 0 R >> endobj\n"
    )
    objs.append(b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")
    objs.append(f"5 0 obj << /Length {len(stream)} >> stream\n".encode("latin-1") + stream + b"\nendstream endobj\n")
    if image:
        img_data = image["data"]
        objs.append(
            f"6 0 obj << /Type /XObject /Subtype /Image /Width {image['width']} /Height {image['height']} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /{image['filter']} /Length {len(img_data)} >> stream\n".encode("latin-1")
            + img_data
            + b"\nendstream endobj\n"
        )

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
    out.extend(f"trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode("latin-1"))
    return bytes(out)


def create_pay_stub_pdf_bytes(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 12 Tf"]
    y = 760
    for line in lines:
        commands.append(f"1 0 0 1 72 {y} Tm ({_escape(line)}) Tj")
        y -= 18
        if y < 40:
            break
    commands.append("ET")
    return _build_pdf(commands)


def create_monthly_pay_stub_pdf_bytes(*, company_name: str, employee_name: str, pay_period: str, pay_date: str, salary: float, bonus: float, reimbursements: float, gross: float, fit: float, ss_ee: float, medicare_ee: float, addl_medicare_ee: float, other_deductions: float, net: float, ytd_gross: float, ytd_taxes_deductions: float, ytd_net: float, logo_path: str | None = None) -> bytes:
    image = _load_image(logo_path)
    commands: list[str] = ["0 0 0 rg"]
    if image:
        # top-right logo
        commands.append(f"q 120 0 0 60 444 724 cm /Im1 Do Q")

    commands.extend([
        "BT",
        "/F1 16 Tf",
        f"1 0 0 1 72 760 Tm ({_escape(company_name)}) Tj",
        "/F1 11 Tf",
        f"1 0 0 1 72 742 Tm ({_escape('Monthly Pay Stub • Pay Period: ' + pay_period)}) Tj",
        f"1 0 0 1 72 726 Tm ({_escape('Pay Date: ' + pay_date)}) Tj",
        f"1 0 0 1 72 700 Tm ({_escape('Employee: ' + employee_name)}) Tj",
        f"1 0 0 1 72 676 Tm ({_escape('Earnings')}) Tj",
        f"1 0 0 1 84 660 Tm ({_escape(f'Salary: {salary:.2f}')}) Tj",
        f"1 0 0 1 84 646 Tm ({_escape(f'Bonus: {bonus:.2f}')}) Tj",
        f"1 0 0 1 84 632 Tm ({_escape(f'Reimbursements: {reimbursements:.2f}')}) Tj",
        f"1 0 0 1 84 618 Tm ({_escape(f'Gross: {gross:.2f}')}) Tj",
        f"1 0 0 1 72 594 Tm ({_escape('Taxes & Deductions')}) Tj",
        f"1 0 0 1 84 578 Tm ({_escape(f'FIT: {fit:.2f}')}) Tj",
        f"1 0 0 1 84 564 Tm ({_escape(f'Social Security EE: {ss_ee:.2f}')}) Tj",
        f"1 0 0 1 84 550 Tm ({_escape(f'Medicare EE: {medicare_ee:.2f}')}) Tj",
        f"1 0 0 1 84 536 Tm ({_escape(f'Additional Medicare EE: {addl_medicare_ee:.2f}')}) Tj",
        f"1 0 0 1 84 522 Tm ({_escape(f'Other Deductions: {other_deductions:.2f}')}) Tj",
        f"1 0 0 1 72 498 Tm ({_escape('Net Pay')}) Tj",
        f"1 0 0 1 84 482 Tm ({_escape(f'Net: {net:.2f}')}) Tj",
        f"1 0 0 1 72 458 Tm ({_escape('YTD Summary')}) Tj",
        f"1 0 0 1 84 442 Tm ({_escape(f'Gross Income YTD: {ytd_gross:.2f}')}) Tj",
        f"1 0 0 1 84 428 Tm ({_escape(f'Total Taxes/Deductions YTD: {ytd_taxes_deductions:.2f}')}) Tj",
        f"1 0 0 1 84 414 Tm ({_escape(f'Net Income YTD: {ytd_net:.2f}')}) Tj",
        "ET",
    ])
    return _build_pdf(commands, image=image)

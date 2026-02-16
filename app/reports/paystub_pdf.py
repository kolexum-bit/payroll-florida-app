from __future__ import annotations

import calendar
from datetime import date

from app.services.pdf import _build_pdf, _escape, _load_image

FILING_STATUS_LABELS = {
    "single_or_married_filing_separately": "Single / Married Filing Separately",
    "married_filing_jointly": "Married Filing Jointly",
    "head_of_household": "Head of Household",
}
PAY_FREQUENCY_LABELS = {
    "daily": "Daily",
    "weekly": "Weekly",
    "biweekly": "Biweekly",
    "semimonthly": "Semimonthly",
    "monthly": "Monthly",
}


def _currency(value: float) -> str:
    return f"${value:,.2f}"


def _safe_float(value: float | None) -> float:
    return float(value or 0.0)


def _address_line(company: object) -> str | None:
    parts = []
    for key in ("address_line1", "city", "state", "zip_code"):
        val = getattr(company, key, None)
        if val:
            parts.append(str(val))
    if not parts:
        return None
    return ", ".join(parts)


def _employee_address(employee: object) -> str:
    parts = [
        getattr(employee, "address_line1", "") or "",
        ", ".join(filter(None, [getattr(employee, "city", None), getattr(employee, "state", None), getattr(employee, "zip_code", None)])),
    ]
    return ", ".join(filter(None, parts))


def _masked_ssn(employee: object) -> str:
    last4 = ""
    if getattr(employee, "ssn", None):
        last4 = str(employee.ssn)[-4:]
    elif getattr(employee, "ssn_last4", None):
        last4 = str(employee.ssn_last4)
    return f"***-**-{last4.zfill(4) if last4 else '0000'}"


def _pay_frequency(payroll_record: object, employee: object) -> str:
    raw = getattr(payroll_record, "pay_frequency", None) or getattr(employee, "pay_frequency", None) or "monthly"
    return PAY_FREQUENCY_LABELS.get(str(raw).lower(), "Monthly")


def generate_paystub_pdf(company: object, employee: object, payroll_record: object, ytd_summary: dict) -> bytes:
    month_name = calendar.month_name[int(payroll_record.month)]
    pay_date = payroll_record.pay_date if isinstance(payroll_record.pay_date, date) else date.fromisoformat(str(payroll_record.pay_date))
    filing_status = FILING_STATUS_LABELS.get(getattr(employee, "filing_status", ""), "Single / Married Filing Separately")
    payroll_period = _pay_frequency(payroll_record, employee)

    fit = _safe_float(payroll_record.federal_withholding)
    ss = _safe_float(payroll_record.social_security_ee)
    medicare = _safe_float(payroll_record.medicare_ee)
    addl_medicare = _safe_float(payroll_record.additional_medicare_ee)
    other_deductions = _safe_float(payroll_record.deductions)
    total_deductions = fit + ss + medicare + addl_medicare + other_deductions

    earnings_rows = [
        ("Regular Pay (Monthly Salary)", _safe_float(getattr(employee, "monthly_salary", 0.0))),
    ]
    if _safe_float(payroll_record.bonus) > 0:
        earnings_rows.append(("Bonus", _safe_float(payroll_record.bonus)))
    if _safe_float(payroll_record.reimbursements) > 0:
        earnings_rows.append(("Reimbursements", _safe_float(payroll_record.reimbursements)))

    deduction_rows = [
        ("Federal Income Tax (FIT)", fit),
        ("Social Security (Employee) 6.2%", ss),
        ("Medicare (Employee) 1.45%", medicare),
    ]
    if addl_medicare > 0:
        deduction_rows.append(("Additional Medicare (Employee)", addl_medicare))
    if other_deductions > 0:
        deduction_rows.append(("Other Deductions", other_deductions))

    image = _load_image(getattr(company, "logo_path", None))

    cmds: list[str] = [
        "0.08 w",
        "0 0 0 RG",
        "0 0 0 rg",
    ]

    # Header and optional logo
    if image:
        scale_w = 86.4
        scale_h = scale_w * (float(image["height"]) / float(image["width"]))
        if scale_h > 54:
            scale_h = 54
            scale_w = scale_h * (float(image["width"]) / float(image["height"]))
        cmds.append(f"q {scale_w:.2f} 0 0 {scale_h:.2f} {612 - 72 - scale_w:.2f} {730 - scale_h:.2f} cm /Im1 Do Q")

    cmds.extend([
        "BT",
        "/F1 18 Tf",
        f"1 0 0 1 50 752 Tm ({_escape(company.name)}) Tj",
        "/F1 10 Tf",
    ])
    comp_addr = _address_line(company)
    y_line = 736
    if comp_addr:
        cmds.append(f"1 0 0 1 50 {y_line} Tm ({_escape(comp_addr)}) Tj")
        y_line -= 14
    cmds.append(f"1 0 0 1 50 {y_line} Tm ({_escape('United States')}) Tj")
    cmds.extend([
        "/F1 11 Tf",
        f"1 0 0 1 350 752 Tm ({_escape(f'Pay Stub Month: {month_name} {payroll_record.year}')}) Tj",
        f"1 0 0 1 350 736 Tm ({_escape(f'Pay Date: {pay_date:%m/%d/%Y}')}) Tj",
        "ET",
        "50 714 m 562 714 l S",
    ])

    # Employee information box
    cmds.extend([
        "50 594 330 108 re S",
        "BT",
        "/F1 11 Tf",
        "1 0 0 1 58 688 Tm (EMPLOYEE INFORMATION) Tj",
        "/F1 10 Tf",
        f"1 0 0 1 58 672 Tm ({_escape(f'Employee Name: {employee.first_name} {employee.last_name}')}) Tj",
        f"1 0 0 1 58 658 Tm ({_escape(f'Employee ID: {employee.id}')}) Tj",
        f"1 0 0 1 58 644 Tm ({_escape(f'Address: {_employee_address(employee)}')}) Tj",
        f"1 0 0 1 58 630 Tm ({_escape(f'SSN: {_masked_ssn(employee)}')}) Tj",
        f"1 0 0 1 58 616 Tm ({_escape(f'Filing Status: {filing_status}')}) Tj",
        f"1 0 0 1 58 602 Tm ({_escape(f'Payroll Period: {payroll_period}')}) Tj",
        "ET",
    ])

    # Net pay box
    cmds.extend([
        "0.93 0.96 1 rg",
        "390 594 172 108 re f",
        "0 0 0 rg",
        "390 594 172 108 re S",
        "BT",
        "/F1 10 Tf",
        "1 0 0 1 430 674 Tm (Employee Net Payment) Tj",
        "/F1 24 Tf",
        f"1 0 0 1 412 632 Tm ({_escape(_currency(_safe_float(payroll_record.net_pay)))}) Tj",
        "ET",
    ])

    # Main table with section headers
    table_x = 50
    table_y = 390
    table_w = 512
    table_h = 188
    mid_x = table_x + (table_w / 2)
    cmds.extend([
        "0.94 0.94 0.94 rg",
        f"{table_x} {table_y + table_h - 24} {table_w} 24 re f",
        "0 0 0 rg",
        f"{table_x} {table_y} {table_w} {table_h} re S",
        f"{mid_x} {table_y} m {mid_x} {table_y + table_h} l S",
        f"{table_x} {table_y + table_h - 24} m {table_x + table_w} {table_y + table_h - 24} l S",
        "BT",
        "/F1 11 Tf",
        f"1 0 0 1 {table_x + 8} {table_y + table_h - 16} Tm (EARNINGS) Tj",
        f"1 0 0 1 {mid_x + 8} {table_y + table_h - 16} Tm (DEDUCTIONS) Tj",
        "ET",
    ])

    y_left = table_y + table_h - 42
    for label, amount in earnings_rows:
        cmds.extend([
            "BT",
            "/F1 9 Tf",
            f"1 0 0 1 {table_x + 8} {y_left} Tm ({_escape(label)}) Tj",
            f"1 0 0 1 {mid_x - 56} {y_left} Tm ({_escape(_currency(amount))}) Tj",
            "ET",
        ])
        y_left -= 16

    y_right = table_y + table_h - 42
    for label, amount in deduction_rows:
        cmds.extend([
            "BT",
            "/F1 9 Tf",
            f"1 0 0 1 {mid_x + 8} {y_right} Tm ({_escape(label)}) Tj",
            f"1 0 0 1 {table_x + table_w - 62} {y_right} Tm ({_escape(_currency(amount))}) Tj",
            "ET",
        ])
        y_right -= 16

    # Totals row
    cmds.extend([
        "0.95 0.95 0.95 rg",
        "50 360 512 24 re f",
        "0 0 0 rg",
        "50 360 512 24 re S",
        "BT",
        "/F1 10 Tf",
        f"1 0 0 1 58 368 Tm ({_escape(f'Gross Earnings: {_currency(_safe_float(payroll_record.gross_pay))}')}) Tj",
        f"1 0 0 1 232 368 Tm ({_escape(f'Total Deductions: {_currency(total_deductions)}')}) Tj",
        f"1 0 0 1 430 368 Tm ({_escape(f'Net Pay: {_currency(_safe_float(payroll_record.net_pay))}')}) Tj",
        "ET",
    ])

    # YTD summary box
    ytd_addl = _safe_float(ytd_summary.get("ytd_addl_medicare", 0.0))
    ytd_lines = [
        f"YTD Gross: {_currency(_safe_float(ytd_summary.get('ytd_gross')))}",
        f"YTD Total Deductions: {_currency(_safe_float(ytd_summary.get('ytd_total_deductions')))}",
        f"YTD Net: {_currency(_safe_float(ytd_summary.get('ytd_net')))}",
        f"YTD FIT: {_currency(_safe_float(ytd_summary.get('ytd_fit')))}",
        f"YTD SS: {_currency(_safe_float(ytd_summary.get('ytd_ss')))}",
        f"YTD Medicare: {_currency(_safe_float(ytd_summary.get('ytd_medicare')))}",
    ]
    if ytd_addl > 0:
        ytd_lines.append(f"YTD Additional Medicare: {_currency(ytd_addl)}")

    cmds.extend([
        "50 240 512 108 re S",
        "0.94 0.94 0.94 rg",
        "50 324 512 24 re f",
        "0 0 0 rg",
        "50 324 512 24 re S",
        "BT",
        "/F1 11 Tf",
        "1 0 0 1 58 332 Tm (YTD SUMMARY) Tj",
        "/F1 10 Tf",
    ])

    y = 308
    for line in ytd_lines:
        cmds.append(f"1 0 0 1 58 {y} Tm ({_escape(line)}) Tj")
        y -= 14
    cmds.append("ET")

    return _build_pdf(cmds, image=image)

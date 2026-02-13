from pathlib import Path
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas


def generate_pay_stub_pdf(path: str, company_name: str, employee_name: str, record: dict, ytd_rows: list[dict]):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(path, pagesize=LETTER)
    y = 760
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, f"Monthly Pay Stub - {company_name}")
    y -= 20
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Employee: {employee_name}")
    y -= 16
    c.drawString(40, y, f"Pay Month/Year: {record['pay_month']}/{record['tax_year']}  Pay Date: {record['pay_date']}")
    y -= 20

    lines = [
        f"Gross Wages: ${record['gross_wages']:.2f}",
        f"Pre-tax Deductions: ${record['pre_tax_deductions']:.2f}",
        f"FIT Withholding: ${record['fit_withholding']:.2f}",
        f"Social Security (EE): ${record['social_security_employee']:.2f}",
        f"Medicare (EE): ${record['medicare_employee']:.2f}",
        f"Additional Medicare (EE): ${record['additional_medicare_employee']:.2f}",
        f"Post-tax Deductions: ${record['post_tax_deductions']:.2f}",
        f"Net Pay: ${record['net_pay']:.2f}",
    ]
    for line in lines:
        c.drawString(40, y, line)
        y -= 14

    y -= 10
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, "Gross & Net by Month (YTD)")
    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(40, y, "Month | Gross | Net | Gross Running Total | Net Running Total")
    y -= 12
    for row in ytd_rows:
        c.drawString(40, y, f"{row['month']:>2} | {row['gross']:>8.2f} | {row['net']:>8.2f} | {row['gross_running']:>10.2f} | {row['net_running']:>10.2f}")
        y -= 12
        if y < 60:
            c.showPage()
            y = 760

    c.save()
    return path

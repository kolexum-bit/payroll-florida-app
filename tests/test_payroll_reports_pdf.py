from app.models import MonthlyPayroll
from tests.conftest import create_company, create_employee


def _seed_payroll(client, company_id: int, employee_id: int):
    for month in [1, 2, 3]:
        client.post(
            f"/monthly-payroll?company_id={company_id}",
            data={"employee_id": employee_id, "year": 2025, "month": month, "pay_date": f"2025-{month:02d}-28", "bonus": 100, "reimbursements": 10, "deductions": 50},
        )


def test_rollups_and_company_separation(client):
    create_company(client, "A", "11", 2.7)
    create_company(client, "B", "22", 3.1)
    create_employee(client, 1, "111-22-3333", "Alice")
    create_employee(client, 2, "111-22-4444", "Bob")
    _seed_payroll(client, 1, 1)
    _seed_payroll(client, 2, 2)

    rt6_a = client.get("/reports?company_id=1&report_type=rt6&year=2025&quarter=1")
    rt6_b = client.get("/reports?company_id=2&report_type=rt6&year=2025&quarter=1")
    assert rt6_a.status_code == 200
    assert rt6_b.status_code == 200
    assert "SPEC Mapping" in rt6_a.text
    assert rt6_a.text != rt6_b.text


def test_941_940_reports_show_non_zero_totals(client):
    create_company(client, "A", "11")
    create_employee(client, 1, "111-22-3333", "Alice")
    _seed_payroll(client, 1, 1)

    r941 = client.get("/reports?company_id=1&report_type=941&year=2025&quarter=1")
    assert r941.status_code == 200
    assert "Form 941 Quarterly Summary" in r941.text
    assert "Additional Medicare EE" in r941.text
    assert "Total Tax: 0" not in r941.text

    r940 = client.get("/reports?company_id=1&report_type=940&year=2025")
    assert r940.status_code == 200
    assert "Form 940 Annual FUTA Summary" in r940.text
    assert "Taxable FUTA Wages" in r940.text
    assert "SPEC Mapping" in r940.text


def test_pay_stub_pdf_smoke_contains_key_strings(client):
    create_company(client, "A", "11")
    create_employee(client, 1, "111-22-3333", "Alice")
    client.post("/monthly-payroll?company_id=1", data={"employee_id": 1, "year": 2025, "month": 3, "pay_date": "2025-03-31", "bonus": 0, "reimbursements": 0, "deductions": 0})

    pay_stub = client.post("/pay-stubs/generate?company_id=1", data={"employee_id": 1, "year": 2025, "month": 3})
    assert pay_stub.status_code == 200
    assert len(pay_stub.content) > 1000
    assert b"Alice Doe" in pay_stub.content
    assert b"A" in pay_stub.content
    assert b"YTD" in pay_stub.content


def test_w2_pdf_smoke(client):
    create_company(client, "A", "11")
    create_employee(client, 1, "111-22-3333", "Alice")
    client.post("/monthly-payroll?company_id=1", data={"employee_id": 1, "year": 2025, "month": 3, "pay_date": "2025-03-31", "bonus": 0, "reimbursements": 0, "deductions": 0})

    w2 = client.post("/w2/generate/1?company_id=1", data={"year": 2025})
    assert w2.status_code == 200
    assert b"W-2 Wage and Tax Statement" in w2.content
    assert b"Box 1 Wages" in w2.content


def test_pay_stub_pdf_ytd_sums_all_records_for_year(client):
    create_company(client, "A", "11")
    create_employee(client, 1, "111-22-3333", "Alice")
    client.post("/monthly-payroll?company_id=1", data={"employee_id": 1, "year": 2025, "month": 1, "pay_date": "2025-01-31", "bonus": 0, "reimbursements": 0, "deductions": 100})
    client.post("/monthly-payroll?company_id=1", data={"employee_id": 1, "year": 2025, "month": 2, "pay_date": "2025-02-28", "bonus": 200, "reimbursements": 0, "deductions": 50})

    pay_stub = client.post("/pay-stubs/generate?company_id=1", data={"employee_id": 1, "year": 2025, "month": 2})
    assert pay_stub.status_code == 200
    assert b"Gross Income YTD" in pay_stub.content
    assert b"Total Taxes/Deductions YTD" in pay_stub.content
    assert b"Net Income YTD" in pay_stub.content

    with client.app.state.session_factory() as db:
        rows = db.query(MonthlyPayroll).filter(MonthlyPayroll.company_id == 1, MonthlyPayroll.employee_id == 1, MonthlyPayroll.year == 2025, MonthlyPayroll.month <= 2).all()
        gross_ytd = sum(r.gross_pay for r in rows)
        total_deductions_ytd = sum(r.federal_withholding + r.social_security_ee + r.medicare_ee + r.additional_medicare_ee + r.deductions for r in rows)
        net_ytd = sum(r.net_pay for r in rows)

    assert f"Gross Income YTD: {gross_ytd:.2f}".encode() in pay_stub.content
    assert f"Total Taxes/Deductions YTD: {total_deductions_ytd:.2f}".encode() in pay_stub.content
    assert f"Net Income YTD: {net_ytd:.2f}".encode() in pay_stub.content


def test_pay_stub_pdf_with_logo_still_contains_key_content(client):
    import io

    create_company(client, "A", "11")
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc``\x00\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
    client.post(
        "/company",
        data={"company_id": 1, "name": "A", "fein": "11", "florida_account_number": "A-FL", "default_tax_year": 2025, "fl_suta_rate": "2.7%"},
        files={"logo": ("logo.png", io.BytesIO(png_bytes), "image/png")},
    )
    create_employee(client, 1, "111-22-3333", "Alice")
    client.post("/monthly-payroll?company_id=1", data={"employee_id": 1, "year": 2025, "month": 3, "pay_date": "2025-03-31", "bonus": 0, "reimbursements": 0, "deductions": 0})

    pay_stub = client.post("/pay-stubs/generate?company_id=1", data={"employee_id": 1, "year": 2025, "month": 3})
    assert pay_stub.status_code == 200
    assert len(pay_stub.content) > 1000
    assert b"Alice Doe" in pay_stub.content
    assert b"YTD" in pay_stub.content

from tests.conftest import create_company, create_employee


def _seed_payroll(client, company_id: int, employee_id: int):
    for month in [1, 2, 3]:
        client.post(f"/monthly-payroll?company_id={company_id}", data={"employee_id": employee_id, "year": 2025, "month": month, "pay_date": f"2025-{month:02d}-28", "bonus": 100, "reimbursements": 10, "deductions": 50})


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
    assert "Total Tax:" in r941.text
    assert "Total Tax: 0" not in r941.text

    r940 = client.get("/reports?company_id=1&report_type=940&year=2025")
    assert r940.status_code == 200
    assert "Form 940 Annual FUTA Summary" in r940.text
    assert "FUTA Tax:" in r940.text
    assert "SPEC Mapping" in r940.text


def test_pay_stub_and_w2_pdf_smoke(client):
    create_company(client, "A", "11")
    create_employee(client, 1, "111-22-3333", "Alice")
    client.post("/monthly-payroll?company_id=1", data={"employee_id": 1, "year": 2025, "month": 3, "pay_date": "2025-03-31", "bonus": 0, "reimbursements": 0, "deductions": 0})

    pay_stub = client.post("/pay-stubs/generate?company_id=1", data={"employee_id": 1, "year": 2025, "month": 3})
    assert pay_stub.status_code == 200
    assert b"Monthly Pay Stub" in pay_stub.content
    assert b"Gross & Net by Month" in pay_stub.content

    w2 = client.post("/w2/generate/1?company_id=1", data={"year": 2025})
    assert w2.status_code == 200
    assert b"W-2 Wage and Tax Statement" in w2.content
    assert b"Box 1 Wages" in w2.content

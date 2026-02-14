from tests.conftest import create_company, create_employee, select_company


def _seed_payroll(client, company_id: int, employee_id: int):
    select_company(client, company_id, "/monthly-payroll")
    for month in [1, 2, 3]:
        client.post("/monthly-payroll", data={"employee_id": employee_id, "year": 2025, "month": month, "pay_date": f"2025-{month:02d}-28", "bonus": 100, "reimbursements": 10, "deductions": 50})


def test_rollups_and_company_separation(client):
    create_company(client, "A", "11", 2.7)
    create_company(client, "B", "22", 3.1)
    create_employee(client, 1, "111-22-3333", "Alice")
    create_employee(client, 2, "111-22-4444", "Bob")
    _seed_payroll(client, 1, 1)
    _seed_payroll(client, 2, 2)

    select_company(client, 1, "/reports")
    rt6_a = client.get("/reports?report_type=rt6&year=2025&quarter=1")
    select_company(client, 2, "/reports")
    rt6_b = client.get("/reports?report_type=rt6&year=2025&quarter=1")
    assert rt6_a.status_code == 200
    assert rt6_b.status_code == 200
    assert rt6_a.text != rt6_b.text


def test_pay_stub_and_w2_pdf_smoke(client):
    create_company(client, "A", "11")
    create_employee(client, 1, "111-22-3333", "Alice")
    select_company(client, 1, "/monthly-payroll")
    client.post("/monthly-payroll", data={"employee_id": 1, "year": 2025, "month": 3, "pay_date": "2025-03-31", "bonus": 0, "reimbursements": 0, "deductions": 0})

    pay_stub = client.post("/pay-stubs/generate", data={"employee_id": 1, "year": 2025, "month": 3})
    assert pay_stub.status_code == 200
    assert b"Monthly Pay Stub" in pay_stub.content
    assert b"Gross & Net by Month" in pay_stub.content

    w2 = client.post("/w2/generate/1", data={"year": 2025})
    assert w2.status_code == 200
    assert b"W-2 Wage and Tax Statement" in w2.content
    assert b"Box 1 Wages" in w2.content

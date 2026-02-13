from tests.conftest import seed_employee


def test_monthly_payroll_crud(client):
    seed_employee(client)
    create = client.post(
        "/monthly-payroll",
        data={
            "employee_id": 1,
            "year": 2025,
            "month": 1,
            "pay_date": "2025-01-31",
            "hours_worked": 173.33,
        },
        follow_redirects=False,
    )
    assert create.status_code == 302
    page = client.get("/monthly-payroll")
    assert "2025/1" in page.text

    client.post(
        "/monthly-payroll",
        data={
            "record_id": 1,
            "employee_id": 1,
            "year": 2025,
            "month": 1,
            "pay_date": "2025-01-30",
            "hours_worked": 150,
        },
    )
    assert "2025-01-30" in client.get("/monthly-payroll").text

    client.post("/monthly-payroll/1/delete")
    assert "2025/1" not in client.get("/monthly-payroll").text


def test_report_rollups_and_exports(client):
    seed_employee(client)
    client.post("/monthly-payroll", data={"employee_id": 1, "year": 2025, "month": 1, "pay_date": "2025-01-31", "hours_worked": 173.33})
    client.post("/monthly-payroll", data={"employee_id": 1, "year": 2025, "month": 2, "pay_date": "2025-02-28", "hours_worked": 173.33})

    rt6 = client.get("/reports?report_type=rt6&year=2025&quarter=1")
    assert rt6.status_code == 200
    assert "Contributions Due" in rt6.text

    f941 = client.get("/reports?report_type=941&year=2025&quarter=1")
    assert "Total Tax" in f941.text

    f940 = client.get("/reports?report_type=940&year=2025")
    assert "FUTA Tax" in f940.text

    csv_resp = client.get("/reports/export/941?year=2025&quarter=1&format=csv")
    assert csv_resp.status_code == 200
    assert "wages" in csv_resp.text


def test_pay_stub_pdf_smoke(client):
    seed_employee(client)
    client.post("/monthly-payroll", data={"employee_id": 1, "year": 2025, "month": 3, "pay_date": "2025-03-31", "hours_worked": 173.33})

    resp = client.post("/pay-stubs/generate", data={"employee_id": 1, "year": 2025, "month": 3})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert b"Monthly Pay Stub" in resp.content
    assert b"Jane Doe" in resp.content

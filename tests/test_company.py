from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def build_client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "test.db"
    app = create_app(f"sqlite:///{db_path}")
    return TestClient(app)


def create_company(client: TestClient):
    return client.post(
        "/company",
        data={
            "name": "Acme Co",
            "fein": "12-3456789",
            "florida_account_number": "FL-111",
            "default_tax_year": 2025,
            "fl_suta_rate": 2.7,
        },
        follow_redirects=False,
    )


def create_employee(client: TestClient):
    create_company(client)
    return client.post(
        "/employees",
        data={
            "company_id": 1,
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane@example.com",
            "monthly_salary": 6000,
        },
        follow_redirects=False,
    )


def create_payroll(client: TestClient):
    create_employee(client)
    return client.post(
        "/monthly-payroll",
        data={"employee_id": 1, "period": "2025-01", "gross_pay": 6000},
        follow_redirects=False,
    )


def test_company_crud(tmp_path: Path):
    client = build_client(tmp_path)

    response = create_company(client)
    assert response.status_code == 302

    list_response = client.get("/company")
    assert "Acme Co" in list_response.text

    update = client.post(
        "/company",
        data={
            "company_id": 1,
            "name": "Acme Updated",
            "fein": "12-3456789",
            "florida_account_number": "FL-111",
            "default_tax_year": 2026,
            "fl_suta_rate": 3.0,
        },
        follow_redirects=False,
    )
    assert update.status_code == 302
    assert "Acme Updated" in client.get("/company").text

    delete_response = client.post("/company/1/delete", follow_redirects=False)
    assert delete_response.status_code == 302
    assert "Acme Updated" not in client.get("/company").text


def test_employee_crud(tmp_path: Path):
    client = build_client(tmp_path)
    response = create_employee(client)
    assert response.status_code == 302
    page = client.get("/employees")
    assert "Jane Doe" in page.text

    update = client.post(
        "/employees",
        data={
            "employee_id": 1,
            "company_id": 1,
            "first_name": "Janet",
            "last_name": "Doe",
            "email": "janet@example.com",
            "monthly_salary": 6200,
        },
        follow_redirects=False,
    )
    assert update.status_code == 302
    assert "Janet Doe" in client.get("/employees").text

    delete = client.post("/employees/1/delete", follow_redirects=False)
    assert delete.status_code == 302
    assert "Janet Doe" not in client.get("/employees").text


def test_monthly_payroll_crud_and_trace(tmp_path: Path):
    client = build_client(tmp_path)
    response = create_payroll(client)
    assert response.status_code == 302

    page = client.get("/monthly-payroll")
    assert "2025-01" in page.text
    assert "No payroll entries yet." not in page.text

    update = client.post(
        "/monthly-payroll",
        data={"payroll_id": 1, "employee_id": 1, "period": "2025-02", "gross_pay": 5000},
        follow_redirects=False,
    )
    assert update.status_code == 302
    updated = client.get("/monthly-payroll")
    assert "2025-02" in updated.text

    delete = client.post("/monthly-payroll/1/delete", follow_redirects=False)
    assert delete.status_code == 302
    assert "2025-02" not in client.get("/monthly-payroll").text


def test_paystub_pdf_endpoint(tmp_path: Path):
    client = build_client(tmp_path)
    create_payroll(client)

    pdf_response = client.get("/paystubs/1.pdf")
    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"].startswith("application/pdf")
    assert pdf_response.content.startswith(b"%PDF")


def test_reports_page(tmp_path: Path):
    client = build_client(tmp_path)
    create_payroll(client)

    response = client.get("/reports")
    assert response.status_code == 200
    assert "Total payroll entries" in response.text
    assert "6000.0" in response.text


def test_navigation_routes_exist(tmp_path: Path):
    client = build_client(tmp_path)
    for route in ["/company", "/employees", "/monthly-payroll", "/paystubs", "/reports"]:
        response = client.get(route)
        assert response.status_code == 200

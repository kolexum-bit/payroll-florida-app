from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def build_client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "test.db"
    app = create_app(f"sqlite:///{db_path}")
    return TestClient(app)


def test_create_company_persists_to_db(tmp_path: Path):
    client = build_client(tmp_path)

    response = client.post(
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

    assert response.status_code == 302
    assert response.headers["location"].startswith("/company")

    list_response = client.get("/company")
    assert "Acme Co" in list_response.text


def test_company_list_returns_company_in_html(tmp_path: Path):
    client = build_client(tmp_path)

    client.post(
        "/company",
        data={
            "name": "Sun Payroll",
            "fein": "98-7654321",
            "florida_account_number": "FL-222",
            "default_tax_year": 2024,
            "fl_suta_rate": 1.9,
        },
    )

    response = client.get("/company")

    assert response.status_code == 200
    assert "<table" in response.text
    assert "Sun Payroll" in response.text
    assert "98-7654321" in response.text


def test_delete_company_removes_company(tmp_path: Path):
    client = build_client(tmp_path)

    client.post(
        "/company",
        data={
            "name": "Delete Me Inc",
            "fein": "11-1111111",
            "florida_account_number": "FL-333",
            "default_tax_year": 2026,
            "fl_suta_rate": 3.1,
        },
    )

    before_delete = client.get("/company")
    assert "Delete Me Inc" in before_delete.text

    delete_response = client.post("/company/1/delete", follow_redirects=False)
    assert delete_response.status_code == 302

    after_delete = client.get("/company")
    assert "Delete Me Inc" not in after_delete.text

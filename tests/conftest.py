from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "test.db"
    app = create_app(f"sqlite:///{db_path}")
    return TestClient(app)


def create_company(client: TestClient, name: str, fein: str, rate: float = 2.7):
    client.post("/company", data={"name": name, "fein": fein, "florida_account_number": f"{name}-FL", "default_tax_year": 2025, "fl_suta_rate": rate})


def select_company(client: TestClient, company_id: int, redirect_to: str = "/employees"):
    client.post("/select-company", data={"company_id": company_id, "redirect_to": redirect_to})


def create_employee(client: TestClient, company_id: int, ssn: str, first: str = "Jane"):
    select_company(client, company_id)
    client.post(
        "/employees",
        data={
            "first_name": first,
            "last_name": "Doe",
            "address_line1": "1 Main St",
            "city": "Miami",
            "state": "FL",
            "zip_code": "33101",
            "ssn": ssn,
            "filing_status": "single",
            "w4_dependents_amount": 0,
            "w4_other_income": 0,
            "w4_deductions": 0,
            "w4_extra_withholding": 0,
            "monthly_salary": 5000,
        },
    )

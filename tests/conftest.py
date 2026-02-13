from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "test.db"
    app = create_app(f"sqlite:///{db_path}")
    return TestClient(app)


def seed_company(client: TestClient) -> None:
    client.post(
        "/company",
        data={
            "name": "Acme Co",
            "fein": "12-3456789",
            "florida_account_number": "FL-111",
            "default_tax_year": 2025,
            "fl_suta_rate": 2.7,
        },
    )


def seed_employee(client: TestClient) -> None:
    seed_company(client)
    client.post(
        "/employees",
        data={
            "company_id": 1,
            "first_name": "Jane",
            "last_name": "Doe",
            "ssn_last4": "1234",
            "filing_status": "single",
            "w4_dependents_amount": 500,
            "w4_other_income": 0,
            "w4_deductions": 100,
            "w4_extra_withholding": 25,
            "pay_type": "salary",
            "base_rate": 5000,
            "default_hours_per_month": 173.33,
        },
    )

from tests.conftest import seed_company


def test_employee_crud_and_w4_fields(client):
    seed_company(client)
    create = client.post(
        "/employees",
        data={
            "company_id": 1,
            "first_name": "Jane",
            "last_name": "Doe",
            "ssn_last4": "1234",
            "filing_status": "single",
            "w4_dependents_amount": 500,
            "w4_other_income": 10,
            "w4_deductions": 20,
            "w4_extra_withholding": 30,
            "pay_type": "hourly",
            "base_rate": 42,
            "default_hours_per_month": 160,
        },
        follow_redirects=False,
    )
    assert create.status_code == 302

    page = client.get("/employees")
    assert "Jane Doe" in page.text
    assert "hourly" in page.text

    client.post(
        "/employees",
        data={
            "employee_id": 1,
            "company_id": 1,
            "first_name": "Janet",
            "last_name": "Doe",
            "ssn_last4": "1234",
            "filing_status": "married",
            "w4_dependents_amount": 600,
            "w4_other_income": 0,
            "w4_deductions": 0,
            "w4_extra_withholding": 0,
            "pay_type": "salary",
            "base_rate": 7000,
            "default_hours_per_month": 173.33,
        },
    )
    assert "Janet Doe" in client.get("/employees").text

    client.post("/employees/1/delete")
    assert "Janet Doe" not in client.get("/employees").text

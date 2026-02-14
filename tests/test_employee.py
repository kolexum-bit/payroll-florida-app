from tests.conftest import create_company, create_employee


def test_employee_scoped_by_company_and_unique_ssn(client):
    create_company(client, "A", "11")
    create_company(client, "B", "22")
    create_employee(client, 1, "111-22-3333", "Alice")
    create_employee(client, 2, "111-22-3333", "Bob")

    a_page = client.get("/employees?company_id=1")
    b_page = client.get("/employees?company_id=2")
    assert "Alice Doe" in a_page.text
    assert "Bob Doe" not in a_page.text
    assert "Bob Doe" in b_page.text

    dup = client.post("/employees?company_id=1", data={"first_name": "Dup", "last_name": "Doe", "address_line1": "1 Main", "city": "Miami", "state": "FL", "zip_code": "33101", "ssn": "111-22-3333", "pay_frequency": "monthly", "filing_status": "single_or_married_filing_separately", "w4_dependents_amount": 0, "w4_other_income": 0, "w4_deductions": 0, "w4_extra_withholding": 0, "monthly_salary": 3000}, follow_redirects=False)
    assert dup.status_code == 302


def test_employee_form_shows_required_w4_and_frequency_fields(client):
    create_company(client, "A", "11")
    page = client.get("/employees?company_id=1")
    assert "Pay Frequency (required)" in page.text
    assert "W-4 Filing Status (required)" in page.text
    assert "W-4 Dependents Amount (Step 3)" in page.text
    assert "Other Income (Step 4a)" in page.text
    assert "Deductions (Step 4b)" in page.text
    assert "Extra Withholding per paycheck (Step 4c)" in page.text

from tests.conftest import create_company, create_employee, select_company


def test_employee_scoped_by_company_and_unique_ssn(client):
    create_company(client, "A", "11")
    create_company(client, "B", "22")
    create_employee(client, 1, "111-22-3333", "Alice")
    create_employee(client, 2, "111-22-3333", "Bob")

    select_company(client, 1)
    a_page = client.get("/employees")
    select_company(client, 2)
    b_page = client.get("/employees")
    assert "Alice Doe" in a_page.text
    assert "Bob Doe" not in a_page.text
    assert "Bob Doe" in b_page.text

    select_company(client, 1)
    dup = client.post("/employees", data={"first_name": "Dup", "last_name": "Doe", "address_line1": "1 Main", "city": "Miami", "state": "FL", "zip_code": "33101", "ssn": "111-22-3333", "filing_status": "single", "w4_dependents_amount": 0, "w4_other_income": 0, "w4_deductions": 0, "w4_extra_withholding": 0, "monthly_salary": 3000}, follow_redirects=False)
    assert dup.status_code == 302

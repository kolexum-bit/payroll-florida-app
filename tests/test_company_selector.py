from tests.conftest import create_company, create_employee, select_company


def test_employees_redirects_without_selected_company(client):
    create_company(client, "A", "11")

    response = client.get("/employees", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/company?message=Please+select+a+company+to+continue.&status=error"


def test_select_company_sets_context_and_loads_employees(client):
    create_company(client, "Acme", "11")

    response = client.post("/select-company", data={"company_id": 1, "redirect_to": "/employees"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/employees"

    employees_page = client.get("/employees")
    assert employees_page.status_code == 200
    assert "Employees - Acme" in employees_page.text


def test_employee_data_filtered_by_selected_company(client):
    create_company(client, "A", "11")
    create_company(client, "B", "22")
    create_employee(client, 1, "111-22-3333", "Alice")
    create_employee(client, 2, "111-22-4444", "Bob")

    select_company(client, 1)
    company_a_page = client.get("/employees")
    assert "Alice Doe" in company_a_page.text
    assert "Bob Doe" not in company_a_page.text

    select_company(client, 2)
    company_b_page = client.get("/employees")
    assert "Bob Doe" in company_b_page.text
    assert "Alice Doe" not in company_b_page.text

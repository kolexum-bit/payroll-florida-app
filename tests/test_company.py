from tests.conftest import create_company


def test_company_crud(client):
    create_company(client, "Acme Co", "12-3456789")
    assert "Acme Co" in client.get("/company").text
    client.post("/company", data={"company_id": 1, "name": "Acme Updated", "fein": "12-3456789", "florida_account_number": "FL-1", "default_tax_year": 2025, "fl_suta_rate": 2.9})
    assert "Acme Updated" in client.get("/company").text
    client.post("/company/1/delete")
    assert "Acme Updated" not in client.get("/company").text

import io

from app.models import Company
from tests.conftest import create_company


def test_company_crud(client):
    create_company(client, "Acme Co", "12-3456789")
    assert "Acme Co" in client.get("/company").text
    client.post("/company", data={"company_id": 1, "name": "Acme Updated", "fein": "12-3456789", "florida_account_number": "FL-1", "default_tax_year": 2025, "fl_suta_rate": 2.9})
    assert "Acme Updated" in client.get("/company").text
    client.post("/company/1/delete")
    assert "Acme Updated" not in client.get("/company").text


def test_company_logo_upload_and_remove(client):
    create_company(client, "Acme Co", "12-3456789")

    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc``\x00\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
    resp = client.post(
        "/company",
        data={"company_id": 1, "name": "Acme Co", "fein": "12-3456789", "florida_account_number": "FL-1", "default_tax_year": 2025, "fl_suta_rate": "2.7%"},
        files={"logo": ("logo.png", io.BytesIO(png_bytes), "image/png")},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Company updated" in resp.text

    with client.app.state.session_factory() as db:
        company = db.get(Company, 1)
        assert company.logo_path

    resp = client.post(
        "/company",
        data={"company_id": 1, "name": "Acme Co", "fein": "12-3456789", "florida_account_number": "FL-1", "default_tax_year": 2025, "fl_suta_rate": "2.7%", "remove_logo": "1"},
    )
    assert resp.status_code == 200

    with client.app.state.session_factory() as db:
        company = db.get(Company, 1)
        assert company.logo_path is None

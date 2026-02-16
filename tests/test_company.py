import io
from pathlib import Path

from app.models import Company
from tests.conftest import create_company


def test_company_crud(client):
    create_company(client, "Acme Co", "12-3456789")
    assert "Acme Co" in client.get("/company").text
    client.post("/company", data={"company_id": 1, "name": "Acme Updated", "fein": "12-3456789", "florida_account_number": "FL-1", "default_tax_year": 2025, "fl_suta_rate": 2.9})
    assert "Acme Updated" in client.get("/company").text
    client.post("/company/1/delete")
    assert "Acme Updated" not in client.get("/company").text


def test_company_logo_upload_saves_file_and_updates_db(client):
    create_company(client, "Acme Co", "12-3456789")

    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc``\x00\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
    resp = client.post(
        "/company/1/logo",
        files={"logo": ("original-client-name.png", io.BytesIO(png_bytes), "image/png")},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Logo uploaded" in resp.text

    with client.app.state.session_factory() as db:
        company = db.get(Company, 1)
        assert company.logo_path == "company_logos/1/logo.png"
        assert company.logo_mime == "image/png"
        logo_file = Path("app/static") / company.logo_path
        assert logo_file.exists()
        assert logo_file.read_bytes() == png_bytes


def test_company_logo_delete_removes_file_and_clears_db(client):
    create_company(client, "Acme Co", "12-3456789")

    jpg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00" + b"\x08" * 64 + b"\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00?\x00\xd2\xcf \xff\xd9"
    upload_resp = client.post(
        "/company/1/logo",
        files={"logo": ("my-logo.jpeg", io.BytesIO(jpg_bytes), "image/jpeg")},
        follow_redirects=True,
    )
    assert upload_resp.status_code == 200

    with client.app.state.session_factory() as db:
        before_delete = db.get(Company, 1)
        logo_file = Path("app/static") / before_delete.logo_path
        assert logo_file.exists()

    resp = client.post("/company/1/logo/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert "Logo removed" in resp.text

    with client.app.state.session_factory() as db:
        company = db.get(Company, 1)
        assert company.logo_path is None
        assert company.logo_mime is None

    assert not logo_file.exists()

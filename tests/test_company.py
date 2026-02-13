def test_company_crud(client):
    create = client.post(
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
    assert create.status_code == 302

    listing = client.get("/company")
    assert "Acme Co" in listing.text

    update = client.post(
        "/company",
        data={
            "company_id": 1,
            "name": "Acme Updated",
            "fein": "12-3456789",
            "florida_account_number": "FL-111",
            "default_tax_year": 2026,
            "fl_suta_rate": 2.9,
        },
    )
    assert update.status_code == 200
    assert "Acme Updated" in client.get("/company").text

    delete = client.post("/company/1/delete", follow_redirects=False)
    assert delete.status_code == 302
    assert "Acme Updated" not in client.get("/company").text

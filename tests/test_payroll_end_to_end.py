from app.models import MonthlyPayroll
from app.services.payroll import DATA_DIR
from tests.conftest import create_company, create_employee


def test_save_payroll_2026_no_500_and_persists(client):
    create_company(client, "Acme", "11", 2.7)
    create_employee(client, 1, "111-22-3333", "Alice")

    resp = client.post(
        "/monthly-payroll?company_id=1",
        data={"employee_id": 1, "year": 2026, "month": 1, "pay_date": "2026-01-31", "bonus": 100, "reimbursements": 50, "deductions": 25},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Payroll created" in resp.text
    assert "Alice Doe" in resp.text

    with client.app.state.session_factory() as db:
        rec = db.query(MonthlyPayroll).filter(MonthlyPayroll.company_id == 1, MonthlyPayroll.employee_id == 1, MonthlyPayroll.year == 2026, MonthlyPayroll.month == 1).one()
        assert rec.gross_pay > 0
        assert rec.federal_withholding > 0
        assert rec.social_security_ee > 0
        assert rec.social_security_er > 0
        assert rec.medicare_ee > 0
        assert rec.medicare_er > 0
        assert rec.futa_er > 0
        assert rec.suta_er > 0
        assert rec.net_pay > 0
        assert rec.calculation_trace["files"] == ["data/tax/2026/rates.json"]


def test_missing_tax_config_returns_friendly_error_and_400(client, monkeypatch):
    create_company(client, "Acme", "11", 2.7)
    create_employee(client, 1, "111-22-3333", "Alice")
    monkeypatch.setattr("app.services.payroll.DATA_DIR", DATA_DIR.parent / "missing")

    html_resp = client.post(
        "/monthly-payroll?company_id=1",
        data={"employee_id": 1, "year": 2099, "month": 1, "pay_date": "2099-01-31", "bonus": 0, "reimbursements": 0, "deductions": 0},
        follow_redirects=True,
    )
    assert html_resp.status_code == 200
    assert "Missing tax configuration" in html_resp.text

    api_resp = client.post(
        "/monthly-payroll?company_id=1",
        data={"employee_id": 1, "year": 2099, "month": 2, "pay_date": "2099-02-28", "bonus": 0, "reimbursements": 0, "deductions": 0},
        headers={"accept": "application/json"},
    )
    assert api_resp.status_code == 400
    assert "Missing tax configuration" in api_resp.text


def test_upsert_one_record_per_period(client):
    create_company(client, "Acme", "11", 2.7)
    create_employee(client, 1, "111-22-3333", "Alice")

    client.post("/monthly-payroll?company_id=1", data={"employee_id": 1, "year": 2025, "month": 3, "pay_date": "2025-03-31", "bonus": 0, "reimbursements": 0, "deductions": 0})
    client.post("/monthly-payroll?company_id=1", data={"employee_id": 1, "year": 2025, "month": 3, "pay_date": "2025-03-31", "bonus": 100, "reimbursements": 0, "deductions": 0})

    with client.app.state.session_factory() as db:
        rows = db.query(MonthlyPayroll).filter(MonthlyPayroll.company_id == 1, MonthlyPayroll.employee_id == 1, MonthlyPayroll.year == 2025, MonthlyPayroll.month == 3).all()
        assert len(rows) == 1
        assert rows[0].bonus == 100


def test_rt6_941_940_match_saved_ledger_math(client):
    create_company(client, "Acme", "11", 2.7)
    create_employee(client, 1, "111-22-3333", "Alice")

    for month in [1, 2, 3]:
        client.post(
            "/monthly-payroll?company_id=1",
            data={"employee_id": 1, "year": 2025, "month": month, "pay_date": f"2025-{month:02d}-28", "bonus": 0, "reimbursements": 0, "deductions": 0},
        )

    with client.app.state.session_factory() as db:
        records = db.query(MonthlyPayroll).filter(MonthlyPayroll.company_id == 1, MonthlyPayroll.year == 2025).all()
        suta_taxable = sum((r.calculation_trace or {}).get("steps", {}).get("suta_taxable_wages", 0) for r in records)
        futa_taxable = sum((r.calculation_trace or {}).get("steps", {}).get("futa_taxable_wages", 0) for r in records)
        assert suta_taxable == 7000
        assert futa_taxable == 7000

    rt6 = client.get("/reports?company_id=1&report_type=rt6&year=2025&quarter=1")
    assert "Taxable Wages: 7000.0" in rt6.text

    r941 = client.get("/reports?company_id=1&report_type=941&year=2025&quarter=1")
    assert "Form 941 Quarterly Summary" in r941.text
    assert "Total Tax:" in r941.text

    r940 = client.get("/reports?company_id=1&report_type=940&year=2025")
    assert "Taxable FUTA Wages: 7000.0" in r940.text

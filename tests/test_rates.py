from app.models import Company, MonthlyPayroll
from app.utils.rates import parse_rate_to_decimal
from tests.conftest import create_company, create_employee


def test_parse_rate_to_decimal_supported_formats():
    assert parse_rate_to_decimal("2.7") == 0.027
    assert parse_rate_to_decimal("2.7%") == 0.027
    assert parse_rate_to_decimal(0.027) == 0.027
    assert parse_rate_to_decimal("0.027") == 0.027
    assert parse_rate_to_decimal("3") == 0.03


def test_company_rate_normalizes_and_rt6_uses_decimal_once(client):
    create_company(client, "Acme", "11", "2.7%")
    create_employee(client, 1, "111-22-3333", "Alice")

    with client.app.state.session_factory() as db:
        company = db.get(Company, 1)
        assert company.fl_suta_rate == 0.027

    client.post(
        "/monthly-payroll?company_id=1",
        data={"employee_id": 1, "year": 2025, "month": 1, "pay_date": "2025-01-31", "bonus": 0, "reimbursements": 0, "deductions": 0},
    )

    with client.app.state.session_factory() as db:
        rec = db.query(MonthlyPayroll).filter(MonthlyPayroll.company_id == 1, MonthlyPayroll.month == 1).one()
        taxable = rec.calculation_trace["steps"]["suta_taxable_wages"]
        assert rec.suta_er == round(taxable * 0.027, 2)

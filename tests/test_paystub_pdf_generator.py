from datetime import date
from types import SimpleNamespace

from app.reports.paystub_pdf import generate_paystub_pdf


def _objects():
    company = SimpleNamespace(
        name="Acme Payroll LLC",
        fein="12-3456789",
        florida_account_number="FL-123",
        address_line1="100 Ocean Dr",
        city="Miami",
        state="FL",
        zip_code="33101",
        logo_path=None,
    )
    employee = SimpleNamespace(
        id=7,
        first_name="Alice",
        last_name="Doe",
        address_line1="1 Main St",
        city="Miami",
        state="FL",
        zip_code="33101",
        ssn="111-22-3333",
        filing_status="single_or_married_filing_separately",
        pay_frequency="monthly",
        monthly_salary=5000.0,
    )
    record = SimpleNamespace(
        year=2025,
        month=3,
        pay_date=date(2025, 3, 31),
        bonus=100.0,
        reimbursements=10.0,
        gross_pay=5110.0,
        federal_withholding=450.0,
        social_security_ee=316.82,
        medicare_ee=74.10,
        additional_medicare_ee=0.0,
        deductions=50.0,
        net_pay=4219.08,
    )
    ytd_summary = {
        "ytd_gross": 10000.0,
        "ytd_net": 8000.0,
        "ytd_fit": 900.0,
        "ytd_ss": 620.0,
        "ytd_medicare": 145.0,
        "ytd_addl_medicare": 0.0,
        "ytd_other_deductions": 80.0,
        "ytd_total_deductions": 1745.0,
    }
    return company, employee, record, ytd_summary


def test_generate_paystub_pdf_bytes_non_empty_and_contains_required_text():
    company, employee, record, ytd_summary = _objects()
    pdf_bytes = generate_paystub_pdf(company, employee, record, ytd_summary)

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert b"SSN: ***-**-3333" in pdf_bytes
    assert b"State Income Tax" not in pdf_bytes
    assert b"Net Pay: $4,219.08" in pdf_bytes

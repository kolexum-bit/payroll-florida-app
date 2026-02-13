from types import SimpleNamespace

from app.services.payroll import W4Data, calculate_monthly_payroll
from app.services.tax_loader import load_tax_data


def w4(**kwargs):
    base = dict(
        filing_status="single",
        step2_checkbox=False,
        dependents_child_count=0,
        dependents_other_count=0,
        other_income_annual=0,
        deductions_annual=0,
        extra_withholding=0,
    )
    base.update(kwargs)
    return W4Data(**base)


def test_w4_scenarios_vary_fit():
    tax = load_tax_data(2026)
    base = calculate_monthly_payroll(
        gross_wages=6000,
        pre_tax_deduction_monthly=0,
        post_tax_deduction_monthly=0,
        w4=w4(),
        tax_data=tax,
        ytd_records=[],
        company_suta_rate=0.027,
    )
    married_step2 = calculate_monthly_payroll(
        gross_wages=6000,
        pre_tax_deduction_monthly=0,
        post_tax_deduction_monthly=0,
        w4=w4(filing_status="married", step2_checkbox=True, dependents_child_count=1, other_income_annual=5000, deductions_annual=2000, extra_withholding=50),
        tax_data=tax,
        ytd_records=[],
        company_suta_rate=0.027,
    )
    assert married_step2["fit_withholding"] != base["fit_withholding"]
    assert married_step2["fit_withholding"] >= 50


def test_social_security_cap_behavior():
    tax = load_tax_data(2026)
    ytd = [SimpleNamespace(gross_wages=176000, taxable_wages_federal=176000)]
    result = calculate_monthly_payroll(
        gross_wages=5000,
        pre_tax_deduction_monthly=0,
        post_tax_deduction_monthly=0,
        w4=w4(),
        tax_data=tax,
        ytd_records=ytd,
        company_suta_rate=0.027,
    )
    assert result["social_security_employee"] == round((176100 - 176000) * 0.062, 2)


def test_medicare_additional_threshold_behavior():
    tax = load_tax_data(2026)
    ytd = [SimpleNamespace(gross_wages=199000, taxable_wages_federal=199000)]
    result = calculate_monthly_payroll(
        gross_wages=3000,
        pre_tax_deduction_monthly=0,
        post_tax_deduction_monthly=0,
        w4=w4(),
        tax_data=tax,
        ytd_records=ytd,
        company_suta_rate=0.027,
    )
    # Additional medicare on wages above threshold: 2000
    assert result["additional_medicare_employee"] == round(2000 * 0.009, 2)


def test_futa_wage_base_cap():
    tax = load_tax_data(2026)
    ytd = [SimpleNamespace(gross_wages=6900, taxable_wages_federal=6900)]
    result = calculate_monthly_payroll(
        gross_wages=2000,
        pre_tax_deduction_monthly=0,
        post_tax_deduction_monthly=0,
        w4=w4(),
        tax_data=tax,
        ytd_records=ytd,
        company_suta_rate=0.027,
    )
    assert result["futa_employer"] == round((7000 - 6900) * 0.006, 2)


def test_rt6_wage_base_cap_and_rate():
    tax = load_tax_data(2026)
    ytd = [SimpleNamespace(gross_wages=6800, taxable_wages_federal=6800)]
    result = calculate_monthly_payroll(
        gross_wages=1000,
        pre_tax_deduction_monthly=0,
        post_tax_deduction_monthly=0,
        w4=w4(),
        tax_data=tax,
        ytd_records=ytd,
        company_suta_rate=0.03,
    )
    assert result["florida_suta_employer"] == round((7000 - 6800) * 0.03, 2)

from __future__ import annotations

import json
from pathlib import Path

from app.models import Employee


DATA_DIR = Path("data/tax")


def round2(value: float) -> float:
    return round(value + 1e-9, 2)


def load_tax_year_data(year: int) -> dict:
    path = DATA_DIR / str(year) / "rates.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def calculate_monthly_payroll(
    employee: Employee,
    year: int,
    bonus: float,
    reimbursements: float,
    deductions: float,
    ytd_ss_wages: float,
    ytd_medicare_wages: float,
    ytd_futa_wages: float,
    ytd_suta_wages: float,
    company_suta_rate_percent: float,
) -> dict:
    tax = load_tax_year_data(year)
    gross = max(0.0, employee.monthly_salary + bonus)
    taxable_wages = max(0.0, gross - deductions)

    annualized = taxable_wages * 12 + employee.w4_other_income - employee.w4_deductions
    fit_cfg = tax["fit"][employee.filing_status]
    fit_annual = max(0.0, (annualized - fit_cfg["standard_deduction"]) * fit_cfg["flat_rate"] - employee.w4_dependents_amount)
    federal = fit_annual / 12 + employee.w4_extra_withholding

    ss_cfg = tax["social_security"]
    medicare_cfg = tax["medicare"]
    futa_cfg = tax["futa"]
    suta_wage_base = tax["suta"]["wage_base"]

    ss_taxable = max(0.0, min(ss_cfg["wage_base"] - ytd_ss_wages, taxable_wages))
    social_security_ee = ss_taxable * ss_cfg["employee_rate"]
    social_security_er = ss_taxable * ss_cfg["employer_rate"]

    medicare_ee = taxable_wages * medicare_cfg["rate"]
    medicare_er = taxable_wages * medicare_cfg["rate"]
    addl_base = max(0.0, ytd_medicare_wages + taxable_wages - medicare_cfg["additional_threshold"]) - max(0.0, ytd_medicare_wages - medicare_cfg["additional_threshold"])
    additional_medicare_ee = max(0.0, addl_base) * medicare_cfg["additional_rate"]

    futa_taxable = max(0.0, min(futa_cfg["wage_base"] - ytd_futa_wages, taxable_wages))
    futa_er = futa_taxable * futa_cfg["rate"]

    suta_taxable = max(0.0, min(suta_wage_base - ytd_suta_wages, taxable_wages))
    suta_er = suta_taxable * (company_suta_rate_percent / 100)

    net = gross + reimbursements - deductions - federal - social_security_ee - medicare_ee - additional_medicare_ee

    trace = {
        "tax_year": year,
        "inputs": {
            "monthly_salary": employee.monthly_salary,
            "bonus": bonus,
            "reimbursements": reimbursements,
            "deductions": deductions,
            "ytd_ss_wages": ytd_ss_wages,
            "ytd_medicare_wages": ytd_medicare_wages,
            "ytd_futa_wages": ytd_futa_wages,
            "ytd_suta_wages": ytd_suta_wages,
            "company_suta_rate_percent": company_suta_rate_percent,
        },
        "tax_table": tax,
    }

    return {
        "gross_pay": round2(gross),
        "federal_withholding": round2(federal),
        "social_security_ee": round2(social_security_ee),
        "medicare_ee": round2(medicare_ee),
        "additional_medicare_ee": round2(additional_medicare_ee),
        "social_security_er": round2(social_security_er),
        "medicare_er": round2(medicare_er),
        "futa_er": round2(futa_er),
        "suta_er": round2(suta_er),
        "net_pay": round2(net),
        "calculation_trace": trace,
    }

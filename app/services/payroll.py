from __future__ import annotations

import json
from pathlib import Path

from app.models import Employee


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "tax"


class TaxConfigError(Exception):
    pass

PERIODS_PER_YEAR = {
    "daily": 260,
    "weekly": 52,
    "biweekly": 26,
    "semimonthly": 24,
    "monthly": 12,
}


def periods_per_year(pay_frequency: str) -> int:
    return PERIODS_PER_YEAR.get((pay_frequency or "monthly").lower(), 12)

def round2(value: float) -> float:
    return round(value + 1e-9, 2)


def _validate_fit_config(fit_cfg: dict, year: int, status: str) -> None:
    if "standard_deduction" not in fit_cfg:
        raise TaxConfigError(f"Missing FIT standard_deduction for {status} in {year}")
    if "brackets" not in fit_cfg or not isinstance(fit_cfg["brackets"], list):
        raise TaxConfigError(f"Missing FIT brackets for {status} in {year}")


def load_tax_year_data(year: int) -> dict:
    path = DATA_DIR / str(year) / "rates.json"
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as exc:
        raise TaxConfigError(f"Missing tax configuration: {path}") from exc

    required_keys = ["fit", "social_security", "medicare", "futa", "suta"]
    missing = [key for key in required_keys if key not in data]
    if missing:
        raise TaxConfigError(f"Missing tax configuration keys for {year}: {', '.join(missing)}")
    return data


def _annual_fit_from_brackets(taxable_income: float, brackets: list[dict]) -> float:
    tax = 0.0
    remaining = taxable_income
    for bracket in brackets:
        upper = bracket.get("up_to")
        rate = float(bracket["rate"])
        if upper is None:
            tax += max(0.0, remaining) * rate
            break
        width = max(0.0, float(upper) - bracket.get("_lower", 0.0))
        taxed = min(max(0.0, remaining), width)
        tax += taxed * rate
        remaining -= taxed
        if remaining <= 0:
            break
    return max(0.0, tax)


def _normalize_brackets(brackets: list[dict]) -> list[dict]:
    lower = 0.0
    normalized: list[dict] = []
    for bracket in brackets:
        item = {"rate": float(bracket["rate"]), "up_to": bracket.get("up_to"), "_lower": lower}
        if item["up_to"] is not None:
            lower = float(item["up_to"])
        normalized.append(item)
    return normalized


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
    company_suta_rate_decimal: float,
) -> dict:
    tax = load_tax_year_data(year)
    fit_cfg = tax["fit"].get(employee.filing_status)
    if not fit_cfg:
        raise TaxConfigError(f"Unsupported filing status '{employee.filing_status}' for {year}")
    _validate_fit_config(fit_cfg, year, employee.filing_status)
    ss_cfg = tax["social_security"]
    medicare_cfg = tax["medicare"]
    futa_cfg = tax["futa"]
    suta_wage_base = tax["suta"]["wage_base"]

    gross = max(0.0, employee.monthly_salary + bonus + reimbursements)
    taxable_wages = max(0.0, gross - deductions)

    period_count = periods_per_year(employee.pay_frequency)
    annualized = taxable_wages * period_count + employee.w4_other_income - employee.w4_deductions
    fit_taxable = max(0.0, annualized - float(fit_cfg["standard_deduction"]))
    fit_brackets = _normalize_brackets(fit_cfg["brackets"])
    fit_annual = max(0.0, _annual_fit_from_brackets(fit_taxable, fit_brackets) - employee.w4_dependents_amount)
    federal = fit_annual / period_count + employee.w4_extra_withholding

    ss_remaining = max(0.0, ss_cfg["wage_base"] - ytd_ss_wages)
    ss_taxable = min(ss_remaining, taxable_wages)
    social_security_ee = ss_taxable * ss_cfg["employee_rate"]
    social_security_er = ss_taxable * ss_cfg["employer_rate"]

    medicare_ee = taxable_wages * medicare_cfg["employee_rate"]
    medicare_er = taxable_wages * medicare_cfg["employer_rate"]
    additional_threshold = medicare_cfg["additional_threshold"][employee.filing_status]
    addl_base = max(0.0, (ytd_medicare_wages + taxable_wages) - additional_threshold) - max(0.0, ytd_medicare_wages - additional_threshold)
    additional_medicare_ee = max(0.0, addl_base) * medicare_cfg["additional_employee_rate"]

    futa_remaining = max(0.0, futa_cfg["wage_base"] - ytd_futa_wages)
    futa_taxable = min(futa_remaining, taxable_wages)
    futa_er = futa_taxable * futa_cfg["employer_rate"]

    suta_remaining = max(0.0, suta_wage_base - ytd_suta_wages)
    suta_taxable = min(suta_remaining, taxable_wages)
    suta_er = suta_taxable * company_suta_rate_decimal

    employee_taxes = federal + social_security_ee + medicare_ee + additional_medicare_ee
    net = gross - employee_taxes - deductions

    trace = {
        "tax_year": year,
        "source": tax.get("source"),
        "files": [f"data/tax/{year}/rates.json"],
        "inputs": {
            "base_pay_amount": employee.monthly_salary,
            "pay_frequency": employee.pay_frequency,
            "periods_per_year": period_count,
            "bonus": bonus,
            "reimbursements": reimbursements,
            "deductions": deductions,
            "w4": {
                "filing_status": employee.filing_status,
                "dependents_amount": employee.w4_dependents_amount,
                "other_income": employee.w4_other_income,
                "deductions": employee.w4_deductions,
                "extra_withholding": employee.w4_extra_withholding,
            },
            "ytd": {
                "ss_wages": ytd_ss_wages,
                "medicare_wages": ytd_medicare_wages,
                "futa_wages": ytd_futa_wages,
                "suta_wages": ytd_suta_wages,
            },
        },
        "steps": {
            "gross_pay": gross,
            "taxable_wages": taxable_wages,
            "fit_annualized_wages": annualized,
            "fit_taxable_annual_wages": fit_taxable,
            "fit_annual_tax_before_credits": _annual_fit_from_brackets(fit_taxable, fit_brackets),
            "fit_annual_tax_after_credits": fit_annual,
            "fit_monthly_withholding": federal,
            "ss_taxable_wages": ss_taxable,
            "medicare_taxable_wages": taxable_wages,
            "additional_medicare_taxable_wages": addl_base,
            "futa_taxable_wages": futa_taxable,
            "suta_taxable_wages": suta_taxable,
            "ss_wage_base_remaining": ss_remaining,
            "futa_wage_base_remaining": futa_remaining,
            "suta_wage_base_remaining": suta_remaining,
        },
        "rounding": "Rounded to 2 decimals after each output line item",
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

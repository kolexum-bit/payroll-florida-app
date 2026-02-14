from __future__ import annotations

import json
from pathlib import Path

from app.models import Employee


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "tax"
PERIODS_PER_YEAR = {
    "daily": 260,
    "weekly": 52,
    "biweekly": 26,
    "semimonthly": 24,
    "monthly": 12,
}
FILING_STATUS_KEYS = {
    "single_or_married_filing_separately",
    "married_filing_jointly",
    "head_of_household",
}


class TaxConfigError(Exception):
    pass


def round2(value: float) -> float:
    return round(value + 1e-9, 2)


def _read_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as exc:
        raise TaxConfigError(f"Tax tables for {path.parent.parent.name if 'fit' in path.parts else path.parent.name} are missing. Please add {path.parent}/...") from exc


def tax_year_dir(year: int) -> Path:
    return DATA_DIR / str(year)


def tax_year_available(year: int) -> bool:
    ydir = tax_year_dir(year)
    return ydir.exists() and (ydir / "rates.json").exists() and (ydir / "metadata.json").exists()


def load_tax_year_data(year: int, pay_frequency: str) -> dict:
    ydir = tax_year_dir(year)
    rates_path = ydir / "rates.json"
    metadata_path = ydir / "metadata.json"
    fit_path = ydir / "fit" / pay_frequency / "percentage_method.json"

    rates = _read_json(rates_path)
    metadata = _read_json(metadata_path)
    fit = _read_json(fit_path)

    required_keys = ["social_security", "medicare", "futa", "suta"]
    missing = [key for key in required_keys if key not in rates]
    if missing:
        raise TaxConfigError(f"Missing tax configuration keys for {year}: {', '.join(missing)}")

    for status in FILING_STATUS_KEYS:
        if status not in fit:
            raise TaxConfigError(f"Missing FIT table for filing status '{status}' ({year}, {pay_frequency})")
        status_cfg = fit[status]
        if "standard_deduction" not in status_cfg or "brackets" not in status_cfg:
            raise TaxConfigError(f"Invalid FIT table for filing status '{status}' ({year}, {pay_frequency})")

    return {
        "year": year,
        "metadata": metadata,
        "rates": rates,
        "fit": fit,
        "files": [
            f"data/tax/{year}/metadata.json",
            f"data/tax/{year}/rates.json",
            f"data/tax/{year}/fit/{pay_frequency}/percentage_method.json",
        ],
    }


def _annual_fit_from_brackets(taxable_income: float, brackets: list[dict]) -> float:
    tax = 0.0
    lower = 0.0
    remaining = taxable_income
    for bracket in brackets:
        upper = bracket.get("up_to")
        rate = float(bracket["rate"])
        if upper is None:
            tax += max(0.0, remaining) * rate
            break
        width = max(0.0, float(upper) - lower)
        taxed = min(max(0.0, remaining), width)
        tax += taxed * rate
        remaining -= taxed
        lower = float(upper)
        if remaining <= 0:
            break
    return max(0.0, tax)


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
    pay_frequency = employee.pay_frequency
    if pay_frequency not in PERIODS_PER_YEAR:
        raise TaxConfigError(f"Unsupported pay frequency '{pay_frequency}'")
    if employee.filing_status not in FILING_STATUS_KEYS:
        raise TaxConfigError(f"Unsupported filing status '{employee.filing_status}'")

    tax_data = load_tax_year_data(year, pay_frequency)
    rates = tax_data["rates"]
    fit_cfg = tax_data["fit"][employee.filing_status]
    ss_cfg = rates["social_security"]
    medicare_cfg = rates["medicare"]
    futa_cfg = rates["futa"]
    suta_wage_base = rates["suta"]["wage_base"]

    periods_per_year = PERIODS_PER_YEAR[pay_frequency]
    gross = max(0.0, employee.monthly_salary + bonus + reimbursements)
    taxable_wages = max(0.0, gross - deductions)

    annualized = taxable_wages * periods_per_year + employee.w4_other_income - employee.w4_deductions
    fit_taxable = max(0.0, annualized - float(fit_cfg["standard_deduction"]))
    fit_annual_before_credits = _annual_fit_from_brackets(fit_taxable, fit_cfg["brackets"])
    fit_annual_after_step3 = max(0.0, fit_annual_before_credits - employee.w4_dependents_amount)
    federal = fit_annual_after_step3 / periods_per_year + employee.w4_extra_withholding

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
        "source": tax_data["metadata"].get("source"),
        "version": tax_data["metadata"].get("version"),
        "files": tax_data["files"],
        "inputs": {
            "pay_frequency": pay_frequency,
            "periods_per_year": periods_per_year,
            "gross_components": {
                "base_salary_amount": employee.monthly_salary,
                "bonus": bonus,
                "reimbursements": reimbursements,
            },
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
            "fit_annual_tax_before_credits": fit_annual_before_credits,
            "fit_annual_tax_after_step3_credit": fit_annual_after_step3,
            "fit_period_withholding": federal,
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

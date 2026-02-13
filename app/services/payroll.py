from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List


def money(value: float | Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class W4Data:
    filing_status: str
    step2_checkbox: bool
    dependents_child_count: int
    dependents_other_count: int
    other_income_annual: float
    deductions_annual: float
    extra_withholding: float


def _get_ytd_values(records: List[Any]) -> Dict[str, Decimal]:
    return {
        "gross": sum((Decimal(str(r.gross_wages)) for r in records), Decimal("0")),
        "ss_taxable": sum((Decimal(str(r.taxable_wages_federal)) for r in records), Decimal("0")),
        "futa_taxable": sum((Decimal(str(r.taxable_wages_federal)) for r in records), Decimal("0")),
    }


def _fit_monthly_withholding(monthly_taxable: Decimal, w4: W4Data, federal: dict) -> tuple[Decimal, dict]:
    fit = federal["fit"]
    status_tables = fit["filing_status"][w4.filing_status]
    table_key = "step2_checked" if w4.step2_checkbox else "step2_unchecked"
    table = status_tables[table_key]

    annual_wages = monthly_taxable * Decimal(str(fit["pay_periods_per_year"]))
    annual_adjusted = annual_wages + Decimal(str(w4.other_income_annual)) - Decimal(str(w4.deductions_annual)) - Decimal(str(table["standard_deduction"]))
    annual_adjusted = max(Decimal("0"), annual_adjusted)

    dependent_credit = (
        Decimal(w4.dependents_child_count) * Decimal(str(fit["dependent_credit_per_child"]))
        + Decimal(w4.dependents_other_count) * Decimal(str(fit["dependent_credit_other"]))
    )

    bracket_used = None
    annual_tax = Decimal("0")
    for bracket in table["brackets"]:
        up_to = bracket["up_to"]
        if up_to is None or annual_adjusted <= Decimal(str(up_to)):
            annual_tax = Decimal(str(bracket["base_tax"])) + (annual_adjusted - Decimal(str(bracket["over"]))) * Decimal(str(bracket["rate"]))
            bracket_used = bracket
            break

    annual_tax = max(Decimal("0"), annual_tax - dependent_credit)
    monthly_fit = money(annual_tax / Decimal(str(fit["pay_periods_per_year"]))) + money(w4.extra_withholding)
    monthly_fit = max(Decimal("0"), monthly_fit)

    trace = {
        "table_name": f"fit.{w4.filing_status}.{table_key}",
        "annual_wages": str(money(annual_wages)),
        "annual_adjusted_wages": str(money(annual_adjusted)),
        "dependent_credit": str(money(dependent_credit)),
        "bracket_used": bracket_used,
        "annual_tax": str(money(annual_tax)),
        "monthly_fit_before_extra": str(money(annual_tax / Decimal(str(fit["pay_periods_per_year"])))),
        "extra_withholding": str(money(w4.extra_withholding)),
        "monthly_fit": str(money(monthly_fit)),
    }
    return money(monthly_fit), trace


def calculate_monthly_payroll(*, gross_wages: float, pre_tax_deduction_monthly: float, post_tax_deduction_monthly: float, w4: W4Data, tax_data: dict, ytd_records: List[Any], company_suta_rate: float) -> dict:
    federal = tax_data["federal"]
    florida = tax_data["florida"]
    ytd = _get_ytd_values(ytd_records)

    gross = money(gross_wages)
    pre_tax = money(pre_tax_deduction_monthly)
    taxable_federal = max(Decimal("0"), gross - pre_tax)
    post_tax = money(post_tax_deduction_monthly)

    fit, fit_trace = _fit_monthly_withholding(taxable_federal, w4, federal)

    fica = federal["fica"]
    ss_cap = Decimal(str(fica["social_security_wage_base"]))
    ss_ytd = ytd["ss_taxable"]
    ss_remaining = max(Decimal("0"), ss_cap - ss_ytd)
    ss_taxable = min(taxable_federal, ss_remaining)
    ss_rate_ee = Decimal(str(fica["social_security_rate_employee"]))
    ss_rate_er = Decimal(str(fica["social_security_rate_employer"]))

    medicare_rate_ee = Decimal(str(fica["medicare_rate_employee"]))
    medicare_rate_er = Decimal(str(fica["medicare_rate_employer"]))
    addl_rate = Decimal(str(fica["additional_medicare_rate_employee"]))
    addl_threshold = Decimal(str(fica["additional_medicare_threshold"]))

    medicare_ytd_gross = ytd["gross"]
    addl_remaining_threshold = max(Decimal("0"), addl_threshold - medicare_ytd_gross)
    addl_medicare_taxable = max(Decimal("0"), taxable_federal - addl_remaining_threshold)

    ss_ee = money(ss_taxable * ss_rate_ee)
    ss_er = money(ss_taxable * ss_rate_er)
    med_ee = money(taxable_federal * medicare_rate_ee)
    med_er = money(taxable_federal * medicare_rate_er)
    addl_med_ee = money(addl_medicare_taxable * addl_rate)

    futa = federal["futa"]
    futa_cap = Decimal(str(futa["wage_base"]))
    futa_ytd = ytd["futa_taxable"]
    futa_remaining = max(Decimal("0"), futa_cap - futa_ytd)
    futa_taxable = min(taxable_federal, futa_remaining)
    futa_tax = money(futa_taxable * Decimal(str(futa["rate"])))

    suta_cap = Decimal(str(florida["rt6"]["wage_base"]))
    suta_ytd = ytd["gross"]
    suta_remaining = max(Decimal("0"), suta_cap - suta_ytd)
    suta_taxable = min(gross, suta_remaining)
    suta_tax = money(suta_taxable * Decimal(str(company_suta_rate)))

    total_employee_deductions = fit + ss_ee + med_ee + addl_med_ee + post_tax
    net_pay = money(gross - pre_tax - total_employee_deductions)

    trace = {
        "tax_year": federal["metadata"]["year"],
        "table_versions": {
            "federal": federal["metadata"]["table_version"],
            "florida": florida["metadata"]["table_version"],
        },
        "w4_inputs": w4.__dict__,
        "inputs": {
            "gross_wages": str(gross),
            "pre_tax_deductions": str(pre_tax),
            "post_tax_deductions": str(post_tax),
        },
        "fit": fit_trace,
        "fica": {
            "social_security": {"ytd": str(money(ss_ytd)), "remaining_cap": str(money(ss_remaining)), "taxable": str(money(ss_taxable)), "employee_tax": str(ss_ee), "employer_tax": str(ss_er)},
            "medicare": {"taxable": str(money(taxable_federal)), "employee_tax": str(med_ee), "employer_tax": str(med_er)},
            "additional_medicare": {"threshold": str(money(addl_threshold)), "ytd_prior": str(money(medicare_ytd_gross)), "taxable": str(money(addl_medicare_taxable)), "employee_tax": str(addl_med_ee)},
        },
        "futa": {"ytd": str(money(futa_ytd)), "remaining_cap": str(money(futa_remaining)), "taxable": str(money(futa_taxable)), "tax": str(futa_tax)},
        "rt6": {"ytd": str(money(suta_ytd)), "remaining_cap": str(money(suta_remaining)), "taxable": str(money(suta_taxable)), "rate": str(company_suta_rate), "tax": str(suta_tax)},
        "rounding": "ROUND_HALF_UP to cents",
    }

    return {
        "gross_wages": float(gross),
        "pre_tax_deductions": float(pre_tax),
        "taxable_wages_federal": float(taxable_federal),
        "fit_withholding": float(fit),
        "social_security_employee": float(ss_ee),
        "medicare_employee": float(med_ee),
        "additional_medicare_employee": float(addl_med_ee),
        "post_tax_deductions": float(post_tax),
        "social_security_employer": float(ss_er),
        "medicare_employer": float(med_er),
        "futa_employer": float(futa_tax),
        "florida_suta_employer": float(suta_tax),
        "net_pay": float(net_pay),
        "calculation_trace": trace,
    }

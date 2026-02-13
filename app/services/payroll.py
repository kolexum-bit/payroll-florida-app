from __future__ import annotations

from app.models import Employee


def round2(value: float) -> float:
    return round(value + 1e-9, 2)


def calculate_monthly_payroll(employee: Employee, hours_worked: float | None = None) -> dict:
    use_hours = hours_worked if hours_worked is not None else employee.default_hours_per_month
    if employee.pay_type == "hourly":
        gross = employee.base_rate * use_hours
    else:
        gross = employee.base_rate

    annualized_gross = gross * 12
    taxable_income = max(0.0, annualized_gross + employee.w4_other_income - employee.w4_deductions)
    estimated_federal_annual = max(0.0, taxable_income * 0.1 - employee.w4_dependents_amount)
    federal = estimated_federal_annual / 12 + employee.w4_extra_withholding

    social_security = gross * 0.062
    medicare = gross * 0.0145
    net = gross - federal - social_security - medicare

    trace = {
        "inputs": {
            "pay_type": employee.pay_type,
            "base_rate": employee.base_rate,
            "hours_worked": use_hours,
            "w4_dependents_amount": employee.w4_dependents_amount,
            "w4_other_income": employee.w4_other_income,
            "w4_deductions": employee.w4_deductions,
            "w4_extra_withholding": employee.w4_extra_withholding,
        },
        "steps": {
            "gross_pay": round2(gross),
            "annualized_gross": round2(annualized_gross),
            "taxable_income": round2(taxable_income),
            "estimated_federal_annual": round2(estimated_federal_annual),
            "federal_withholding_monthly": round2(federal),
            "social_security": round2(social_security),
            "medicare": round2(medicare),
            "net_pay": round2(net),
        },
    }

    return {
        "hours_worked": round2(use_hours),
        "gross_pay": round2(gross),
        "federal_withholding": round2(federal),
        "social_security": round2(social_security),
        "medicare": round2(medicare),
        "net_pay": round2(net),
        "taxable_wages": round2(gross),
        "calculation_trace": trace,
    }

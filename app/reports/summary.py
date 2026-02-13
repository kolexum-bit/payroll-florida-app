from collections import defaultdict


def quarter_months(q: int):
    return {1: [1, 2, 3], 2: [4, 5, 6], 3: [7, 8, 9], 4: [10, 11, 12]}[q]


def form_941_summary(records):
    out = defaultdict(float)
    for r in records:
        out["line_2_wages_tips_other_comp"] += r.gross_wages
        out["line_3_federal_income_tax_withheld"] += r.fit_withholding
        out["line_5a_taxable_social_security_wages"] += r.taxable_wages_federal
        out["line_5a_tax_social_security"] += r.social_security_employee + r.social_security_employer
        out["line_5c_taxable_medicare_wages_tips"] += r.taxable_wages_federal
        out["line_5c_tax_medicare"] += r.medicare_employee + r.medicare_employer
        out["line_5d_taxable_wages_additional_medicare"] += r.taxable_wages_federal
        out["line_5d_tax_additional_medicare_withholding"] += r.additional_medicare_employee
    out["line_5e_total_social_security_medicare_taxes"] = (
        out["line_5a_tax_social_security"] + out["line_5c_tax_medicare"] + out["line_5d_tax_additional_medicare_withholding"]
    )
    out["line_6_total_taxes_before_adjustments"] = out["line_3_federal_income_tax_withheld"] + out["line_5e_total_social_security_medicare_taxes"]
    return dict(out)


def rt6_summary(records, suta_rate: float, wage_base: float):
    employees = defaultdict(lambda: {"gross": 0.0})
    for r in records:
        key = r.employee_id
        employees[key]["gross"] += r.gross_wages

    detail = []
    total_gross = total_taxable = total_excess = 0.0
    for emp_id, values in employees.items():
        gross = values["gross"]
        taxable = min(gross, wage_base)
        excess = max(0.0, gross - wage_base)
        total_gross += gross
        total_taxable += taxable
        total_excess += excess
        detail.append({"employee_id": emp_id, "gross": gross, "taxable": taxable, "excess": excess})

    return {
        "gross_wages": total_gross,
        "excess_wages": total_excess,
        "taxable_wages": total_taxable,
        "tax_due": total_taxable * suta_rate,
        "employee_detail": detail,
    }


def form_940_summary(records):
    out = defaultdict(float)
    out["line_3_total_payments"] = sum(r.gross_wages for r in records)
    out["line_7_futa_taxable_wages"] = sum(min(r.taxable_wages_federal, 7000) for r in records)
    out["line_8_futa_tax_before_adjustments"] = sum(r.futa_employer for r in records)
    return dict(out)

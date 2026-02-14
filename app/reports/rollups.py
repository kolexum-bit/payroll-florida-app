from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import MonthlyPayroll


def _quarter_months(quarter: int) -> tuple[int, int]:
    start = (quarter - 1) * 3 + 1
    return start, start + 2


def _base_query(db: Session, company_id: int, year: int):
    return db.query(MonthlyPayroll).filter(MonthlyPayroll.company_id == company_id, MonthlyPayroll.year == year)


def _trace_step(record: MonthlyPayroll, key: str) -> float:
    return float((record.calculation_trace or {}).get("steps", {}).get(key, 0.0))


def rt6_summary(db: Session, company_id: int, year: int, quarter: int, suta_rate_decimal: float) -> dict:
    start, end = _quarter_months(quarter)
    records = _base_query(db, company_id, year).filter(MonthlyPayroll.month >= start, MonthlyPayroll.month <= end).all()
    total_wages = round(sum(_trace_step(r, "taxable_wages") for r in records), 2)
    taxable_wages = round(sum(_trace_step(r, "suta_taxable_wages") for r in records), 2)
    contributions_due = round(sum(r.suta_er for r in records), 2)
    return {
        "records": records,
        "wages": total_wages,
        "taxable_wages": taxable_wages,
        "contributions_due": contributions_due,
        "line_mapping": {
            "RT-6 Line 1": "Total wages paid",
            "RT-6 Line 2": "Taxable wages (after $7,000 wage base cap)",
            "RT-6 Line 3": f"Tax due at {(suta_rate_decimal * 100):.3f}%",
        },
    }


def form941_summary(db: Session, company_id: int, year: int, quarter: int) -> dict:
    start, end = _quarter_months(quarter)
    records = _base_query(db, company_id, year).filter(MonthlyPayroll.month >= start, MonthlyPayroll.month <= end).all()
    wages = round(sum(_trace_step(r, "taxable_wages") for r in records), 2)
    federal_withholding = round(sum(r.federal_withholding for r in records), 2)
    ss_wages = round(sum(_trace_step(r, "ss_taxable_wages") for r in records), 2)
    ss_tax = round(sum(r.social_security_ee + r.social_security_er for r in records), 2)
    medicare_wages = round(sum(_trace_step(r, "medicare_taxable_wages") for r in records), 2)
    medicare_tax = round(sum(r.medicare_ee + r.medicare_er for r in records), 2)
    addl_medicare_ee = round(sum(r.additional_medicare_ee for r in records), 2)

    return {
        "records": records,
        "wages": wages,
        "federal_withholding": federal_withholding,
        "social_security_wages": ss_wages,
        "social_security_tax": ss_tax,
        "medicare_wages": medicare_wages,
        "medicare_tax": medicare_tax,
        "additional_medicare_ee": addl_medicare_ee,
        "total_tax": round(federal_withholding + ss_tax + medicare_tax + addl_medicare_ee, 2),
        "line_mapping": {
            "Line 2": "Taxable wages, tips, and other compensation",
            "Line 3": "Federal income tax withheld",
            "Line 5a": "Social Security taxable wages and EE+ER tax",
            "Line 5c": "Medicare taxable wages and EE+ER tax",
            "Line 5d": "Additional Medicare Tax withheld (employee only)",
        },
    }


def form940_summary(db: Session, company_id: int, year: int) -> dict:
    records = _base_query(db, company_id, year).all()
    total_wages = round(sum(_trace_step(r, "taxable_wages") for r in records), 2)
    taxable_wages = round(sum(_trace_step(r, "futa_taxable_wages") for r in records), 2)
    futa_tax = round(sum(r.futa_er for r in records), 2)
    return {
        "records": records,
        "wages": total_wages,
        "futa_taxable_wages": taxable_wages,
        "futa_tax": futa_tax,
        "line_mapping": {
            "Line 3": "Total payments to all employees",
            "Line 7": "Taxable FUTA wages after $7,000 wage base cap",
            "Line 12": "FUTA tax due",
        },
    }


def employee_w2_totals(db: Session, company_id: int, employee_id: int, year: int) -> dict:
    records = db.query(MonthlyPayroll).filter(
        MonthlyPayroll.company_id == company_id,
        MonthlyPayroll.employee_id == employee_id,
        MonthlyPayroll.year == year,
    ).all()
    gross = round(sum(r.gross_pay for r in records), 2)
    fit = round(sum(r.federal_withholding for r in records), 2)
    ss_wages = round(sum(_trace_step(r, "ss_taxable_wages") for r in records), 2)
    ss_tax = round(sum(r.social_security_ee for r in records), 2)
    med_wages = round(sum(_trace_step(r, "medicare_taxable_wages") for r in records), 2)
    med_tax = round(sum(r.medicare_ee + r.additional_medicare_ee for r in records), 2)
    return {
        "records": records,
        "box1_wages": gross,
        "box2_fit": fit,
        "box3_ss_wages": ss_wages,
        "box4_ss_tax": ss_tax,
        "box5_medicare_wages": med_wages,
        "box6_medicare_tax": med_tax,
    }

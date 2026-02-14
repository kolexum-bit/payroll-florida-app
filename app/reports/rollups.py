from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import MonthlyPayroll


def _quarter_months(quarter: int) -> tuple[int, int]:
    start = (quarter - 1) * 3 + 1
    return start, start + 2


def _base_query(db: Session, company_id: int, year: int):
    return db.query(MonthlyPayroll).filter(MonthlyPayroll.company_id == company_id, MonthlyPayroll.year == year)


def rt6_summary(db: Session, company_id: int, year: int, quarter: int, suta_rate_percent: float) -> dict:
    start, end = _quarter_months(quarter)
    records = _base_query(db, company_id, year).filter(MonthlyPayroll.month >= start, MonthlyPayroll.month <= end).all()
    taxable_wages = round(sum(r.gross_pay - r.deductions for r in records), 2)
    contributions_due = round(sum(r.suta_er for r in records), 2)
    return {
        "records": records,
        "wages": taxable_wages,
        "taxable_wages": taxable_wages,
        "contributions_due": contributions_due,
        "line_mapping": {
            "RT-6 Line 1": "Total wages paid",
            "RT-6 Line 2": "Taxable wages (after wage base cap)",
            "RT-6 Line 3": f"Tax due at {suta_rate_percent}%",
        },
    }


def form941_summary(db: Session, company_id: int, year: int, quarter: int) -> dict:
    start, end = _quarter_months(quarter)
    records = _base_query(db, company_id, year).filter(MonthlyPayroll.month >= start, MonthlyPayroll.month <= end).all()
    wages = round(sum(r.gross_pay for r in records), 2)
    federal_withholding = round(sum(r.federal_withholding for r in records), 2)
    social_security = round(sum(r.social_security_ee + r.social_security_er for r in records), 2)
    medicare = round(sum(r.medicare_ee + r.medicare_er + r.additional_medicare_ee for r in records), 2)
    return {
        "records": records,
        "wages": wages,
        "federal_withholding": federal_withholding,
        "social_security_tax": social_security,
        "medicare_tax": medicare,
        "total_tax": round(federal_withholding + social_security + medicare, 2),
        "line_mapping": {
            "Line 2": "Wages",
            "Line 3": "FIT withheld",
            "Line 5a": "Social Security EE+ER",
            "Line 5c/5d": "Medicare EE+ER + Additional Medicare EE",
        },
    }


def form940_summary(db: Session, company_id: int, year: int) -> dict:
    records = _base_query(db, company_id, year).all()
    taxable_wages = round(sum((r.calculation_trace or {}).get("steps", {}).get("futa_taxable_wages", 0.0) for r in records), 2)
    futa_tax = round(sum(r.futa_er for r in records), 2)
    return {
        "records": records,
        "wages": taxable_wages,
        "futa_tax": futa_tax,
        "line_mapping": {
            "Line 7": "Taxable FUTA wages",
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
    ss_wages = round(sum((r.calculation_trace or {}).get("steps", {}).get("ss_taxable_wages", 0.0) for r in records), 2)
    ss_tax = round(sum(r.social_security_ee for r in records), 2)
    med_wages = round(sum((r.calculation_trace or {}).get("steps", {}).get("medicare_taxable_wages", 0.0) for r in records), 2)
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

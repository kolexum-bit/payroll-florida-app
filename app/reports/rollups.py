from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import MonthlyPayroll


def _quarter_months(quarter: int) -> tuple[int, int]:
    start = (quarter - 1) * 3 + 1
    return start, start + 2


def rt6_summary(db: Session, year: int, quarter: int) -> dict:
    start, end = _quarter_months(quarter)
    records = (
        db.query(MonthlyPayroll)
        .filter(MonthlyPayroll.year == year, MonthlyPayroll.month >= start, MonthlyPayroll.month <= end)
        .all()
    )
    wages = round(sum(r.taxable_wages for r in records), 2)
    contributions_due = round(wages * 0.027, 2)
    return {"records": records, "wages": wages, "contributions_due": contributions_due}


def form941_summary(db: Session, year: int, quarter: int) -> dict:
    start, end = _quarter_months(quarter)
    records = (
        db.query(MonthlyPayroll)
        .filter(MonthlyPayroll.year == year, MonthlyPayroll.month >= start, MonthlyPayroll.month <= end)
        .all()
    )
    wages = round(sum(r.gross_pay for r in records), 2)
    federal_withholding = round(sum(r.federal_withholding for r in records), 2)
    fica = round(sum(r.social_security + r.medicare for r in records), 2)
    return {
        "records": records,
        "wages": wages,
        "federal_withholding": federal_withholding,
        "fica": fica,
        "total_tax": round(federal_withholding + fica, 2),
    }


def form940_summary(db: Session, year: int) -> dict:
    records = db.query(MonthlyPayroll).filter(MonthlyPayroll.year == year).all()
    wages = round(sum(r.taxable_wages for r in records), 2)
    futa_tax = round(wages * 0.006, 2)
    return {"records": records, "wages": wages, "futa_tax": futa_tax}

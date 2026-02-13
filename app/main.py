from __future__ import annotations

import csv
from datetime import date
from io import StringIO
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import Company, Employee, PayrollRecord
from .reports.pdf import generate_pay_stub_pdf
from .reports.summary import form_940_summary, form_941_summary, quarter_months, rt6_summary
from .services.payroll import W4Data, calculate_monthly_payroll
from .services.tax_loader import load_tax_data

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Florida Payroll App")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def get_company(db: Session) -> Company | None:
    return db.query(Company).first()


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("index.html", {"request": request, "company": get_company(db)})


@app.get("/company", response_class=HTMLResponse)
def company_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("company.html", {"request": request, "company": get_company(db)})


@app.post("/company")
def create_or_update_company(
    name: str = Form(...),
    fein: str = Form(...),
    fl_account_number: str = Form(...),
    default_tax_year: int = Form(...),
    fl_suta_rate: float = Form(...),
    db: Session = Depends(get_db),
):
    company = get_company(db)
    if company is None:
        company = Company(name=name, fein=fein, fl_account_number=fl_account_number, default_tax_year=default_tax_year, fl_suta_rate=fl_suta_rate)
        db.add(company)
    else:
        company.name = name
        company.fein = fein
        company.fl_account_number = fl_account_number
        company.default_tax_year = default_tax_year
        company.fl_suta_rate = fl_suta_rate
    db.commit()
    return {"ok": True}


@app.get("/employees", response_class=HTMLResponse)
def employees_page(request: Request, db: Session = Depends(get_db)):
    company = get_company(db)
    employees = db.query(Employee).all()
    return templates.TemplateResponse("employees.html", {"request": request, "company": company, "employees": employees})


@app.post("/employees")
def create_employee(
    first_name: str = Form(...),
    last_name: str = Form(...),
    ssn_last4: str = Form(...),
    filing_status: str = Form(...),
    step2_checkbox: bool = Form(False),
    dependents_child_count: int = Form(0),
    dependents_other_count: int = Form(0),
    other_income_annual: float = Form(0),
    deductions_annual: float = Form(0),
    extra_withholding: float = Form(0),
    pre_tax_deduction_monthly: float = Form(0),
    post_tax_deduction_monthly: float = Form(0),
    db: Session = Depends(get_db),
):
    company = get_company(db)
    if company is None:
        raise HTTPException(400, "Create company first")
    emp = Employee(
        company_id=company.id,
        first_name=first_name,
        last_name=last_name,
        ssn_last4=ssn_last4,
        filing_status=filing_status,
        step2_checkbox=step2_checkbox,
        dependents_child_count=dependents_child_count,
        dependents_other_count=dependents_other_count,
        other_income_annual=other_income_annual,
        deductions_annual=deductions_annual,
        extra_withholding=extra_withholding,
        pre_tax_deduction_monthly=pre_tax_deduction_monthly,
        post_tax_deduction_monthly=post_tax_deduction_monthly,
    )
    db.add(emp)
    db.commit()
    return {"ok": True}


@app.get("/monthly-payroll", response_class=HTMLResponse)
def payroll_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("payroll.html", {"request": request, "employees": db.query(Employee).filter(Employee.active == True).all(), "company": get_company(db)})


@app.post("/monthly-payroll/run")
def run_payroll(
    employee_id: int = Form(...),
    tax_year: int = Form(...),
    pay_month: int = Form(...),
    pay_date: date = Form(...),
    gross_wages: float = Form(...),
    db: Session = Depends(get_db),
):
    employee = db.get(Employee, employee_id)
    company = get_company(db)
    if employee is None or company is None:
        raise HTTPException(400, "Missing employee/company")

    existing = db.query(PayrollRecord).filter_by(employee_id=employee_id, tax_year=tax_year, pay_month=pay_month).first()
    if existing:
        raise HTTPException(400, "Payroll for this month already exists")

    tax_data = load_tax_data(tax_year)
    ytd_records = db.query(PayrollRecord).filter(PayrollRecord.employee_id == employee_id, PayrollRecord.tax_year == tax_year, PayrollRecord.pay_month < pay_month).all()

    w4 = W4Data(
        filing_status=employee.filing_status,
        step2_checkbox=employee.step2_checkbox,
        dependents_child_count=employee.dependents_child_count,
        dependents_other_count=employee.dependents_other_count,
        other_income_annual=employee.other_income_annual,
        deductions_annual=employee.deductions_annual,
        extra_withholding=employee.extra_withholding,
    )

    calc = calculate_monthly_payroll(
        gross_wages=gross_wages,
        pre_tax_deduction_monthly=employee.pre_tax_deduction_monthly,
        post_tax_deduction_monthly=employee.post_tax_deduction_monthly,
        w4=w4,
        tax_data=tax_data,
        ytd_records=ytd_records,
        company_suta_rate=company.fl_suta_rate,
    )

    record = PayrollRecord(company_id=company.id, employee_id=employee.id, tax_year=tax_year, pay_month=pay_month, pay_date=pay_date, **calc)
    db.add(record)
    db.commit()
    return {"ok": True, "record_id": record.id}


@app.get("/pay-stubs", response_class=HTMLResponse)
def pay_stub_list(request: Request, db: Session = Depends(get_db)):
    rows = db.query(PayrollRecord).order_by(PayrollRecord.tax_year.desc(), PayrollRecord.pay_month.desc()).all()
    return templates.TemplateResponse("paystubs.html", {"request": request, "rows": rows})


@app.get("/pay-stubs/{record_id}.pdf")
def pay_stub_pdf(record_id: int, db: Session = Depends(get_db)):
    record = db.get(PayrollRecord, record_id)
    if not record:
        raise HTTPException(404)
    emp = db.get(Employee, record.employee_id)
    comp = db.get(Company, record.company_id)

    ytd_rows = []
    running_gross = running_net = 0.0
    ytd = db.query(PayrollRecord).filter(PayrollRecord.employee_id == record.employee_id, PayrollRecord.tax_year == record.tax_year, PayrollRecord.pay_month <= record.pay_month).order_by(PayrollRecord.pay_month).all()
    for row in ytd:
        running_gross += row.gross_wages
        running_net += row.net_pay
        ytd_rows.append({"month": row.pay_month, "gross": row.gross_wages, "net": row.net_pay, "gross_running": running_gross, "net_running": running_net})

    out_path = Path("artifacts") / f"pay_stub_{record_id}.pdf"
    generate_pay_stub_pdf(
        str(out_path),
        comp.name,
        f"{emp.first_name} {emp.last_name}",
        {
            "pay_month": record.pay_month,
            "tax_year": record.tax_year,
            "pay_date": str(record.pay_date),
            "gross_wages": record.gross_wages,
            "pre_tax_deductions": record.pre_tax_deductions,
            "fit_withholding": record.fit_withholding,
            "social_security_employee": record.social_security_employee,
            "medicare_employee": record.medicare_employee,
            "additional_medicare_employee": record.additional_medicare_employee,
            "post_tax_deductions": record.post_tax_deductions,
            "net_pay": record.net_pay,
        },
        ytd_rows,
    )
    return FileResponse(out_path)


@app.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request):
    return templates.TemplateResponse("reports.html", {"request": request})


@app.get("/reports/941", response_class=HTMLResponse)
def report_941(request: Request, year: int, quarter: int, db: Session = Depends(get_db)):
    months = quarter_months(quarter)
    records = db.query(PayrollRecord).filter(PayrollRecord.tax_year == year, PayrollRecord.pay_month.in_(months)).all()
    summary = form_941_summary(records)
    return templates.TemplateResponse("report_941.html", {"request": request, "summary": summary, "year": year, "quarter": quarter})


@app.get("/reports/rt6", response_class=HTMLResponse)
def report_rt6(request: Request, year: int, quarter: int, db: Session = Depends(get_db)):
    months = quarter_months(quarter)
    company = get_company(db)
    records = db.query(PayrollRecord).filter(PayrollRecord.tax_year == year, PayrollRecord.pay_month.in_(months)).all()
    florida = load_tax_data(year)["florida"]
    summary = rt6_summary(records, company.fl_suta_rate, florida["rt6"]["wage_base"])
    return templates.TemplateResponse("report_rt6.html", {"request": request, "summary": summary, "year": year, "quarter": quarter})


@app.get("/reports/rt6.csv")
def report_rt6_csv(year: int, quarter: int, db: Session = Depends(get_db)):
    months = quarter_months(quarter)
    company = get_company(db)
    records = db.query(PayrollRecord).filter(PayrollRecord.tax_year == year, PayrollRecord.pay_month.in_(months)).all()
    florida = load_tax_data(year)["florida"]
    summary = rt6_summary(records, company.fl_suta_rate, florida["rt6"]["wage_base"])

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["employee_id", "gross", "taxable", "excess"])
    writer.writeheader()
    for row in summary["employee_detail"]:
        writer.writerow(row)

    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=rt6_{year}_q{quarter}.csv"})


@app.get("/reports/940", response_class=HTMLResponse)
def report_940(request: Request, year: int, db: Session = Depends(get_db)):
    records = db.query(PayrollRecord).filter(PayrollRecord.tax_year == year).all()
    summary = form_940_summary(records)
    return templates.TemplateResponse("report_940.html", {"request": request, "summary": summary, "year": year})

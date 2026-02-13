from __future__ import annotations

import csv
import io
import os
from datetime import date
from typing import Optional

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import create_session_factory, get_db
from app.models import Company, Employee, MonthlyPayroll
from app.reports.rollups import form940_summary, form941_summary, rt6_summary
from app.services.payroll import calculate_monthly_payroll
from app.services.pdf import create_pay_stub_pdf_bytes


def create_app(database_url: Optional[str] = None) -> FastAPI:
    app = FastAPI(title="Payroll Florida App")
    templates = Jinja2Templates(directory="app/templates")

    resolved_database_url = database_url or os.getenv("DATABASE_URL", "sqlite:///./payroll.db")
    session_factory = create_session_factory(resolved_database_url)

    def db_dependency():
        yield from get_db(session_factory)

    @app.get("/")
    def root():
        return RedirectResponse(url="/company", status_code=302)

    @app.get("/company")
    def company_page(request: Request, edit_id: Optional[int] = None, message: Optional[str] = None, status: str = "success", db: Session = Depends(db_dependency)):
        companies = db.query(Company).order_by(Company.id.asc()).all()
        return templates.TemplateResponse("company.html", {"request": request, "companies": companies, "edit_company": db.get(Company, edit_id) if edit_id else None, "message": message, "status": status})

    @app.post("/company")
    def upsert_company(company_id: Optional[int] = Form(default=None), name: str = Form(...), fein: str = Form(...), florida_account_number: str = Form(...), default_tax_year: int = Form(...), fl_suta_rate: float = Form(...), db: Session = Depends(db_dependency)):
        company = db.get(Company, company_id) if company_id else Company()
        if company_id and not company:
            return RedirectResponse(url="/company?message=Company+not+found&status=error", status_code=302)
        company.name = name
        company.fein = fein
        company.florida_account_number = florida_account_number
        company.default_tax_year = default_tax_year
        company.fl_suta_rate = fl_suta_rate
        if not company_id:
            db.add(company)
        db.commit()
        message = "Company+updated" if company_id else "Company+created"
        return RedirectResponse(url=f"/company?message={message}&status=success", status_code=302)

    @app.post("/company/{company_id}/delete")
    def delete_company(company_id: int, db: Session = Depends(db_dependency)):
        company = db.get(Company, company_id)
        if company:
            db.delete(company)
            db.commit()
            return RedirectResponse(url="/company?message=Company+deleted&status=success", status_code=302)
        return RedirectResponse(url="/company?message=Company+not+found&status=error", status_code=302)

    @app.get("/employees")
    def employee_page(request: Request, edit_id: Optional[int] = None, message: Optional[str] = None, status: str = "success", db: Session = Depends(db_dependency)):
        employees = db.query(Employee).order_by(Employee.id.asc()).all()
        companies = db.query(Company).order_by(Company.name.asc()).all()
        return templates.TemplateResponse("employees.html", {"request": request, "employees": employees, "companies": companies, "edit_employee": db.get(Employee, edit_id) if edit_id else None, "message": message, "status": status})

    @app.post("/employees")
    def upsert_employee(
        employee_id: Optional[int] = Form(default=None),
        company_id: int = Form(...),
        first_name: str = Form(...),
        last_name: str = Form(...),
        ssn_last4: str = Form(...),
        filing_status: str = Form(...),
        w4_dependents_amount: float = Form(0.0),
        w4_other_income: float = Form(0.0),
        w4_deductions: float = Form(0.0),
        w4_extra_withholding: float = Form(0.0),
        pay_type: str = Form(...),
        base_rate: float = Form(...),
        default_hours_per_month: float = Form(173.33),
        db: Session = Depends(db_dependency),
    ):
        emp = db.get(Employee, employee_id) if employee_id else Employee()
        if employee_id and not emp:
            return RedirectResponse(url="/employees?message=Employee+not+found&status=error", status_code=302)
        emp.company_id = company_id
        emp.first_name = first_name
        emp.last_name = last_name
        emp.ssn_last4 = ssn_last4
        emp.filing_status = filing_status
        emp.w4_dependents_amount = w4_dependents_amount
        emp.w4_other_income = w4_other_income
        emp.w4_deductions = w4_deductions
        emp.w4_extra_withholding = w4_extra_withholding
        emp.pay_type = pay_type
        emp.base_rate = base_rate
        emp.default_hours_per_month = default_hours_per_month
        if not employee_id:
            db.add(emp)
        db.commit()
        message = "Employee+updated" if employee_id else "Employee+created"
        return RedirectResponse(url=f"/employees?message={message}&status=success", status_code=302)

    @app.post("/employees/{employee_id}/delete")
    def delete_employee(employee_id: int, db: Session = Depends(db_dependency)):
        emp = db.get(Employee, employee_id)
        if emp:
            db.delete(emp)
            db.commit()
            return RedirectResponse(url="/employees?message=Employee+deleted&status=success", status_code=302)
        return RedirectResponse(url="/employees?message=Employee+not+found&status=error", status_code=302)

    @app.get("/monthly-payroll")
    def payroll_page(request: Request, edit_id: Optional[int] = None, message: Optional[str] = None, status: str = "success", db: Session = Depends(db_dependency)):
        records = db.query(MonthlyPayroll).order_by(MonthlyPayroll.year.desc(), MonthlyPayroll.month.desc()).all()
        employees = db.query(Employee).order_by(Employee.last_name.asc()).all()
        return templates.TemplateResponse("monthly_payroll.html", {"request": request, "records": records, "employees": employees, "edit_record": db.get(MonthlyPayroll, edit_id) if edit_id else None, "message": message, "status": status})

    @app.post("/monthly-payroll")
    def upsert_payroll(record_id: Optional[int] = Form(default=None), employee_id: int = Form(...), year: int = Form(...), month: int = Form(...), pay_date: date = Form(...), hours_worked: float = Form(...), db: Session = Depends(db_dependency)):
        employee = db.get(Employee, employee_id)
        if not employee:
            return RedirectResponse(url="/monthly-payroll?message=Employee+not+found&status=error", status_code=302)
        result = calculate_monthly_payroll(employee, hours_worked)
        rec = db.get(MonthlyPayroll, record_id) if record_id else MonthlyPayroll()
        if record_id and not rec:
            return RedirectResponse(url="/monthly-payroll?message=Record+not+found&status=error", status_code=302)

        # prevent duplicate month records for create/update
        existing = db.query(MonthlyPayroll).filter(MonthlyPayroll.employee_id == employee_id, MonthlyPayroll.year == year, MonthlyPayroll.month == month).first()
        if existing and (not record_id or existing.id != record_id):
            return RedirectResponse(url="/monthly-payroll?message=Record+already+exists+for+employee+month&status=error", status_code=302)

        rec.employee_id = employee_id
        rec.year = year
        rec.month = month
        rec.pay_date = pay_date
        rec.hours_worked = result["hours_worked"]
        rec.gross_pay = result["gross_pay"]
        rec.federal_withholding = result["federal_withholding"]
        rec.social_security = result["social_security"]
        rec.medicare = result["medicare"]
        rec.net_pay = result["net_pay"]
        rec.taxable_wages = result["taxable_wages"]
        rec.calculation_trace = result["calculation_trace"]
        if not record_id:
            db.add(rec)
        db.commit()
        message = "Payroll+updated" if record_id else "Payroll+created"
        return RedirectResponse(url=f"/monthly-payroll?message={message}&status=success", status_code=302)

    @app.post("/monthly-payroll/{record_id}/delete")
    def delete_payroll(record_id: int, db: Session = Depends(db_dependency)):
        rec = db.get(MonthlyPayroll, record_id)
        if rec:
            db.delete(rec)
            db.commit()
            return RedirectResponse(url="/monthly-payroll?message=Payroll+deleted&status=success", status_code=302)
        return RedirectResponse(url="/monthly-payroll?message=Record+not+found&status=error", status_code=302)

    @app.get("/pay-stubs")
    def pay_stubs_page(request: Request, message: Optional[str] = None, status: str = "success", db: Session = Depends(db_dependency)):
        employees = db.query(Employee).order_by(Employee.last_name.asc()).all()
        records = db.query(MonthlyPayroll).order_by(MonthlyPayroll.year.desc(), MonthlyPayroll.month.desc()).all()
        return templates.TemplateResponse("pay_stubs.html", {"request": request, "employees": employees, "records": records, "message": message, "status": status})

    @app.post("/pay-stubs/generate")
    def generate_pay_stub(employee_id: int = Form(...), year: int = Form(...), month: int = Form(...), db: Session = Depends(db_dependency)):
        record = db.query(MonthlyPayroll).filter(MonthlyPayroll.employee_id == employee_id, MonthlyPayroll.year == year, MonthlyPayroll.month == month).first()
        if not record:
            return RedirectResponse(url="/pay-stubs?message=No+payroll+record+found&status=error", status_code=302)
        emp = record.employee
        lines = [
            "Monthly Pay Stub",
            f"Employee: {emp.first_name} {emp.last_name}",
            f"Year/Month: {record.year}/{record.month}",
            f"Pay Date: {record.pay_date.isoformat()}",
            f"Gross: {record.gross_pay:.2f}",
            f"Federal: {record.federal_withholding:.2f}",
            f"Social Security: {record.social_security:.2f}",
            f"Medicare: {record.medicare:.2f}",
            f"Net Pay: {record.net_pay:.2f}",
        ]
        content = create_pay_stub_pdf_bytes(lines)
        filename = f"pay_stub_{emp.last_name}_{year}_{month}.pdf"
        return Response(content=content, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={filename}"})

    def _csv_response(filename: str, headers: list[str], rows: list[list[object]]) -> Response:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        writer.writerows(rows)
        return Response(content=buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})

    @app.get("/reports")
    def reports_page(request: Request, year: int = date.today().year, quarter: int = 1, report_type: str = "rt6", db: Session = Depends(db_dependency)):
        report_data: dict
        if report_type == "941":
            report_data = form941_summary(db, year, quarter)
            template = "reports_941.html"
        elif report_type == "940":
            report_data = form940_summary(db, year)
            template = "reports_940.html"
        else:
            report_type = "rt6"
            report_data = rt6_summary(db, year, quarter)
            template = "reports_rt6.html"
        return templates.TemplateResponse(template, {"request": request, "year": year, "quarter": quarter, "report_type": report_type, "report_data": report_data})

    @app.get("/reports/export/{report_type}")
    def export_report(report_type: str, format: str = "csv", year: int = date.today().year, quarter: int = 1, db: Session = Depends(db_dependency)):
        if report_type == "941":
            data = form941_summary(db, year, quarter)
            if format == "pdf":
                lines = [f"Form 941 Summary {year} Q{quarter}", f"Wages: {data['wages']:.2f}", f"Federal withholding: {data['federal_withholding']:.2f}", f"FICA: {data['fica']:.2f}", f"Total tax: {data['total_tax']:.2f}"]
                return Response(content=create_pay_stub_pdf_bytes(lines), media_type="application/pdf")
            return _csv_response(f"form941_{year}_Q{quarter}.csv", ["wages", "federal_withholding", "fica", "total_tax"], [[data["wages"], data["federal_withholding"], data["fica"], data["total_tax"]]])

        if report_type == "940":
            data = form940_summary(db, year)
            if format == "pdf":
                lines = [f"Form 940 Summary {year}", f"Taxable FUTA wages: {data['wages']:.2f}", f"FUTA Tax: {data['futa_tax']:.2f}"]
                return Response(content=create_pay_stub_pdf_bytes(lines), media_type="application/pdf")
            return _csv_response(f"form940_{year}.csv", ["wages", "futa_tax"], [[data["wages"], data["futa_tax"]]])

        data = rt6_summary(db, year, quarter)
        if format == "pdf":
            lines = [f"RT-6 Summary {year} Q{quarter}", f"Taxable wages: {data['wages']:.2f}", f"Contributions due: {data['contributions_due']:.2f}"]
            return Response(content=create_pay_stub_pdf_bytes(lines), media_type="application/pdf")
        return _csv_response(f"rt6_{year}_Q{quarter}.csv", ["wages", "contributions_due"], [[data["wages"], data["contributions_due"]]])

    return app


app = create_app()

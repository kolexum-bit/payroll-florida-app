from __future__ import annotations

import csv
import io
import os
from datetime import date
from urllib.parse import quote_plus

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import create_session_factory, get_db
from app.models import Company, Employee, MonthlyPayroll
from app.reports.rollups import employee_w2_totals, form940_summary, form941_summary, rt6_summary
from app.services.payroll import calculate_monthly_payroll
from app.services.pdf import create_pay_stub_pdf_bytes


def create_app(database_url: str | None = None) -> FastAPI:
    app = FastAPI(title="Payroll Florida App")
    templates = Jinja2Templates(directory="app/templates")
    session_factory = create_session_factory(database_url or os.getenv("DATABASE_URL", "sqlite:///./payroll.db"))

    def db_dependency():
        yield from get_db(session_factory)

    def current_company(request: Request, db: Session) -> Company | None:
        cid = request.query_params.get("company_id") or request.cookies.get("current_company_id")
        if not cid:
            return None
        return db.get(Company, int(cid))

    def base_ctx(request: Request, db: Session, **extra):
        companies = db.query(Company).order_by(Company.name.asc()).all()
        company = current_company(request, db)
        return {"request": request, "companies": companies, "current_company": company, **extra}

    @app.get("/")
    def root():
        return RedirectResponse(url="/company", status_code=302)

    @app.post("/select-company")
    def select_company(company_id: int = Form(...)):
        resp = RedirectResponse(url=f"/employees?company_id={company_id}", status_code=302)
        resp.set_cookie("current_company_id", str(company_id), httponly=True)
        return resp

    @app.get("/company")
    def company_page(request: Request, edit_id: int | None = None, message: str | None = None, status: str = "success", db: Session = Depends(db_dependency)):
        return templates.TemplateResponse("company.html", base_ctx(request, db, message=message, status=status, edit_company=db.get(Company, edit_id) if edit_id else None))

    @app.post("/company")
    def upsert_company(
        company_id: int | None = Form(default=None),
        name: str = Form(...),
        fein: str = Form(...),
        florida_account_number: str = Form(...),
        default_tax_year: int = Form(...),
        fl_suta_rate: float = Form(...),
        db: Session = Depends(db_dependency),
    ):
        company = db.get(Company, company_id) if company_id else Company()
        if company_id and not company:
            return RedirectResponse(url="/company?message=Company+not+found&status=error", status_code=302)
        company.name, company.fein, company.florida_account_number = name, fein, florida_account_number
        company.default_tax_year, company.fl_suta_rate = default_tax_year, fl_suta_rate
        if not company_id:
            db.add(company)
        db.commit()
        return RedirectResponse(url=f"/company?message={'Company+updated' if company_id else 'Company+created'}&status=success", status_code=302)

    @app.post("/company/{company_id}/delete")
    def delete_company(company_id: int, db: Session = Depends(db_dependency)):
        company = db.get(Company, company_id)
        if not company:
            return RedirectResponse(url="/company?message=Company+not+found&status=error", status_code=302)
        db.delete(company)
        db.commit()
        return RedirectResponse(url="/company?message=Company+deleted+with+cascade&status=success", status_code=302)

    @app.get("/employees")
    def employee_page(request: Request, edit_id: int | None = None, message: str | None = None, status: str = "success", db: Session = Depends(db_dependency)):
        company = current_company(request, db)
        employees = db.query(Employee).filter(Employee.company_id == company.id).order_by(Employee.id.asc()).all() if company else []
        edit_employee = db.get(Employee, edit_id) if edit_id and company else None
        if edit_employee and edit_employee.company_id != company.id:
            edit_employee = None
        return templates.TemplateResponse("employees.html", base_ctx(request, db, employees=employees, edit_employee=edit_employee, message=message, status=status))

    @app.post("/employees")
    def upsert_employee(
        request: Request,
        employee_id: int | None = Form(default=None),
        first_name: str = Form(...),
        last_name: str = Form(...),
        address_line1: str = Form(...),
        city: str = Form(...),
        state: str = Form(...),
        zip_code: str = Form(...),
        ssn: str = Form(...),
        filing_status: str = Form(...),
        w4_dependents_amount: float = Form(0.0),
        w4_other_income: float = Form(0.0),
        w4_deductions: float = Form(0.0),
        w4_extra_withholding: float = Form(0.0),
        monthly_salary: float = Form(...),
        db: Session = Depends(db_dependency),
    ):
        company = current_company(request, db)
        if not company:
            return RedirectResponse(url="/employees?message=Select+a+company+first&status=error", status_code=302)
        emp = db.get(Employee, employee_id) if employee_id else Employee(company_id=company.id)
        if employee_id and (not emp or emp.company_id != company.id):
            return RedirectResponse(url=f"/employees?company_id={company.id}&message=Employee+not+found&status=error", status_code=302)
        for k, v in {
            "first_name": first_name, "last_name": last_name, "address_line1": address_line1, "city": city,
            "state": state.upper(), "zip_code": zip_code, "ssn": ssn, "filing_status": filing_status,
            "w4_dependents_amount": w4_dependents_amount, "w4_other_income": w4_other_income,
            "w4_deductions": w4_deductions, "w4_extra_withholding": w4_extra_withholding, "monthly_salary": monthly_salary,
        }.items():
            setattr(emp, k, v)
        if not employee_id:
            db.add(emp)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return RedirectResponse(url=f"/employees?company_id={company.id}&message=SSN+must+be+unique+within+company&status=error", status_code=302)
        return RedirectResponse(url=f"/employees?company_id={company.id}&message={'Employee+updated' if employee_id else 'Employee+created'}&status=success", status_code=302)

    @app.post("/employees/{employee_id}/delete")
    def delete_employee(request: Request, employee_id: int, db: Session = Depends(db_dependency)):
        company = current_company(request, db)
        emp = db.get(Employee, employee_id)
        if not company or not emp or emp.company_id != company.id:
            return RedirectResponse(url=f"/employees?company_id={company.id if company else ''}&message=Employee+not+found&status=error", status_code=302)
        db.delete(emp)
        db.commit()
        return RedirectResponse(url=f"/employees?company_id={company.id}&message=Employee+deleted&status=success", status_code=302)

    @app.get("/monthly-payroll")
    def payroll_page(request: Request, edit_id: int | None = None, message: str | None = None, status: str = "success", db: Session = Depends(db_dependency)):
        company = current_company(request, db)
        employees = db.query(Employee).filter(Employee.company_id == company.id).order_by(Employee.last_name.asc()).all() if company else []
        records = db.query(MonthlyPayroll).filter(MonthlyPayroll.company_id == company.id).order_by(MonthlyPayroll.year.desc(), MonthlyPayroll.month.desc()).all() if company else []
        edit_record = db.get(MonthlyPayroll, edit_id) if edit_id and company else None
        if edit_record and edit_record.company_id != company.id:
            edit_record = None
        return templates.TemplateResponse("monthly_payroll.html", base_ctx(request, db, employees=employees, records=records, edit_record=edit_record, message=message, status=status))

    @app.post("/monthly-payroll")
    def upsert_payroll(request: Request, record_id: int | None = Form(default=None), employee_id: int = Form(...), year: int = Form(...), month: int = Form(...), pay_date: date = Form(...), bonus: float = Form(0.0), reimbursements: float = Form(0.0), deductions: float = Form(0.0), db: Session = Depends(db_dependency)):
        company = current_company(request, db)
        employee = db.get(Employee, employee_id)
        if not company or not employee or employee.company_id != company.id:
            return RedirectResponse(url=f"/monthly-payroll?company_id={company.id if company else ''}&message=Employee+outside+company+scope&status=error", status_code=302)

        ytd = db.query(MonthlyPayroll).filter(MonthlyPayroll.company_id == company.id, MonthlyPayroll.employee_id == employee_id, MonthlyPayroll.year == year, MonthlyPayroll.month < month)
        ytd_records = ytd.all()
        result = calculate_monthly_payroll(
            employee=employee,
            year=year,
            bonus=bonus,
            reimbursements=reimbursements,
            deductions=deductions,
            ytd_ss_wages=sum(r.social_security_ee / 0.062 if r.social_security_ee else 0 for r in ytd_records),
            ytd_medicare_wages=sum(r.medicare_ee / 0.0145 if r.medicare_ee else 0 for r in ytd_records),
            ytd_futa_wages=sum(r.futa_er / 0.006 if r.futa_er else 0 for r in ytd_records),
            ytd_suta_wages=sum(r.suta_er / (company.fl_suta_rate / 100) if r.suta_er and company.fl_suta_rate else 0 for r in ytd_records),
            company_suta_rate_percent=company.fl_suta_rate,
        )
        rec = db.get(MonthlyPayroll, record_id) if record_id else MonthlyPayroll(company_id=company.id, employee_id=employee_id)
        if record_id and (not rec or rec.company_id != company.id):
            return RedirectResponse(url=f"/monthly-payroll?company_id={company.id}&message=Payroll+record+not+found&status=error", status_code=302)
        rec.company_id, rec.employee_id, rec.year, rec.month, rec.pay_date = company.id, employee_id, year, month, pay_date
        rec.bonus, rec.reimbursements, rec.deductions = bonus, reimbursements, deductions
        for key, value in result.items():
            setattr(rec, key, value)
        if not record_id:
            db.add(rec)
        db.commit()
        return RedirectResponse(url=f"/monthly-payroll?company_id={company.id}&message={'Payroll+updated' if record_id else 'Payroll+created'}&status=success", status_code=302)

    @app.post("/monthly-payroll/{record_id}/delete")
    def delete_payroll(request: Request, record_id: int, db: Session = Depends(db_dependency)):
        company = current_company(request, db)
        rec = db.get(MonthlyPayroll, record_id)
        if not company or not rec or rec.company_id != company.id:
            return RedirectResponse(url=f"/monthly-payroll?company_id={company.id if company else ''}&message=Record+not+found&status=error", status_code=302)
        db.delete(rec)
        db.commit()
        return RedirectResponse(url=f"/monthly-payroll?company_id={company.id}&message=Payroll+deleted&status=success", status_code=302)

    @app.get("/pay-stubs")
    def pay_stubs_page(request: Request, message: str | None = None, status: str = "success", db: Session = Depends(db_dependency)):
        company = current_company(request, db)
        employees = db.query(Employee).filter(Employee.company_id == company.id).order_by(Employee.last_name.asc()).all() if company else []
        records = db.query(MonthlyPayroll).filter(MonthlyPayroll.company_id == company.id).order_by(MonthlyPayroll.year.desc(), MonthlyPayroll.month.desc()).all() if company else []
        return templates.TemplateResponse("pay_stubs.html", base_ctx(request, db, employees=employees, records=records, message=message, status=status))

    @app.post("/pay-stubs/generate")
    def generate_pay_stub(request: Request, employee_id: int = Form(...), year: int = Form(...), month: int = Form(...), db: Session = Depends(db_dependency)):
        company = current_company(request, db)
        record = db.query(MonthlyPayroll).filter(MonthlyPayroll.company_id == (company.id if company else -1), MonthlyPayroll.employee_id == employee_id, MonthlyPayroll.year == year, MonthlyPayroll.month == month).first()
        if not company or not record:
            return RedirectResponse(url=f"/pay-stubs?company_id={company.id if company else ''}&message=No+payroll+record+found&status=error", status_code=302)
        emp = record.employee
        ytd = db.query(MonthlyPayroll).filter(MonthlyPayroll.company_id == company.id, MonthlyPayroll.employee_id == employee_id, MonthlyPayroll.year == year, MonthlyPayroll.month <= month).all()
        lines = ["Monthly Pay Stub", f"Company: {company.name}", f"Employee: {emp.first_name} {emp.last_name}", f"Year/Month: {record.year}/{record.month}", f"Pay Date: {record.pay_date.isoformat()}", f"Gross: {record.gross_pay:.2f}", f"Net Pay: {record.net_pay:.2f}", "Gross & Net by Month (YTD)"]
        for r in ytd:
            lines.append(f"{r.year}-{r.month:02d} Gross {r.gross_pay:.2f} Net {r.net_pay:.2f}")
        return Response(content=create_pay_stub_pdf_bytes(lines), media_type="application/pdf")

    @app.post("/w2/generate/{employee_id}")
    def generate_w2(request: Request, employee_id: int, year: int = Form(...), db: Session = Depends(db_dependency)):
        company = current_company(request, db)
        employee = db.get(Employee, employee_id)
        if not company or not employee or employee.company_id != company.id:
            return RedirectResponse(url=f"/pay-stubs?company_id={company.id if company else ''}&message=Employee+not+found&status=error", status_code=302)
        totals = employee_w2_totals(db, company.id, employee_id, year)
        lines = ["W-2 Wage and Tax Statement", f"Employer: {company.name}", f"Employee: {employee.first_name} {employee.last_name}", f"SSN (last4): {employee.ssn_last4}", f"Tax Year: {year}", f"Box 1 Wages: {totals['box1_wages']:.2f}", f"Box 2 FIT: {totals['box2_fit']:.2f}", f"Box 3 SS Wages: {totals['box3_ss_wages']:.2f}", f"Box 4 SS Tax: {totals['box4_ss_tax']:.2f}", f"Box 5 Medicare Wages: {totals['box5_medicare_wages']:.2f}", f"Box 6 Medicare Tax: {totals['box6_medicare_tax']:.2f}"]
        return Response(content=create_pay_stub_pdf_bytes(lines), media_type="application/pdf")

    @app.post("/w2/generate-batch")
    def generate_w2_batch(request: Request, year: int = Form(...), db: Session = Depends(db_dependency)):
        company = current_company(request, db)
        if not company:
            return RedirectResponse(url="/pay-stubs?message=Select+a+company+first&status=error", status_code=302)
        employees = db.query(Employee).filter(Employee.company_id == company.id).all()
        lines = [f"Batch W-2 Summary {company.name} {year}"]
        for e in employees:
            totals = employee_w2_totals(db, company.id, e.id, year)
            lines.append(f"{e.first_name} {e.last_name}: Box1 {totals['box1_wages']:.2f} Box2 {totals['box2_fit']:.2f}")
        return Response(content=create_pay_stub_pdf_bytes(lines), media_type="application/pdf")

    def _csv_response(filename: str, headers: list[str], rows: list[list[object]]) -> Response:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(headers)
        writer.writerows(rows)
        return Response(content=buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})

    @app.get("/reports")
    def reports_page(request: Request, year: int = date.today().year, quarter: int = 1, report_type: str = "rt6", db: Session = Depends(db_dependency)):
        company = current_company(request, db)
        if not company:
            return templates.TemplateResponse("reports_rt6.html", base_ctx(request, db, year=year, quarter=quarter, report_type="rt6", report_data={"wages": 0, "contributions_due": 0, "line_mapping": {}}))
        if report_type == "941":
            report_data = form941_summary(db, company.id, year, quarter)
            template = "reports_941.html"
        elif report_type == "940":
            report_data = form940_summary(db, company.id, year)
            template = "reports_940.html"
        else:
            report_type, template = "rt6", "reports_rt6.html"
            report_data = rt6_summary(db, company.id, year, quarter, company.fl_suta_rate)
        return templates.TemplateResponse(template, base_ctx(request, db, year=year, quarter=quarter, report_type=report_type, report_data=report_data))

    @app.get("/reports/export/{report_type}")
    def export_report(request: Request, report_type: str, format: str = "csv", year: int = date.today().year, quarter: int = 1, db: Session = Depends(db_dependency)):
        company = current_company(request, db)
        if not company:
            return RedirectResponse(url="/reports?message=Select+a+company+first&status=error", status_code=302)
        if report_type == "941":
            data = form941_summary(db, company.id, year, quarter)
            if format == "pdf":
                return Response(content=create_pay_stub_pdf_bytes([f"Form 941 {year} Q{quarter}", f"Total tax: {data['total_tax']:.2f}"]), media_type="application/pdf")
            return _csv_response("form941.csv", ["wages", "federal_withholding", "social_security_tax", "medicare_tax", "total_tax"], [[data["wages"], data["federal_withholding"], data["social_security_tax"], data["medicare_tax"], data["total_tax"]]])
        if report_type == "940":
            data = form940_summary(db, company.id, year)
            if format == "pdf":
                return Response(content=create_pay_stub_pdf_bytes([f"Form 940 {year}", f"FUTA Tax: {data['futa_tax']:.2f}"]), media_type="application/pdf")
            return _csv_response("form940.csv", ["wages", "futa_tax"], [[data["wages"], data["futa_tax"]]])
        data = rt6_summary(db, company.id, year, quarter, company.fl_suta_rate)
        if format == "pdf":
            return Response(content=create_pay_stub_pdf_bytes([f"RT6 {year} Q{quarter}", f"Contributions: {data['contributions_due']:.2f}"]), media_type="application/pdf")
        return _csv_response("rt6.csv", ["taxable_wages", "contributions_due"], [[data["taxable_wages"], data["contributions_due"]]])

    return app


app = create_app()

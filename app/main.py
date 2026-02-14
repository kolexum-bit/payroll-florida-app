from __future__ import annotations

import csv
import io
import logging
import os
import re
import shutil
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import create_session_factory, get_db
from app.models import Company, Employee, MonthlyPayroll
from app.reports.rollups import employee_w2_totals, form940_summary, form941_summary, rt6_summary
from app.services.payroll import DATA_DIR, TaxConfigError, calculate_monthly_payroll
from app.services.pdf import create_pay_stub_pdf_bytes
from app.utils.rates import format_rate_percent, parse_rate_to_decimal

logger = logging.getLogger(__name__)
PAY_FREQUENCIES = ("weekly", "biweekly", "semimonthly", "monthly", "daily")


def create_app(database_url: str | None = None) -> FastAPI:
    app = FastAPI(title="Payroll Florida App")
    templates = Jinja2Templates(directory="app/templates")
    static_root = Path("app/static")
    upload_root = static_root / "uploads"
    upload_root.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=static_root), name="static")
    session_factory = create_session_factory(database_url or os.getenv("DATABASE_URL", "sqlite:///./payroll.db"))
    app.state.session_factory = session_factory

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
        employee_count = db.query(Employee).filter(Employee.company_id == company.id).count() if company else 0
        wizard_steps = [
            {"name": "Company", "path": "/company", "enabled": True},
            {"name": "Employees", "path": "/employees", "enabled": company is not None},
            {"name": "Payroll", "path": "/monthly-payroll", "enabled": company is not None and employee_count > 0},
            {"name": "Pay Stub / W-2", "path": "/pay-stubs", "enabled": company is not None and employee_count > 0},
            {"name": "Reports", "path": "/reports", "enabled": company is not None and employee_count > 0},
        ]
        current_step = next((idx + 1 for idx, step in enumerate(wizard_steps) if request.url.path.startswith(step["path"])), 1)
        return {
            "request": request,
            "companies": companies,
            "current_company": company,
            "wizard_steps": wizard_steps,
            "current_step": current_step,
            "format_rate_percent": format_rate_percent,
            **extra,
        }

    def redirect_with_banner(path: str, message: str, status: str = "error"):
        joiner = "&" if "?" in path else "?"
        return RedirectResponse(url=f"{path}{joiner}message={quote_plus(message)}&status={status}", status_code=302)

    def require_company(request: Request, db: Session):
        company = current_company(request, db)
        if not company:
            return None, redirect_with_banner("/company", "Please select a company to continue.")
        return company, None

    def require_company_with_employees(request: Request, db: Session):
        company, redirect = require_company(request, db)
        if redirect:
            return None, redirect
        has_employees = db.query(Employee).filter(Employee.company_id == company.id).first() is not None
        if not has_employees:
            return None, redirect_with_banner(f"/employees?company_id={company.id}", "Add at least 1 employee first.")
        return company, None

    def normalize_ssn(raw: str) -> str | None:
        digits = re.sub(r"\D", "", raw or "")
        if len(digits) != 9:
            return None
        return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        if "text/html" in request.headers.get("accept", ""):
            return RedirectResponse(url="/company?message=Something+went+wrong.+Please+try+again.&status=error", status_code=302)
        return JSONResponse(status_code=500, content={"detail": "Internal server error. Please contact support if this persists."})

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
        fl_suta_rate: str = Form(...),
        logo: UploadFile | None = File(default=None),
        remove_logo: str | None = Form(default=None),
        db: Session = Depends(db_dependency),
    ):
        company = db.get(Company, company_id) if company_id else Company()
        if company_id and not company:
            return RedirectResponse(url="/company?message=Company+not+found&status=error", status_code=302)
        company.name, company.fein, company.florida_account_number = name, fein, florida_account_number
        company.default_tax_year = default_tax_year
        try:
            company.fl_suta_rate = parse_rate_to_decimal(fl_suta_rate)
        except ValueError as exc:
            return RedirectResponse(url=f"/company?message={quote_plus(str(exc))}&status=error", status_code=302)

        if remove_logo:
            if company.logo_path:
                (static_root / company.logo_path).unlink(missing_ok=True)
            company.logo_path = None

        if logo and logo.filename:
            content_type = (logo.content_type or "").lower()
            ext = Path(logo.filename).suffix.lower()
            allowed = {".png", ".jpg", ".jpeg"}
            allowed_types = {"image/png", "image/jpeg", "image/jpg"}
            if ext not in allowed or content_type not in allowed_types:
                return RedirectResponse(url="/company?message=Logo+must+be+PNG+or+JPG&status=error", status_code=302)

            logo.file.seek(0, os.SEEK_END)
            size = logo.file.tell()
            logo.file.seek(0)
            if size > 2 * 1024 * 1024:
                return RedirectResponse(url="/company?message=Logo+must+be+2MB+or+smaller&status=error", status_code=302)

            if not company_id:
                db.add(company)
                db.flush()

            company_upload_dir = upload_root / str(company.id)
            company_upload_dir.mkdir(parents=True, exist_ok=True)
            target = company_upload_dir / f"logo{ext}"
            for existing in company_upload_dir.glob("logo.*"):
                existing.unlink(missing_ok=True)
            with target.open("wb") as output:
                shutil.copyfileobj(logo.file, output)
            company.logo_path = str(Path("uploads") / str(company.id) / target.name)

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
        company, redirect = require_company(request, db)
        if redirect:
            return redirect
        employees = db.query(Employee).filter(Employee.company_id == company.id).order_by(Employee.id.asc()).all()
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
        pay_frequency: str = Form("monthly"),
        monthly_salary: float = Form(...),
        db: Session = Depends(db_dependency),
    ):
        company, redirect = require_company(request, db)
        if redirect:
            return redirect
        emp = db.get(Employee, employee_id) if employee_id else Employee(company_id=company.id)
        if employee_id and (not emp or emp.company_id != company.id):
            return RedirectResponse(url=f"/employees?company_id={company.id}&message=Employee+not+found&status=error", status_code=302)
        selected_pay_frequency = (pay_frequency or "monthly").lower()
        if selected_pay_frequency not in PAY_FREQUENCIES:
            return redirect_with_banner(f"/employees?company_id={company.id}", "Choose a valid pay frequency.")
        parsed_ssn = normalize_ssn(ssn)
        if not parsed_ssn:
            return redirect_with_banner(f"/employees?company_id={company.id}", "Enter SSN in format 123-45-6789.")

        for k, v in {
            "first_name": first_name,
            "last_name": last_name,
            "address_line1": address_line1,
            "city": city,
            "state": state.upper(),
            "zip_code": zip_code,
            "ssn": parsed_ssn,
            "filing_status": filing_status,
            "w4_dependents_amount": w4_dependents_amount,
            "w4_other_income": w4_other_income,
            "w4_deductions": w4_deductions,
            "w4_extra_withholding": w4_extra_withholding,
            "pay_frequency": selected_pay_frequency,
            "monthly_salary": monthly_salary,
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
        company, redirect = require_company_with_employees(request, db)
        if redirect:
            return redirect
        employees = db.query(Employee).filter(Employee.company_id == company.id).order_by(Employee.last_name.asc()).all()
        records = db.query(MonthlyPayroll).filter(MonthlyPayroll.company_id == company.id).order_by(MonthlyPayroll.year.desc(), MonthlyPayroll.month.desc()).all()
        edit_record = db.get(MonthlyPayroll, edit_id) if edit_id and company else None
        if edit_record and edit_record.company_id != company.id:
            edit_record = None
        return templates.TemplateResponse("monthly_payroll.html", base_ctx(request, db, employees=employees, records=records, edit_record=edit_record, message=message, status=status))

    @app.post("/monthly-payroll")
    def upsert_payroll(request: Request, record_id: int | None = Form(default=None), employee_id: int = Form(...), year: int = Form(...), month: int = Form(...), pay_date: date = Form(...), bonus: float = Form(0.0), reimbursements: float = Form(0.0), deductions: float = Form(0.0), db: Session = Depends(db_dependency)):
        company = current_company(request, db)
        employee = db.get(Employee, employee_id)
        if not employee or employee.company_id != company.id:
            return RedirectResponse(url=f"/monthly-payroll?company_id={company.id}&message=Employee+outside+company+scope&status=error", status_code=302)

        if employee.pay_frequency != "monthly":
            year = pay_date.year
            month = pay_date.month

        if not (Path(f"/data/tax/{year}").exists() or (DATA_DIR / str(year)).exists()):
            return redirect_with_banner(
                f"/monthly-payroll?company_id={company.id}",
                f"Cannot save payroll yet. Missing required tax data folder: /data/tax/{year}/. Add that folder and rates.json, then try again.",
            )

        ytd_records = db.query(MonthlyPayroll).filter(
            MonthlyPayroll.company_id == company.id,
            MonthlyPayroll.employee_id == employee_id,
            MonthlyPayroll.year == year,
            MonthlyPayroll.month < month,
        ).all()

        def _trace_wages(record: MonthlyPayroll, key: str) -> float:
            return float((record.calculation_trace or {}).get("steps", {}).get(key, 0.0))

        try:
            result = calculate_monthly_payroll(
                employee=employee,
                year=year,
                bonus=bonus,
                reimbursements=reimbursements,
                deductions=deductions,
                ytd_ss_wages=sum(_trace_wages(r, "ss_taxable_wages") for r in ytd_records),
                ytd_medicare_wages=sum(_trace_wages(r, "medicare_taxable_wages") for r in ytd_records),
                ytd_futa_wages=sum(_trace_wages(r, "futa_taxable_wages") for r in ytd_records),
                ytd_suta_wages=sum(_trace_wages(r, "suta_taxable_wages") for r in ytd_records),
                company_suta_rate_decimal=company.fl_suta_rate,
            )
        except TaxConfigError as exc:
            logger.warning("Tax config error for company=%s employee=%s year=%s month=%s: %s", company.id, employee_id, year, month, exc)
            message = quote_plus(str(exc))
            accepts = request.headers.get("accept", "")
            if "text/html" in accepts or "*/*" in accepts:
                return RedirectResponse(url=f"/monthly-payroll?company_id={company.id}&message={message}&status=error", status_code=302)
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        existing = db.query(MonthlyPayroll).filter(
            MonthlyPayroll.company_id == company.id,
            MonthlyPayroll.employee_id == employee_id,
            MonthlyPayroll.year == year,
            MonthlyPayroll.month == month,
        ).first()

        rec = db.get(MonthlyPayroll, record_id) if record_id else existing
        if record_id and (not rec or rec.company_id != company.id):
            return RedirectResponse(url=f"/monthly-payroll?company_id={company.id}&message=Payroll+record+not+found&status=error", status_code=302)
        if not rec:
            rec = MonthlyPayroll(company_id=company.id, employee_id=employee_id)
            db.add(rec)
        rec.company_id, rec.employee_id, rec.year, rec.month, rec.pay_date = company.id, employee_id, year, month, pay_date
        rec.bonus, rec.reimbursements, rec.deductions = bonus, reimbursements, deductions
        for key, value in result.items():
            setattr(rec, key, value)

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return RedirectResponse(url=f"/monthly-payroll?company_id={company.id}&message=Duplicate+payroll+period+for+employee&status=error", status_code=302)
        return RedirectResponse(url=f"/monthly-payroll?company_id={company.id}&message={'Payroll+updated' if existing or record_id else 'Payroll+created'}&status=success", status_code=302)

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
        company, redirect = require_company_with_employees(request, db)
        if redirect:
            return redirect
        employees = db.query(Employee).filter(Employee.company_id == company.id).order_by(Employee.last_name.asc()).all()
        records = db.query(MonthlyPayroll).filter(MonthlyPayroll.company_id == company.id).order_by(MonthlyPayroll.year.desc(), MonthlyPayroll.month.desc()).all()
        return templates.TemplateResponse("pay_stubs.html", base_ctx(request, db, employees=employees, records=records, message=message, status=status))

    @app.post("/pay-stubs/generate")
    def generate_pay_stub(request: Request, employee_id: int = Form(...), year: int = Form(...), month: int = Form(...), db: Session = Depends(db_dependency)):
        company, redirect = require_company_with_employees(request, db)
        if redirect:
            return redirect
        record = db.query(MonthlyPayroll).filter(MonthlyPayroll.company_id == (company.id if company else -1), MonthlyPayroll.employee_id == employee_id, MonthlyPayroll.year == year, MonthlyPayroll.month == month).first()
        if not company or not record:
            return RedirectResponse(url=f"/pay-stubs?company_id={company.id if company else ''}&message=No+payroll+record+found&status=error", status_code=302)
        emp = record.employee
        ytd = db.query(MonthlyPayroll).filter(MonthlyPayroll.company_id == company.id, MonthlyPayroll.employee_id == employee_id, MonthlyPayroll.year == year, MonthlyPayroll.month <= month).order_by(MonthlyPayroll.month.asc()).all()
        ytd_gross = round(sum(r.gross_pay for r in ytd), 2)
        ytd_taxes_deductions = round(sum(r.federal_withholding + r.social_security_ee + r.medicare_ee + r.additional_medicare_ee + r.deductions for r in ytd), 2)
        ytd_net = round(sum(r.net_pay for r in ytd), 2)
        logo_line = f"Logo: {company.logo_path}" if company.logo_path else "Logo: none"

        lines = [
            "Monthly Pay Stub",
            logo_line,
            f"Company: {company.name}",
            f"Employee: {emp.first_name} {emp.last_name}",
            f"Year/Month: {record.year}/{record.month:02d}",
            f"Pay Date: {record.pay_date.isoformat()}",
            "",
            "[Earnings]",
            f"Salary: {emp.monthly_salary:.2f}",
            f"Bonus: {record.bonus:.2f}",
            f"Reimbursements: {record.reimbursements:.2f}",
            f"Gross: {record.gross_pay:.2f}",
            "",
            "[Taxes & Deductions]",
            f"FIT: {record.federal_withholding:.2f}",
            f"Social Security EE: {record.social_security_ee:.2f}",
            f"Medicare EE: {record.medicare_ee:.2f}",
            f"Additional Medicare EE: {record.additional_medicare_ee:.2f}",
            f"Other Deductions: {record.deductions:.2f}",
            "",
            "[Net Pay]",
            f"Net: {record.net_pay:.2f}",
            "",
            "[YTD Summary]",
            f"Gross Income YTD: {ytd_gross:.2f}",
            f"Total Taxes/Deductions YTD: {ytd_taxes_deductions:.2f}",
            f"Net Income YTD: {ytd_net:.2f}",
        ]
        return Response(content=create_pay_stub_pdf_bytes(lines), media_type="application/pdf")

    @app.post("/w2/generate/{employee_id}")
    def generate_w2(request: Request, employee_id: int, year: int = Form(...), db: Session = Depends(db_dependency)):
        company, redirect = require_company_with_employees(request, db)
        if redirect:
            return redirect
        employee = db.get(Employee, employee_id)
        if not company or not employee or employee.company_id != company.id:
            return RedirectResponse(url=f"/pay-stubs?company_id={company.id if company else ''}&message=Employee+not+found&status=error", status_code=302)
        totals = employee_w2_totals(db, company.id, employee_id, year)
        lines = ["W-2 Wage and Tax Statement", f"Employer: {company.name}", f"Employee: {employee.first_name} {employee.last_name}", f"SSN (last4): {employee.ssn_last4}", f"Tax Year: {year}", f"Box 1 Wages: {totals['box1_wages']:.2f}", f"Box 2 FIT: {totals['box2_fit']:.2f}", f"Box 3 SS Wages: {totals['box3_ss_wages']:.2f}", f"Box 4 SS Tax: {totals['box4_ss_tax']:.2f}", f"Box 5 Medicare Wages: {totals['box5_medicare_wages']:.2f}", f"Box 6 Medicare Tax: {totals['box6_medicare_tax']:.2f}"]
        return Response(content=create_pay_stub_pdf_bytes(lines), media_type="application/pdf")

    @app.post("/w2/generate-batch")
    def generate_w2_batch(request: Request, year: int = Form(...), db: Session = Depends(db_dependency)):
        company, redirect = require_company_with_employees(request, db)
        if redirect:
            return redirect
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
        company, redirect = require_company_with_employees(request, db)
        if redirect:
            return redirect
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
        company, redirect = require_company_with_employees(request, db)
        if redirect:
            return redirect
        if report_type == "941":
            data = form941_summary(db, company.id, year, quarter)
            if format == "pdf":
                return Response(content=create_pay_stub_pdf_bytes([f"Form 941 {year} Q{quarter}", f"FIT: {data['federal_withholding']:.2f}", f"SS tax: {data['social_security_tax']:.2f}", f"Medicare tax: {data['medicare_tax']:.2f}", f"Additional Medicare EE: {data['additional_medicare_ee']:.2f}", f"Total tax: {data['total_tax']:.2f}"]), media_type="application/pdf")
            return _csv_response("form941.csv", ["wages", "federal_withholding", "social_security_wages", "social_security_tax", "medicare_wages", "medicare_tax", "additional_medicare_ee", "total_tax"], [[data["wages"], data["federal_withholding"], data["social_security_wages"], data["social_security_tax"], data["medicare_wages"], data["medicare_tax"], data["additional_medicare_ee"], data["total_tax"]]])
        if report_type == "940":
            data = form940_summary(db, company.id, year)
            if format == "pdf":
                return Response(content=create_pay_stub_pdf_bytes([f"Form 940 {year}", f"Total wages: {data['wages']:.2f}", f"Taxable FUTA wages: {data['futa_taxable_wages']:.2f}", f"FUTA Tax: {data['futa_tax']:.2f}"]), media_type="application/pdf")
            return _csv_response("form940.csv", ["wages", "futa_taxable_wages", "futa_tax"], [[data["wages"], data["futa_taxable_wages"], data["futa_tax"]]])
        data = rt6_summary(db, company.id, year, quarter, company.fl_suta_rate)
        if format == "pdf":
            return Response(content=create_pay_stub_pdf_bytes([f"RT6 {year} Q{quarter}", f"Taxable wages: {data['taxable_wages']:.2f}", f"Contributions: {data['contributions_due']:.2f}"]), media_type="application/pdf")
        return _csv_response("rt6.csv", ["wages", "taxable_wages", "contributions_due"], [[data["wages"], data["taxable_wages"], data["contributions_due"]]])

    return app


app = create_app()

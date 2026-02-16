from __future__ import annotations

import csv
import io
import logging
import os
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
from app.services.payroll import TaxConfigError, calculate_monthly_payroll, tax_year_available
from app.services.pdf import create_monthly_pay_stub_pdf_bytes, create_pay_stub_pdf_bytes
from app.services.tax_validation import validate_fit_tables, validate_tax_year_data
from app.utils.rates import format_rate_percent, parse_rate_to_decimal

logger = logging.getLogger(__name__)



PAY_FREQUENCY_OPTIONS = ["daily", "weekly", "biweekly", "semimonthly", "monthly"]
FILING_STATUS_OPTIONS = [
    "single_or_married_filing_separately",
    "married_filing_jointly",
    "head_of_household",
]

def create_app(database_url: str | None = None) -> FastAPI:
    app = FastAPI(title="Payroll Florida App")
    templates = Jinja2Templates(directory="app/templates")
    static_root = Path("app/static")
    logo_root = static_root / "company_logos"
    logo_root.mkdir(parents=True, exist_ok=True)
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
        tax_validation = validate_tax_year_data(company.default_tax_year) if company else None
        return {
            "request": request,
            "companies": companies,
            "current_company": company,
            "tax_validation": tax_validation,
            "format_rate_percent": format_rate_percent,
            **extra,
        }

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

    def _delete_company_logo_files(company_id: int):
        company_logo_dir = (logo_root / str(company_id)).resolve()
        expected_root = logo_root.resolve()
        if expected_root not in company_logo_dir.parents:
            return
        if company_logo_dir.exists():
            for existing in company_logo_dir.glob("logo.*"):
                existing.unlink(missing_ok=True)

    def _store_company_logo(company: Company, logo: UploadFile) -> tuple[str, str]:
        content_type = (logo.content_type or "").lower()
        ext = Path(logo.filename or "").suffix.lower()
        allowed_exts = {".png", ".jpg", ".jpeg"}
        allowed_mime = {"image/png", "image/jpeg", "image/jpg"}
        if ext not in allowed_exts or content_type not in allowed_mime:
            raise ValueError("Logo must be PNG or JPG")

        logo_bytes = logo.file.read()
        if len(logo_bytes) > 2 * 1024 * 1024:
            raise ValueError("Logo must be 2MB or smaller")

        normalized_ext = ".jpg" if ext in {".jpg", ".jpeg"} else ".png"
        company_logo_dir = (logo_root / str(company.id)).resolve()
        expected_root = logo_root.resolve()
        if expected_root not in company_logo_dir.parents:
            raise ValueError("Invalid logo upload path")

        company_logo_dir.mkdir(parents=True, exist_ok=True)
        for existing in company_logo_dir.glob("logo.*"):
            existing.unlink(missing_ok=True)

        filename = f"logo{normalized_ext}"
        target = (company_logo_dir / filename).resolve()
        if company_logo_dir != target.parent:
            raise ValueError("Invalid logo upload path")
        target.write_bytes(logo_bytes)

        rel_path = Path("company_logos") / str(company.id) / filename
        normalized_mime = "image/jpeg" if normalized_ext == ".jpg" else "image/png"
        return str(rel_path), normalized_mime

    @app.post("/company")
    def upsert_company(
        company_id: int | None = Form(default=None),
        name: str = Form(...),
        fein: str = Form(...),
        florida_account_number: str = Form(...),
        default_tax_year: int = Form(...),
        fl_suta_rate: str = Form(...),
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

        if not company_id:
            db.add(company)
        db.commit()
        return RedirectResponse(url=f"/company?message={'Company+updated' if company_id else 'Company+created'}&status=success", status_code=302)

    @app.post("/company/{company_id}/logo")
    def upload_company_logo(company_id: int, logo: UploadFile = File(...), db: Session = Depends(db_dependency)):
        company = db.get(Company, company_id)
        if not company:
            return RedirectResponse(url="/company?message=Company+not+found&status=error", status_code=302)
        try:
            logo_path, logo_mime = _store_company_logo(company, logo)
        except ValueError as exc:
            return RedirectResponse(url=f"/company?edit_id={company_id}&message={quote_plus(str(exc))}&status=error", status_code=302)

        company.logo_path = logo_path
        company.logo_mime = logo_mime
        db.commit()
        return RedirectResponse(url=f"/company?edit_id={company_id}&message=Logo+uploaded&status=success", status_code=302)

    @app.post("/company/{company_id}/logo/delete")
    def delete_company_logo(company_id: int, db: Session = Depends(db_dependency)):
        company = db.get(Company, company_id)
        if not company:
            return RedirectResponse(url="/company?message=Company+not+found&status=error", status_code=302)

        _delete_company_logo_files(company_id)
        company.logo_path = None
        company.logo_mime = None
        db.commit()
        return RedirectResponse(url=f"/company?edit_id={company_id}&message=Logo+removed&status=success", status_code=302)

    @app.post("/company/{company_id}/delete")
    def delete_company(company_id: int, db: Session = Depends(db_dependency)):
        company = db.get(Company, company_id)
        if not company:
            return RedirectResponse(url="/company?message=Company+not+found&status=error", status_code=302)
        _delete_company_logo_files(company_id)
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
        return templates.TemplateResponse("employees.html", base_ctx(request, db, employees=employees, edit_employee=edit_employee, message=message, status=status, pay_frequency_options=PAY_FREQUENCY_OPTIONS, filing_status_options=FILING_STATUS_OPTIONS))

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
        pay_frequency: str = Form(...),
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
        if pay_frequency not in PAY_FREQUENCY_OPTIONS:
            return RedirectResponse(url=f"/employees?company_id={company.id}&message=Invalid+pay+frequency&status=error", status_code=302)
        if filing_status not in FILING_STATUS_OPTIONS:
            return RedirectResponse(url=f"/employees?company_id={company.id}&message=Invalid+filing+status&status=error", status_code=302)
        numeric_fields = {
            "w4_dependents_amount": w4_dependents_amount,
            "w4_other_income": w4_other_income,
            "w4_deductions": w4_deductions,
            "w4_extra_withholding": w4_extra_withholding,
            "monthly_salary": monthly_salary,
        }
        if any(v < 0 for v in numeric_fields.values()):
            return RedirectResponse(url=f"/employees?company_id={company.id}&message=Numeric+fields+must+be+zero+or+greater&status=error", status_code=302)
        for k, v in {
            "first_name": first_name,
            "last_name": last_name,
            "address_line1": address_line1,
            "city": city,
            "state": state.upper(),
            "zip_code": zip_code,
            "ssn": ssn,
            "pay_frequency": pay_frequency,
            "filing_status": filing_status,
            "w4_dependents_amount": w4_dependents_amount,
            "w4_other_income": w4_other_income,
            "w4_deductions": w4_deductions,
            "w4_extra_withholding": w4_extra_withholding,
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
        company = current_company(request, db)
        employees = db.query(Employee).filter(Employee.company_id == company.id).order_by(Employee.last_name.asc()).all() if company else []
        records = db.query(MonthlyPayroll).filter(MonthlyPayroll.company_id == company.id).order_by(MonthlyPayroll.year.desc(), MonthlyPayroll.month.desc()).all() if company else []
        edit_record = db.get(MonthlyPayroll, edit_id) if edit_id and company else None
        if edit_record and edit_record.company_id != company.id:
            edit_record = None
        missing_tax_year_banner = None
        if company and not tax_year_available(company.default_tax_year):
            missing_tax_year_banner = f"Tax tables for {company.default_tax_year} are missing. Please add /data/tax/{company.default_tax_year}/..."
        return templates.TemplateResponse("monthly_payroll.html", base_ctx(request, db, employees=employees, records=records, edit_record=edit_record, message=message, status=status, missing_tax_year_banner=missing_tax_year_banner))

    @app.post("/monthly-payroll")
    def upsert_payroll(request: Request, record_id: int | None = Form(default=None), employee_id: int = Form(...), year: int | None = Form(default=None), month: int = Form(...), pay_date: date = Form(...), bonus: float = Form(0.0), reimbursements: float = Form(0.0), deductions: float = Form(0.0), db: Session = Depends(db_dependency)):
        company = current_company(request, db)
        employee = db.get(Employee, employee_id)
        if not company or not employee or employee.company_id != company.id:
            return RedirectResponse(url=f"/monthly-payroll?company_id={company.id if company else ''}&message=Employee+outside+company+scope&status=error", status_code=302)
        calc_year = year or company.default_tax_year
        validation_result = validate_fit_tables(calc_year, employee.pay_frequency)
        if not validation_result.ok:
            guide = f"Tax tables for {calc_year} are missing or invalid for {employee.pay_frequency}. Please update data/tax/{calc_year}/validation.json and fit tables."
            detail = " ".join(validation_result.errors) if validation_result.errors else guide
            message = quote_plus(f"{guide} Details: {detail}")
            accepts = request.headers.get("accept", "")
            if "text/html" in accepts or "*/*" in accepts:
                return RedirectResponse(url=f"/monthly-payroll?company_id={company.id}&message={message}&status=error", status_code=302)
            raise HTTPException(status_code=400, detail={"message": guide, "validation": validation_result.to_dict()})
        if not tax_year_available(calc_year):
            missing_msg = f"Tax tables for {calc_year} are missing. Please add /data/tax/{calc_year}/..."
            accepts = request.headers.get("accept", "")
            if "text/html" in accepts or "*/*" in accepts:
                msg = quote_plus(missing_msg)
                return RedirectResponse(url=f"/monthly-payroll?company_id={company.id}&message={msg}&status=error", status_code=302)
            raise HTTPException(status_code=400, detail=missing_msg)

        ytd_records = db.query(MonthlyPayroll).filter(
            MonthlyPayroll.company_id == company.id,
            MonthlyPayroll.employee_id == employee_id,
            MonthlyPayroll.year == calc_year,
            MonthlyPayroll.month < month,
        ).all()

        def _trace_wages(record: MonthlyPayroll, key: str) -> float:
            return float((record.calculation_trace or {}).get("steps", {}).get(key, 0.0))

        try:
            result = calculate_monthly_payroll(
                employee=employee,
                year=calc_year,
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
            MonthlyPayroll.year == calc_year,
            MonthlyPayroll.month == month,
        ).first()

        rec = db.get(MonthlyPayroll, record_id) if record_id else existing
        if record_id and (not rec or rec.company_id != company.id):
            return RedirectResponse(url=f"/monthly-payroll?company_id={company.id}&message=Payroll+record+not+found&status=error", status_code=302)
        if not rec:
            rec = MonthlyPayroll(company_id=company.id, employee_id=employee_id)
            db.add(rec)
        rec.company_id, rec.employee_id, rec.year, rec.month, rec.pay_date = company.id, employee_id, calc_year, month, pay_date
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
        ytd = db.query(MonthlyPayroll).filter(MonthlyPayroll.company_id == company.id, MonthlyPayroll.employee_id == employee_id, MonthlyPayroll.year == year, MonthlyPayroll.month <= month).order_by(MonthlyPayroll.month.asc()).all()
        ytd_gross = round(sum(r.gross_pay for r in ytd), 2)
        ytd_taxes_deductions = round(sum(r.federal_withholding + r.social_security_ee + r.medicare_ee + r.additional_medicare_ee + r.deductions for r in ytd), 2)
        ytd_net = round(sum(r.net_pay for r in ytd), 2)
        logo_abs_path = None
        if company.logo_path:
            resolved_logo = (static_root / company.logo_path).resolve()
            if logo_root.resolve() in resolved_logo.parents and resolved_logo.exists():
                logo_abs_path = str(resolved_logo)

        pdf_bytes = create_monthly_pay_stub_pdf_bytes(
            company_name=company.name,
            employee_name=f"{emp.first_name} {emp.last_name}",
            pay_period=f"{record.year}/{record.month:02d}",
            pay_date=record.pay_date.isoformat(),
            salary=emp.monthly_salary,
            bonus=record.bonus,
            reimbursements=record.reimbursements,
            gross=record.gross_pay,
            fit=record.federal_withholding,
            ss_ee=record.social_security_ee,
            medicare_ee=record.medicare_ee,
            addl_medicare_ee=record.additional_medicare_ee,
            other_deductions=record.deductions,
            net=record.net_pay,
            ytd_gross=ytd_gross,
            ytd_taxes_deductions=ytd_taxes_deductions,
            ytd_net=ytd_net,
            logo_path=logo_abs_path,
        )
        return Response(content=pdf_bytes, media_type="application/pdf")

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

    @app.get("/health/tax/{year}")
    def tax_health(year: int, pay_frequency: str = "monthly"):
        result = validate_fit_tables(year, pay_frequency)
        return JSONResponse(content=result.to_dict())

    return app


app = create_app()

import json
import os
from io import BytesIO
from typing import Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import create_session_factory, get_db
from app.models import Company, Employee, MonthlyPayroll


def create_app(database_url: Optional[str] = None) -> FastAPI:
    app = FastAPI(title="Payroll Florida App")
    templates = Jinja2Templates(directory="app/templates")

    resolved_database_url = database_url or os.getenv("DATABASE_URL", "sqlite:///./payroll.db")
    session_factory = create_session_factory(resolved_database_url)

    def db_dependency():
        yield from get_db(session_factory)

    def calc_payroll(gross_pay: float) -> dict:
        fed = round(gross_pay * 0.10, 2)
        ss = round(gross_pay * 0.062, 2)
        med = round(gross_pay * 0.0145, 2)
        net = round(gross_pay - fed - ss - med, 2)
        return {
            "federal_withholding": fed,
            "social_security": ss,
            "medicare": med,
            "net_pay": net,
            "calculation_trace": json.dumps(
                {
                    "steps": [
                        {"name": "gross_pay", "value": gross_pay},
                        {"name": "federal_withholding", "rate": 0.10, "value": fed},
                        {"name": "social_security", "rate": 0.062, "value": ss},
                        {"name": "medicare", "rate": 0.0145, "value": med},
                        {"name": "net_pay", "value": net},
                    ]
                }
            ),
        }

    @app.get("/")
    def root():
        return RedirectResponse(url="/company", status_code=302)

    @app.get("/company")
    def company_page(
        request: Request,
        edit_id: Optional[int] = None,
        message: Optional[str] = None,
        status: str = "success",
        db: Session = Depends(db_dependency),
    ):
        companies = db.query(Company).order_by(Company.id.asc()).all()
        company_to_edit = db.get(Company, edit_id) if edit_id else None
        return templates.TemplateResponse(
            "company.html",
            {
                "request": request,
                "companies": companies,
                "edit_company": company_to_edit,
                "message": message,
                "status": status,
            },
        )

    @app.post("/company")
    def upsert_company(
        company_id: Optional[int] = Form(default=None),
        name: str = Form(...),
        fein: str = Form(...),
        florida_account_number: str = Form(...),
        default_tax_year: int = Form(...),
        fl_suta_rate: float = Form(...),
        db: Session = Depends(db_dependency),
    ):
        if company_id:
            company = db.get(Company, company_id)
            if company:
                company.name = name
                company.fein = fein
                company.florida_account_number = florida_account_number
                company.default_tax_year = default_tax_year
                company.fl_suta_rate = fl_suta_rate
                return RedirectResponse(
                    url="/company?message=Company+updated&status=success", status_code=302
                )

        company = Company(
            name=name,
            fein=fein,
            florida_account_number=florida_account_number,
            default_tax_year=default_tax_year,
            fl_suta_rate=fl_suta_rate,
        )
        db.add(company)
        return RedirectResponse(url="/company?message=Company+created&status=success", status_code=302)

    @app.post("/company/{company_id}/delete")
    def delete_company(company_id: int, db: Session = Depends(db_dependency)):
        company = db.get(Company, company_id)
        if company:
            db.delete(company)
            return RedirectResponse(url="/company?message=Company+deleted&status=success", status_code=302)
        return RedirectResponse(url="/company?message=Company+not+found&status=error", status_code=302)

    @app.get("/employees")
    def employees_page(
        request: Request,
        edit_id: Optional[int] = None,
        message: Optional[str] = None,
        status: str = "success",
        db: Session = Depends(db_dependency),
    ):
        employees = db.query(Employee).order_by(Employee.id.asc()).all()
        companies = db.query(Company).order_by(Company.name.asc()).all()
        edit_employee = db.get(Employee, edit_id) if edit_id else None
        return templates.TemplateResponse(
            "employees.html",
            {
                "request": request,
                "employees": employees,
                "companies": companies,
                "edit_employee": edit_employee,
                "message": message,
                "status": status,
            },
        )

    @app.post("/employees")
    def upsert_employee(
        employee_id: Optional[int] = Form(default=None),
        company_id: int = Form(...),
        first_name: str = Form(...),
        last_name: str = Form(...),
        email: str = Form(...),
        monthly_salary: float = Form(...),
        db: Session = Depends(db_dependency),
    ):
        if not db.get(Company, company_id):
            return RedirectResponse(url="/employees?message=Company+not+found&status=error", status_code=302)

        if employee_id:
            employee = db.get(Employee, employee_id)
            if employee:
                employee.company_id = company_id
                employee.first_name = first_name
                employee.last_name = last_name
                employee.email = email
                employee.monthly_salary = monthly_salary
                return RedirectResponse(url="/employees?message=Employee+updated&status=success", status_code=302)

        db.add(
            Employee(
                company_id=company_id,
                first_name=first_name,
                last_name=last_name,
                email=email,
                monthly_salary=monthly_salary,
            )
        )
        return RedirectResponse(url="/employees?message=Employee+created&status=success", status_code=302)

    @app.post("/employees/{employee_id}/delete")
    def delete_employee(employee_id: int, db: Session = Depends(db_dependency)):
        employee = db.get(Employee, employee_id)
        if employee:
            db.delete(employee)
            return RedirectResponse(url="/employees?message=Employee+deleted&status=success", status_code=302)
        return RedirectResponse(url="/employees?message=Employee+not+found&status=error", status_code=302)

    @app.get("/monthly-payroll")
    def monthly_payroll_page(
        request: Request,
        edit_id: Optional[int] = None,
        message: Optional[str] = None,
        status: str = "success",
        db: Session = Depends(db_dependency),
    ):
        entries = db.query(MonthlyPayroll).order_by(MonthlyPayroll.id.desc()).all()
        employees = db.query(Employee).order_by(Employee.last_name.asc()).all()
        edit_entry = db.get(MonthlyPayroll, edit_id) if edit_id else None
        return templates.TemplateResponse(
            "monthly_payroll.html",
            {
                "request": request,
                "entries": entries,
                "employees": employees,
                "edit_entry": edit_entry,
                "message": message,
                "status": status,
            },
        )

    @app.post("/monthly-payroll")
    def upsert_monthly_payroll(
        payroll_id: Optional[int] = Form(default=None),
        employee_id: int = Form(...),
        period: str = Form(...),
        gross_pay: float = Form(...),
        db: Session = Depends(db_dependency),
    ):
        if not db.get(Employee, employee_id):
            return RedirectResponse(url="/monthly-payroll?message=Employee+not+found&status=error", status_code=302)

        if len(period) != 7 or period[4] != "-":
            return RedirectResponse(url="/monthly-payroll?message=Invalid+period+format&status=error", status_code=302)

        computed = calc_payroll(gross_pay)
        if payroll_id:
            entry = db.get(MonthlyPayroll, payroll_id)
            if entry:
                entry.employee_id = employee_id
                entry.period = period
                entry.gross_pay = gross_pay
                entry.federal_withholding = computed["federal_withholding"]
                entry.social_security = computed["social_security"]
                entry.medicare = computed["medicare"]
                entry.net_pay = computed["net_pay"]
                entry.calculation_trace = computed["calculation_trace"]
                return RedirectResponse(url="/monthly-payroll?message=Payroll+updated&status=success", status_code=302)

        db.add(
            MonthlyPayroll(
                employee_id=employee_id,
                period=period,
                gross_pay=gross_pay,
                federal_withholding=computed["federal_withholding"],
                social_security=computed["social_security"],
                medicare=computed["medicare"],
                net_pay=computed["net_pay"],
                calculation_trace=computed["calculation_trace"],
            )
        )
        return RedirectResponse(url="/monthly-payroll?message=Payroll+created&status=success", status_code=302)

    @app.post("/monthly-payroll/{payroll_id}/delete")
    def delete_monthly_payroll(payroll_id: int, db: Session = Depends(db_dependency)):
        entry = db.get(MonthlyPayroll, payroll_id)
        if entry:
            db.delete(entry)
            return RedirectResponse(url="/monthly-payroll?message=Payroll+deleted&status=success", status_code=302)
        return RedirectResponse(url="/monthly-payroll?message=Payroll+not+found&status=error", status_code=302)

    @app.get("/paystubs")
    def paystubs_page(request: Request, db: Session = Depends(db_dependency)):
        entries = db.query(MonthlyPayroll).order_by(MonthlyPayroll.id.desc()).all()
        return templates.TemplateResponse("paystubs.html", {"request": request, "entries": entries})

    @app.get("/paystubs/{payroll_id}.pdf")
    def paystub_pdf(payroll_id: int, db: Session = Depends(db_dependency)):
        entry = db.get(MonthlyPayroll, payroll_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Payroll not found")

        lines = [
            f"Pay Stub #{entry.id}",
            f"Employee: {entry.employee.first_name} {entry.employee.last_name}",
            f"Period: {entry.period}",
            f"Gross Pay: ${entry.gross_pay:.2f}",
            f"Federal: ${entry.federal_withholding:.2f}",
            f"Social Security: ${entry.social_security:.2f}",
            f"Medicare: ${entry.medicare:.2f}",
            f"Net Pay: ${entry.net_pay:.2f}",
        ]

        text = "\n".join(lines)
        stream = BytesIO()
        content = f"BT /F1 12 Tf 50 750 Td ({text.replace(chr(10), ') Tj T* (')}) Tj ET"
        pdf = (
            "%PDF-1.4\n"
            "1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n"
            "2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n"
            "3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>endobj\n"
            "4 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n"
            f"5 0 obj<< /Length {len(content)} >>stream\n{content}\nendstream endobj\n"
            "xref\n0 6\n0000000000 65535 f \n"
            "0000000010 00000 n \n0000000062 00000 n \n0000000117 00000 n \n0000000243 00000 n \n0000000313 00000 n \n"
            "trailer<< /Size 6 /Root 1 0 R >>\nstartxref\n0\n%%EOF"
        )
        stream.write(pdf.encode("latin-1", errors="ignore"))
        return Response(
            content=stream.getvalue(),
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename=paystub-{entry.id}.pdf"},
        )

    @app.get("/reports")
    def reports_page(request: Request, db: Session = Depends(db_dependency)):
        summary = (
            db.query(
                func.count(MonthlyPayroll.id),
                func.coalesce(func.sum(MonthlyPayroll.gross_pay), 0.0),
                func.coalesce(func.sum(MonthlyPayroll.net_pay), 0.0),
                func.coalesce(func.sum(MonthlyPayroll.federal_withholding), 0.0),
            )
            .one()
        )
        recent = db.query(MonthlyPayroll).order_by(MonthlyPayroll.id.desc()).limit(10).all()
        return templates.TemplateResponse(
            "reports.html",
            {
                "request": request,
                "summary": {
                    "count": summary[0],
                    "gross": round(summary[1], 2),
                    "net": round(summary[2], 2),
                    "federal": round(summary[3], 2),
                },
                "recent": recent,
            },
        )

    return app


app = create_app()

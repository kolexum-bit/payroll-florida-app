import os
from typing import Optional

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import create_session_factory, get_db
from app.models import Company


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
                db.commit()
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
        db.commit()
        return RedirectResponse(url="/company?message=Company+created&status=success", status_code=302)

    @app.post("/company/{company_id}/delete")
    def delete_company(company_id: int, db: Session = Depends(db_dependency)):
        company = db.get(Company, company_id)
        if company:
            db.delete(company)
            db.commit()
            return RedirectResponse(
                url="/company?message=Company+deleted&status=success", status_code=302
            )
        return RedirectResponse(url="/company?message=Company+not+found&status=error", status_code=302)

    return app


app = create_app()

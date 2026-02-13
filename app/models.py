from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    fein: Mapped[str] = mapped_column(String(32), nullable=False)
    florida_account_number: Mapped[str] = mapped_column(String(64), nullable=False)
    default_tax_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fl_suta_rate: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    ssn_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    filing_status: Mapped[str] = mapped_column(String(32), nullable=False, default="single")
    w4_dependents_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    w4_other_income: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    w4_deductions: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    w4_extra_withholding: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pay_type: Mapped[str] = mapped_column(String(32), nullable=False, default="salary")
    base_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    default_hours_per_month: Mapped[float] = mapped_column(Float, nullable=False, default=173.33)

    company: Mapped[Company] = relationship()


class MonthlyPayroll(Base):
    __tablename__ = "monthly_payrolls"
    __table_args__ = (UniqueConstraint("employee_id", "year", "month", name="uq_employee_year_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    pay_date: Mapped[date] = mapped_column(Date, nullable=False)
    hours_worked: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    gross_pay: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    federal_withholding: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    social_security: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    medicare: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    net_pay: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    taxable_wages: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    calculation_trace: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    employee: Mapped[Employee] = relationship()

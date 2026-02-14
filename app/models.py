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
    logo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    employees: Mapped[list["Employee"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    payrolls: Mapped[list["MonthlyPayroll"]] = relationship(back_populates="company", cascade="all, delete-orphan")


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (
        UniqueConstraint("company_id", "ssn", name="uq_employee_company_ssn"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    zip_code: Mapped[str] = mapped_column(String(12), nullable=False)
    ssn: Mapped[str] = mapped_column(String(11), nullable=False)
    filing_status: Mapped[str] = mapped_column(String(32), nullable=False, default="single")
    w4_dependents_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    w4_other_income: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    w4_deductions: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    w4_extra_withholding: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pay_frequency: Mapped[str] = mapped_column(String(20), nullable=False, default="monthly")
    monthly_salary: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    company: Mapped[Company] = relationship(back_populates="employees")

    @property
    def ssn_last4(self) -> str:
        return self.ssn[-4:]


class MonthlyPayroll(Base):
    __tablename__ = "monthly_payrolls"
    __table_args__ = (
        UniqueConstraint("company_id", "employee_id", "year", "month", name="uq_company_employee_year_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    pay_date: Mapped[date] = mapped_column(Date, nullable=False)
    bonus: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reimbursements: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    deductions: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    gross_pay: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    federal_withholding: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    social_security_ee: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    medicare_ee: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    additional_medicare_ee: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    social_security_er: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    medicare_er: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    futa_er: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    suta_er: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    net_pay: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    calculation_trace: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    employee: Mapped[Employee] = relationship()
    company: Mapped[Company] = relationship(back_populates="payrolls")

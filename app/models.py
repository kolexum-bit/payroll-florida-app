from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    employees: Mapped[list["Employee"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    monthly_salary: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    company: Mapped[Company] = relationship(back_populates="employees")
    payroll_entries: Mapped[list["MonthlyPayroll"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )


class MonthlyPayroll(Base):
    __tablename__ = "monthly_payroll"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    gross_pay: Mapped[float] = mapped_column(Float, nullable=False)
    federal_withholding: Mapped[float] = mapped_column(Float, nullable=False)
    social_security: Mapped[float] = mapped_column(Float, nullable=False)
    medicare: Mapped[float] = mapped_column(Float, nullable=False)
    net_pay: Mapped[float] = mapped_column(Float, nullable=False)
    calculation_trace: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    employee: Mapped[Employee] = relationship(back_populates="payroll_entries")

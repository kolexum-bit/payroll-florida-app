from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import relationship

from .database import Base


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    fein = Column(String, nullable=False)
    fl_account_number = Column(String, nullable=False)
    default_tax_year = Column(Integer, default=2026)
    fl_suta_rate = Column(Float, default=0.027)
    created_at = Column(DateTime, server_default=func.now())

    employees = relationship("Employee", back_populates="company")


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    ssn_last4 = Column(String, nullable=False)
    filing_status = Column(String, nullable=False, default="single")
    step2_checkbox = Column(Boolean, default=False)
    dependents_child_count = Column(Integer, default=0)
    dependents_other_count = Column(Integer, default=0)
    other_income_annual = Column(Float, default=0.0)
    deductions_annual = Column(Float, default=0.0)
    extra_withholding = Column(Float, default=0.0)
    pre_tax_deduction_monthly = Column(Float, default=0.0)
    post_tax_deduction_monthly = Column(Float, default=0.0)
    active = Column(Boolean, default=True)

    company = relationship("Company", back_populates="employees")
    payroll_records = relationship("PayrollRecord", back_populates="employee")


class PayrollRecord(Base):
    __tablename__ = "payroll_records"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    tax_year = Column(Integer, nullable=False)
    pay_month = Column(Integer, nullable=False)
    pay_date = Column(Date, nullable=False)

    gross_wages = Column(Float, nullable=False)
    pre_tax_deductions = Column(Float, default=0.0)
    taxable_wages_federal = Column(Float, nullable=False)

    fit_withholding = Column(Float, default=0.0)
    social_security_employee = Column(Float, default=0.0)
    medicare_employee = Column(Float, default=0.0)
    additional_medicare_employee = Column(Float, default=0.0)
    post_tax_deductions = Column(Float, default=0.0)

    social_security_employer = Column(Float, default=0.0)
    medicare_employer = Column(Float, default=0.0)
    futa_employer = Column(Float, default=0.0)
    florida_suta_employer = Column(Float, default=0.0)

    net_pay = Column(Float, nullable=False)
    calculation_trace = Column(JSON, nullable=False)

    created_at = Column(DateTime, server_default=func.now())

    employee = relationship("Employee", back_populates="payroll_records")

# SPEC

## Scope
This implementation supports strict multi-company payroll with per-company data separation.

## Data model
- `employees.company_id` FK to `companies.id`.
- `monthly_payrolls.company_id` FK to `companies.id`.
- Unique constraints:
  - `(company_id, ssn)` for employees.
  - `(company_id, employee_id, year, month)` for payroll rows.
- Deletion rule: **cascade delete** company -> employees/payroll.

## Assumptions and sources
- Tax year config loaded from `data/tax/{year}/`.
- Source metadata stored in `metadata.json` (`source`, `version`, `last_updated`, `notes`, `tax_year`, `method`).
- FIT uses Pub 15-T style percentage method tables by pay frequency + filing status.
- `validation.json` stores key year invariants (standard deductions + bracket thresholds) used to detect wrong-year tables.

## Rounding
- Monetary values rounded to 2 decimals after each computed line item.

## Year versioning
- Calculations load year-specific data by payroll year and employee pay frequency.
- Missing/mismatched tax year data is a user-facing validation error (no crash).
- Payroll save is blocked when metadata, required FIT files, or Pub 15-T invariants do not validate for the selected year/frequency.
- Troubleshooting endpoint: `/health/tax/{year}` returns structured validation results.

## Pay stub rendering
- Pay stub header renders the company logo at top-right when `companies.logo_path` is present and the file can be loaded from local disk.
- Missing/unreadable logo files are ignored silently (PDF generation does not fail).

## W-2 mapping
Generated from stored payroll ledger totals:
- Box 1 = sum(gross_pay)
- Box 2 = sum(federal_withholding)
- Box 3 = SS wages derived from EE SS tax / 0.062
- Box 4 = sum(social_security_ee)
- Box 5 = Medicare wages derived from medicare_ee / 0.0145
- Box 6 = sum(medicare_ee + additional_medicare_ee)

## Employer reports mapping
- RT-6 quarterly:
  - Total/Taxable wages from payroll rows in quarter.
  - Tax due from stored `suta_er` rollup.
- Form 941 quarterly:
  - FIT withheld + SS EE/ER + Medicare EE/ER + Additional Medicare EE.
- Form 940 annual:
  - FUTA taxable wages from payroll FUTA ledger and annual wage cap.


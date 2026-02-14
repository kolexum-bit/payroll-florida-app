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
- Tax year config loaded from `data/tax/{year}/rates.json`.
- Source metadata stored in tax file (`source` key).
- FIT uses simplified profile derived from Pub 15-T style inputs (filing status + W-4 fields).

## Rounding
- Monetary values rounded to 2 decimals after each computed line item.

## Year versioning
- Calculations load year-specific rates by payroll year.
- Missing tax file is an error and should be handled by supplying that year config.

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


## Current limitation (documented)
- Payroll rows are still stored as monthly records (`year` + `month`).
- For non-monthly employees, the UI now accepts pay date and derives year/month, and FIT is computed using employee `pay_frequency` periods-per-year.
- This is an incremental step; full native weekly/biweekly period storage is not yet implemented.

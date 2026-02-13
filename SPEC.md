# Florida Payroll App Specification

## 1) Assumptions
- Payroll frequency is **monthly** (one payroll per employee per month).
- One company in the local app database for small-business usage.
- Employee payroll uses regular monthly gross wages input per run.
- Tax year is selected per payroll run and drives parameter loading from `/data/tax/{year}`.
- IRS Pub 15-T percentage method is used for FIT with annualized wages and W-4 adjustments.

## 2) Sources
- **IRS Publication 15-T** (withholding methods; year-versioned tables and logic inputs).
- **IRS / SSA FICA guidance** for Social Security and Medicare rates/wage limits.
- **IRS Form 941 instructions** for quarterly federal return mapping.
- **IRS Form 940 instructions** for annual FUTA mapping.
- **Florida Department of Revenue RT-6 guidance** for reemployment tax summaries.

## 3) Tax Data Architecture
Tax configuration is externalized to:
- `/data/tax/{year}/federal.json`
- `/data/tax/{year}/florida.json`

`federal.json` includes:
- FIT percentage method brackets by filing status and Step-2 checkbox state.
- Standard deduction-style offsets used by the selected method.
- FICA and FUTA rates, wage bases, and thresholds.

`florida.json` includes:
- RT-6/SUTA wage base and default employer rate.

To add a new year:
1. Copy prior year folder to `/data/tax/{new_year}`.
2. Update tax parameter values and FIT bracket tables.
3. Set table metadata/version fields.
4. Run tests and validate sample payrolls.

## 4) Rounding Rules
- Currency intermediate values are rounded to cents (`ROUND_HALF_UP`) when persisted.
- FIT annual tax estimate is rounded to cents, then divided by 12 for monthly withholding and rounded to cents.
- FICA components are calculated at monthly level with cap-aware taxable wages and rounded to cents.
- Rounding events are recorded in `calculation_trace`.

## 5) Payroll Ledger and Rollups
Each monthly payroll record stores:
- gross wages
- employee taxes (FIT, SS, Medicare, Additional Medicare)
- employer taxes (SS, Medicare, FUTA, FL SUTA)
- net pay
- detailed `calculation_trace`

### Quarterly rollups
- **Form 941 summary** aggregates monthly records in quarter:
  - wages, FIT withheld, taxable SS wages/tax, taxable Medicare wages/tax, additional medicare withheld.
- **Florida RT-6 summary** aggregates quarter:
  - gross wages, excess wages above annual base, taxable wages, tax due (taxable wages × employer rate).
  - employee-level wage detail is exportable as CSV.

### Annual rollups
- **Form 940 summary** aggregates annual FUTA:
  - FUTA taxable wages capped at annual wage base per employee.
  - FUTA contributions due = taxable FUTA wages × FUTA rate.

## 6) Auditability
`calculation_trace` JSON captures:
- tax year and data file versions
- W-4 inputs used
- selected FIT table name
- intermediate values and rounding steps
- cap calculations (SS/FUTA/RT-6)


# Payroll Florida App Spec

## Persistence Architecture
- SQLite with SQLAlchemy ORM.
- Single session factory per app instance.
- All routes consume the same `db_dependency` generator.

## Payroll Assumptions
- Monthly gross for salary employees equals `base_rate`.
- Monthly gross for hourly employees equals `base_rate * hours_worked`.
- Simplified withholding model used for deterministic app behavior:
  - Federal estimate: `max(0, ((gross*12 + other_income - deductions)*10%) - dependents) / 12 + extra_withholding`
  - Social Security: `6.2%`
  - Medicare: `1.45%`
- Rounded to 2 decimals with deterministic helper.
- Every payroll row stores `calculation_trace` JSON with inputs and step outputs.

## Reports
- RT-6 quarterly wages + contribution estimate.
- 941 quarterly wages, withholding, and FICA summary.
- 940 annual FUTA wages + tax estimate.

## Export
- CSV exports for each report.
- PDF exports rendered with an internal lightweight PDF writer.

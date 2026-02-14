# Florida Payroll App (Multi-Company)

Run:
1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. `uvicorn app.main:app --reload`

## Dev DB reset
- SQLite schema is created automatically on boot.
- Reset by deleting `payroll.db` then restarting app.

## Multi-company flow
- Create companies on `/company`.
- Choose **Current Company** in top nav.
- All Employees, Payroll, Pay Stub/W-2 and Reports are filtered to selected company.

## Tax data
- Year-versioned files are loaded from `data/tax/{year}/rates.json` using project-root paths.
- Required config files currently committed:
  - `data/tax/2025/rates.json`
  - `data/tax/2026/rates.json`
- Required keys in each year file:
  - `fit` (filing status profiles)
  - `social_security` (`employee_rate`, `employer_rate`, `wage_base`)
  - `medicare` (`employee_rate`, `employer_rate`, `additional_employee_rate`, `additional_threshold`)
  - `futa` (`employer_rate`, `wage_base`)
  - `suta` (`wage_base`)

### Adding a new tax year
1. Copy the latest year directory, e.g. `cp -R data/tax/2026 data/tax/2027`.
2. Update `rates.json` values and source metadata for the new year.
3. Run `pytest` to verify payroll calculations and reports still pass.
4. Commit the new year config before using that year in Monthly Payroll.

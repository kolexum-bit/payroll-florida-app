# Florida Payroll Web App

Simple monthly payroll app for a Florida company with:
- Federal income tax (FIT) withholding using year-versioned Pub 15-T style tables
- Form 941 quarterly summary
- Form 940 annual FUTA summary
- Florida RT-6 quarterly summary + CSV employee detail
- Pay stub PDF generation

## One-command run

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start app:
   ```bash
   ./run.sh
   ```
3. Open `http://localhost:8000`

## Guided UI
Top menu has 5 items:
1. Company
2. Employees
3. Monthly Payroll
4. Pay Stubs
5. Reports

## Tax data (no hardcoded tables)
- Tax files are in `data/tax/{year}/`.
- Start year: `2026` with:
  - `federal.json`
  - `florida.json`

To add a new year, copy folder `data/tax/2026` to `data/tax/<new_year>` and update values.

## Tests
Run:
```bash
pytest
```

## Notes
- Payroll records include `calculation_trace` JSON for auditability.
- SQLite database file is `payroll.db` in project root.

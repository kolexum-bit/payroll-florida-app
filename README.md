# Florida Payroll App (Multi-Company)

## Quick start
1. `python -m venv .venv`
2. `source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. `uvicorn app.main:app --reload`
5. Open `http://127.0.0.1:8000`

## Clean database reset
For a full clean run:
1. Stop the server.
2. Delete the SQLite file: `rm -f payroll.db`.
3. Start the server again with `uvicorn app.main:app --reload`.

The schema is recreated automatically at startup.

## End-to-end workflow
1. Create one or more companies at `/company`.
2. Select the active company in the top navigation (sets `current_company_id`).
3. Add employees at `/employees`.
4. Save monthly payroll rows at `/monthly-payroll`.
5. Generate pay stubs and W-2 PDFs at `/pay-stubs`.
6. Open `/reports` and switch between RT-6, Form 941, and Form 940.

## UX and calculation behavior
- FL SUTA rate accepts `%` or decimal input (`2.7`, `2.7%`, `0.027`) and is stored canonically as a decimal value.
- Company Setup supports optional PNG/JPG logo upload (max 2MB), preview, replace, and remove.
- Pay stub PDFs include sectioned layout (Earnings, Taxes & Deductions, Net Pay, YTD Summary) and YTD cumulative totals.
- YTD totals are computed per employee, company, and tax year for all records up to the selected pay period month.

## Tax data configuration
- Tax-year files are loaded from `data/tax/{year}/...` using a year-versioned contract.
- FIT withholding uses IRS Pub 15-T style percentage method tables in frequency-specific files (no in-code tax tables).
- FICA/FUTA/SUTA rates and wage bases are loaded per year from JSON.

### Tax data contract
- `data/tax/{year}/metadata.json` (`source`, `version`, `last_updated`)
- `data/tax/{year}/rates.json` (FICA/FUTA/SUTA + Medicare additional thresholds)
- `data/tax/{year}/fit/{pay_frequency}/percentage_method.json` where `pay_frequency` is one of:
  - `daily`, `weekly`, `biweekly`, `semimonthly`, `monthly`

### Annual update workflow
1. Scaffold a new year: `python tools/import_tax_year.py --year 2026 --from-year 2025`
2. Update:
   - `data/tax/2026/metadata.json` with official publication/source info and date.
   - `data/tax/2026/rates.json` for SSA/FICA/FUTA/SUTA changes.
   - `data/tax/2026/fit/*/percentage_method.json` for Pub 15-T tables by filing status.
3. Set company **Default Tax Year** to the new year in `/company`.
4. Run `pytest -q` before release.

## Tests
Run all tests:
- `pytest -q`

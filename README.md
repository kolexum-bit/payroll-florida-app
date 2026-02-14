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

## Tax data configuration
- Tax-year files are loaded from `data/tax/{year}/rates.json`.
- FIT withholding uses year-specific Pub 15-T style bracket data in each file (no in-code tax tables).
- FICA/FUTA/SUTA rates and wage bases are loaded per year from the same JSON.

### Required keys in each `rates.json`
- `fit` (`single`/`married` with `standard_deduction` and `brackets`)
- `social_security` (`employee_rate`, `employer_rate`, `wage_base`)
- `medicare` (`employee_rate`, `employer_rate`, `additional_employee_rate`, `additional_threshold`)
- `futa` (`employer_rate`, `wage_base`)
- `suta` (`wage_base`)

## Tests
Run all tests:
- `pytest -q`


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
- Year-versioned files under `data/tax/{year}/rates.json`.
- Add next year by copying and updating that file; no tax constants are hardcoded in routes.


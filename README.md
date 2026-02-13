# Payroll Florida App

A simple web app for Florida payroll workflows with 5 screens:
- Company
- Employees
- Monthly Payroll
- Pay Stubs
- Reports (RT-6, 941, 940)

## Run locally
1. Create a virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Start the app:
   ```bash
   uvicorn app.main:app --reload
   ```
4. Open `http://127.0.0.1:8000`.

## Run tests
```bash
pytest
```

## Notes
- Uses a single SQLAlchemy + SQLite setup and one DB dependency pattern.
- Monthly payroll stores `calculation_trace` JSON for auditability.
- Reports can be exported as CSV or PDF.

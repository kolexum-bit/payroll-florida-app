# payroll-florida-app
 (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
diff --git a/AGENTS.md b/AGENTS.md
new file mode 100644
index 0000000000000000000000000000000000000000..f83e0e8239a7262d24d48278c39d15224a188aa8
--- /dev/null
+++ b/AGENTS.md
@@ -0,0 +1,31 @@
+# AGENTS.md
+
+## Scope
+These instructions apply to the entire repository.
+
+## Product Rules
+- Build and maintain a Florida payroll web app focused on monthly payroll calculations and summaries.
+- UI must stay simple and guided for non-technical users.
+- Keep top navigation at **5 menu items max**: Company, Employees, Monthly Payroll, Pay Stubs, Reports.
+- Do not hardcode tax tables/rates in application logic. Store tax parameters in `/data/tax/{year}/...` and load from files.
+- FIT withholding must be computed using year-versioned Pub 15-T data files and W-4 inputs.
+- Every paycheck/payroll record must include an auditable `calculation_trace` JSON.
+
+## Engineering Rules
+- Use Python FastAPI + SQLite + server-rendered templates unless explicitly asked otherwise.
+- Keep code modular: `services/` for calculation logic, `reports/` for report builders, `templates/` for UI.
+- Any new tax year should be added by creating a new folder under `data/tax/{year}`.
+- Preserve deterministic rounding and include rounding steps in traces.
+
+## Testing Rules
+- Maintain unit tests for:
+  - W-4 scenario handling
+  - Social Security cap behavior
+  - Medicare + Additional Medicare threshold behavior
+  - FUTA cap behavior
+  - Florida RT-6/SUTA cap behavior
+- Tests must run locally with `pytest`.
+
+## Documentation Rules
+- Keep `SPEC.md` updated for assumptions, sources, rounding, and rollup logic.
+- Keep `README.md` non-technical and step-by-step for local run.
 
EOF
)

# Troubleshooting and Root Cause Notes

## What broke previously
The prior "Company" fix unintentionally narrowed the app to only one module:
- Navigation links for Employees, Monthly Payroll, Pay Stubs, and Reports were placeholders (`#`).
- Only Company routes and template existed, so other screens were effectively disabled.
- README was overwritten with a patch artifact instead of setup instructions.

## Root cause
- Incomplete refactor that merged only Company CRUD while removing/omitting the rest of the module routes/templates.
- Missing end-to-end tests for non-Company flows allowed regressions to ship.

## What is fixed now
- Restored full app navigation and implemented all required modules with server-rendered templates.
- Unified DB architecture and dependency pattern across all routes.
- Added CRUD + persistence tests for Company, Employees, and Monthly Payroll.
- Added report rollup and PDF generation smoke coverage.

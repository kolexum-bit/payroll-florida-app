#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

PAY_FREQUENCIES = ["daily", "weekly", "biweekly", "semimonthly", "monthly"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a new tax-year scaffold under data/tax/{year}/")
    parser.add_argument("--year", type=int, required=True, help="Tax year to scaffold")
    parser.add_argument("--from-year", type=int, default=None, help="Optional source year to copy from")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    data_root = repo_root / "data" / "tax"
    target = data_root / str(args.year)
    if target.exists():
        raise SystemExit(f"Target year already exists: {target}")

    if args.from_year is not None:
        source = data_root / str(args.from_year)
        if not source.exists():
            raise SystemExit(f"Source year does not exist: {source}")
        target.mkdir(parents=True)
        (target / "rates.json").write_text((source / "rates.json").read_text())
        for freq in PAY_FREQUENCIES:
            dst_dir = target / "fit" / freq
            dst_dir.mkdir(parents=True, exist_ok=True)
            src_file = source / "fit" / freq / "percentage_method.json"
            (dst_dir / "percentage_method.json").write_text(src_file.read_text())
        metadata = json.loads((source / "metadata.json").read_text())
        metadata["version"] = f"{args.year}.1"
        metadata["last_updated"] = f"{args.year}-01-01"
        (target / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    else:
        target.mkdir(parents=True)
        (target / "rates.json").write_text(json.dumps({
            "social_security": {"employee_rate": 0.062, "employer_rate": 0.062, "wage_base": 0},
            "medicare": {
                "employee_rate": 0.0145,
                "employer_rate": 0.0145,
                "additional_employee_rate": 0.009,
                "additional_threshold": {
                    "single_or_married_filing_separately": 200000,
                    "married_filing_jointly": 250000,
                    "head_of_household": 200000,
                },
            },
            "futa": {"employer_rate": 0.006, "wage_base": 7000},
            "suta": {"wage_base": 7000},
        }, indent=2) + "\n")
        template_fit = {
            "single_or_married_filing_separately": {"standard_deduction": 0, "brackets": [{"up_to": None, "rate": 0.0}]},
            "married_filing_jointly": {"standard_deduction": 0, "brackets": [{"up_to": None, "rate": 0.0}]},
            "head_of_household": {"standard_deduction": 0, "brackets": [{"up_to": None, "rate": 0.0}]},
        }
        for freq in PAY_FREQUENCIES:
            dst_dir = target / "fit" / freq
            dst_dir.mkdir(parents=True, exist_ok=True)
            (dst_dir / "percentage_method.json").write_text(json.dumps(template_fit, indent=2) + "\n")
        (target / "metadata.json").write_text(json.dumps({
            "source": "Fill with IRS Pub 15-T and SSA/FICA sources",
            "version": f"{args.year}.1",
            "last_updated": f"{args.year}-01-01",
            "notes": "Update rates.json and fit/*/percentage_method.json before using in production.",
        }, indent=2) + "\n")

    print(f"Created {target}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.services import payroll


@dataclass
class ValidationResult:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def add_error(self, message: str) -> None:
        self.ok = False
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def merge(self, other: "ValidationResult") -> None:
        if not other.ok:
            self.ok = False
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        if other.details:
            self.details.update(other.details)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_json(path: Path, result: ValidationResult, *, label: str) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        result.add_error(f"Missing required file for tax year validation: {path.as_posix()}")
    except json.JSONDecodeError as exc:
        result.add_error(f"Invalid JSON in {label}: {exc}")
    return None


def validate_tax_year_data(year: int) -> ValidationResult:
    result = ValidationResult()
    year_dir = payroll.DATA_DIR / str(year)
    metadata_path = year_dir / "metadata.json"
    rates_path = year_dir / "rates.json"
    validation_path = year_dir / "validation.json"

    metadata = _read_json(metadata_path, result, label="metadata.json")
    _read_json(rates_path, result, label="rates.json")
    validation = _read_json(validation_path, result, label="validation.json")

    required_meta_fields = ["source", "version", "last_updated", "notes"]
    if metadata is not None:
        missing_fields = [field for field in required_meta_fields if field not in metadata]
        if missing_fields:
            result.add_error(f"metadata.json is missing required fields: {', '.join(missing_fields)}")

        if "tax_year" not in metadata:
            result.add_warning("metadata.json is missing required field 'tax_year'.")
            result.ok = False
        elif metadata["tax_year"] != year:
            result.add_error(f"metadata.json tax_year mismatch: expected {year}, found {metadata['tax_year']}")

        method = metadata.get("method")
        notes = str(metadata.get("notes", "")).lower()
        if method not in {"percentage", "wage_bracket"}:
            result.add_error("metadata.json method must be one of: percentage, wage_bracket")
        elif "percentage" in notes and method != "percentage":
            result.add_error("metadata.json method must be 'percentage' when notes indicate percentage tables")

    if validation is not None:
        if validation.get("tax_year") != year:
            result.add_error(f"validation.json tax_year mismatch: expected {year}, found {validation.get('tax_year')}")

    for frequency in payroll.PERIODS_PER_YEAR:
        fit_path = year_dir / "fit" / frequency / "percentage_method.json"
        if not fit_path.exists():
            result.add_error(
                f"Missing FIT percentage tables for {year} at fit/{frequency}/percentage_method.json"
            )

    result.details["year"] = year
    result.details["checked_files"] = [
        metadata_path.as_posix(),
        rates_path.as_posix(),
        validation_path.as_posix(),
    ]
    return result


def validate_fit_tables(year: int, pay_frequency: str) -> ValidationResult:
    result = validate_tax_year_data(year)
    year_dir = payroll.DATA_DIR / str(year)
    fit_path = year_dir / "fit" / pay_frequency / "percentage_method.json"
    validation_path = year_dir / "validation.json"

    if pay_frequency not in payroll.PERIODS_PER_YEAR:
        result.add_error(f"Unsupported pay frequency '{pay_frequency}' for FIT validation")
        return result

    fit = _read_json(fit_path, result, label="percentage_method.json")
    validation = _read_json(validation_path, result, label="validation.json")
    if fit is None or validation is None:
        return result

    expected_sd = validation.get("standard_deduction", {})
    expected_brackets = validation.get("bracket_thresholds", {})
    details: dict[str, Any] = {"pay_frequency": pay_frequency, "filing_status": {}}

    for status in payroll.FILING_STATUS_KEYS:
        if status not in fit:
            result.add_error(f"Missing FIT table for filing status '{status}' ({year}, {pay_frequency})")
            continue
        status_table = fit[status]
        status_details: dict[str, Any] = {}

        expected_status_sd = expected_sd.get(status)
        actual_sd = status_table.get("standard_deduction")
        status_details["standard_deduction"] = {"expected": expected_status_sd, "actual": actual_sd}
        if expected_status_sd is not None and actual_sd != expected_status_sd:
            result.add_error(
                f"Tax tables appear to be for a different year (expected standard deduction {expected_status_sd}, found {actual_sd}) for {status}."
            )

        expected_thresholds = expected_brackets.get(status, [])
        brackets = status_table.get("brackets", [])
        actual_thresholds = [item.get("up_to") for item in brackets if item.get("up_to") is not None]
        checks = min(3, len(expected_thresholds), len(actual_thresholds))
        compared = []
        for idx in range(checks):
            compared.append({"index": idx, "expected": expected_thresholds[idx], "actual": actual_thresholds[idx]})
            if expected_thresholds[idx] != actual_thresholds[idx]:
                result.add_error(
                    f"Tax tables appear to be for a different year (expected bracket threshold {expected_thresholds[idx]}, found {actual_thresholds[idx]}) for {status} bracket {idx + 1}."
                )
        status_details["bracket_threshold_checks"] = compared
        details["filing_status"][status] = status_details

    result.details["fit_validation"] = details
    return result

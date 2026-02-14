import json
import shutil
from pathlib import Path

from app.services import tax_validation


REPO_ROOT = Path(__file__).resolve().parents[1]


def _copy_year(tmp_path: Path, year: int) -> Path:
    src = REPO_ROOT / "data" / "tax" / str(year)
    dst_root = tmp_path / "data" / "tax"
    dst = dst_root / str(year)
    shutil.copytree(src, dst)
    return dst_root


def test_missing_metadata_json_fails(tmp_path, monkeypatch):
    data_dir = _copy_year(tmp_path, 2025)
    (data_dir / "2025" / "metadata.json").unlink()
    monkeypatch.setattr("app.services.payroll.DATA_DIR", data_dir)

    result = tax_validation.validate_tax_year_data(2025)

    assert result.ok is False
    assert any("metadata.json" in err for err in result.errors)


def test_metadata_tax_year_mismatch_fails(tmp_path, monkeypatch):
    data_dir = _copy_year(tmp_path, 2025)
    metadata_path = data_dir / "2025" / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["tax_year"] = 2026
    metadata_path.write_text(json.dumps(metadata))
    monkeypatch.setattr("app.services.payroll.DATA_DIR", data_dir)

    result = tax_validation.validate_tax_year_data(2025)

    assert result.ok is False
    assert any("tax_year mismatch" in err for err in result.errors)


def test_validation_standard_deduction_mismatch_fails(tmp_path, monkeypatch):
    data_dir = _copy_year(tmp_path, 2025)
    val_path = data_dir / "2025" / "validation.json"
    validation = json.loads(val_path.read_text())
    validation["standard_deduction"]["single_or_married_filing_separately"] += 1
    val_path.write_text(json.dumps(validation))
    monkeypatch.setattr("app.services.payroll.DATA_DIR", data_dir)

    result = tax_validation.validate_fit_tables(2025, "monthly")

    assert result.ok is False
    assert any("expected standard deduction" in err for err in result.errors)


def test_correct_folder_and_files_pass(tmp_path, monkeypatch):
    data_dir = _copy_year(tmp_path, 2025)
    monkeypatch.setattr("app.services.payroll.DATA_DIR", data_dir)

    result = tax_validation.validate_fit_tables(2025, "monthly")

    assert result.ok is True
    assert result.errors == []

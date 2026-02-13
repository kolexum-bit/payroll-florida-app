import json
from pathlib import Path

BASE_TAX_DIR = Path(__file__).resolve().parents[2] / "data" / "tax"


def load_tax_data(year: int) -> dict:
    year_dir = BASE_TAX_DIR / str(year)
    federal_path = year_dir / "federal.json"
    florida_path = year_dir / "florida.json"

    if not federal_path.exists() or not florida_path.exists():
        raise FileNotFoundError(f"Missing tax data files for year {year} in {year_dir}")

    with federal_path.open() as f:
        federal = json.load(f)
    with florida_path.open() as f:
        florida = json.load(f)

    return {"federal": federal, "florida": florida}

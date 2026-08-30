import json

from scripts.check_readiness import _catalog_check, _public_set_check
from scripts.download_catalog import validate_catalog


def _write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_catalog_check_explains_when_catalog_is_missing(tmp_path):
    check = _catalog_check(tmp_path / "missing.jsonl")
    assert check.status == "FAIL"
    assert "download_catalog.py" in check.detail


def test_catalog_validator_counts_unique_products(tmp_path):
    path = tmp_path / "catalog.jsonl"
    _write_jsonl(
        path,
        [
            {"parent_asin": "A", "title": "One", "categories": ["Shoes"]},
            {"parent_asin": "B", "title": "Two", "categories": ["Clothing"]},
        ],
    )
    count, asins = validate_catalog(path)
    assert count == 2
    assert asins == {"A", "B"}


def test_public_set_check_rejects_wrong_scenario_mix(tmp_path):
    path = tmp_path / "public.jsonl"
    _write_jsonl(path, [{"scenario_type": "buying"}])
    check = _public_set_check(path)
    assert check.status == "FAIL"

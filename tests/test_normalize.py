import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.normalize import normalize, normalize_pollco, validate  # noqa: E402


def test_normalize_pollco_age_merge():
    raw = pd.DataFrame(
        {
            "age": ["18-24", "25-34", "65+"],
            "gender": ["Male", "Female", "Male"],
            "candidate": ["A", "B", "A"],
            "count": [10, 20, 30],
        }
    )
    out = normalize_pollco(raw)
    assert list(out["age_bin"]) == ["18-29", "18-29", "65+"]
    assert list(out["gender"]) == ["male", "female", "male"]
    assert out["n"].sum() == 60


def test_normalize_end_to_end():
    raw = load_sample()
    out = normalize(raw, "pollco")
    assert set(out["age_bin"]).issubset({"18-29", "30-44", "45-64", "65+"})


def test_validate_rejects_bad_age():
    bad = pd.DataFrame({"age_bin": ["99+"], "n": [1]})
    with pytest.raises(ValueError):
        validate(bad)


def load_sample() -> pd.DataFrame:
    path = ROOT / "data" / "raw" / "demo_pollco" / "pollco.csv"
    return pd.read_csv(path)

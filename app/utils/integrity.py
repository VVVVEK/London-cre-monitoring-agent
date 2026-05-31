"""Data integrity helpers shared across skills."""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd


def clean_optional_str(value: Any) -> Optional[str]:
    """Convert pandas NaN / empty values to None for pydantic optional str fields."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text

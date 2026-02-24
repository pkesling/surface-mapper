from __future__ import annotations

from datetime import date


def season_label(observed_at: date) -> str:
    month = observed_at.month
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    return "fall"


__all__ = ["season_label"]

"""surface_mapper.render.scales module."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _normalize(values: pd.Series, ref: pd.Series | None = None) -> pd.Series:
    """Internal helper for normalize."""
    basis = ref if ref is not None else values
    basis = basis.astype(float)
    min_v = float(values.min())
    max_v = float(values.max())
    if ref is not None:
        min_v = float(basis.min())
        max_v = float(basis.max())
    if max_v == min_v:
        return pd.Series(np.zeros(len(values), dtype=float), index=values.index)
    return (values - min_v) / (max_v - min_v)


def scale_values(values: pd.Series, scale: str, gamma: float, reference: pd.Series | None = None) -> pd.Series:
    """Scale values."""
    vals = values.astype(float)
    if vals.empty:
        return vals
    if scale == "linear":
        return vals
    if scale == "log":
        transformed = np.log1p(np.clip(vals, a_min=0.0, a_max=None))
        transformed_series = pd.Series(transformed, index=vals.index)
        ref_transformed = None
        if reference is not None:
            ref_transformed = pd.Series(np.log1p(np.clip(reference.astype(float), a_min=0.0, a_max=None)))
        return _normalize(transformed_series, ref=ref_transformed)
    if scale == "gamma":
        normalized = _normalize(vals, ref=reference)
        return normalized.pow(gamma)
    raise ValueError(f"Unsupported scale: {scale}")

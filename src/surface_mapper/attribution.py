"""surface_mapper.attribution module."""

from __future__ import annotations

E_BIRD_BASIC_DATASET_CITATION = (
    "eBird Basic Dataset. Version: EBD_relJan-2026. Cornell Lab of Ornithology, Ithaca, New York. Jan 2026."
)


def dataset_attribution(dataset: str | None) -> str | None:
    """Dataset attribution."""
    if dataset is None:
        return None
    normalized = dataset.strip().lower()
    if normalized in {"ebird-ebd", "ebird", "ebd"}:
        return E_BIRD_BASIC_DATASET_CITATION
    return None


__all__ = ["E_BIRD_BASIC_DATASET_CITATION", "dataset_attribution"]

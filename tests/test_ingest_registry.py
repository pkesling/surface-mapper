from surface_mapper.ingest.registry import list_adapters, resolve_adapter


def test_builtin_ebird_adapter_registered() -> None:
    adapters = set(list_adapters())
    assert "ebird-ebd" in adapters
    assert "ebird" in adapters
    assert "ebd" in adapters


def test_ebird_aliases_resolve_to_same_adapter() -> None:
    canonical = resolve_adapter("ebird-ebd")
    assert resolve_adapter("ebird") is canonical
    assert resolve_adapter("ebd") is canonical

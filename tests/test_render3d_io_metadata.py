"""Tests for test_render3d_io_metadata."""

import json
from pathlib import Path

from surface_mapper import __version__
from surface_mapper.render3d.io import write_export_metadata


def _build_min_glb(payload: dict[str, object]) -> bytes:
    """Internal helper for build min glb."""
    json_chunk = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    json_pad = (-len(json_chunk)) % 4
    if json_pad:
        json_chunk += b" " * json_pad

    chunks = bytearray()
    chunks.extend(len(json_chunk).to_bytes(4, "little", signed=False))
    chunks.extend(b"JSON")
    chunks.extend(json_chunk)

    total_len = 12 + len(chunks)
    header = bytearray()
    header.extend(b"glTF")
    header.extend((2).to_bytes(4, "little", signed=False))
    header.extend(total_len.to_bytes(4, "little", signed=False))
    return bytes(header + chunks)


def _read_glb_json(path: Path) -> dict[str, object]:
    """Internal helper for read glb json."""
    blob = path.read_bytes()
    assert blob[:4] == b"glTF"
    chunk_len = int.from_bytes(blob[12:16], "little", signed=False)
    chunk_type = blob[16:20]
    assert chunk_type == b"JSON"
    chunk = blob[20 : 20 + chunk_len]
    return json.loads(chunk.decode("utf-8").rstrip(" \t\r\n\0"))


def test_write_export_metadata_embeds_metadata_into_glb(tmp_path: Path) -> None:
    """Test write export metadata embeds metadata into glb."""
    out_path = tmp_path / "mesh.glb"
    out_path.write_bytes(_build_min_glb({"asset": {"version": "2.0"}}))

    metadata = {"surface_mapper_version": __version__, "metric": "attention", "resolution": 6}
    write_export_metadata(out_path, metadata)

    payload = _read_glb_json(out_path)
    assert payload["asset"]["extras"]["surface_mapper"]["metric"] == "attention"
    assert payload["asset"]["extras"]["surface_mapper"]["resolution"] == 6
    assert Path(f"{out_path}.meta.json").exists()

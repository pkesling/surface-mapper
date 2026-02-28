"""surface_mapper.render3d.io module."""

from __future__ import annotations

import json
from pathlib import Path

_GLB_MAGIC = b"glTF"
_GLB_JSON_CHUNK_TYPE = b"JSON"


def _require_pyvista():
    """Internal helper for require pyvista."""
    try:
        import pyvista as pv
    except ImportError as exc:
        raise ImportError(
            "render 3d requires optional dependency 'pyvista'. Install with: pip install 'surface-mapper[render3d]'"
        ) from exc
    return pv


def _save_with_gltf_writer(mesh, out_path: Path) -> None:
    """Internal helper for save with gltf writer."""
    pv = _require_pyvista()
    plotter = pv.Plotter(off_screen=True)
    try:
        scalars = "value" if ("value" in mesh.point_data or "value" in mesh.cell_data) else None
        plotter.add_mesh(mesh, scalars=scalars)
        plotter.export_gltf(str(out_path))
    finally:
        plotter.close()


def export_mesh(mesh, out_path: str, export_format: str) -> Path:
    """Export mesh."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    ext = export_format.lower()
    if ext not in {"glb", "obj", "stl"}:
        raise ValueError("Unsupported export format. Use one of: glb, obj, stl.")

    if out.suffix.lower() != f".{ext}":
        out = out.with_suffix(f".{ext}")

    try:
        mesh.save(str(out))
    except Exception:
        if ext == "glb":
            _save_with_gltf_writer(mesh, out)
        else:
            raise

    return out


def _embed_glb_metadata(out_path: Path, metadata: dict[str, object]) -> None:
    """Internal helper for embed glb metadata."""
    blob = out_path.read_bytes()
    if len(blob) < 20 or blob[:4] != _GLB_MAGIC:
        return

    version = int.from_bytes(blob[4:8], "little", signed=False)
    if version != 2:
        return

    chunks: list[tuple[bytes, bytes]] = []
    offset = 12
    while offset + 8 <= len(blob):
        chunk_length = int.from_bytes(blob[offset : offset + 4], "little", signed=False)
        chunk_type = blob[offset + 4 : offset + 8]
        chunk_start = offset + 8
        chunk_end = chunk_start + chunk_length
        if chunk_end > len(blob):
            return
        chunks.append((chunk_type, blob[chunk_start:chunk_end]))
        offset = chunk_end
    if not chunks:
        return

    json_idx = next((i for i, (chunk_type, _) in enumerate(chunks) if chunk_type == _GLB_JSON_CHUNK_TYPE), None)
    if json_idx is None:
        return

    json_chunk = chunks[json_idx][1]
    json_payload = json.loads(json_chunk.decode("utf-8").rstrip(" \t\r\n\0"))
    asset = json_payload.get("asset")
    if not isinstance(asset, dict):
        asset = {}
    extras = asset.get("extras")
    if not isinstance(extras, dict):
        extras = {}
    extras["surface_mapper"] = metadata
    asset["extras"] = extras
    json_payload["asset"] = asset

    encoded = json.dumps(json_payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    padding = (-len(encoded)) % 4
    if padding:
        encoded = encoded + (b" " * padding)
    chunks[json_idx] = (_GLB_JSON_CHUNK_TYPE, encoded)

    rebuilt = bytearray()
    rebuilt.extend(_GLB_MAGIC)
    rebuilt.extend(version.to_bytes(4, "little", signed=False))
    rebuilt.extend((0).to_bytes(4, "little", signed=False))
    for chunk_type, chunk_data in chunks:
        rebuilt.extend(len(chunk_data).to_bytes(4, "little", signed=False))
        rebuilt.extend(chunk_type)
        rebuilt.extend(chunk_data)
    rebuilt[8:12] = len(rebuilt).to_bytes(4, "little", signed=False)
    out_path.write_bytes(bytes(rebuilt))


def write_export_metadata(out_path: Path, metadata: dict[str, object]) -> Path:
    """Write export metadata."""
    meta_path = Path(f"{out_path}.meta.json")
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    if out_path.suffix.lower() == ".glb":
        try:
            _embed_glb_metadata(out_path, metadata)
        except Exception:
            pass

    return meta_path

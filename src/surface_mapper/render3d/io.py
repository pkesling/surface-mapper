from __future__ import annotations

import json
from pathlib import Path


def _require_pyvista():
    try:
        import pyvista as pv
    except ImportError as exc:
        raise ImportError(
            "render 3d requires optional dependency 'pyvista'. Install with: pip install 'surface-mapper[render3d]'"
        ) from exc
    return pv


def _save_with_gltf_writer(mesh, out_path: Path) -> None:
    pv = _require_pyvista()
    plotter = pv.Plotter(off_screen=True)
    try:
        scalars = "value" if ("value" in mesh.point_data or "value" in mesh.cell_data) else None
        plotter.add_mesh(mesh, scalars=scalars)
        plotter.export_gltf(str(out_path))
    finally:
        plotter.close()


def export_mesh(mesh, out_path: str, export_format: str) -> Path:
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


def write_export_metadata(out_path: Path, metadata: dict[str, object]) -> Path:
    meta_path = Path(f"{out_path}.meta.json")
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return meta_path

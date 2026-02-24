from __future__ import annotations

from pathlib import Path
from typing import Any


def _require_pyvista():
    try:
        import pyvista as pv
    except ImportError as exc:
        raise ImportError(
            "render 3d preview requires optional dependency 'pyvista'. Install with: pip install 'surface-mapper[render3d]'"
        ) from exc
    return pv


def _set_north_up_camera(plotter, bounds: tuple[float, float, float, float, float, float], base_z: float) -> None:
    min_x, max_x, min_y, max_y, _min_z, max_z = bounds
    cx = 0.5 * (min_x + max_x)
    cy = 0.5 * (min_y + max_y)
    span_x = max(max_x - min_x, 1e-6)
    span_y = max(max_y - min_y, 1e-6)
    span = max(span_x, span_y)
    camera_height = max(max_z - base_z, 1.0) + (span * 2.0)

    camera = plotter.camera
    camera.SetFocalPoint(cx, cy, base_z)
    camera.SetPosition(cx, cy, base_z + camera_height)
    camera.SetViewUp(0.0, 1.0, 0.0)
    camera.SetParallelProjection(True)
    camera.SetParallelScale(span * 0.55)


def _combine_bounds(*meshes):
    mins = [float("inf"), float("inf"), float("inf")]
    maxs = [float("-inf"), float("-inf"), float("-inf")]
    found = False
    for mesh in meshes:
        if mesh is None:
            continue
        b = mesh.bounds
        mins[0] = min(mins[0], float(b[0]))
        maxs[0] = max(maxs[0], float(b[1]))
        mins[1] = min(mins[1], float(b[2]))
        maxs[1] = max(maxs[1], float(b[3]))
        mins[2] = min(mins[2], float(b[4]))
        maxs[2] = max(maxs[2], float(b[5]))
        found = True
    if not found:
        return None
    return (mins[0], maxs[0], mins[1], maxs[1], mins[2], maxs[2])


def render_preview(
    hex_mesh,
    preview_path: str,
    cmap: str,
    style: str,
    base_z: float,
    neighbors_fill: str,
    neighbors_alpha: float,
    water_fill: str,
    water_alpha: float,
    north_up: bool = True,
    neighbors_mesh: Any | None = None,
    water_mesh: Any | None = None,
    region_bounds: tuple[float, float, float, float] | None = None,
    camera_preset: str | None = None,
) -> Path:
    pv = _require_pyvista()
    out = Path(preview_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    background = "#ffffff" if style == "classic" else "#090d14"
    plotter = pv.Plotter(off_screen=True, window_size=(1400, 1000))
    try:
        scalars = "value" if ("value" in hex_mesh.point_data or "value" in hex_mesh.cell_data) else None
        plotter.set_background(background)
        if neighbors_mesh is not None:
            plotter.add_mesh(
                neighbors_mesh,
                color=neighbors_fill,
                opacity=neighbors_alpha,
                smooth_shading=False,
            )
        if water_mesh is not None:
            plotter.add_mesh(
                water_mesh,
                color=water_fill,
                opacity=water_alpha,
                smooth_shading=False,
            )
        plotter.add_mesh(
            hex_mesh,
            scalars=scalars,
            cmap=cmap,
            smooth_shading=True,
            specular=0.2,
            show_scalar_bar=True,
        )

        if north_up:
            if region_bounds is not None:
                min_x, min_y, max_x, max_y = region_bounds
                merged_bounds = _combine_bounds(hex_mesh, neighbors_mesh, water_mesh)
                if merged_bounds is None:
                    merged_bounds = hex_mesh.bounds
                z_bounds = merged_bounds[4], merged_bounds[5]
                camera_bounds = (min_x, max_x, min_y, max_y, z_bounds[0], z_bounds[1])
            else:
                camera_bounds = _combine_bounds(hex_mesh, neighbors_mesh, water_mesh) or hex_mesh.bounds
            _set_north_up_camera(plotter, camera_bounds, base_z=base_z)
        elif camera_preset:
            # Camera presets are reserved for a future pass. Keep parameter plumbed.
            _ = camera_preset
        plotter.show(screenshot=str(out), auto_close=False)
    finally:
        plotter.close()

    return out

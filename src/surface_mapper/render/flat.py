"""surface_mapper.render.flat module."""

from __future__ import annotations

import json
import logging
from datetime import datetime, UTC
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
from shapely.affinity import rotate
from shapely.geometry import box
from shapely.ops import unary_union

from surface_mapper.render.base import Renderer
from surface_mapper.render.boundaries import get_neighbor_boundary
from surface_mapper.render.contracts import RenderArtifacts, RenderSpec, SurfaceQuery
from surface_mapper.render.h3_geometry import h3_df_to_gdf
from surface_mapper.render.layers import load_layer, reproject_to, select_polygon
from surface_mapper.render.load_surface import load_surface
from surface_mapper.render.scales import scale_values
from surface_mapper.render.styles import get_cmap
from surface_mapper import __version__
from surface_mapper.attribution import dataset_attribution

logger = logging.getLogger("surface_mapper.render.flat")

_SEASONS = ["winter", "spring", "summer", "fall"]


def stats_sidecar_path(out_path: str) -> Path:
    """Stats sidecar path."""
    output = Path(out_path)
    return output.with_name(f"{output.stem}.stats.json")


def _resolve_projection(projection: str) -> str | None:
    """Internal helper for resolve projection."""
    if projection == "auto":
        return "EPSG:5070"
    if projection == "epsg:5070":
        return "EPSG:5070"
    if projection == "epsg:3857":
        return "EPSG:3857"
    if projection == "none":
        return None
    raise ValueError(f"Unsupported projection: {projection}")


def _load_query_df(query: SurfaceQuery, time_slice: str | None) -> pd.DataFrame:
    """Internal helper for load query df."""
    q = SurfaceQuery(
        db_path=query.db_path,
        table=query.table,
        dataset=query.dataset,
        metric=query.metric,
        grid=query.grid,
        resolution=query.resolution,
        time_slice=time_slice,
        min_support=query.min_support,
    )
    return load_surface(q)


def _make_boundary(spec: RenderSpec, gdf: pd.DataFrame, projection: str | None):
    """Internal helper for make boundary."""
    if spec.region_file is not None:
        region_layer = load_layer(spec.region_file)
        boundary_gdf = select_polygon(region_layer, spec.region_key, spec.region_value)
        return reproject_to(boundary_gdf, projection)
    raise ValueError(
        "Missing --region-file. SurfaceMapper renders using user-provided geodata fidelity. "
        "Run: surface-mapper geodata fetch-defaults, then pass --region-file (or set it in config.json)."
    )


def _make_neighbors(spec: RenderSpec, boundary_gdf, projection: str | None):
    """Internal helper for make neighbors."""
    if not spec.neighbors:
        return None
    if spec.neighbors_file is not None:
        return reproject_to(load_layer(spec.neighbors_file), projection)
    logger.warning("--neighbors enabled but no --neighbors-file provided; using fallback frame")
    return get_neighbor_boundary(boundary_gdf)


def _make_water(spec: RenderSpec, projection: str | None):
    """Internal helper for make water."""
    if not spec.mask_water:
        return None
    if spec.water_file is None:
        raise ValueError("--mask-water was set but no --water-file was provided")
    return reproject_to(load_layer(spec.water_file), projection)


def _clip_and_mask(gdf, boundary_gdf, water_gdf):
    """Internal helper for clip and mask."""
    clipped = gdf.clip(boundary_gdf)
    if water_gdf is not None and not water_gdf.empty:
        water_mask = water_gdf.clip(boundary_gdf)
        if not water_mask.empty:
            water_mask = water_mask.copy()
            water_mask["geometry"] = water_mask.geometry.apply(
                lambda geom: geom.buffer(0) if geom is not None and not geom.is_valid else geom
            )
            water_union = unary_union(water_mask.geometry)
        else:
            water_union = None
        if water_union is not None:
            clipped = clipped.copy()
            clipped["geometry"] = clipped.geometry.apply(lambda geom: geom.difference(water_union))
            clipped = clipped[~clipped.geometry.is_empty]
    return clipped


def _clip_to_axes(gdf, ax):
    """Internal helper for clip to axes."""
    if gdf is None or gdf.empty:
        return gdf
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    bbox = box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    return gdf.clip(bbox)


def _rotation_origin(boundary_gdf):
    """Internal helper for rotation origin."""
    if hasattr(boundary_gdf.geometry, "union_all"):
        return boundary_gdf.geometry.union_all().centroid
    return boundary_gdf.unary_union.centroid


def _rotate_gdf(gdf, rotate_deg: float, origin):
    """Internal helper for rotate gdf."""
    if gdf is None or gdf.empty or rotate_deg == 0.0:
        return gdf
    gdf = gdf.copy()
    gdf["geometry"] = gdf.geometry.apply(lambda geom: rotate(geom, rotate_deg, origin=origin))
    return gdf


def _set_framing(ax, boundary_gdf, pad_pct: float) -> None:
    """Internal helper for set framing."""
    minx, miny, maxx, maxy = boundary_gdf.total_bounds
    dx = max(maxx - minx, 1e-9)
    dy = max(maxy - miny, 1e-9)
    dxpad = dx * pad_pct
    dypad = dy * pad_pct
    ax.set_xlim(minx - dxpad, maxx + dxpad)
    ax.set_ylim(miny - dypad, maxy + dypad)


def _draw_common_layers(ax, spec: RenderSpec, boundary_gdf, neighbors_gdf, water_gdf) -> None:
    """Internal helper for draw common layers."""
    if water_gdf is not None and not water_gdf.empty:
        ax.set_facecolor(spec.water_fill)
    else:
        ax.set_facecolor(spec.background_color)

    if neighbors_gdf is not None and not neighbors_gdf.empty:
        neighbors_gdf.plot(ax=ax, color=spec.neighbors_fill, edgecolor="none", alpha=spec.neighbors_alpha)

    if water_gdf is not None and not water_gdf.empty:
        water_gdf.plot(ax=ax, color=spec.water_fill, edgecolor="none", alpha=spec.water_alpha)


def _draw_outline(ax, spec: RenderSpec, boundary_gdf) -> None:
    """Internal helper for draw outline."""
    boundary_gdf.boundary.plot(
        ax=ax,
        color=spec.outline_color,
        linewidth=spec.outline_width,
        alpha=0.95,
        zorder=2,
    )


def _build_png_metadata(query: SurfaceQuery, spec: RenderSpec, rowcount: int) -> dict[str, str]:
    """Internal helper for build png metadata."""
    attribution = dataset_attribution(query.dataset)
    payload = {
        "surface_mapper_version": __version__,
        "renderer": "flat",
        "created_utc": datetime.now(UTC).isoformat(),
        "query": {
            "db_path": query.db_path,
            "table": query.table,
            "dataset": query.dataset,
            "metric": query.metric,
            "grid": query.grid,
            "resolution": query.resolution,
            "time_slice": query.time_slice,
            "min_support": query.min_support,
        },
        "spec": {
            "style": spec.style,
            "scale": spec.scale,
            "gamma": spec.gamma,
            "width_px": spec.width_px,
            "height_px": spec.height_px,
            "dpi": spec.dpi,
            "projection": spec.projection,
            "layout_mode": spec.layout_mode,
            "preset_name": spec.preset_name,
            "rotate_deg": spec.rotate_deg,
            "region_file": spec.region_file,
            "neighbors_file": spec.neighbors_file,
            "water_file": spec.water_file,
            "mask_water": spec.mask_water,
            "out_path": spec.out_path,
        },
        "rowcount": rowcount,
    }
    if attribution is not None:
        payload["data_attribution"] = attribution
    return {
        "Software": f"surface-mapper {__version__}",
        "surface_mapper": json.dumps(payload, separators=(",", ":"), sort_keys=True),
    }


class FlatRenderer(Renderer):
    """FlatRenderer."""
    def render(self, query: SurfaceQuery, spec: RenderSpec) -> RenderArtifacts:
        """Render."""
        projection = _resolve_projection(spec.projection)
        cmap = get_cmap(spec.style, query.metric, spec.colormap, spec.diverging_colormap)

        if spec.layout_mode == "quad":
            return self._render_quad(query, spec, projection, cmap)
        return self._render_single(query, spec, projection, cmap)

    def _render_single(self, query: SurfaceQuery, spec: RenderSpec, projection: str | None, cmap):
        """Internal helper for render single."""
        df = _load_query_df(query, query.time_slice)
        if df.empty:
            hint = ""
            if query.time_slice is not None:
                hint = " Did you build your surface with --seasonal enabled?"
            raise ValueError(
                "No surface rows matched query "
                f"dataset={query.dataset} metric={query.metric} grid={query.grid} res={query.resolution} "
                f"time_slice={query.time_slice} min_support={query.min_support}.{hint}"
            )

        gdf = h3_df_to_gdf(df)
        if projection is not None:
            gdf = gdf.to_crs(projection)

        boundary_gdf = _make_boundary(spec, gdf, projection)
        neighbors_gdf = _make_neighbors(spec, boundary_gdf, projection)
        water_gdf = _make_water(spec, projection)
        rotation_origin = _rotation_origin(boundary_gdf)
        if spec.rotate_deg != 0.0:
            boundary_gdf = _rotate_gdf(boundary_gdf, spec.rotate_deg, rotation_origin)
            neighbors_gdf = _rotate_gdf(neighbors_gdf, spec.rotate_deg, rotation_origin)
            water_gdf = _rotate_gdf(water_gdf, spec.rotate_deg, rotation_origin)
            gdf = _rotate_gdf(gdf, spec.rotate_deg, rotation_origin)

        clipped = _clip_and_mask(gdf, boundary_gdf, water_gdf)
        if clipped.empty:
            raise ValueError("No renderable surface polygons remain after region/water clipping")

        scaled = scale_values(clipped["value"], spec.scale, spec.gamma)
        clipped = clipped.copy()
        clipped["scaled_value"] = scaled

        if spec.scale == "linear":
            vmin = float(clipped["scaled_value"].min())
            vmax = float(clipped["scaled_value"].max())
        else:
            vmin, vmax = 0.0, 1.0

        fig, ax = plt.subplots(figsize=(spec.width_px / spec.dpi, spec.height_px / spec.dpi), dpi=spec.dpi)
        fig.patch.set_facecolor(spec.background_color)

        _set_framing(ax, boundary_gdf, spec.pad_pct)
        ax.set_aspect("equal", adjustable="box")
        boundary_for_plot = _clip_to_axes(boundary_gdf, ax)
        neighbors_for_plot = _clip_to_axes(neighbors_gdf, ax)
        water_for_plot = _clip_to_axes(water_gdf, ax)
        clipped_for_plot = _clip_to_axes(clipped, ax)

        _draw_common_layers(ax, spec, boundary_for_plot, neighbors_for_plot, water_for_plot)
        _draw_outline(ax, spec, boundary_for_plot)
        clipped_for_plot.plot(
            ax=ax,
            column="scaled_value",
            cmap=cmap,
            linewidth=spec.edge_width,
            edgecolor=spec.edge_color,
            legend=False,
            vmin=vmin,
            vmax=vmax,
            zorder=3,
        )

        self._decorate_single(fig, ax, spec, query)
        self._add_colorbar(fig, ax, spec, cmap, vmin, vmax, query.metric)

        ax.set_axis_off()

        output_path = Path(spec.out_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(
            output_path,
            format=spec.output_format,
            bbox_inches="tight",
            pad_inches=0.05,
            metadata=_build_png_metadata(query, spec, len(df)),
        )
        plt.close(fig)

        self._write_stats(spec.out_path, df)
        return RenderArtifacts(output_path=spec.out_path)

    def _render_quad(self, query: SurfaceQuery, spec: RenderSpec, projection: str | None, cmap):
        """Internal helper for render quad."""
        season_dfs = {season: _load_query_df(query, season) for season in _SEASONS}
        non_empty = [df for df in season_dfs.values() if not df.empty]
        if not non_empty:
            raise ValueError(
                "No seasonal surface rows found for winter/spring/summer/fall. "
                "Did you build your surface with --seasonal enabled?"
            )

        season_gdfs = {}
        for season, df in season_dfs.items():
            if df.empty:
                season_gdfs[season] = None
                continue
            gdf = h3_df_to_gdf(df)
            season_gdfs[season] = gdf.to_crs(projection) if projection is not None else gdf

        first_non_empty = next(g for g in season_gdfs.values() if g is not None)
        boundary_gdf = _make_boundary(spec, first_non_empty, projection)
        neighbors_gdf = _make_neighbors(spec, boundary_gdf, projection)
        water_gdf = _make_water(spec, projection)
        rotation_origin = _rotation_origin(boundary_gdf)
        if spec.rotate_deg != 0.0:
            boundary_gdf = _rotate_gdf(boundary_gdf, spec.rotate_deg, rotation_origin)
            neighbors_gdf = _rotate_gdf(neighbors_gdf, spec.rotate_deg, rotation_origin)
            water_gdf = _rotate_gdf(water_gdf, spec.rotate_deg, rotation_origin)
            for season in _SEASONS:
                if season_gdfs[season] is not None:
                    season_gdfs[season] = _rotate_gdf(season_gdfs[season], spec.rotate_deg, rotation_origin)

        clipped_by_season = {}
        all_values: list[pd.Series] = []
        for season in _SEASONS:
            gdf = season_gdfs[season]
            if gdf is None:
                clipped_by_season[season] = None
                continue
            clipped = _clip_and_mask(gdf, boundary_gdf, water_gdf)
            if clipped.empty:
                clipped_by_season[season] = None
                continue
            clipped_by_season[season] = clipped
            all_values.append(clipped["value"].astype(float))

        if not all_values:
            raise ValueError("No renderable seasonal polygons remain after region/water clipping")

        reference_values = pd.concat(all_values, ignore_index=True)
        if spec.scale == "linear":
            vmin = float(reference_values.min())
            vmax = float(reference_values.max())
        else:
            vmin, vmax = 0.0, 1.0

        fig, axes = plt.subplots(
            2,
            2,
            figsize=(spec.width_px / spec.dpi, spec.height_px / spec.dpi),
            dpi=spec.dpi,
            constrained_layout=True,
        )
        fig.patch.set_facecolor(spec.background_color)

        for ax, season in zip(axes.flatten(), _SEASONS):
            ax.set_facecolor(spec.background_color)
            _set_framing(ax, boundary_gdf, spec.pad_pct)
            ax.set_aspect("equal", adjustable="box")
            boundary_for_plot = _clip_to_axes(boundary_gdf, ax)
            neighbors_for_plot = _clip_to_axes(neighbors_gdf, ax)
            water_for_plot = _clip_to_axes(water_gdf, ax)
            _draw_common_layers(ax, spec, boundary_for_plot, neighbors_for_plot, water_for_plot)
            _draw_outline(ax, spec, boundary_for_plot)

            clipped = clipped_by_season[season]
            if clipped is not None:
                clipped = clipped.copy()
                clipped["scaled_value"] = scale_values(
                    clipped["value"],
                    spec.scale,
                    spec.gamma,
                    reference=reference_values,
                )
                clipped_for_plot = _clip_to_axes(clipped, ax)
                clipped_for_plot.plot(
                    ax=ax,
                    column="scaled_value",
                    cmap=cmap,
                    linewidth=spec.edge_width,
                    edgecolor=spec.edge_color,
                    legend=False,
                    vmin=vmin,
                    vmax=vmax,
                    zorder=3,
                )

            ax.set_axis_off()

            if spec.quad_titles:
                ax.set_title(season.title(), fontsize=max(10, spec.title_fontsize - 2), pad=4)

        if spec.title_enabled:
            if spec.title:
                title_text = spec.title
            else:
                region_name = spec.region_value or query.dataset
                title_text = f"{region_name} All Dates {query.metric} by Season (H3 res {query.resolution})"
            fig.suptitle(title_text, fontsize=spec.title_fontsize)
        if spec.subtitle_enabled and spec.subtitle:
            fig.text(0.5, 0.96, spec.subtitle, ha="center", va="top", fontsize=spec.subtitle_fontsize)

        self._add_colorbar(fig, axes.flatten().tolist(), spec, cmap, vmin, vmax, query.metric)

        output_path = Path(spec.out_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(
            output_path,
            format=spec.output_format,
            bbox_inches="tight",
            pad_inches=0.05,
            metadata=_build_png_metadata(query, spec, len(pd.concat(non_empty, ignore_index=True))),
        )
        plt.close(fig)

        self._write_stats(spec.out_path, pd.concat(non_empty, ignore_index=True))
        return RenderArtifacts(output_path=spec.out_path)

    def _decorate_single(self, fig, ax, spec: RenderSpec, query: SurfaceQuery) -> None:
        """Internal helper for decorate single."""
        if spec.title_enabled and spec.title:
            ax.set_title(spec.title, fontsize=spec.title_fontsize, pad=spec.title_pad)
        if spec.subtitle_enabled and spec.subtitle:
            fig.text(0.5, 0.94, spec.subtitle, ha="center", va="top", fontsize=spec.subtitle_fontsize)

    def _add_colorbar(self, fig, ax_or_axes, spec: RenderSpec, cmap, vmin: float, vmax: float, metric: str) -> None:
        """Internal helper for add colorbar."""
        if not spec.show_legend or spec.legend_location == "none":
            return
        if vmax == vmin:
            vmax = vmin + 1e-9

        norm = Normalize(vmin=vmin, vmax=vmax)
        sm = ScalarMappable(norm=norm, cmap=cmap)
        sm.set_array([])

        label = spec.legend_label or f"{metric} ({spec.scale})"
        if spec.legend_location == "bottom":
            cbar = fig.colorbar(sm, ax=ax_or_axes, orientation="horizontal", fraction=0.05, pad=0.06)
        else:
            cbar = fig.colorbar(sm, ax=ax_or_axes, orientation="vertical", fraction=0.046, pad=0.04)
        cbar.set_label(label)

    def _write_stats(self, out_path: str, df: pd.DataFrame) -> None:
        """Internal helper for write stats."""
        values = df["value"]
        stats = {
            "rowcount": int(len(df)),
            "value_min": float(values.min()),
            "value_max": float(values.max()),
            "value_mean": float(values.mean()),
            "output_path": out_path,
        }
        sidecar = stats_sidecar_path(out_path)
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(json.dumps(stats, indent=2), encoding="utf-8")

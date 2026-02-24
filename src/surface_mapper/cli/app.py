from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, cast

import typer
from shapely.ops import unary_union

from surface_mapper import __version__
from surface_mapper.config import load_json_config, render_3d_config, render_flat_config
from surface_mapper.contracts.normalized import NORMALIZED_EVENTS_TABLE, NORMALIZED_OBS_TABLE
from surface_mapper.geodata import default_geodata_dest, ensure_derived_defaults
from surface_mapper.geodata.defaults import DEFAULT_DATASETS, DEFAULT_STATE_NEIGHBORS
from surface_mapper.ingest import IngestRequest, resolve_adapter
from surface_mapper.render.contracts import RenderScale, RenderSpec, RenderStyle, SurfaceQuery
from surface_mapper.render.flat import FlatRenderer, stats_sidecar_path
from surface_mapper.render.layers import load_layer, reproject_to, select_polygon
from surface_mapper.render.presets import RenderPreset
from surface_mapper.render.scales import scale_values
from surface_mapper.render.styles import get_cmap
from surface_mapper.render3d.builder import Surface3DSpec, build_surface_mesh, get_builder_registry
from surface_mapper.render3d.hex_prism import polygon_gdf_to_flat_mesh
from surface_mapper.render3d.io import export_mesh, write_export_metadata
from surface_mapper.render3d.preview import render_preview
from surface_mapper.render3d.transforms import resolve_xy_transform, transform_xy_gdf
from surface_mapper.store.duckdb_store import (
    DuckDBStore,
    count_rows,
    create_normalized_tables,
)
from surface_mapper.surface.build import (
    build_event_cells,
    create_event_cells_table,
    create_surface_table,
    write_surface_attention,
    write_surface_richness_mean,
    write_surface_richness_unique,
)

app = typer.Typer(
    name="surface-mapper",
    no_args_is_help=True,
    help="Build geospatial analytic surfaces from BYOD datasets, then render/export them.",
)
export_app = typer.Typer(help="Export artifacts from DuckDB.")
render_app = typer.Typer(help="Render surface outputs.")
geodata_app = typer.Typer(help="Download/manage default geodata layers.")
logger = logging.getLogger("surface_mapper.cli")


def metric_completion() -> list[str]:
    return ["attention", "richness_unique", "richness_mean"]


def dataset_completion() -> list[str]:
    return ["ebird-ebd"]


def projection_completion() -> list[str]:
    return ["auto", "5070", "3857", "none"]


def layout_completion() -> list[str]:
    return ["single", "quad"]


def preset_completion() -> list[str]:
    return ["classic", "neon"]


def style_completion() -> list[str]:
    return ["classic", "neon"]


def scale_completion() -> list[str]:
    return ["linear", "log", "gamma"]


def render3d_mode_completion() -> list[str]:
    return sorted(get_builder_registry())


def export3d_completion() -> list[str]:
    return ["glb", "obj", "stl"]


def scale_units_completion() -> list[str]:
    return ["m", "km"]


def center_origin_completion() -> list[str]:
    return ["region", "data"]


def time_slice_completion() -> list[str]:
    return ["winter", "spring", "summer", "fall"]


def log_level_completion() -> list[str]:
    return ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def _parse_log_level(value: str) -> int | None:
    return getattr(logging, value.upper(), None)


def _configure_logging(log_level: str | None = None) -> None:
    level_name = log_level or os.getenv("SURFACE_MAPPER_LOG_LEVEL", "INFO")
    level = _parse_log_level(level_name)
    if level is None:
        level = logging.INFO

    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        )
        return
    root.setLevel(level)


def version_callback(value: bool) -> None:
    if value:
        _configure_logging()
        logger.info("surface-mapper %s", __version__)
        raise typer.Exit()


@app.callback()
def main_cb(
    log_level: str | None = typer.Option(
        None,
        "--log-level",
        help="Global log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).",
        autocompletion=log_level_completion,
    ),
    version: bool = typer.Option(
        False,
        "--version",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """SurfaceMapper CLI."""
    if log_level is not None and _parse_log_level(log_level) is None:
        raise typer.BadParameter(
            "Unsupported log level. Use one of: DEBUG, INFO, WARNING, ERROR, CRITICAL.",
            param_hint="--log-level",
        )
    _configure_logging(log_level)
    return


@app.command()
def ingest(
    dataset: str = typer.Argument(..., help="Dataset adapter name (ebird-ebd, ebd, ebird)."),
    obs: str = typer.Option(..., "--obs", help="Path to observations TSV."),
    sampling: str | None = typer.Option(None, "--sampling", help="Path to sampling TSV."),
    out: str = typer.Option("data/surfaces.duckdb", "--out", "-o", help="Output DuckDB path."),
    batch_size: int = typer.Option(50000, "--batch-size", min=1, help="Batch insert size."),
    progress: bool = typer.Option(
        True,
        "--progress/--no-progress",
        help="Show lightweight ingestion progress output.",
    ),
    progress_every: int = typer.Option(
        200000,
        "--progress-every",
        min=1,
        help="Print progress every N read rows per file.",
    ),
    python_parser: bool = typer.Option(
        False,
        "--python-parser/--no-python-parser",
        help="Use Python csv parser fallback instead of DuckDB-native CSV ingestion.",
    ),
) -> None:
    """Ingest source files via a dataset adapter into normalized DuckDB tables."""
    try:
        adapter = resolve_adapter(dataset)
    except KeyError as exc:
        logger.error(str(exc))
        raise typer.BadParameter(str(exc), param_hint="dataset") from exc

    obs_path = Path(obs)
    sampling_path = Path(sampling) if sampling else None
    start_time = time.time()

    logger.info(
        "Starting ingest dataset=%s obs=%s sampling=%s out=%s batch_size=%d progress=%s progress_every=%d python_parser=%s",
        dataset,
        obs_path,
        sampling_path,
        out,
        batch_size,
        progress,
        progress_every,
        python_parser,
    )

    store = DuckDBStore(Path(out))
    conn = store.connect()
    try:
        logger.info("Connected to DuckDB: %s", out)
        create_normalized_tables(conn)
        logger.info("Ensured normalized tables and indexes exist")
        stats = adapter.ingest(
            conn,
            IngestRequest(
                dataset=dataset,
                obs_path=obs_path,
                sampling_path=sampling_path,
                batch_size=batch_size,
                progress=progress,
                progress_every=progress_every,
                python_parser=python_parser,
                start_time=start_time,
            ),
        )

        total_obs = count_rows(conn, NORMALIZED_OBS_TABLE)
        total_events = count_rows(conn, NORMALIZED_EVENTS_TABLE)
        logger.info(
            "ingest complete inserted_obs=%d inserted_events=%d rows_read_obs=%d rows_read_events=%d "
            "batches_obs=%d batches_events=%d total_obs=%d total_events=%d db=%s",
            stats.inserted_obs,
            stats.inserted_events,
            stats.rows_read_obs,
            stats.rows_read_events,
            stats.batches_flushed_obs,
            stats.batches_flushed_events,
            total_obs,
            total_events,
            out,
        )
    except Exception:
        logger.exception("Ingest failed for dataset=%s out=%s", dataset, out)
        raise typer.Exit(code=1)
    finally:
        conn.close()
        logger.info("Closed DuckDB connection: %s", out)


@app.command()
def surface(
    db: str = typer.Option("data/surfaces.duckdb", "--db", help="DuckDB path."),
    dataset: str = typer.Option("ebird-ebd", "--dataset", help="Dataset key.", autocompletion=dataset_completion),
    metric: str = typer.Option(
        "attention",
        "--metric",
        help="Metric to build (attention, richness, etc.).",
        autocompletion=metric_completion,
    ),
    res: int = typer.Option(6, "--res", help="Grid resolution (e.g., H3 resolution)."),
    seasonal: bool = typer.Option(False, "--seasonal/--no-seasonal", help="Build seasonal surface slices."),
    min_checklists: int | None = typer.Option(
        None, "--min-checklists", help="Optional checklist threshold (richness metrics only)."
    ),
    out_table: str = typer.Option("surface_cells", "--out-table", help="Destination surface table name."),
    force_event_cells: bool = typer.Option(
        False,
        "--force-event-cells/--no-force-event-cells",
        help="Recompute event_cells even if rows already exist for dataset/resolution.",
    ),
) -> None:
    """Build a surface table (cell_id + metric + value + support...)."""
    writer_map = {
        "attention": write_surface_attention,
        "richness_unique": write_surface_richness_unique,
        "richness_mean": write_surface_richness_mean,
    }
    if metric not in writer_map:
        logger.error("Unsupported surface metric '%s'", metric)
        raise typer.BadParameter(
            "Unsupported metric. Use one of: attention, richness_unique, richness_mean.",
            param_hint="--metric",
        )

    if metric == "attention" and min_checklists is not None:
        logger.warning("Ignoring --min-checklists for attention metric")

    logger.info(
        "Starting surface build db=%s dataset=%s metric=%s res=%d seasonal=%s out_table=%s force_event_cells=%s",
        db,
        dataset,
        metric,
        res,
        seasonal,
        out_table,
        force_event_cells,
    )

    store = DuckDBStore(Path(db))
    conn = store.connect()
    try:
        create_normalized_tables(conn)
        create_surface_table(conn, out_table)
        create_event_cells_table(conn)
        build_event_cells(conn, dataset=dataset, res=res, force=force_event_cells)

        writer = writer_map[metric]
        if seasonal:
            rows_written = 0
            for slice_name in ("winter", "spring", "summer", "fall"):
                if metric == "attention":
                    rows_written += writer(conn, dataset=dataset, res=res, out_table=out_table, time_slice=slice_name)
                else:
                    rows_written += writer(
                        conn,
                        dataset=dataset,
                        res=res,
                        out_table=out_table,
                        time_slice=slice_name,
                        min_checklists=min_checklists,
                    )
            distinct_cells = int(
                conn.execute(
                    f"""
                    SELECT COUNT(DISTINCT cell_id)
                    FROM {out_table}
                    WHERE dataset = ? AND resolution = ? AND metric = ? AND time_slice IS NOT NULL;
                    """,
                    [dataset, res, metric],
                ).fetchone()[0]
            )
        else:
            if metric == "attention":
                rows_written = writer(conn, dataset=dataset, res=res, out_table=out_table, time_slice=None)
            else:
                rows_written = writer(
                    conn,
                    dataset=dataset,
                    res=res,
                    out_table=out_table,
                    time_slice=None,
                    min_checklists=min_checklists,
                )
            distinct_cells = int(
                conn.execute(
                    f"""
                    SELECT COUNT(DISTINCT cell_id)
                    FROM {out_table}
                    WHERE dataset = ? AND resolution = ? AND metric = ? AND time_slice IS NULL;
                    """,
                    [dataset, res, metric],
                ).fetchone()[0]
            )

        logger.info(
            "surface complete rows_written=%d distinct_cells=%d metric=%s res=%d table=%s",
            rows_written,
            distinct_cells,
            metric,
            res,
            out_table,
        )
    except Exception:
        logger.exception("Surface build failed db=%s dataset=%s metric=%s res=%d", db, dataset, metric, res)
        raise typer.Exit(code=1)
    finally:
        conn.close()
        logger.info("Closed DuckDB connection: %s", db)


@render_app.command("flat")
def render_flat(
    config: str | None = typer.Option(None, "--config", help="Path to JSON config file."),
    preset: str | None = typer.Option(
        None,
        "--preset",
        help="Render preset name (e.g., classic, neon).",
        autocompletion=preset_completion,
    ),
    preset_file: str | None = typer.Option(None, "--preset-file", help="Path to custom preset JSON/YAML."),
    db: str | None = typer.Option(None, "--db", help="DuckDB path."),
    table: str | None = typer.Option(None, "--table", help="Surface table name."),
    dataset: str | None = typer.Option(None, "--dataset", help="Dataset key.", autocompletion=dataset_completion),
    metric: str | None = typer.Option(None, "--metric", help="Surface metric.", autocompletion=metric_completion),
    res: int | None = typer.Option(None, "--res", help="Grid resolution."),
    time_slice: str | None = typer.Option(
        None,
        "--time-slice",
        help="Optional seasonal slice.",
        autocompletion=time_slice_completion,
    ),
    min_support: float | None = typer.Option(None, "--min-support", help="Optional support threshold."),
    style: RenderStyle | None = typer.Option(None, "--style", help="Render style.", autocompletion=style_completion),
    scale: RenderScale | None = typer.Option(None, "--scale", help="Value scaling mode.", autocompletion=scale_completion),
    gamma: float | None = typer.Option(None, "--gamma", help="Gamma exponent used when --scale=gamma."),
    rotate_deg: float | None = typer.Option(
        None,
        "--rotate-deg",
        help="Rotate rendered composition in degrees (aesthetic framing).",
    ),
    projection: str | None = typer.Option(
        None,
        "--projection",
        help="Projection mode: auto, 5070, 3857, none.",
        autocompletion=projection_completion,
    ),
    layout: str | None = typer.Option(
        None,
        "--layout",
        help="Render layout mode: single or quad.",
        autocompletion=layout_completion,
    ),
    region_file: str | None = typer.Option(
        None,
        "--region-file",
        help="Path to region polygon file (GeoJSON/shapefile/etc; fidelity depends on input).",
    ),
    neighbors_file: str | None = typer.Option(
        None,
        "--neighbors-file",
        help="Optional neighboring polygons file (GeoJSON/shapefile/etc; fidelity depends on input).",
    ),
    water_file: str | None = typer.Option(
        None,
        "--water-file",
        help="Optional water polygons file (GeoJSON/shapefile/etc; fidelity depends on input).",
    ),
    region_key: str | None = typer.Option(
        None,
        "--region-key",
        help="Field name used to select region from --region-file.",
    ),
    region_value: str | None = typer.Option(
        None,
        "--region-value",
        help="Field value used with --region-key to select target region.",
    ),
    neighbors: bool | None = typer.Option(None, "--neighbors/--no-neighbors", help="Render neighbor frame backdrop."),
    mask_water: bool | None = typer.Option(
        None,
        "--mask-water/--no-mask-water",
        help="Subtract water polygons from rendered hex geometry.",
    ),
    title: str | None = typer.Option(None, "--title", help="Optional figure title."),
    subtitle: str | None = typer.Option(None, "--subtitle", help="Optional figure subtitle."),
    out: str | None = typer.Option(None, "--out", help="Output image path."),
) -> None:
    """Render flat surface output PNG."""
    config_payload = load_json_config(Path(config).expanduser() if config else None)
    flat_cfg = render_flat_config(config_payload)

    preset_name = preset or flat_cfg.get("preset") or "classic"
    preset_file_value = preset_file or flat_cfg.get("preset_file")
    preset_model = RenderPreset.load(str(preset_file_value) if preset_file_value else str(preset_name))
    preset_defaults = {
        "style": preset_model.style,
        "scale": preset_model.scale_defaults.scale,
        "gamma": preset_model.scale_defaults.gamma,
        "layout": preset_model.layout.mode,
        "quad_titles": preset_model.layout.quad_titles,
        "pad_pct": preset_model.framing.pad_pct,
        "show_legend": preset_model.legend.show,
        "legend_location": preset_model.legend.location,
        "legend_label": preset_model.legend.label,
        "colormap": preset_model.colormap,
        "diverging_colormap": preset_model.diverging_colormap,
        "background_color": preset_model.background_color,
        "neighbors_fill": preset_model.neighbors_fill,
        "neighbors_alpha": preset_model.neighbors_alpha,
        "water_fill": preset_model.water_fill,
        "water_alpha": preset_model.water_alpha,
        "outline_color": preset_model.outline_color,
        "outline_width": preset_model.outline_width,
        "edge_color": preset_model.edge_color,
        "edge_width": preset_model.edge_width,
        "title_enabled": preset_model.title.enabled,
        "title_fontsize": preset_model.title.fontsize,
        "title_pad": preset_model.title.pad,
        "subtitle_enabled": preset_model.subtitle.enabled,
        "subtitle_fontsize": preset_model.subtitle.fontsize,
    }

    resolved_values: dict[str, Any] = {}
    resolved_sources: dict[str, str] = {}

    def resolve_option(key: str, cli_value: Any, default: Any) -> Any:
        if cli_value is not None:
            resolved_sources[key] = "cli"
            resolved_values[key] = cli_value
            return cli_value
        if key in flat_cfg:
            resolved_sources[key] = "config"
            resolved_values[key] = flat_cfg[key]
            return flat_cfg[key]
        resolved_sources[key] = "default"
        resolved_values[key] = default
        return default

    db_value = resolve_option("db", db, None)
    table_value = resolve_option("table", table, "surface_cells")
    dataset_value = resolve_option("dataset", dataset, "ebird-ebd")
    metric_value = resolve_option("metric", metric, None)
    res_value = resolve_option("res", res, None)
    time_slice_value = resolve_option("time_slice", time_slice, None)
    min_support_value = resolve_option("min_support", min_support, None)
    style_value = resolve_option("style", style, preset_defaults["style"])
    scale_value = resolve_option("scale", scale, preset_defaults["scale"])
    gamma_value = resolve_option("gamma", gamma, preset_defaults["gamma"])
    rotate_deg_value = resolve_option("rotate_deg", rotate_deg, 0.0)
    projection_value = resolve_option("projection", projection, "auto")
    layout_value = resolve_option("layout", layout, preset_defaults["layout"])
    quad_titles_value = resolve_option("quad_titles", None, preset_defaults["quad_titles"])
    pad_pct_value = resolve_option("pad_pct", None, preset_defaults["pad_pct"])
    show_legend_value = resolve_option("show_legend", None, preset_defaults["show_legend"])
    legend_location_value = resolve_option("legend_location", None, preset_defaults["legend_location"])
    legend_label_value = resolve_option("legend_label", None, preset_defaults["legend_label"])
    colormap_value = resolve_option("colormap", None, preset_defaults["colormap"])
    diverging_colormap_value = resolve_option("diverging_colormap", None, preset_defaults["diverging_colormap"])
    background_color_value = resolve_option("background_color", None, preset_defaults["background_color"])
    neighbors_fill_value = resolve_option("neighbors_fill", None, preset_defaults["neighbors_fill"])
    neighbors_alpha_value = resolve_option("neighbors_alpha", None, preset_defaults["neighbors_alpha"])
    water_fill_value = resolve_option("water_fill", None, preset_defaults["water_fill"])
    water_alpha_value = resolve_option("water_alpha", None, preset_defaults["water_alpha"])
    outline_color_value = resolve_option("outline_color", None, preset_defaults["outline_color"])
    outline_width_value = resolve_option("outline_width", None, preset_defaults["outline_width"])
    edge_color_value = resolve_option("edge_color", None, preset_defaults["edge_color"])
    edge_width_value = resolve_option("edge_width", None, preset_defaults["edge_width"])
    title_enabled_value = resolve_option("title_enabled", None, preset_defaults["title_enabled"])
    title_fontsize_value = resolve_option("title_fontsize", None, preset_defaults["title_fontsize"])
    title_pad_value = resolve_option("title_pad", None, preset_defaults["title_pad"])
    subtitle_enabled_value = resolve_option("subtitle_enabled", None, preset_defaults["subtitle_enabled"])
    subtitle_fontsize_value = resolve_option("subtitle_fontsize", None, preset_defaults["subtitle_fontsize"])
    region_file_value = resolve_option("region_file", region_file, None)
    neighbors_file_value = resolve_option("neighbors_file", neighbors_file, None)
    water_file_value = resolve_option("water_file", water_file, None)
    region_key_value = resolve_option("region_key", region_key, "STUSPS")
    region_value_value = resolve_option("region_value", region_value, None)
    neighbors_value = resolve_option("neighbors", neighbors, True)
    mask_water_value = resolve_option("mask_water", mask_water, False)
    title_value = resolve_option("title", title, None)
    subtitle_value = resolve_option("subtitle", subtitle, None)
    out_value = resolve_option("out", out, None)

    explicit_inputs = {
        "config": config,
        "db": db,
        "table": table,
        "dataset": dataset,
        "metric": metric,
        "res": res,
        "time_slice": time_slice,
        "min_support": min_support,
        "style": style,
        "scale": scale,
        "gamma": gamma,
        "rotate_deg": rotate_deg,
        "projection": projection,
        "layout": layout,
        "preset": preset,
        "preset_file": preset_file,
        "region_file": region_file,
        "neighbors_file": neighbors_file,
        "water_file": water_file,
        "region_key": region_key,
        "region_value": region_value,
        "neighbors": neighbors,
        "mask_water": mask_water,
        "title": title,
        "subtitle": subtitle,
        "out": out,
    }
    explicit_inputs = {k: v for k, v in explicit_inputs.items() if v is not None}
    logger.info(
        "render flat config preset=%s explicit=%s resolved=%s sources=%s",
        preset_model.name,
        explicit_inputs,
        resolved_values,
        resolved_sources,
    )
    overridden_fields = sorted([k for k, src in resolved_sources.items() if src in {"cli", "config"}])
    logger.info("render flat preset overrides=%s", overridden_fields)

    if db_value is None:
        raise typer.BadParameter("Missing required value for db (use --db or config render.flat.db).", param_hint="--db")
    if metric_value is None:
        raise typer.BadParameter(
            "Missing required value for metric (use --metric or config render.flat.metric).",
            param_hint="--metric",
        )
    if res_value is None:
        raise typer.BadParameter("Missing required value for res (use --res or config render.flat.res).", param_hint="--res")
    if out_value is None:
        raise typer.BadParameter("Missing required value for out (use --out or config render.flat.out).", param_hint="--out")

    projection_map = {
        "auto": "auto",
        "5070": "epsg:5070",
        "3857": "epsg:3857",
        "epsg:5070": "epsg:5070",
        "epsg:3857": "epsg:3857",
        "none": "none",
    }
    if projection_value not in projection_map:
        raise typer.BadParameter("Unsupported projection. Use one of: auto, 5070, 3857, none.", param_hint="--projection")
    if str(layout_value) not in {"single", "quad"}:
        raise typer.BadParameter("Unsupported layout. Use one of: single, quad.", param_hint="--layout")

    query = SurfaceQuery(
        db_path=str(db_value),
        table=str(table_value),
        dataset=str(dataset_value),
        metric=str(metric_value),
        grid="h3",
        resolution=int(res_value),
        time_slice=time_slice_value,
        min_support=min_support_value,
    )
    spec = RenderSpec(
        style=style_value,
        scale=scale_value,
        gamma=float(gamma_value),
        rotate_deg=float(rotate_deg_value),
        projection=projection_map[str(projection_value)],
        layout_mode=str(layout_value),
        quad_titles=bool(quad_titles_value),
        neighbors=bool(neighbors_value),
        mask_water=bool(mask_water_value),
        pad_pct=float(pad_pct_value),
        show_legend=bool(show_legend_value),
        legend_location=str(legend_location_value),
        legend_label=legend_label_value,
        colormap=colormap_value,
        diverging_colormap=diverging_colormap_value,
        background_color=str(background_color_value),
        neighbors_fill=str(neighbors_fill_value),
        neighbors_alpha=float(neighbors_alpha_value),
        water_fill=str(water_fill_value),
        water_alpha=float(water_alpha_value),
        outline_color=str(outline_color_value),
        outline_width=float(outline_width_value),
        edge_color=edge_color_value,
        edge_width=float(edge_width_value),
        title_enabled=bool(title_enabled_value),
        title_fontsize=int(title_fontsize_value),
        title_pad=float(title_pad_value),
        subtitle_enabled=bool(subtitle_enabled_value),
        subtitle_fontsize=int(subtitle_fontsize_value),
        preset_name=preset_model.name,
        region_file=region_file_value,
        neighbors_file=neighbors_file_value,
        water_file=water_file_value,
        region_key=str(region_key_value),
        region_value=region_value_value,
        title=title_value,
        subtitle=subtitle_value,
        out_path=str(out_value),
    )

    try:
        artifacts = FlatRenderer().render(query, spec)
        sidecar = stats_sidecar_path(spec.out_path)
        rows = "unknown"
        if sidecar.exists():
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            rows = str(payload.get("rowcount", "unknown"))
        typer.echo(f"OK rendered flat (rows={rows}, out={artifacts.output_path})")
    except Exception:
        logger.exception(
            "Render failed db=%s table=%s dataset=%s metric=%s res=%d",
            db_value,
            table_value,
            dataset_value,
            metric_value,
            int(res_value),
        )
        raise typer.Exit(code=1)


@render_app.command("3d")
def render_3d(
    config: str | None = typer.Option(None, "--config", help="Path to JSON config file."),
    preset: str | None = typer.Option(
        None,
        "--preset",
        help="Render preset name (e.g., classic, neon).",
        autocompletion=preset_completion,
    ),
    preset_file: str | None = typer.Option(None, "--preset-file", help="Path to custom preset JSON/YAML."),
    mode: str = typer.Option(
        "hex-prism",
        "--mode",
        help="3D surface mode.",
        autocompletion=render3d_mode_completion,
    ),
    db: str = typer.Option("data/surfaces.duckdb", "--db", help="DuckDB path."),
    table: str = typer.Option("surface_cells", "--table", help="Surface table name."),
    dataset: str = typer.Option("ebird-ebd", "--dataset", help="Dataset key.", autocompletion=dataset_completion),
    metric: str = typer.Option("attention", "--metric", help="Surface metric.", autocompletion=metric_completion),
    res: int = typer.Option(6, "--res", help="Grid resolution."),
    time_slice: str | None = typer.Option(
        None,
        "--time-slice",
        help="Optional seasonal slice.",
        autocompletion=time_slice_completion,
    ),
    min_support: float | None = typer.Option(None, "--min-support", help="Optional support threshold."),
    style: RenderStyle = typer.Option("classic", "--style", help="Render style.", autocompletion=style_completion),
    scale: RenderScale = typer.Option("gamma", "--scale", help="Value scaling mode.", autocompletion=scale_completion),
    gamma: float = typer.Option(0.6, "--gamma", help="Gamma exponent used when --scale=gamma."),
    center: bool | None = typer.Option(None, "--center/--no-center", help="Center XY coordinates near origin."),
    center_origin: str | None = typer.Option(
        None,
        "--center-origin",
        help="Centering reference: region or data.",
        autocompletion=center_origin_completion,
    ),
    scale_units: str | None = typer.Option(
        None,
        "--scale-units",
        help="Coordinate units: m or km.",
        autocompletion=scale_units_completion,
    ),
    z_exaggeration: float | None = typer.Option(None, "--z-exaggeration", help="Height exaggeration multiplier."),
    height_scale: float = typer.Option(1.0, "--height-scale", help="Height multiplier applied to scaled values."),
    base_z: float = typer.Option(0.0, "--base-z", help="Base Z offset."),
    export: str = typer.Option("glb", "--export", help="3D export format.", autocompletion=export3d_completion),
    out: str = typer.Option("out.glb", "--out", help="Output mesh path."),
    preview: str | None = typer.Option(None, "--preview", help="Optional preview PNG screenshot path."),
    region_file: str | None = typer.Option(
        None,
        "--region-file",
        help="Path to region polygon file (GeoJSON/shapefile/etc).",
    ),
    neighbors_file: str | None = typer.Option(
        None,
        "--neighbors-file",
        help="Optional neighboring polygons file (GeoJSON/shapefile/etc).",
    ),
    water_file: str | None = typer.Option(
        None,
        "--water-file",
        help="Optional water polygons file (GeoJSON/shapefile/etc).",
    ),
    region_key: str = typer.Option(
        "STUSPS",
        "--region-key",
        help="Field name used to select region from --region-file.",
    ),
    region_value: str | None = typer.Option(
        None,
        "--region-value",
        help="Field value used with --region-key to select target region.",
    ),
    neighbors: bool = typer.Option(True, "--neighbors/--no-neighbors", help="Render neighbor base layer."),
    mask_water: bool = typer.Option(
        False,
        "--mask-water/--no-mask-water",
        help="Subtract water polygons from rendered hex geometry.",
    ),
    north_up: bool = typer.Option(True, "--north-up/--no-north-up", help="Use north-up map camera in preview."),
    camera: str | None = typer.Option(None, "--camera", help="Optional camera preset name (stub)."),
) -> None:
    """Render 3D surface output mesh."""
    export_value = str(export).lower()
    if export_value not in {"glb", "obj", "stl"}:
        raise typer.BadParameter("Unsupported export format. Use one of: glb, obj, stl.", param_hint="--export")

    registry = get_builder_registry()
    if mode not in registry:
        raise typer.BadParameter(
            f"Unsupported mode. Use one of: {', '.join(sorted(registry))}.",
            param_hint="--mode",
        )

    config_payload = load_json_config(Path(config).expanduser() if config else None)
    cfg_3d = render_3d_config(config_payload)

    center_value = bool(center if center is not None else cfg_3d.get("center", True))
    scale_units_value = str(scale_units if scale_units is not None else cfg_3d.get("scale_units", "m")).lower()
    z_exaggeration_value = float(
        z_exaggeration if z_exaggeration is not None else cfg_3d.get("z_exaggeration", 1.0)
    )
    center_origin_value = str(center_origin if center_origin is not None else cfg_3d.get("center_origin", "region")).lower()
    if scale_units_value not in {"m", "km"}:
        raise typer.BadParameter("Unsupported scale units. Use one of: m, km.", param_hint="--scale-units")
    if center_origin_value not in {"region", "data"}:
        raise typer.BadParameter("Unsupported center origin. Use one of: region, data.", param_hint="--center-origin")

    query = SurfaceQuery(
        db_path=str(db),
        table=str(table),
        dataset=str(dataset),
        metric=str(metric),
        grid="h3",
        resolution=int(res),
        time_slice=time_slice,
        min_support=min_support,
    )
    preset_name = preset or style
    preset_model = RenderPreset.load(str(preset_file) if preset_file else str(preset_name))

    spec = Surface3DSpec(
        mode=mode,
        scale=scale,
        gamma=float(gamma),
        style=cast(RenderStyle, preset_model.style),
        colormap=preset_model.colormap,
        height_scale=float(height_scale),
        base_z=float(base_z),
        scale_factor=1.0,
        z_exaggeration=z_exaggeration_value,
        camera_preset=camera,
    )

    try:
        from surface_mapper.render.h3_geometry import h3_df_to_gdf
        from surface_mapper.render.load_surface import load_surface

        df = load_surface(query)
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

        boundary_gdf = None
        region_bounds = None
        if region_file is not None:
            boundary_layer = load_layer(region_file)
            boundary_gdf = select_polygon(boundary_layer, region_key, region_value)
            boundary_gdf = reproject_to(boundary_gdf, str(gdf.crs))
            region_bounds = tuple(float(v) for v in boundary_gdf.total_bounds)
            gdf = gdf.clip(boundary_gdf)

        neighbors_gdf = None
        if neighbors and neighbors_file is not None:
            neighbors_gdf = load_layer(neighbors_file)
            neighbors_gdf = reproject_to(neighbors_gdf, str(gdf.crs))
            if boundary_gdf is not None:
                neighbors_gdf = neighbors_gdf.clip(boundary_gdf)

        water_gdf = None
        if water_file is not None:
            water_gdf = load_layer(water_file)
            water_gdf = reproject_to(water_gdf, str(gdf.crs))
            if boundary_gdf is not None:
                water_gdf = water_gdf.clip(boundary_gdf)
            water_gdf = water_gdf[~water_gdf.geometry.is_empty]

        if mask_water:
            if water_gdf is None:
                raise ValueError("--mask-water was set but no --water-file was provided")
            if not water_gdf.empty:
                water_union = unary_union(water_gdf.geometry)
                gdf = gdf.copy()
                gdf["geometry"] = gdf.geometry.apply(lambda geom: geom.difference(water_union))
                gdf = gdf[~gdf.geometry.is_empty]

        if gdf.empty:
            raise ValueError("No renderable surface polygons remain after region/water clipping")

        transform = resolve_xy_transform(
            gdf=gdf,
            boundary_gdf=boundary_gdf,
            center=center_value,
            center_origin=center_origin_value,
            scale_units=scale_units_value,
        )
        gdf = transform_xy_gdf(gdf, transform.origin_x, transform.origin_y, transform.scale_factor)
        if boundary_gdf is not None:
            boundary_gdf = transform_xy_gdf(boundary_gdf, transform.origin_x, transform.origin_y, transform.scale_factor)
            region_bounds = tuple(float(v) for v in boundary_gdf.total_bounds)
        if neighbors_gdf is not None and not neighbors_gdf.empty:
            neighbors_gdf = transform_xy_gdf(neighbors_gdf, transform.origin_x, transform.origin_y, transform.scale_factor)
        if water_gdf is not None and not water_gdf.empty:
            water_gdf = transform_xy_gdf(water_gdf, transform.origin_x, transform.origin_y, transform.scale_factor)

        gdf = gdf.copy()
        gdf["scaled_value"] = scale_values(gdf["value"], spec.scale, spec.gamma)
        spec = Surface3DSpec(
            mode=spec.mode,
            scale=spec.scale,
            gamma=spec.gamma,
            style=spec.style,
            colormap=spec.colormap,
            height_scale=spec.height_scale,
            base_z=spec.base_z * transform.scale_factor,
            scale_factor=transform.scale_factor,
            z_exaggeration=spec.z_exaggeration,
            camera_preset=spec.camera_preset,
        )

        mesh = build_surface_mesh(gdf, spec)

        neighbors_mesh = None
        if preview and neighbors_gdf is not None and not neighbors_gdf.empty:
            neighbors_mesh = polygon_gdf_to_flat_mesh(
                neighbors_gdf,
                z=spec.base_z - (0.5 * spec.scale_factor),
                color_name="neighbors",
            )

        water_mesh = None
        if preview and water_gdf is not None and not water_gdf.empty:
            water_mesh = polygon_gdf_to_flat_mesh(
                water_gdf,
                z=spec.base_z - (0.25 * spec.scale_factor),
                color_name="water",
            )

        cmap = get_cmap(spec.style, query.metric, preset_model.colormap, preset_model.diverging_colormap).name
        out_path = export_mesh(mesh, out_path=str(out), export_format=export_value)
        crs_value = None
        if gdf.crs is not None:
            crs_value = str(gdf.crs)
        write_export_metadata(
            out_path=out_path,
            metadata={
                "projection": crs_value,
                "crs": crs_value,
                "origin": {"x": transform.origin_x, "y": transform.origin_y},
                "center": center_value,
                "center_origin": center_origin_value,
                "scale_units": scale_units_value,
                "scale_factor": transform.scale_factor,
                "z_exaggeration": z_exaggeration_value,
                "height_scale": float(height_scale),
                "dataset": query.dataset,
                "metric": query.metric,
                "res": query.resolution,
                "time_slice": query.time_slice,
            },
        )
        preview_path = None
        if preview:
            preview_path = render_preview(
                hex_mesh=mesh,
                preview_path=str(preview),
                cmap=cmap,
                style=spec.style,
                base_z=spec.base_z,
                neighbors_fill=preset_model.neighbors_fill,
                neighbors_alpha=preset_model.neighbors_alpha,
                water_fill=preset_model.water_fill,
                water_alpha=preset_model.water_alpha,
                north_up=north_up,
                neighbors_mesh=neighbors_mesh,
                water_mesh=water_mesh,
                region_bounds=region_bounds,
                camera_preset=spec.camera_preset,
            )

        preview_text = f", preview={preview_path}" if preview_path is not None else ""
        typer.echo(f"OK rendered 3d (rows={len(df)}, out={out_path}{preview_text})")
        typer.echo("Import into Blender: File -> Import -> glTF 2.0 (.glb)")
    except NotImplementedError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    except ImportError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    except Exception:
        logger.exception(
            "Render 3D failed db=%s table=%s dataset=%s metric=%s res=%d mode=%s",
            db,
            table,
            dataset,
            metric,
            int(res),
            mode,
        )
        raise typer.Exit(code=1)


@export_app.command("surface")
def export_surface(
    db: str = typer.Option("data/surfaces.duckdb", "--db", help="DuckDB path."),
    out: str = typer.Option(..., "--out", help="Output parquet path."),
    surface_table: str = typer.Option("surface_cells", "--surface-table", help="Surface table to export."),
) -> None:
    """Export a surface table to parquet."""
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    conn = DuckDBStore(Path(db)).connect()
    try:
        logger.info("Starting surface export db=%s table=%s out=%s", db, surface_table, out)
        conn.execute(
            f"COPY (SELECT * FROM {surface_table}) TO ? (FORMAT PARQUET);",
            [str(out_path)],
        )
        rows = int(conn.execute(f"SELECT COUNT(*) FROM {surface_table};").fetchone()[0])
        logger.info("surface export complete rows=%d table=%s out=%s", rows, surface_table, out)
    except Exception:
        logger.exception("Surface export failed db=%s table=%s out=%s", db, surface_table, out)
        raise typer.Exit(code=1)
    finally:
        conn.close()
        logger.info("Closed DuckDB connection: %s", db)


@geodata_app.command("fetch-defaults")
def geodata_fetch_defaults(
    dest: str | None = typer.Option(None, "--dest", help="Destination directory for unpacked defaults."),
    state: str = typer.Option("WI", "--state", help="Target state STUSPS code for derived outputs."),
    neighbors: str | None = typer.Option(
        None,
        "--neighbors",
        help="Comma-separated neighboring STUSPS codes (example: MN,IA,IL,MI).",
    ),
    derived_dir: str | None = typer.Option(
        None,
        "--derived-dir",
        help="Directory for derived GeoJSON outputs (default: <dest>/derived).",
    ),
    crs: str = typer.Option("EPSG:5070", "--crs", help="CRS for derived outputs."),
    force: bool = typer.Option(False, "--force", help="Redownload/re-extract even if files already exist."),
) -> None:
    """Download + unpack default boundary/water datasets."""
    dest_dir = Path(dest).expanduser() if dest else default_geodata_dest()
    state_code = state.upper()
    neighbor_codes = (
        [part.strip().upper() for part in neighbors.split(",") if part.strip()]
        if neighbors is not None
        else list(DEFAULT_STATE_NEIGHBORS.get(state_code, ()))
    )
    if not neighbor_codes:
        raise typer.BadParameter(
            f"No neighbor codes provided and no default neighbor list is defined for state '{state_code}'.",
            param_hint="--neighbors",
        )

    try:
        installed = ensure_derived_defaults(
            dest_dir=dest_dir,
            state=state_code,
            neighbor_codes=neighbor_codes,
            derived_dir=Path(derived_dir).expanduser() if derived_dir else None,
            crs=crs,
            force=force,
        )
    except Exception as exc:
        typer.echo(f"Failed to fetch default geodata: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"Installed default geodata in: {dest_dir}")
    for key in sorted(installed):
        typer.echo(f"{key}: {installed[key]}")
    typer.echo(
        "Render example: "
        f"surface-mapper render flat --db data/surfaces.duckdb --metric attention --res 6 "
        f"--region-file {installed['boundary_geojson']} "
        f"--neighbors-file {installed['neighbors_geojson']} "
        f"--water-file {installed['lakes_geojson']} "
        f"--mask-water --out out.png"
    )


@geodata_app.command("show-defaults")
def geodata_show_defaults(
    dest: str | None = typer.Option(None, "--dest", help="Base directory where defaults are or will be installed."),
) -> None:
    """Show default geodata sources and usage guidance."""
    dest_dir = Path(dest).expanduser() if dest else default_geodata_dest()
    typer.echo(f"default_dest: {dest_dir}")
    for dataset in DEFAULT_DATASETS:
        typer.echo(f"dataset: {dataset.name}")
        for url in dataset.urls:
            typer.echo(f"  url: {url}")
    typer.echo("override_paths:")
    typer.echo("  render uses --region-file / --neighbors-file / --water-file")
    typer.echo("  fidelity depends on the geodata files you provide")
    typer.echo("example:")
    typer.echo("  surface-mapper geodata fetch-defaults")
    typer.echo(
        "  surface-mapper render flat --db data/surfaces.duckdb --metric attention --res 6 "
        "--region-file data/geodata/default/derived/WI_boundary.geojson "
        "--neighbors-file data/geodata/default/derived/WI_neighbors.geojson "
        "--water-file data/geodata/default/derived/WI_lakes.geojson --mask-water --out out.png"
    )


app.add_typer(render_app, name="render")
app.add_typer(export_app, name="export")
app.add_typer(geodata_app, name="geodata")


def main() -> None:
    app()


if __name__ == "__main__":
    main()

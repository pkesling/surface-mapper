from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zipfile import ZipFile

from surface_mapper.geodata.defaults import DEFAULT_DATASETS, DefaultDataset
from surface_mapper.geodata.derive import derive_boundary, derive_lakes, derive_neighbors
from surface_mapper.geodata.paths import default_derived_paths

_USER_AGENT = "surface-mapper/0.1 (+https://github.com/pkesling/surface-mapper)"
logger = logging.getLogger("surface_mapper.geodata.fetch")


def _default_dest_dir() -> Path:
    cwd = Path.cwd().resolve()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "src" / "surface_mapper").exists():
            return candidate / "data" / "geodata" / "default"
    return Path.home() / ".cache" / "surface-mapper" / "geodata" / "default"


def default_geodata_dest() -> Path:
    return _default_dest_dir()


def _required_components_exist(base_path: Path) -> bool:
    return all(base_path.with_suffix(ext).exists() for ext in (".shp", ".dbf", ".shx", ".prj"))


def _download_to_path(url: str, target: Path) -> None:
    logger.debug("Downloading geodata url=%s target=%s", url, target)
    req = Request(url, headers={"User-Agent": _USER_AGENT})
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        with urlopen(req, timeout=60) as response, tmp_path.open("wb") as out:
            shutil.copyfileobj(response, out)
        tmp_path.replace(target)
        logger.debug("Download complete url=%s bytes=%d", url, target.stat().st_size)
    except HTTPError as exc:
        logger.debug("HTTP download error url=%s status=%s reason=%s", url, exc.code, exc.reason, exc_info=True)
        tmp_path.unlink(missing_ok=True)
        raise
    except URLError as exc:
        logger.debug("URL download error url=%s reason=%s", url, exc.reason, exc_info=True)
        tmp_path.unlink(missing_ok=True)
        raise
    except Exception:
        logger.debug("Unexpected download error url=%s", url, exc_info=True)
        tmp_path.unlink(missing_ok=True)
        raise


def fetch_and_unpack(urls: list[str], dest_dir: Path, force: bool) -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    archive_path = dest_dir / "source.zip"
    logger.debug("Preparing fetch dest_dir=%s force=%s archive=%s", dest_dir, force, archive_path)

    if force and archive_path.exists():
        logger.debug("Force enabled; removing existing archive=%s", archive_path)
        archive_path.unlink()

    last_error: Exception | None = None
    if not archive_path.exists():
        for url in urls:
            try:
                logger.debug("Attempting URL for archive download url=%s", url)
                _download_to_path(url, archive_path)
                last_error = None
                logger.debug("Selected download URL url=%s", url)
                break
            except Exception as exc:
                last_error = exc
                logger.debug("Download attempt failed url=%s error=%s", url, exc, exc_info=True)
        if last_error is not None:
            raise RuntimeError(f"Failed to download from provided URLs: {urls}") from last_error
    else:
        logger.debug("Archive already exists; reusing archive=%s", archive_path)

    with ZipFile(archive_path) as zf:
        members = zf.namelist()
        logger.debug("Unpacking archive=%s members=%d", archive_path, len(members))
        zf.extractall(dest_dir)

    return [dest_dir / member for member in members]


def _ensure_dataset(dataset: DefaultDataset, dest_dir: Path, force: bool) -> Path:
    dataset_dir = dest_dir / dataset.name
    dataset_dir.mkdir(parents=True, exist_ok=True)
    shp_path = dataset_dir / f"{dataset.expected_basename}.shp"
    logger.debug(
        "Ensuring default dataset=%s dir=%s expected_shp=%s force=%s",
        dataset.name,
        dataset_dir,
        shp_path,
        force,
    )

    if shp_path.exists() and _required_components_exist(shp_path) and not force:
        logger.debug("Dataset already present dataset=%s shp=%s", dataset.name, shp_path)
        return shp_path

    fetch_and_unpack(list(dataset.urls), dataset_dir, force=force)

    if not _required_components_exist(shp_path):
        logger.debug("Expected shapefile components missing dataset=%s shp=%s", dataset.name, shp_path)
        raise RuntimeError(
            f"Downloaded default {dataset.name} dataset but expected shapefile components are missing at {shp_path}"
        )

    return shp_path


def ensure_defaults(dest_dir: Path, force: bool) -> dict[str, Path]:
    resolved = dest_dir.expanduser().resolve()
    results: dict[str, Path] = {}

    for dataset in DEFAULT_DATASETS:
        shp = _ensure_dataset(dataset, resolved, force=force)
        results[f"{dataset.name}_shp"] = shp
        results[f"{dataset.name}_dir"] = shp.parent

    return results


def ensure_derived_defaults(
    dest_dir: Path,
    state: str,
    neighbor_codes: list[str],
    derived_dir: Path | None,
    crs: str,
    force: bool,
) -> dict[str, Path]:
    resolved_dest = dest_dir.expanduser().resolve()
    installed = ensure_defaults(resolved_dest, force=force)
    out_paths = default_derived_paths(resolved_dest, state=state, derived_dir=derived_dir.expanduser().resolve() if derived_dir else None)

    boundary_path = out_paths["boundary_geojson"]
    boundary_wgs84_path = out_paths["boundary_wgs84_geojson"]
    neighbors_path = out_paths["neighbors_geojson"]
    lakes_path = out_paths["lakes_geojson"]

    if force or not boundary_path.exists():
        derive_boundary(
            states_path=installed["states_shp"],
            state=state,
            out_path=boundary_path,
            crs=crs,
        )
    else:
        logger.debug("Derived boundary already exists; skipping path=%s", boundary_path)

    if force or not boundary_wgs84_path.exists():
        derive_boundary(
            states_path=installed["states_shp"],
            state=state,
            out_path=boundary_wgs84_path,
            crs="EPSG:4326",
        )
    else:
        logger.debug("Derived WGS84 boundary already exists; skipping path=%s", boundary_wgs84_path)

    if force or not neighbors_path.exists():
        derive_neighbors(
            states_path=installed["states_shp"],
            neighbor_codes=neighbor_codes,
            out_path=neighbors_path,
            crs=crs,
        )
    else:
        logger.debug("Derived neighbors already exists; skipping path=%s", neighbors_path)

    if force or not lakes_path.exists():
        derive_lakes(
            lakes_path=installed["lakes_shp"],
            boundary_geojson_path=boundary_path,
            out_path=lakes_path,
            crs=crs,
        )
    else:
        logger.debug("Derived lakes already exists; skipping path=%s", lakes_path)

    return {
        **installed,
        **out_paths,
    }


__all__ = ["default_geodata_dest", "fetch_and_unpack", "ensure_defaults", "ensure_derived_defaults"]

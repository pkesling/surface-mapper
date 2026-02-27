from pathlib import Path

import pytest

from surface_mapper.blender.scripts.render_glb import build_parser, main, resolve_paths


def test_build_parser_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["--glb", "input.glb", "--out", "output.png"])

    assert args.glb == "input.glb"
    assert args.out == "output.png"
    assert args.collection == "MAP_GEOMETRY"
    assert args.engine == "CYCLES"
    assert args.samples == 512
    assert args.resolution == 2048


def test_resolve_paths_returns_absolute_paths(tmp_path: Path) -> None:
    glb = tmp_path / "mesh.glb"
    out = tmp_path / "renders" / "result.png"
    glb_path, out_path = resolve_paths(str(glb), str(out))

    assert glb_path.is_absolute()
    assert out_path.is_absolute()
    assert glb_path == glb.resolve()
    assert out_path == out.resolve()


def test_main_raises_file_not_found_before_blender_import(tmp_path: Path) -> None:
    missing_glb = tmp_path / "missing.glb"
    out = tmp_path / "render.png"

    with pytest.raises(FileNotFoundError):
        main(["--glb", str(missing_glb), "--out", str(out)])

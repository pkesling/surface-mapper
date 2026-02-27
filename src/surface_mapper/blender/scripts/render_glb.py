import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import bpy as _bpy


def _require_bpy():
    try:
        import bpy
    except ImportError as exc:
        raise RuntimeError(
            "bpy is required at runtime. Run this script via Blender CLI, e.g. "
            "`blender -b template.blend -P render_glb.py -- --glb in.glb --out out.png`."
        ) from exc
    return bpy


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--glb", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--collection", default="MAP_GEOMETRY")
    parser.add_argument("--engine", default="CYCLES")
    parser.add_argument("--samples", type=int, default=512)
    parser.add_argument("--resolution", type=int, default=2048)
    return parser


def resolve_paths(glb: str, out: str) -> tuple[Path, Path]:
    glb_path = Path(glb).expanduser().resolve()
    out_path = Path(out).expanduser().resolve()
    return glb_path, out_path


def ensure_collection(bpy: Any, name: str):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def clear_collection(bpy: Any, col: Any) -> None:
    # Remove all objects linked to this collection
    objs = list(col.objects)
    for obj in objs:
        col.objects.unlink(obj)
        # If object is not linked anywhere else, delete it from the file
        if obj.users_collection == ():
            bpy.data.objects.remove(obj, do_unlink=True)


def import_glb(bpy: Any, glb_path: Path) -> list[Any]:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(glb_path))
    after = set(bpy.data.objects)
    new_objects = [o for o in (after - before)]
    return new_objects


def link_objects_to_collection(objects: list[Any], col: Any) -> None:
    for obj in objects:
        # Only keep meshes (ignore cameras/lights/empties unless you want them)
        if obj.type != "MESH":
            continue
        # Unlink from all existing collections
        for c in list(obj.users_collection):
            c.objects.unlink(obj)
        # Link to target collection
        col.objects.link(obj)


def configure_render(bpy: Any, engine: str, samples: int, resolution: int) -> None:
    scene = bpy.context.scene
    scene.render.engine = engine
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100

    if engine.upper() == "CYCLES":
        scene.cycles.samples = samples
        # If you want GPU, you can add that later; keep it simple for now.


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    glb_path, out_path = resolve_paths(args.glb, args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not glb_path.exists():
        raise FileNotFoundError(glb_path)

    bpy = _require_bpy()

    target_col = ensure_collection(bpy, args.collection)
    clear_collection(bpy, target_col)

    new_objs = import_glb(bpy, glb_path)
    link_objects_to_collection(new_objs, target_col)

    configure_render(bpy, args.engine, args.samples, args.resolution)

    bpy.context.scene.render.filepath = str(out_path)
    bpy.ops.render.render(write_still=True)

    return 0


if __name__ == "__main__":
    # Blender passes script args after `--`
    try:
        idx = sys.argv.index("--")
        script_args = sys.argv[idx + 1 :]
    except ValueError:
        script_args = []

    try:
        raise SystemExit(main(script_args))
    except Exception as e:
        print(f"[render_glb.py] ERROR: {e}", file=sys.stderr)
        raise SystemExit(2)

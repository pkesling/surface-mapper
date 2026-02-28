"""surface_mapper.render.blender_runner module."""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from pathlib import Path

MACOS_BLENDER_APP = Path("/Applications/Blender.app/Contents/MacOS/Blender")
DEFAULT_SCRIPT_CANDIDATES = (
    Path("blender/scripts/render_glb.py"),
    Path("src/surface_mapper/blender/scripts/render_glb.py"),
)
PRESET_TEMPLATES = {
    "default": Path("assets/blender/templates/orthographic_hex_prism_v1.blend"),
    "classic": Path("assets/blender/templates/orthographic_hex_prism_v1.blend"),
    "neon": Path("assets/blender/templates/orthographic_hex_prism_v1.blend"),
}


def find_repo_root(start: Path | None = None) -> Path:
    """Find repo root."""
    origin = start or Path(__file__).resolve()
    for candidate in (origin, *origin.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise ValueError("Unable to locate repository root (pyproject.toml not found).")


def resolve_blender_binary(blender: str | None) -> Path:
    """Resolve blender binary."""
    if blender:
        candidate = Path(blender).expanduser().resolve()
        if candidate.exists():
            return candidate
        raise ValueError(f"Blender binary not found at: {candidate}")

    from_path = shutil.which("blender")
    if from_path:
        return Path(from_path).resolve()

    if sys.platform == "darwin" and MACOS_BLENDER_APP.exists():
        return MACOS_BLENDER_APP

    raise ValueError(
        "Could not find Blender. Install Blender and add it to PATH, or pass --blender "
        "(macOS default: /Applications/Blender.app/Contents/MacOS/Blender)."
    )


def resolve_script_path(repo_root: Path) -> Path:
    """Resolve script path."""
    for rel in DEFAULT_SCRIPT_CANDIDATES:
        candidate = (repo_root / rel).resolve()
        if candidate.exists():
            return candidate
    searched = ", ".join(str(repo_root / rel) for rel in DEFAULT_SCRIPT_CANDIDATES)
    raise ValueError(f"Blender render script not found. Looked in: {searched}")


def available_presets(repo_root: Path) -> dict[str, Path]:
    """Available presets."""
    return {
        name: (repo_root / rel).resolve()
        for name, rel in PRESET_TEMPLATES.items()
        if (repo_root / rel).exists()
    }


def resolve_template_path(repo_root: Path, preset: str, template: str | None) -> Path:
    """Resolve template path."""
    if template:
        template_path = Path(template).expanduser().resolve()
        if template_path.exists():
            return template_path
        raise ValueError(f"Template file not found: {template_path}")

    presets = available_presets(repo_root)
    key = preset.strip().lower()
    if key not in presets:
        available = ", ".join(sorted(presets)) if presets else "none found"
        raise ValueError(f"Unknown preset '{preset}'. Available presets: {available}")
    return presets[key]


def build_blender_command(
    blender_bin: Path,
    template_path: Path,
    script_path: Path,
    glb_path: Path,
    out_path: Path,
    collection: str,
    engine: str,
    samples: int,
    resolution: int,
) -> list[str]:
    """Build blender command."""
    return [
        str(blender_bin),
        "-b",
        str(template_path),
        "-P",
        str(script_path),
        "--",
        "--glb",
        str(glb_path),
        "--out",
        str(out_path),
        "--collection",
        collection,
        "--engine",
        engine,
        "--samples",
        str(samples),
        "--resolution",
        str(resolution),
    ]


def format_command(cmd: list[str]) -> str:
    """Format command."""
    return " ".join(shlex.quote(part) for part in cmd)


def run_blender_headless(cmd: list[str], verbose: bool) -> subprocess.CompletedProcess[str]:
    """Run blender headless."""
    return subprocess.run(
        cmd,
        check=False,
        capture_output=not verbose,
        text=True,
    )

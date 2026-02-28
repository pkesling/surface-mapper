# Contributing to SurfaceMapper

Thanks for your interest in contributing.

SurfaceMapper is maintainer-led and quality-focused. Contributions are welcome, and review is centered on clarity, correctness, and reproducibility.

## Project Ethos

- SurfaceMapper prioritizes accurate, precise geospatial representation.
- Aesthetics are welcome, but they must not silently change meaning.
- Defaults and presets should be publication-safe:
- Titles, legends, units, and scales should be explicit.
- No hidden exaggeration, implicit transforms, or ambiguous framing.

## Start With Discussion for Large Changes

Please open an issue or discussion before starting substantial work, including:

- New render styles or preset families
- New geometry/render modes
- Major CLI behavior changes
- Dependency strategy changes
- File format or output contract changes

This prevents surprise mega-PRs, reduces rework, and keeps the project coherent.

## What You Can Submit Directly

PRs are welcome without pre-discussion for:

- Bug fixes
- Documentation improvements
- Small refactors that preserve behavior

New presets and styles are also welcome. Start small (1-2 presets), then iterate through review.

If you want to contribute many styles, consider a separate preset-pack repository, or submit a smaller curated subset here first. We may later maintain an official/core vs community split, but that is not formalized yet.

## Practical Workflow

1. Fork the repository.
2. Create a focused branch from the current default branch.
3. Make your changes with clear commit messages.
4. Run tests locally.
5. Open a PR with context, rationale, and validation notes.

Current test command:

```bash
uv run pytest
```

Keep each PR focused on one logical change. Large mixed-scope PRs are hard to review and often delayed.

## Style and Quality Expectations

- Keep code readable and direct; avoid unnecessary abstractions.
- Preserve backward compatibility when reasonable.
- If a change is breaking, call it out explicitly in the PR description.
- For new visual outputs, include:
- At least one example image
- The exact command used to generate it
- Explicit legend/scale behavior in the PR notes

## Review and Maintainer Decisions

The maintainer reviews and merges changes, and may request revisions before approval.

Not every PR will be merged. If a PR is declined, feedback will be provided so contributors understand the decision and possible next steps.

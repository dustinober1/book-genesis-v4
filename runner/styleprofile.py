"""Per-project lint threshold overrides.

lint.py's ``Thresholds`` are seeded from a single reference draft's editorial
report and a handful of genre profiles -- useful defaults, but they encode
one book's tics and one editor's calibration, not this author's. A project
can override any threshold field by adding a ``style-profile.yaml`` at the
project root:

    lint:
      em_dash_per_1k: "3.2"
      phrase_per_10k: "6.0"

This module reads that file, coerces its string values to the numeric types
``Thresholds`` actually declares, and reports anything it does not
recognize instead of silently ignoring it -- matching the "a manifest typo
must not silently disable a gate" principle already applied to gate checks
(see gates.py's ``run_check``). An override that fails to coerce or that
targets an unknown field is a warning the caller must surface, never a
raised exception that aborts the whole lint run.

runner/corpus.py (baseline calibration from the author's own writing) is the
intended producer of this file; a user can also hand-write or hand-edit it.
Values are always written/read as quoted strings, matching the rest of this
project's hand-rolled YAML subset -- see filesystem.py's docstring on why
there is no real YAML parser here.

No external dependencies, matching the rest of runner/.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Dict, List, Tuple

from runner.filesystem import _load_simple_yaml_map  # the one YAML-ish parser in this repo
from runner.lint import Thresholds

STYLE_PROFILE_FILENAME = "style-profile.yaml"

# The block name inside style-profile.yaml that holds lint threshold
# overrides. `_load_simple_yaml_map` only understands two levels (top-level
# key -> {scalar: value}), so a bare `em_dash_per_1k: "3.2"` at zero indent
# would silently discard its own value (see filesystem._load_simple_yaml_map)
# -- every override must live nested under this block.
LINT_BLOCK = "lint"

_FIELD_TYPES: Dict[str, type] = {
    f.name: (int if f.type == "int" else float)
    for f in dataclasses.fields(Thresholds)
}


class StyleProfileWarning(str):
    """A human-readable problem with a style profile that did not stop it
    from loading. Subclassing str keeps callers that just want to print
    warnings simple, without hiding that this is a distinct concept from an
    error.
    """


def load_raw_overrides(path: Path) -> Dict[str, str]:
    """Read the `lint:` block of a style-profile.yaml. Returns {} if the
    file does not exist or declares no `lint:` block -- both are the normal
    case for a project that has not calibrated a personal baseline yet.
    """
    if not path.is_file():
        return {}
    entries = _load_simple_yaml_map(path)
    block = entries.get(LINT_BLOCK, {})
    return {k: v for k, v in block.items() if isinstance(v, str)}


def coerce_overrides(raw: Dict[str, str]) -> Tuple[Dict[str, object], List[str]]:
    """Coerce string values to the field's declared type and separate out
    anything that does not belong.

    Two ways an entry can be bad, reported as distinct warnings so a typo is
    debuggable: the key does not name a real Thresholds field, or the value
    does not parse as that field's type (an unquoted-looking float on an int
    field, a non-numeric string, etc).
    """
    coerced: Dict[str, object] = {}
    warnings: List[str] = []
    for key, value in raw.items():
        field_type = _FIELD_TYPES.get(key)
        if field_type is None:
            warnings.append(
                f"style-profile.yaml: unknown lint threshold {key!r} -- ignored. "
                f"Known keys: {', '.join(sorted(_FIELD_TYPES))}.")
            continue
        try:
            coerced[key] = field_type(value)
        except (TypeError, ValueError):
            warnings.append(
                f"style-profile.yaml: {key}={value!r} is not a valid "
                f"{field_type.__name__} -- ignored.")
    return coerced, warnings


def resolve_thresholds(
    *, profile: str = "", style_profile_path: Path | None = None,
) -> Tuple[Thresholds, List[str]]:
    """The base genre profile with any style-profile.yaml overrides applied
    on top. Never raises: a missing or override-free file just returns the
    genre default unchanged, and a bad override is dropped with a warning
    rather than aborting the lint run it's meant to improve.
    """
    base = Thresholds.for_profile(profile)
    if style_profile_path is None:
        return base, []
    raw = load_raw_overrides(style_profile_path)
    if not raw:
        return base, []
    coerced, warnings = coerce_overrides(raw)
    if not coerced:
        return base, warnings
    return base.with_overrides(coerced), warnings


def render_style_profile(overrides: Dict[str, object]) -> str:
    """Render a `lint:` block in this repo's flat YAML-subset dialect --
    the inverse of load_raw_overrides. Used by runner/corpus.py to write a
    derived style-profile.yaml the user can review and hand-edit.
    """
    lines = [f"{LINT_BLOCK}:"]
    for key in sorted(overrides):
        lines.append(f'  {key}: "{overrides[key]}"')
    return "\n".join(lines) + "\n"

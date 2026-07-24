"""Resolve the repo/skill roots the runner depends on.

The runner is distributed two ways:

1. Inside a checkout of this repo, where ``runner/`` sits next to
   ``skills/book-genesis-codex/``.
2. Installed by ``install.sh``/``install.ps1`` into a user's Claude Code
   home, where ``runner/`` and the skill directories are copied to
   separate locations (see ``BOOK_GENESIS_HOME`` below).

Resolution order:

1. ``BOOK_GENESIS_HOME`` env var, if set — treated as the directory that
   directly contains ``skills/`` (and, for repo_root() purposes, is also
   used as the root).
2. The parent of this file's directory (``parents[1]``) — correct inside
   a checkout, and also correct for the installer layout once the
   installer copies the skill directories alongside ``runner/`` (see
   install.sh/install.ps1 changes).

All lookups are functions, not module-level constants, so tests can
monkeypatch ``BOOK_GENESIS_HOME`` or pass an explicit override.
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_VAR = "BOOK_GENESIS_HOME"


def _candidates(override: Path | None = None) -> list[Path]:
    candidates: list[Path] = []
    if override is not None:
        candidates.append(Path(override))
    env_value = os.environ.get(_ENV_VAR)
    if env_value:
        candidates.append(Path(env_value))
    candidates.append(Path(__file__).resolve().parents[1])
    return candidates


def repo_root(override: Path | None = None) -> Path:
    """Return the first candidate root that looks valid.

    A root is valid if it contains ``skills/book-genesis-codex``. Raises
    ``FileNotFoundError`` naming every location tried if none match.
    """

    tried = []
    for candidate in _candidates(override):
        tried.append(candidate)
        if (candidate / "skills" / "book-genesis-codex").is_dir():
            return candidate
    tried_str = ", ".join(str(t) for t in tried)
    raise FileNotFoundError(
        "Could not locate the book-genesis-codex skill directory. Tried: "
        f"{tried_str}. Set {_ENV_VAR} to the directory containing 'skills/' "
        "if you are running an installed copy of the runner."
    )


def skill_root(override: Path | None = None) -> Path:
    return repo_root(override) / "skills" / "book-genesis-codex"


def manifest_path(override: Path | None = None) -> Path:
    return skill_root(override) / "references" / "pipeline" / "manifest.yaml"


def bestseller_studio_root(override: Path | None = None) -> Path:
    return repo_root(override) / "skills" / "book-bestseller-studio"


def agent_registry_path(override: Path | None = None) -> Path:
    return bestseller_studio_root(override) / "references" / "agent-registry.yaml"

"""Safely adopt an existing manuscript into a Book Genesis project.

Book Genesis has never had a "start from a draft I already wrote" path --
every project began at Phase 1 with a blank `manuscript/chapters/`. Novel
Forge's adoption flow (`/novel-adopt`) is a useful shape to borrow: copy
(never move) the source, verify by hash, never silently overwrite an
occupied destination, and reject anything that looks like a path-traversal
or symlink trick before touching the filesystem.

This is intentionally narrower than Novel Forge's version -- no DOCX/EPUB
conversion, no Pandoc dependency. It handles the common case (a folder of
`.md`/`.txt` chapter files) and leaves format conversion to the writer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import hashlib
from pathlib import Path
import shutil
from typing import List


ACCEPTED_SUFFIXES = {".md", ".txt"}


@dataclass
class AdoptedFile:
    source: str
    destination: str
    bytes: int
    source_sha256: str
    destination_sha256: str
    archived_previous: str = ""


@dataclass
class AdoptionReport:
    adopted: List[AdoptedFile] = field(default_factory=list)
    rejected: List[str] = field(default_factory=list)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _is_unsafe(source_root: Path, path: Path) -> str:
    """Return a rejection reason, or empty string if the path is safe."""

    if path.is_symlink():
        return "symlink"
    for parent in path.parents:
        if parent == source_root:
            break
        if parent.is_symlink():
            return "symlink ancestor"
    try:
        resolved = path.resolve()
        resolved.relative_to(source_root.resolve())
    except ValueError:
        return "resolves outside source directory (path traversal)"
    return ""


def _archive_existing(target: Path, dest: Path) -> str:
    today = date.today().isoformat()
    archive_dir = target / ".archive" / today / "files"
    n = 0
    candidate = archive_dir / dest.name
    while candidate.exists():
        n += 1
        candidate = archive_dir / f"{dest.stem}-{n}{dest.suffix}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(dest), str(candidate))
    return str(candidate.relative_to(target))


def adopt_manuscript(source: Path, target: Path) -> AdoptionReport:
    report = AdoptionReport()
    if not source.is_dir():
        report.rejected.append(f"source is not a directory: {source}")
        return report

    dest_dir = target / "manuscript" / "chapters"
    dest_dir.mkdir(parents=True, exist_ok=True)

    for path in sorted(source.iterdir()):
        if path.is_dir():
            continue
        if path.suffix.lower() not in ACCEPTED_SUFFIXES:
            report.rejected.append(f"{path.name}: unsupported file type {path.suffix!r}")
            continue

        unsafe_reason = _is_unsafe(source, path)
        if unsafe_reason:
            report.rejected.append(f"{path.name}: rejected ({unsafe_reason})")
            continue

        if path.stat().st_size == 0:
            report.rejected.append(f"{path.name}: empty source file")
            continue

        dest = dest_dir / path.name
        archived = ""
        if dest.exists():
            archived = _archive_existing(target, dest)

        source_hash = _sha256(path)
        shutil.copy2(path, dest)
        dest_hash = _sha256(dest)
        if dest_hash != source_hash:
            report.rejected.append(f"{path.name}: hash mismatch after copy, rolled back")
            dest.unlink(missing_ok=True)
            continue

        report.adopted.append(AdoptedFile(
            source=str(path), destination=str(dest.relative_to(target)),
            bytes=dest.stat().st_size, source_sha256=source_hash,
            destination_sha256=dest_hash, archived_previous=archived,
        ))

    return report


def render_adoption_report(report: AdoptionReport) -> str:
    lines = ["# Manuscript Adoption Report", ""]
    lines.append(f"Adopted {len(report.adopted)} file(s). Rejected {len(report.rejected)} file(s).")
    lines.append("")

    if report.adopted:
        lines.append("## Adopted")
        lines.append("")
        lines.append("| Source | Destination | Bytes | SHA-256 | Archived previous |")
        lines.append("|---|---|---|---|---|")
        for f in report.adopted:
            lines.append(
                f"| {f.source} | {f.destination} | {f.bytes} | {f.destination_sha256[:12]}… | "
                f"{f.archived_previous or '—'} |"
            )
        lines.append("")

    if report.rejected:
        lines.append("## Rejected")
        for item in report.rejected:
            lines.append(f"- {item}")
        lines.append("")

    lines.append(
        "Adopted chapters land at voice-intake / book-planning readiness only. "
        "No canon, outline, entity state, or evaluation is manufactured for them -- "
        "run `/entity-tracker` (BUILD mode) and `/continuity-guardian` before treating "
        "this manuscript as pipeline-ready."
    )
    return "\n".join(lines)

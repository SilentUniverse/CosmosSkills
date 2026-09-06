#!/usr/bin/env python3
"""Validate skill frontmatter, local links, and inter-skill call references."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable


NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FIELD_RE = re.compile(r"^([A-Za-z][A-Za-z0-9-]*):(?:[ \t]+(.*))?$")
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
INLINE_SLASH_RE = re.compile(r"`/([a-z][a-z0-9-]*)\b[^`\n]*`")
DOUBLE_HYPHEN_FLAG_RE = re.compile(r"(?<![\w-])--[a-z][a-z0-9-]*")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
# GitHub slugs: drop punctuation, keep word characters (incl. CJK), hyphenate each
# whitespace character without collapsing runs. Setext headings are not generated,
# so a setext-only target stays unflagged (prefer missing a break over a false one).
ANCHOR_PUNCTUATION_RE = re.compile(r"[^\w\s-]", re.UNICODE)
KNOWN_FIELDS = {
    "name",
    "description",
    "argument-hint",
    "disable-model-invocation",
    "paths",
    "icon",
    "color",
    "metadata",
    "license",
    "compatibility",
    "allowed-tools",
}
COLLECTION_FIELDS = {"paths", "metadata"}
CURSOR_COLORS = {
    "default",
    "green",
    "cyan",
    "blue",
    "purple",
    "magenta",
    "orange",
    "yellow",
    "red",
    "brand",
}
DEFAULT_ROOTS = ("workflow", "tooling")
MARKDOWN_EXCLUDED_PARTS = {".eval-campaigns", ".eval-runs", ".git", ".scratch", ".venv", "node_modules"}
RETIRED_SKILL_NAMES = {
    "caveman": "brief",
    "git-guardrails-claude-code": "shell-guardrails",
    "grilling": "grill",
    "merge-conflicts": "conflicts",
    "modern-cli-guardrails": "shell-guardrails",
}
NON_SKILL_SLASH_TOKENS = {"backticks", "c", "clear", "compact", "pattern", "settings", "tmp"}
# Coarse ceilings for always-resident surfaces (every turn pays them); growth beyond
# current headroom is a visible metric first, a red line only at these outer bounds.
DESCRIPTION_BUDGET_BYTES = 12_000
RESIDENT_POLICY_BUDGET_BYTES = 8_000


class SkillError(ValueError):
    pass


def _parse_scalar(raw: str, source: Path, line_number: int) -> object:
    if not raw:
        raise SkillError(f"{source}:{line_number}: empty scalar")
    if raw.startswith('"'):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SkillError(f"{source}:{line_number}: invalid quoted scalar: {exc.msg}") from exc
        if not isinstance(value, str):
            raise SkillError(f"{source}:{line_number}: expected a string")
        return value
    if raw.startswith("'"):
        if len(raw) < 2 or not raw.endswith("'"):
            raise SkillError(f"{source}:{line_number}: unterminated quoted scalar")
        return raw[1:-1].replace("''", "'")
    if raw in {"true", "false"}:
        return raw == "true"
    if ": " in raw or " #" in raw or raw[0] in "[{&*!|>@`\"'":
        raise SkillError(
            f"{source}:{line_number}: quote this YAML-sensitive scalar or use a folded block"
        )
    return raw


def parse_frontmatter(skill_file: Path) -> tuple[dict[str, object], int]:
    lines = skill_file.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise SkillError(f"{skill_file}:1: missing opening frontmatter delimiter")

    try:
        closing = lines.index("---", 1)
    except ValueError as exc:
        raise SkillError(f"{skill_file}: missing closing frontmatter delimiter") from exc

    values: dict[str, object] = {}
    index = 1
    while index < closing:
        line = lines[index]
        match = FIELD_RE.fullmatch(line)
        if not match:
            raise SkillError(
                f"{skill_file}:{index + 1}: frontmatter supports one top-level scalar per field"
            )
        key, raw = match.group(1), match.group(2) or ""
        if key not in KNOWN_FIELDS:
            raise SkillError(f"{skill_file}:{index + 1}: unsupported frontmatter field {key!r}")
        if key in values:
            raise SkillError(f"{skill_file}:{index + 1}: duplicate frontmatter field {key!r}")

        if raw in {">", ">-", "|", "|-"}:
            block: list[str] = []
            index += 1
            while index < closing and (not lines[index] or lines[index][0].isspace()):
                if lines[index]:
                    if not lines[index].startswith("  "):
                        raise SkillError(
                            f"{skill_file}:{index + 1}: block scalar content must use two-space indentation"
                        )
                    block.append(lines[index][2:])
                else:
                    block.append("")
                index += 1
            if not block:
                raise SkillError(f"{skill_file}:{index + 1}: empty block scalar for {key!r}")
            values[key] = "\n".join(block) if raw.startswith("|") else " ".join(
                part.strip() for part in block if part.strip()
            )
            continue

        if not raw and key in COLLECTION_FIELDS:
            block: list[str] = []
            index += 1
            while index < closing and (not lines[index] or lines[index][0].isspace()):
                if lines[index]:
                    if not lines[index].startswith("  "):
                        raise SkillError(
                            f"{skill_file}:{index + 1}: collection content must use two-space indentation"
                        )
                    block.append(lines[index][2:])
                index += 1
            if not block:
                raise SkillError(f"{skill_file}:{index + 1}: empty collection for {key!r}")
            if key == "paths":
                items: list[str] = []
                for item in block:
                    if not item.startswith("- "):
                        raise SkillError(
                            f"{skill_file}: paths entries must be a two-space-indented YAML list"
                        )
                    value = _parse_scalar(item[2:].strip(), skill_file, index + 1)
                    if not isinstance(value, str):
                        raise SkillError(f"{skill_file}: each paths entry must be a string")
                    items.append(value)
                values[key] = items
            else:
                mapping: dict[str, object] = {}
                for item in block:
                    match = FIELD_RE.fullmatch(item)
                    if not match or not match.group(2):
                        raise SkillError(f"{skill_file}: metadata must contain scalar key-value pairs")
                    metadata_key, metadata_raw = match.group(1), match.group(2)
                    mapping[metadata_key] = _parse_scalar(metadata_raw, skill_file, index + 1)
                values[key] = mapping
            continue

        values[key] = _parse_scalar(raw, skill_file, index + 1)
        index += 1

    if not any(line.strip() for line in lines[closing + 1 :]):
        raise SkillError(f"{skill_file}:{closing + 2}: skill body is empty")
    return values, closing + 1


def validate_skill(skill_file: Path) -> list[str]:
    errors: list[str] = []
    try:
        values, _ = parse_frontmatter(skill_file)
    except (OSError, UnicodeError, SkillError) as exc:
        return [str(exc)]

    name = values.get("name")
    description = values.get("description")
    if not isinstance(name, str):
        errors.append(f"{skill_file}: missing string field 'name'")
    else:
        if len(name) > 64 or not NAME_RE.fullmatch(name):
            errors.append(
                f"{skill_file}: name must be 1-64 lowercase letters, digits, or single hyphens"
            )
        if name != skill_file.parent.name:
            errors.append(
                f"{skill_file}: name {name!r} must match directory {skill_file.parent.name!r}"
            )

    if not isinstance(description, str):
        errors.append(f"{skill_file}: missing string field 'description'")
    else:
        if not 1 <= len(description) <= 1024:
            errors.append(f"{skill_file}: description must contain 1-1024 characters")
        if not description.startswith("Use when ") and not description.startswith("Use only when "):
            errors.append(f"{skill_file}: description must start with 'Use when' or 'Use only when'")

    invocation = values.get("disable-model-invocation")
    if invocation is not None and not isinstance(invocation, bool):
        errors.append(f"{skill_file}: disable-model-invocation must be true or false")
    hint = values.get("argument-hint")
    if hint is not None and not isinstance(hint, str):
        errors.append(f"{skill_file}: argument-hint must be a string")
    elif isinstance(hint, str) and DOUBLE_HYPHEN_FLAG_RE.search(hint):
        errors.append(f"{skill_file}: skill flags in argument-hint must use a single hyphen")
    paths = values.get("paths")
    if paths is not None and not isinstance(paths, (str, list)):
        errors.append(f"{skill_file}: paths must be a comma-separated string or a list")
    for key in ("icon", "license", "compatibility", "allowed-tools"):
        value = values.get(key)
        if value is not None and not isinstance(value, str):
            errors.append(f"{skill_file}: {key} must be a string")
    compatibility = values.get("compatibility")
    if isinstance(compatibility, str) and len(compatibility) > 500:
        errors.append(f"{skill_file}: compatibility must contain at most 500 characters")
    color = values.get("color")
    if color is not None and (not isinstance(color, str) or color not in CURSOR_COLORS):
        errors.append(f"{skill_file}: color must be one of {', '.join(sorted(CURSOR_COLORS))}")
    metadata = values.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        errors.append(f"{skill_file}: metadata must be a mapping")
    elif isinstance(metadata, dict) and any(not isinstance(value, str) for value in metadata.values()):
        errors.append(f"{skill_file}: metadata values must be strings")
    return errors


def resident_budget(skill_files: Iterable[Path], cwd: Path) -> tuple[list[str], str]:
    """Measure the per-turn resident surfaces: parsed descriptions plus the shared policy.

    Descriptions ride the system prompt on every turn, so the aggregate is the token
    budget worth watching; invalid frontmatter is skipped here because validate_skill
    already reports it."""
    errors: list[str] = []
    total = 0
    count = 0
    for skill_file in skill_files:
        try:
            values, _ = parse_frontmatter(skill_file)
        except (OSError, UnicodeError, SkillError):
            continue
        description = values.get("description")
        if isinstance(description, str):
            total += len(description.encode("utf-8"))
            count += 1
    if total > DESCRIPTION_BUDGET_BYTES:
        errors.append(
            f"resident budget: {count} descriptions total {total}B exceeds {DESCRIPTION_BUDGET_BYTES}B"
        )
    policy = cwd / "claude" / "CLAUDE.md"
    try:
        policy_bytes = policy.stat().st_size
    except OSError:
        policy_bytes = None
    if policy_bytes is not None and policy_bytes > RESIDENT_POLICY_BUDGET_BYTES:
        errors.append(
            f"resident budget: claude/CLAUDE.md {policy_bytes}B exceeds {RESIDENT_POLICY_BUDGET_BYTES}B"
        )
    policy_text = f"{policy_bytes}B" if policy_bytes is not None else "absent"
    summary = (
        f"resident: {count} descriptions {total}B/{DESCRIPTION_BUDGET_BYTES}B, "
        f"claude/CLAUDE.md {policy_text}/{RESIDENT_POLICY_BUDGET_BYTES}B"
    )
    return errors, summary


def github_slug(heading: str) -> str:
    text = ANCHOR_PUNCTUATION_RE.sub("", heading.strip())
    return re.sub(r"\s", "-", text.lower())


def heading_slugs(markdown_path: Path) -> set[str]:
    """Anchors GitHub would generate for a file's out-of-fence ATX headings.

    Duplicate headings get the -1, -2, ... suffixes GitHub appends."""
    slugs: set[str] = set()
    counts: dict[str, int] = {}
    in_fence = False
    for line in markdown_path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = HEADING_RE.match(line)
        if not match:
            continue
        slug = github_slug(match.group(2))
        if not slug:
            continue
        index = counts.get(slug, 0)
        counts[slug] = index + 1
        slugs.add(slug if index == 0 else "%s-%d" % (slug, index))
    return slugs


def validate_links(markdown_file: Path, slug_cache: dict | None = None) -> list[str]:
    errors: list[str] = []
    cache = slug_cache if slug_cache is not None else {}

    def slugs_of(path: Path) -> set[str]:
        if path not in cache:
            cache[path] = heading_slugs(path)
        return cache[path]

    text = markdown_file.read_text(encoding="utf-8")
    in_fence = False
    for line_number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        prose = re.sub(r"`[^`]*`", "", line)
        for match in LINK_RE.finditer(prose):
            destination = match.group(1).strip()
            if destination.startswith("<") and destination.endswith(">"):
                destination = destination[1:-1]
            destination = destination.split(maxsplit=1)[0]
            path_text = destination.split("#", 1)[0]
            anchor = destination.split("#", 1)[1] if "#" in destination else ""
            if not path_text or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", path_text):
                if anchor and not path_text and "/" not in anchor:
                    if anchor not in slugs_of(markdown_file):
                        errors.append(
                            f"{markdown_file}:{line_number}: local anchor does not match any heading: {destination}"
                        )
                continue
            if any(token in path_text for token in ("<", ">", "{", "}")):
                continue
            target = (markdown_file.parent / path_text).resolve()
            if not target.exists():
                errors.append(
                    f"{markdown_file}:{line_number}: local link target does not exist: {destination}"
                )
            elif (
                anchor
                and target.suffix == ".md"
                and "/" not in anchor
                and anchor not in slugs_of(target)
            ):
                errors.append(
                    f"{markdown_file}:{line_number}: link anchor matches no heading in {path_text}: {destination}"
                )
    return errors


def validate_retired_references(markdown_file: Path) -> list[str]:
    errors: list[str] = []
    text = markdown_file.read_text(encoding="utf-8")
    for old_name, new_name in RETIRED_SKILL_NAMES.items():
        match = re.search(rf"(?<![A-Za-z0-9-]){re.escape(old_name)}(?![A-Za-z0-9-])", text)
        if match:
            line_number = text.count("\n", 0, match.start()) + 1
            errors.append(
                f"{markdown_file}:{line_number}: retired skill reference {old_name!r}; use {new_name!r}"
            )
    return errors


def validate_skill_calls(markdown_file: Path, skill_names: set[str]) -> list[str]:
    errors: list[str] = []
    text = markdown_file.read_text(encoding="utf-8")
    in_fence = False
    for line_number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in INLINE_SLASH_RE.finditer(line):
            target = match.group(1)
            if line[match.end(1) : match.end(1) + 1] == "/":
                continue
            if target in skill_names:
                if DOUBLE_HYPHEN_FLAG_RE.search(match.group()):
                    errors.append(
                        f"{markdown_file}:{line_number}: skill flags for /{target} must use a single hyphen"
                    )
                continue
            if target in NON_SKILL_SLASH_TOKENS:
                continue
            errors.append(
                f"{markdown_file}:{line_number}: slash reference {target!r} is not an installed skill"
            )
    return errors


def collect_skills(inputs: Iterable[str], cwd: Path) -> list[Path]:
    paths = [cwd / item for item in inputs] if inputs else [cwd / item for item in DEFAULT_ROOTS]
    skills: set[Path] = set()
    for path in paths:
        path = path.resolve()
        if path.is_file():
            if path.name != "SKILL.md":
                raise SkillError(f"{path}: expected SKILL.md or a directory")
            skills.add(path)
        elif path.is_dir():
            direct = path / "SKILL.md"
            if direct.is_file():
                skills.add(direct.resolve())
            else:
                skills.update(candidate.resolve() for candidate in path.rglob("SKILL.md"))
        else:
            raise SkillError(f"{path}: path does not exist")
    return sorted(skills)


def run(inputs: Iterable[str], cwd: Path) -> tuple[list[str], int, int]:
    requested = list(inputs)
    skill_files = collect_skills(requested, cwd)
    errors: list[str] = []
    markdown_files: set[Path] = set()
    catalog_markdown_files: set[Path] = set()
    names: dict[str, Path] = {}
    for skill_file in skill_files:
        errors.extend(validate_skill(skill_file))
        try:
            values, _ = parse_frontmatter(skill_file)
        except (OSError, UnicodeError, SkillError):
            values = {}
        name = values.get("name")
        if isinstance(name, str):
            if name in names and names[name] != skill_file:
                errors.append(f"{skill_file}: duplicate skill name {name!r}; first seen at {names[name]}")
            names[name] = skill_file
        package_files = set(skill_file.parent.rglob("*.md"))
        markdown_files.update(package_files)
        catalog_markdown_files.update(package_files)

    known_names = set(names)
    for root_name in DEFAULT_ROOTS:
        root = cwd / root_name
        if not root.is_dir():
            continue
        catalog_markdown_files.update(root.rglob("*.md"))
        for catalog_skill in root.rglob("SKILL.md"):
            try:
                catalog_values, _ = parse_frontmatter(catalog_skill)
            except (OSError, UnicodeError, SkillError):
                continue
            catalog_name = catalog_values.get("name")
            if isinstance(catalog_name, str):
                known_names.add(catalog_name)

    for scope in [cwd / item for item in requested] if requested else [cwd]:
        if not scope.is_dir():
            continue
        markdown_files.update(
            path.resolve()
            for path in scope.rglob("*.md")
            if not MARKDOWN_EXCLUDED_PARTS.intersection(path.relative_to(scope).parts)
        )

    slug_cache: dict[Path, set[str]] = {}
    for markdown_file in sorted(markdown_files):
        try:
            errors.extend(validate_links(markdown_file, slug_cache))
            if markdown_file in catalog_markdown_files:
                errors.extend(validate_retired_references(markdown_file))
            errors.extend(validate_skill_calls(markdown_file, known_names))
        except (OSError, UnicodeError) as exc:
            errors.append(str(exc))
    return errors, len(skill_files), len(markdown_files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="SKILL.md files, skill directories, or catalog roots")
    args = parser.parse_args(argv)
    try:
        errors, skill_count, markdown_count = run(args.paths, Path.cwd())
        budget_errors, budget_summary = resident_budget(collect_skills(args.paths, Path.cwd()), Path.cwd())
    except SkillError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    errors.extend(budget_errors)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"FAILED: {len(errors)} error(s)", file=sys.stderr)
        return 1
    print(f"OK: {skill_count} skills, {markdown_count} Markdown files; {budget_summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

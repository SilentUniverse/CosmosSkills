#!/usr/bin/env bash
# Install skills into ~/.claude/skills (symlinks) and copy the global layer.
# Usage: bash install.sh [--dry-run] [--force] [--target DIR] [--claude-root DIR]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
TARGET="${HOME}/.claude/skills"
CLAUDE_ROOT="${HOME}/.claude"
DRY_RUN=0
FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --force) FORCE=1; shift ;;
    --target) TARGET="$2"; shift 2 ;;
    --claude-root) CLAUDE_ROOT="$2"; shift 2 ;;
    *) echo "Unknown flag: $1" >&2; exit 2 ;;
  esac
done

skill_name() {
  awk '
    BEGIN { p = 0 }
    /^---[[:space:]]*$/ { p++; next }
    p == 1 && $0 ~ /^name:[[:space:]]*/ {
      sub(/^name:[[:space:]]*/, "")
      gsub(/^["'\'']+|["'\'']+$/, "")
      gsub(/[[:space:]]+$/, "")
      print
      exit
    }
    p >= 2 { exit }
  ' "$1"
}

SKILL_MDS=()
while IFS= read -r md; do
  SKILL_MDS+=("$md")
done < <(find "$ROOT" -name SKILL.md -type f | LC_ALL=C sort)
if [[ ${#SKILL_MDS[@]} -eq 0 ]]; then
  echo "No SKILL.md found under $ROOT. Put install.sh at repository root." >&2
  exit 1
fi

NAMES=()
SOURCES=()
for md in "${SKILL_MDS[@]}"; do
  name="$(skill_name "$md")"
  dir="$(dirname "$md")"
  if [[ -z "$name" ]]; then
    echo "Skip (frontmatter has no name): $md" >&2
    continue
  fi
  if [[ ${#NAMES[@]} -gt 0 ]]; then
    for existing in "${NAMES[@]}"; do
      if [[ "$existing" == "$name" ]]; then
        echo "Duplicate name '$name'" >&2
        exit 1
      fi
    done
  fi
  NAMES+=("$name")
  SOURCES+=("$dir")
done

echo "Found ${#NAMES[@]} skills, target: $TARGET"
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[DryRun] Preview only."
fi

if [[ ! -d "$TARGET" ]]; then
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[DryRun] Create folder: $TARGET"
  else
    mkdir -p "$TARGET"
  fi
fi

BACKUP_DIR="$TARGET/_backup-$(date +%Y%m%d-%H%M%S)"
linked=0
backed_up=0

for i in "${!NAMES[@]}"; do
  name="${NAMES[$i]}"
  src="${SOURCES[$i]}"
  link="$TARGET/$name"

  if [[ -e "$link" || -L "$link" ]]; then
    if [[ -L "$link" ]]; then
      if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "[DryRun] Recreate link $name"
      else
        rm -f "$link"
      fi
    elif [[ "$FORCE" -eq 1 ]]; then
      if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "[DryRun] -Force remove real folder $link"
      else
        rm -rf "$link"
      fi
    else
      dest="$BACKUP_DIR/$name"
      if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "[DryRun] Backup $name -> $dest, then relink"
      else
        mkdir -p "$BACKUP_DIR"
        mv "$link" "$dest"
        backed_up=$((backed_up + 1))
      fi
    fi
  fi

  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[DryRun] Link %-26s -> %s\n' "$name" "$src"
  else
    ln -s "$src" "$link"
    printf 'Linked %-26s -> %s\n' "$name" "$src"
    linked=$((linked + 1))
  fi
done

# Orphan symlinks that still point into this repo but are not a current skill.
for entry in "$TARGET"/*; do
  [[ -e "$entry" || -L "$entry" ]] || continue
  [[ -L "$entry" ]] || continue
  dest="$(readlink "$entry")"
  case "$dest" in
    "$ROOT"/*) ;;
    *) continue ;;
  esac
  base="$(basename "$entry")"
  keep=0
  for n in "${NAMES[@]}"; do
    [[ "$n" == "$base" ]] && keep=1 && break
  done
  if [[ "$keep" -eq 0 ]]; then
    if [[ "$DRY_RUN" -eq 1 ]]; then
      echo "[DryRun] Remove orphan link: $entry"
    else
      rm -f "$entry"
      echo "Removed orphan link: $entry"
    fi
  fi
done

copy_file() {
  local src="$1" dest="$2" label="$3"
  [[ -f "$src" ]] || return 0
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[DryRun] Copy $label -> $dest"
  else
    mkdir -p "$(dirname "$dest")"
    cp -f "$src" "$dest"
    echo "$label: copied -> $dest"
  fi
}

echo
copy_file "$ROOT/engineering/ARTIFACT-FORMAT.md" "$TARGET/ARTIFACT-FORMAT.md" "Contract: ARTIFACT-FORMAT.md"
for gate in verify-artifacts.ps1 verify-artifacts.sh; do
  copy_file "$ROOT/engineering/$gate" "$TARGET/$gate" "Gate: $gate"
done

if [[ -d "$ROOT/ClaudeMD" ]]; then
  copy_file "$ROOT/ClaudeMD/CLAUDE.md" "$CLAUDE_ROOT/CLAUDE.md" "Guidelines: CLAUDE.md"
  ref_target="$CLAUDE_ROOT/references"
  ref_count=0
  for ref in "$ROOT/ClaudeMD"/*.md; do
    [[ -f "$ref" ]] || continue
    [[ "$(basename "$ref")" == "CLAUDE.md" ]] && continue
    if [[ "$DRY_RUN" -eq 1 ]]; then
      :
    else
      mkdir -p "$ref_target"
      cp -f "$ref" "$ref_target/$(basename "$ref")"
    fi
    ref_count=$((ref_count + 1))
  done
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[DryRun] Copy $ref_count reference file(s) -> $ref_target"
  else
    if [[ -d "$ref_target" ]]; then
      for deployed in "$ref_target"/*.md; do
        [[ -f "$deployed" ]] || continue
        bn="$(basename "$deployed")"
        [[ -f "$ROOT/ClaudeMD/$bn" ]] || rm -f "$deployed"
      done
    fi
    echo "References: copied $ref_count file(s) -> $ref_target"
  fi
fi

HOOKS=(
  "misc/modern-cli-guardrails/scripts/block-legacy-cli.sh"
  "misc/git-guardrails-claude-code/scripts/block-dangerous-git.sh"
)
hooks_target="$CLAUDE_ROOT/hooks"
copied_hooks=0
for rel in "${HOOKS[@]}"; do
  src="$ROOT/$rel"
  if [[ ! -f "$src" ]]; then
    echo "Listed hook script not found: $src" >&2
    exit 1
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[DryRun] Copy hook $rel -> $hooks_target"
  else
    mkdir -p "$hooks_target"
    cp -f "$src" "$hooks_target/"
    chmod +x "$hooks_target/$(basename "$src")"
    copied_hooks=$((copied_hooks + 1))
  fi
done
if [[ "$DRY_RUN" -eq 0 && "$copied_hooks" -gt 0 ]]; then
  echo "Hooks: copied $copied_hooks script(s) -> $hooks_target"
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Dry run done. Remove --dry-run to apply."
else
  echo "Done: $linked links created."
  if [[ "$backed_up" -gt 0 ]]; then
    echo "Backed up $backed_up existing folders to: $BACKUP_DIR"
  fi
  echo "Use /<name> in Claude Code. hys-setup is the project bootstrap entry."
fi

#!/usr/bin/env bash
set -euo pipefail

# Book Genesis installer for macOS/Linux.
# Installs full skill folders, including supporting references, to ~/.claude/.

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$REPO_DIR/skills"
KNOWLEDGE_DIR="$REPO_DIR/knowledge"
AGENTS_DIR="$REPO_DIR/agents"
RUNNER_DIR="$REPO_DIR/runner"
TARGET_SKILLS="$HOME/.claude/skills"
TARGET_KNOWLEDGE="$HOME/.claude/knowledge"
TARGET_AGENTS="$HOME/.claude/agents"
TARGET_RUNNER_ROOT="$HOME/.claude/book-genesis-runner"
TARGET_RUNNER="$TARGET_RUNNER_ROOT/runner"
RUNNER_SKILL_DEPS=("book-genesis-codex" "book-bestseller-studio")

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo -e "${BLUE}Book Genesis${NC}"
echo -e "${YELLOW}V4/V5 legacy system + portable Codex edition${NC}"
echo ""
echo -e "${YELLOW}Installing skills, supporting references, agents, and knowledge base${NC}"
echo ""

if [ ! -d "$SKILLS_DIR" ]; then
  echo -e "${RED}Error: skills/ directory not found. Run this script from the repository root.${NC}"
  exit 1
fi

mkdir -p "$TARGET_SKILLS" "$TARGET_KNOWLEDGE" "$TARGET_AGENTS"

count=0
for skill_dir in "$SKILLS_DIR"/*/; do
  skill_name=$(basename "$skill_dir")
  if [ -f "$skill_dir/SKILL.md" ]; then
    rm -rf "$TARGET_SKILLS/$skill_name"
    mkdir -p "$TARGET_SKILLS/$skill_name"
    cp -R "$skill_dir". "$TARGET_SKILLS/$skill_name/"
    echo -e "  ${GREEN}+${NC} $skill_name"
    count=$((count + 1))
  fi
done

# skills/optional/ holds skills book-genesis-full (Production Mode) dispatches
# to but Craft Mode doesn't need by default (voice-fingerprint, reader-persona,
# entity-tracker, continuity-guardian, book-auto). Install them flattened into
# the same skills/ namespace so /book-genesis-full's phase dispatches resolve.
# skills/deprecated/ (chaos-engine, quality-gate, dialogue-polish, hook-craft,
# mechanical-preprocess) is intentionally NOT installed — a benchmark found
# these hurt output quality or they were merged into book-editor; see
# skills/book-genesis-full/SKILL.md's "Post-V6 Recalibration" section.
if [ -d "$SKILLS_DIR/optional" ]; then
  for skill_dir in "$SKILLS_DIR/optional"/*/; do
    skill_name=$(basename "$skill_dir")
    if [ -f "$skill_dir/SKILL.md" ]; then
      rm -rf "$TARGET_SKILLS/$skill_name"
      mkdir -p "$TARGET_SKILLS/$skill_name"
      cp -R "$skill_dir". "$TARGET_SKILLS/$skill_name/"
      echo -e "  ${GREEN}+${NC} $skill_name (optional, used by book-genesis-full)"
      count=$((count + 1))
    fi
  done
fi

kb_count=0
if [ -d "$KNOWLEDGE_DIR" ]; then
  for kb_file in "$KNOWLEDGE_DIR"/*.md; do
    if [ -f "$kb_file" ]; then
      cp "$kb_file" "$TARGET_KNOWLEDGE/"
      echo -e "  ${GREEN}+${NC} knowledge/$(basename "$kb_file")"
      kb_count=$((kb_count + 1))
    fi
  done

  # Knowledge subdirectories (genre-packs/, etc.) are copied whole.
  for kb_subdir in "$KNOWLEDGE_DIR"/*/; do
    if [ -d "$kb_subdir" ]; then
      sub_name=$(basename "$kb_subdir")
      rm -rf "$TARGET_KNOWLEDGE/$sub_name"
      mkdir -p "$TARGET_KNOWLEDGE/$sub_name"
      cp -R "$kb_subdir". "$TARGET_KNOWLEDGE/$sub_name/"
      sub_files=$(find "$TARGET_KNOWLEDGE/$sub_name" -type f | wc -l | tr -d ' ')
      echo -e "  ${GREEN}+${NC} knowledge/$sub_name/ ($sub_files files)"
      kb_count=$((kb_count + sub_files))
    fi
  done
fi

runner_count=0
if [ -d "$RUNNER_DIR" ]; then
  rm -rf "$TARGET_RUNNER"
  mkdir -p "$TARGET_RUNNER"
  cp -R "$RUNNER_DIR"/. "$TARGET_RUNNER/"
  find "$TARGET_RUNNER" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
  runner_count=$(find "$TARGET_RUNNER" -name '*.py' -type f | wc -l | tr -d ' ')
  echo -e "  ${GREEN}+${NC} runner/ ($runner_count modules — lint + chronology gates)"

  # The runner resolves the manifest/skill root relative to its own
  # location (or via BOOK_GENESIS_HOME). Copy the skills it depends on
  # alongside it so init/prepare-phase/advance-phase/gate/demo work from
  # an installed copy, not just inside a repo checkout.
  mkdir -p "$TARGET_RUNNER_ROOT/skills"
  for dep in "${RUNNER_SKILL_DEPS[@]}"; do
    if [ -d "$SKILLS_DIR/$dep" ]; then
      rm -rf "$TARGET_RUNNER_ROOT/skills/$dep"
      mkdir -p "$TARGET_RUNNER_ROOT/skills/$dep"
      cp -R "$SKILLS_DIR/$dep"/. "$TARGET_RUNNER_ROOT/skills/$dep/"
      echo -e "  ${GREEN}+${NC} book-genesis-runner/skills/$dep (runner dependency)"
    fi
  done
fi

agent_count=0
if [ -d "$AGENTS_DIR" ]; then
  for agent_file in "$AGENTS_DIR"/*.md; do
    if [ -f "$agent_file" ]; then
      cp "$agent_file" "$TARGET_AGENTS/"
      echo -e "  ${GREEN}+${NC} agent/$(basename "$agent_file")"
      agent_count=$((agent_count + 1))
    fi
  done
fi

echo ""
echo -e "${GREEN}Done.${NC} $count skills + $agent_count agents + $kb_count knowledge files + $runner_count runner modules installed"
echo ""
echo -e "Skills:    ${BLUE}$TARGET_SKILLS${NC}"
echo -e "Agents:    ${BLUE}$TARGET_AGENTS${NC}"
echo -e "Knowledge: ${BLUE}$TARGET_KNOWLEDGE${NC}"
echo -e "Runner:    ${BLUE}$TARGET_RUNNER${NC}"
echo ""
echo "Quality gates (run from any project directory):"
echo -e "  ${BLUE}python3 $TARGET_RUNNER_ROOT/runner/cli.py gate <project>${NC}"
echo -e "  ${BLUE}python3 $TARGET_RUNNER_ROOT/runner/cli.py lint <project>${NC}"
echo -e "  ${BLUE}python3 $TARGET_RUNNER_ROOT/runner/cli.py check-timeline <project>${NC}"
echo -e "  ${BLUE}python3 $TARGET_RUNNER_ROOT/runner/cli.py human-pass plan <project>${NC}  (hand-rewrite a few lines per chapter)"
echo -e "  ${BLUE}python3 $TARGET_RUNNER_ROOT/runner/cli.py baseline <project> --corpus <your-writing>${NC}  (personal calibration)"
echo ""
echo "Open Claude Code and type /book-genesis or /book-genesis-codex to start writing."
echo ""

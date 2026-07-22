#!/usr/bin/env bash
# LEXBRIDGE Knowledge Repository — local setup script
# -----------------------------------------------------------------------
# Reproduces the Sprint 2.5 reorganization on your machine, where you
# already have the source data (LEXBRIDGE_Knowledge_Graph_v1.zip). This
# script does NOT re-download or invent any data — it only moves your
# existing kb_merged/knowledge/ tree into the new repo layout and drops
# in the scaffold files (registry, scripts, README, etc.) that are
# provided alongside this script in the same output folder.
#
# Usage:
#   1. Unzip LEXBRIDGE_Knowledge_Graph_v1.zip somewhere, e.g. ~/Downloads/graph
#      -> should produce ~/Downloads/graph/kb_merged/knowledge/{laws,judgments,...}
#   2. Place this script + the scaffold/ folder (README.md, CHANGELOG.md,
#      schemas/, scripts/, metadata/, indexes/registry_manifest.json) next
#      to each other.
#   3. Run: ./setup_knowledge_repo.sh ~/Downloads/graph/kb_merged/knowledge ~/lexbridge-knowledge
#
set -euo pipefail

SRC="${1:?Usage: $0 <path-to-kb_merged/knowledge> <path-to-new-repo-dir>}"
DEST="${2:?Usage: $0 <path-to-kb_merged/knowledge> <path-to-new-repo-dir>}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -d "$SRC/laws" ] || [ ! -d "$SRC/judgments" ]; then
  echo "ERROR: $SRC does not look like a kb_merged/knowledge folder (expected laws/, judgments/, ...)." >&2
  exit 1
fi

mkdir -p "$DEST/knowledge" "$DEST/indexes" "$DEST/scripts" "$DEST/schemas" "$DEST/metadata"

for d in laws judgments principles procedures deadlines templates references; do
  if [ -d "$SRC/$d" ]; then
    cp -r "$SRC/$d" "$DEST/knowledge/$d"
  fi
done

[ -f "$SRC/KNOWLEDGE_GRAPH_INDEX.json" ] && cp "$SRC/KNOWLEDGE_GRAPH_INDEX.json" "$DEST/indexes/"
[ -f "$SRC/MASTER_INDEX.json" ] && cp "$SRC/MASTER_INDEX.json" "$DEST/indexes/"
[ -d "$SRC/search_index" ] && cp -r "$SRC/search_index" "$DEST/indexes/search_index"

# Drop in the scaffold (registry, scripts, README, etc.) shipped alongside this script.
cp "$SCRIPT_DIR/README.md" "$DEST/"
cp "$SCRIPT_DIR/CHANGELOG.md" "$DEST/"
cp "$SCRIPT_DIR/.gitignore" "$DEST/"
cp "$SCRIPT_DIR/schemas/document-types.registry.json" "$DEST/schemas/"
cp "$SCRIPT_DIR/scripts/build_index.py" "$DEST/scripts/"
cp "$SCRIPT_DIR/metadata/PROVENANCE.md" "$DEST/metadata/"

echo "Reorganized knowledge repo written to: $DEST"
echo "Running registry validation..."
python3 "$DEST/scripts/build_index.py" --root "$DEST"

echo
echo "Next steps:"
echo "  cd $DEST"
echo "  git init"
echo "  git remote add origin https://github.com/diesadw/lexbridge-knowledge.git"
echo "  git add -A"
echo "  git commit -m 'Sprint 2.5: initial knowledge repository split'"
echo "  git branch -M main"
echo "  git push -u origin main"

#!/usr/bin/env bash
# Usage: ./release.sh [major|minor|patch|x.y.z]
# Default: patch
set -euo pipefail

BUMP=${1:-patch}
METADATA="archaeotrench_utilities/metadata.txt"

# Read current version from metadata.txt
CURRENT=$(grep '^version=' "$METADATA" | cut -d= -f2)
IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT"

case "$BUMP" in
  major) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
  minor) MINOR=$((MINOR + 1)); PATCH=0 ;;
  patch) PATCH=$((PATCH + 1)) ;;
  [0-9]*.[0-9]*.[0-9]*)
    MAJOR="${BUMP%%.*}"; REST="${BUMP#*.}"; MINOR="${REST%%.*}"; PATCH="${REST##*.}" ;;
  *)
    echo "Usage: $0 [major|minor|patch|x.y.z]" >&2
    exit 1 ;;
esac

NEW="${MAJOR}.${MINOR}.${PATCH}"

# Bump version in metadata.txt (Python handles macOS/Linux sed differences)
python3 - <<PYEOF
import re, pathlib
p = pathlib.Path("$METADATA")
p.write_text(re.sub(r"^version=.*", "version=$NEW", p.read_text(), flags=re.M))
PYEOF

echo "Version: ${CURRENT} -> ${NEW}"

git add "$METADATA"
git commit -m "chore: release v${NEW}"
git tag "v${NEW}"
git push origin HEAD "v${NEW}"

echo "Tagged v${NEW} and pushed — GitHub Actions will create the release."

#!/usr/bin/env bash
# Put release/README_public.md into the README.md of the public repo, only when it differs.
# Used by .github/workflows/release.yml after a (non-prerelease) release was created; GH_TOKEN must be allowed to
# write to the repo. Env: REPO (default foolshang/PoE-Filter-Generator), BRANCH (default main),
# FILE (default release/README_public.md), TAG (only used in the commit message).
set -euo pipefail
REPO="${REPO:-foolshang/PoE-Filter-Generator}"
BRANCH="${BRANCH:-main}"
FILE="${FILE:-release/README_public.md}"
TAG="${TAG:-release}"

if [ ! -s "$FILE" ]; then
  echo "::error::$FILE is missing or empty"
  exit 1
fi

# the README on the branch: its blob sha (needed to update it) and its content (to see whether it changed)
sha=$(gh api "repos/$REPO/contents/README.md?ref=$BRANCH" --jq .sha)
if gh api "repos/$REPO/contents/README.md?ref=$BRANCH" -H "Accept: application/vnd.github.raw" | cmp -s - "$FILE"; then
  echo "README.md of $REPO ($BRANCH) already matches $FILE - nothing to commit"
  exit 0
fi

content=$(base64 -w0 "$FILE")
gh api -X PUT "repos/$REPO/contents/README.md" \
  -f message="docs: README for $TAG" \
  -f content="$content" \
  -f sha="$sha" \
  -f branch="$BRANCH" \
  --jq '"README.md updated: " + .commit.html_url'

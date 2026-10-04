#!/usr/bin/env bash
# Owner-run deployment: the context contains committed code only, never local tooling.
set -euo pipefail

repo_root=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
cd "$repo_root"
if [[ -n $(git status --porcelain --untracked-files=normal) ]]; then
    echo "Refusing to deploy a dirty working tree; commit the intended code first." >&2
    exit 1
fi

stage_dir=$(mktemp -d "${TMPDIR:-/tmp}/llm-gateway-demo.XXXXXX")
trap 'rm -rf -- "$stage_dir"' EXIT
# Read the Dockerfile from the archive too, so concurrent edits cannot enter the context.
git archive HEAD | tar -x -C "$stage_dir"
git rev-parse HEAD > "$stage_dir/BUILD_COMMIT"
cp "$stage_dir/deploy/demo/Dockerfile" "$stage_dir/Dockerfile"
insta --agent build "$stage_dir" --port 3000
# InstaCloud prints the public URL on a successful deployment; leave it visible.
insta --agent deploy "$stage_dir" --group appliance --port 3000

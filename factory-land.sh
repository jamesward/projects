#!/usr/bin/env bash
# Land changes on main through a pull request. main has no bypass (DESIGN.md 14), so every change,
# the owner's included, is a branch, a PR and a squash merge.
#
#   ./factory-land.sh "commit message" path...
#
# Commits the listed files (only those) from the working tree onto a new branch, pushes it, opens a
# PR, squash-merges it and updates local main. Each merge starts a short `heroku control` run.
set -euo pipefail

msg=${1:?usage: ./factory-land.sh "commit message" path...}
shift
[ $# -gt 0 ] || { echo "list the files to commit" >&2; exit 1; }

[ "$(git branch --show-current)" = main ] || { echo "run this from main" >&2; exit 1; }
git pull -q --ff-only

branch="land/$(date +%Y%m%d-%H%M%S)"
git switch -q -c "$branch"
git add -- "$@"
git commit -q -m "$msg"
git push -q -u origin "$branch"
pr=$(gh pr create --base main --head "$branch" --title "${msg:0:72}" --body "$msg")
gh pr merge "$pr" --squash --delete-branch
git switch -q main 2>/dev/null || true
git pull -q --ff-only
git log -1 --format='landed %h %s'

#!/usr/bin/env bash
# Checklist for putting a repo under the factory: prints what's done, what's missing,
# and the exact browser step for the Claude GitHub App (which only GitHub's UI can change
# when the installation uses "Only select repositories").
#
#   ./factory-repo-check.sh webjars/webjars-locator-lite
set -uo pipefail
repo="${1:?usage: $0 owner/repo}"
owner="${repo%%/*}"

ok()   { printf '  [x] %s\n' "$*"; }
todo() { printf '  [ ] %s\n' "$*"; }

echo "== $repo"
default="$(gh repo view "$repo" --json defaultBranchRef -q .defaultBranchRef.name)" || { echo "cannot read $repo with gh"; exit 1; }
echo "default branch: $default"

echo
echo "1. Factory files on '$default' (routines only see the default branch)"
has() { gh api "repos/$repo/contents/$1?ref=$default" --silent 2>/dev/null; }
files=".factory/MAINTENANCE.md AGENTS.md .github/workflows"
if has build.sbt || has pom.xml || has build.gradle.kts || has build.gradle; then
  files="$files .mcp.json .claude/settings.json .kiro/settings/mcp.json"   # build projects: MCP config
else
  files="$files .slugignore"                                              # static sites: no MCP
fi
for f in $files; do
  if has "$f"; then ok "$f"; else todo "$f (missing)"; fi
done
if gh api "repos/$repo/contents/.github/dependabot.yml?ref=$default" --silent 2>/dev/null; then todo ".github/dependabot.yml should be removed"; fi
if gh api "repos/$repo/contents/.factory/skills/zen-of-projects/SKILL.md?ref=$default" --silent 2>/dev/null; then
  echo "  note: .factory/skills/zen-of-projects/SKILL.md (unreleased Skill test copy) is present"
fi

if gh label list -R "$repo" --json name -q '.[].name' 2>/dev/null | grep -qx needs-human; then ok "label needs-human"; else
  todo "label needs-human: gh label create needs-human -R $repo --color B60205 --description 'The maintenance routine needs a maintainer decision'"; fi

echo
echo "2. Claude GitHub App access for '$owner'"
type="$(gh api "users/$owner" --jq .type)"
if [ "$type" = "Organization" ]; then
  inst="$(gh api "orgs/$owner/installations" --jq '.installations[] | select(.app_slug=="claude") | "\(.id) \(.repository_selection)"' 2>/dev/null)"
  if [ -z "$inst" ]; then
    todo "Claude App is not installed on $owner: https://github.com/apps/claude/installations/new"
  else
    id="${inst%% *}"; sel="${inst##* }"
    if [ "$sel" = "all" ]; then
      ok "installed on all repositories of $owner"
    else
      todo "In the browser, open https://github.com/organizations/$owner/settings/installations/$id"
      echo "      Repository access -> Only select repositories -> Select repositories -> add '${repo#*/}' -> Save."
      echo "      (gh can't check this list, so check it once per new repo. Skip if it's already listed.)"
    fi
  fi
else
  todo "In the browser, open https://github.com/settings/installations, click Configure next to Claude,"
  echo "      then Repository access -> Select repositories -> add '${repo#*/}' -> Save (skip if already listed)."
fi

echo
echo "3. Routine"
if grep -q "| \`$repo\` |" "$(dirname "$0")/FACTORY.md"; then
  ok "listed in FACTORY.md (Managed Repos & Schedules)"
else
  todo "add '$repo' to a table in FACTORY.md 'Managed Repos & Schedules' (weekly is the default)"
fi
echo "      then run: $(dirname "$0")/factory-routines-sync.py --apply   (creates the routine; report-only without --apply)"
echo
echo "4. Verify: only after step 2 is done in the browser (nothing here can check it), run it once"
echo "   (claude -p \"/schedule run <repo name> maintenance\") and read the run log. A push or 'create branch' 403"
echo "   ('Claude doesn't have GitHub access') means step 2 isn't done yet."

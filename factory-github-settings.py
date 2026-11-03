#!/usr/bin/env python3
"""Check (and with --apply, fix) consistent GitHub settings on every maintained repo.

    ./factory-github-settings.py           # report only
    ./factory-github-settings.py --apply   # change settings that differ

Repos come from FACTORY.md: every "Source: https://github.com/<owner>/<repo>" (and bare repo URL) in
"Maintained Projects" (not "No Longer Maintained"), plus every repo in the "Managed Repos & Schedules" tables.

Settings:
  - You (the gh user) watch the repo with "All activity" (GitHub's default is "Participating").
  - Wiki is off. If the wiki has pages, it's reported and left on unless --force-wiki is given.
  - Projects are off.
  - Head branches are deleted when a PR merges. The routines merge through the REST API, which keeps
    the branch, and a leftover `claude/maintenance` made the next run's push fail as non-fast-forward.
  - Dependabot alerts (vulnerability alerts) are on, for the owner; routines don't read them (their
    token can't), they keep every dependency on its latest release instead. Dependabot security
    update PRs are off: they ignored projects' documented exceptions (for example a Java 8 target).
Archived repos and repos you don't administer are reported and skipped. Settings the token can't
read are reported with "?" (cloud sessions' GitHub App can read some of them but change none).
factory-sync.py runs check() for every repo and keeps a needs-human issue in jamesward/projects
open while anything differs; this script, run locally with --apply, is how it gets fixed.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

FACTORY = Path(__file__).with_name("FACTORY.md")
APPLY = "--apply" in sys.argv
FORCE_WIKI = "--force-wiki" in sys.argv


def gh(*args, check=True):
    r = subprocess.run(["gh", "api", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip())
    return r


def repos():
    md = FACTORY.read_text()
    found = set()
    maintained = md[md.index("## Maintained Projects"):]
    if "\n## No Longer Maintained" in maintained:
        maintained = maintained[:maintained.index("\n## No Longer Maintained")]
    for m in re.finditer(r"https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", maintained):
        found.add(m.group(1).removesuffix(".git"))
    for m in re.finditer(r"^\| `([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)` \|", md, re.M):
        found.add(m.group(1))
    return sorted(found)


def wiki_has_pages(repo):
    r = subprocess.run(["git", "ls-remote", f"https://github.com/{repo}.wiki.git"],
                       capture_output=True, text=True, timeout=60,
                       env={"GIT_TERMINAL_PROMPT": "0", "PATH": "/usr/bin:/bin:/run/current-system/sw/bin:"
                            + __import__("os").environ.get("PATH", "")})
    return r.returncode == 0 and bool(r.stdout.strip())


def check(repo, force_wiki=None):
    """What differs from the factory's settings on one repo, without changing anything:
      repo      GitHub's name for it (differs from FACTORY.md after a rename)
      skipped   why it wasn't checked (archived, or unreadable), else None
      admin     whether this token administers it (changes other than watching need admin)
      todo      [(kind, description)]: what --apply would change
      problems  [description]: what needs a decision (wiki with pages, a rename)
      unknown   [description]: settings this token couldn't read. Cloud sessions reach GitHub
                through the Claude GitHub App, which has only read access to administration and
                can't see the owner's watch setting, so "unknown" isn't "wrong".
    """
    force_wiki = FORCE_WIKI if force_wiki is None else force_wiki
    out = {"repo": repo, "skipped": None, "admin": False, "todo": [], "problems": [], "unknown": []}
    r = gh(f"repos/{repo}", check=False)
    if r.returncode != 0:
        out["skipped"] = f"can't read it ({(r.stderr.strip() or r.stdout.strip())[:80]})"
        return out
    info = json.loads(r.stdout)
    if info["full_name"].lower() != repo.lower():
        out["problems"].append(f"GitHub redirects to {info['full_name']}; update FACTORY.md")
        out["repo"] = repo = info["full_name"]
    if info.get("archived"):
        out["skipped"] = "archived"
        return out
    admin = out["admin"] = info.get("permissions", {}).get("admin", False)
    todo, unknown = out["todo"], out["unknown"]

    sub = gh(f"repos/{repo}/subscription", check=False)
    if sub.returncode == 0 or "HTTP 404" in sub.stderr:  # 404: not subscribed
        s = json.loads(sub.stdout) if sub.returncode == 0 else {}
        if not (s.get("subscribed") and not s.get("ignored")):
            now = "ignoring" if s.get("ignored") else ("watching" if s.get("subscribed") else "participating only")
            todo.append(("watch", f"watch all activity (now: {now})"))
    else:
        unknown.append("watch setting")

    if info.get("has_wiki"):
        if wiki_has_pages(repo) and not force_wiki:
            out["problems"].append("wiki is on and has pages; left on (re-run with --force-wiki to turn it off)")
        else:
            todo.append(("wiki", "turn wiki off"))
    if info.get("has_projects"):
        todo.append(("projects", "turn projects off"))
    if "delete_branch_on_merge" not in info:
        unknown.append("delete head branches on merge")
    elif not info["delete_branch_on_merge"]:
        todo.append(("delete_branch", "delete head branches on merge"))

    alerts = gh(f"repos/{repo}/vulnerability-alerts", check=False)  # 204 on, 404 off (or not visible)
    if alerts.returncode == 0:
        pass
    elif admin and "HTTP 404" in alerts.stderr:
        todo.append(("alerts", "turn Dependabot alerts on"))
    else:
        unknown.append("Dependabot alerts")
    fixes = (info.get("security_and_analysis") or {}).get("dependabot_security_updates", {}).get("status")
    if fixes is None and not admin:  # admins of private repos without it get null too: not enabled
        unknown.append("Dependabot security update PRs")
    elif fixes == "enabled":
        todo.append(("fixes", "turn Dependabot security update PRs off"))
    return out


def main():
    changes = problems = 0
    for repo in repos():
        c = check(repo)
        repo = c["repo"]
        for p in c["problems"]:
            print(f"!  {repo}: {p}"); problems += 1
        if c["skipped"]:
            if c["skipped"] == "archived":
                print(f".  {repo}: archived, skipped")
            else:
                print(f"!! {repo}: {c['skipped']}"); problems += 1
            continue
        if c["unknown"]:
            print(f"?  {repo}: couldn't read {', '.join(c['unknown'])}"); problems += 1
        todo = c["todo"]
        if not todo:
            if not c["unknown"]:
                print(f"=  {repo}: ok")
            continue
        if not c["admin"] and any(k != "watch" for k, _ in todo):
            print(f"!! {repo}: needs {', '.join(d for k, d in todo if k != 'watch')} but you aren't an admin")
            problems += 1
            todo = [t for t in todo if t[0] == "watch"]
            if not todo:
                continue
        print(f"~  {repo}: " + "; ".join(d for _, d in todo))
        changes += len(todo)
        if APPLY:
            for kind, _ in todo:
                if kind == "watch":
                    gh("-X", "PUT", f"repos/{repo}/subscription", "-F", "subscribed=true", "-F", "ignored=false", "--silent")
                elif kind == "wiki":
                    gh("-X", "PATCH", f"repos/{repo}", "-F", "has_wiki=false", "--silent")
                elif kind == "projects":
                    gh("-X", "PATCH", f"repos/{repo}", "-F", "has_projects=false", "--silent")
                elif kind == "delete_branch":
                    gh("-X", "PATCH", f"repos/{repo}", "-F", "delete_branch_on_merge=true", "--silent")
                elif kind == "alerts":
                    gh("-X", "PUT", f"repos/{repo}/vulnerability-alerts", "--silent")
                elif kind == "fixes":
                    gh("-X", "DELETE", f"repos/{repo}/automated-security-fixes", "--silent")
    verb = "made" if APPLY else "needed (run with --apply)"
    print(f"\n{changes} change(s) {verb}; {problems} item(s) need attention.")


if __name__ == "__main__":
    main()

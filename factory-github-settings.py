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
  - Dependabot alerts (vulnerability alerts) are on, and Dependabot security update PRs are off: the
    maintenance routine handles open alerts in its rolling PR (zen-of-projects), within each
    project's documented exceptions (for example a Java 8 target).
Archived repos and repos you don't administer are reported and skipped.
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


def main():
    changes = problems = 0
    for repo in repos():
        r = gh(f"repos/{repo}", check=False)
        if r.returncode != 0:
            print(f"!! {repo}: can't read it ({r.stderr.strip()[:80]})"); problems += 1; continue
        info = json.loads(r.stdout)
        if info["full_name"].lower() != repo.lower():
            print(f"!! {repo}: GitHub redirects to {info['full_name']}; update FACTORY.md"); problems += 1
            repo = info["full_name"]
        if info.get("archived"):
            print(f".  {repo}: archived, skipped"); continue
        admin = info.get("permissions", {}).get("admin", False)
        todo = []

        sub = gh(f"repos/{repo}/subscription", check=False)
        s = json.loads(sub.stdout) if sub.returncode == 0 else {}
        if not (s.get("subscribed") and not s.get("ignored")):
            now = "ignoring" if s.get("ignored") else ("watching" if s.get("subscribed") else "participating only")
            todo.append(("watch", f"watch all activity (now: {now})"))

        if info.get("has_wiki"):
            if wiki_has_pages(repo) and not FORCE_WIKI:
                print(f"!  {repo}: wiki is on and has pages; left on (re-run with --force-wiki to turn it off)")
                problems += 1
            else:
                todo.append(("wiki", "turn wiki off"))
        if info.get("has_projects"):
            todo.append(("projects", "turn projects off"))

        if admin:
            alerts = gh(f"repos/{repo}/vulnerability-alerts", check=False).returncode == 0  # 204 on, 404 off
            if not alerts:
                todo.append(("alerts", "turn Dependabot alerts on"))
            fixes = (info.get("security_and_analysis") or {}).get("dependabot_security_updates", {}).get("status")
            if fixes == "enabled":
                todo.append(("fixes", "turn Dependabot security update PRs off"))

        if not todo:
            print(f"=  {repo}: ok"); continue
        if not admin and any(k != "watch" for k, _ in todo):
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
                elif kind == "alerts":
                    gh("-X", "PUT", f"repos/{repo}/vulnerability-alerts", "--silent")
                elif kind == "fixes":
                    gh("-X", "DELETE", f"repos/{repo}/automated-security-fixes", "--silent")
    verb = "made" if APPLY else "needed (run with --apply)"
    print(f"\n{changes} change(s) {verb}; {problems} item(s) need attention.")


if __name__ == "__main__":
    main()

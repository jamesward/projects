#!/usr/bin/env python3
"""Sync the factory's canonical files into every managed repo, without running any routine.

    ./factory-sync.py                  # report drift only (dry run)
    ./factory-sync.py --apply          # open/update a 'Factory sync:' PR per drifted repo, merge after CI
    ./factory-sync.py --list           # print the managed repos (for add_repo in a cloud session)
    ./factory-sync.py owner/repo ...   # limit to these repos

Managed repos are the ones in FACTORY.md's schedule tables. For each, the default branch is
compared with the canonical factory files:

  .factory/MAINTENANCE.md    the bootstrap in the released zen-of-projects Skill (start.jamesward.com);
                             a no-Skills-dependency variant for NO_SKILLS_DEP; CUSTOM_MAINTENANCE skipped
  .claude/sbt-mcp-stdio.sh   ./sbt-mcp-stdio.sh (sbt repos)
  .mcp.json                  the factory-owned server entry (sbt-mcp bridge, or javadocs); others kept
  .claude/settings.json      that server in enabledMcpjsonServers (+ the Skill fetch permission for
                             NO_SKILLS_DEP); other settings kept
  .kiro/settings/mcp.json    the factory-owned server entry; others kept
  .github/dependabot.yml     must not exist
  label needs-human          must exist

AGENTS.md and everything else are left to each repo's maintenance routine. --apply commits to the
bot-owned branch claude/factory-sync, opens or updates one PR titled 'Factory sync: ...', and
squash-merges it once its CI checks have run and passed. A PR with failing or no checks gets the
needs-human label and a comment. A PR whose checks are still running is left for the next run.
It never triggers a routine. Uses only git and `gh api` (REST), so it also works in cloud sessions.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
FACTORY = HERE / "FACTORY.md"
BRIDGE = HERE / "sbt-mcp-stdio.sh"
SKILL_URL = "https://start.jamesward.com"
BRANCH = "claude/factory-sync"
CHECK_WAIT_SECONDS = int(os.environ.get("FACTORY_SYNC_CHECK_WAIT", "1200"))

# Site repos with their own MAINTENANCE.md (not the Skill's bootstrap) and no MCP servers.
CUSTOM_MAINTENANCE = {"jamesward/ai4jvm", "MindviewLLC/podcast"}
# Repos that deliberately don't depend on com.jamesward:skills (see their AGENTS.md).
NO_SKILLS_DEP = {"skillsjars/skillsjars-gradle-plugin", "skillsjars/skillsjars-maven-plugin",
                 "skillsjars/skillsjars-example-spring-ai"}

JAVADOCS = {"type": "http", "url": "https://www.javadocs.dev/mcp"}
FETCH_CMD = ("mkdir -p /tmp/zen-of-projects && curl -fsSL --retry 5 --retry-delay 10 --retry-all-errors "
             "https://start.jamesward.com -o /tmp/zen-of-projects/SKILL.md")
LABEL = {"name": "needs-human", "color": "B60205",
         "description": "The maintenance routine needs a maintainer decision"}


def run(*cmd, cwd=None, check=True, input=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, input=input)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}: {(r.stderr or r.stdout).strip()}")
    return r


def gh(path, method="GET", fields=None, check=True):
    cmd = ["gh", "api", "-X", method, path]
    data = None
    if fields is not None:
        cmd += ["--input", "-"]
        data = json.dumps(fields)
    for attempt in range(4):
        r = run(*cmd, check=False, input=data)
        if r.returncode == 0:
            return json.loads(r.stdout) if r.stdout.strip() else None
        err = (r.stderr or r.stdout).strip()
        if not re.search(r"HTTP 5\d\d|EOF|timeout|connection", err, re.I) or attempt == 3:
            if check:
                raise RuntimeError(f"gh api {method} {path}: {err}")
            return None
        time.sleep(5 * (attempt + 1))


# ---------- canonical content ----------

def managed_repos():
    md = FACTORY.read_text()
    start = md.index("### Managed repos (updated daily)")
    end = md.index("\n## ", start)
    return sorted(set(re.findall(r"^\| `([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)` \|", md[start:end], re.M)))


def bootstrap():
    req = urllib.request.Request(SKILL_URL, headers={"User-Agent": "factory-sync"})
    skill = urllib.request.urlopen(req, timeout=60).read().decode()
    m = re.search(r"^````markdown\n(.*?)^````$", skill, re.S | re.M)
    if not m:
        sys.exit(f"no ````markdown bootstrap block in {SKILL_URL}")
    return m.group(1)


def no_skills_bootstrap(boot):
    """Bootstrap steps 1-3 replaced by a fetch of the published Skill."""
    a = boot.index("1. Update the Skills dependency")
    b = boot.index("and don't delete it.", boot.index("3. Read `.kiro/skills"))
    b = boot.index("\n", b)
    return boot[:a] + f"""1. Fetch the zen-of-projects Skill. This repo has no `com.jamesward:skills` dependency (see
   `AGENTS.md`), so read the published Skill directly:

   ```bash
   {FETCH_CMD}
   ```

   If it fails, quote the exact error and stop.
2. Read `/tmp/zen-of-projects/SKILL.md` and follow its "Maintenance Routine" section, using
   `AGENTS.md` for this project's commands and documented exceptions. Skip any step about the
   Skills dependency or extracting Skills. While an unreleased version of the Skill is being
   tested, `.factory/skills/zen-of-projects/SKILL.md` exists. Read that file instead, and don't
   delete it.""" + boot[b:]


# ---------- per-repo desired state ----------

def load_json(p):
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except ValueError:
        return None  # unparseable: report, don't touch


def put_server(p, name, entry, changes, drop_prefix=None):
    j = load_json(p)
    if j is None:
        changes.append(f"{p.name}: not valid JSON, left alone")
        return None
    servers = j.setdefault("mcpServers", {})
    for k in [k for k in servers if drop_prefix and k.startswith(drop_prefix) and k != name]:
        del servers[k]
    if servers.get(name) != entry:
        servers[name] = entry
        return j
    return None


def desired(repo, d, boot):
    """Edit the checkout at d toward the canonical files; return a list of change descriptions."""
    d = Path(d)
    changes = []
    kind = "sbt" if (d / "build.sbt").exists() else (
        "jvm" if any((d / f).exists() for f in ("pom.xml", "build.gradle.kts", "build.gradle")) else "site")

    def write(rel, text, why):
        p = d / rel
        if not p.exists() or p.read_text() != text:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
            changes.append(why)

    def write_json(rel, obj, why):
        if obj is not None:
            write(rel, json.dumps(obj, indent=2) + "\n", why)

    for f in (".github/dependabot.yml", ".github/dependabot.yaml"):
        if (d / f).exists():
            (d / f).unlink()
            changes.append(f"remove {f} (the routine keeps dependencies current)")

    if repo in CUSTOM_MAINTENANCE or kind == "site":
        return kind, changes

    text = no_skills_bootstrap(boot) if repo in NO_SKILLS_DEP else boot
    write(".factory/MAINTENANCE.md", text, ".factory/MAINTENANCE.md: current bootstrap from the zen-of-projects Skill")
    if (d / ".factory/DAILY.md").exists():
        (d / ".factory/DAILY.md").unlink()
        changes.append("remove .factory/DAILY.md (renamed to MAINTENANCE.md)")

    if kind == "sbt":
        mcp = load_json(d / ".mcp.json") or {}
        kiro = load_json(d / ".kiro/settings/mcp.json") or {}
        names = [k for k in list(mcp.get("mcpServers", {})) + list(kiro.get("mcpServers", {})) if k.startswith("sbt-mcp")]
        name = names[0] if names else f"sbt-mcp-{repo.split('/')[1]}"
        port = re.search(r"mcpPort\s*:=\s*(\d+)", (d / "build.sbt").read_text())
        write(".claude/sbt-mcp-stdio.sh", BRIDGE.read_text(), ".claude/sbt-mcp-stdio.sh: current sbt-mcp stdio bridge")
        os.chmod(d / ".claude/sbt-mcp-stdio.sh", 0o755)
        bridge = {"type": "stdio", "command": "bash", "args": [".claude/sbt-mcp-stdio.sh"], "timeout": 1800000}
        write_json(".mcp.json", put_server(d / ".mcp.json", name, bridge, changes, "sbt-mcp"),
                   f".mcp.json: {name} uses the stdio bridge with a 30-minute timeout")
        if port:
            http = {"type": "http", "url": f"http://127.0.0.1:{port.group(1)}/", "timeout": 1800000, "disabled": False}
            write_json(".kiro/settings/mcp.json", put_server(d / ".kiro/settings/mcp.json", name, http, changes, "sbt-mcp"),
                       f".kiro/settings/mcp.json: {name} on port {port.group(1)} with a 30-minute timeout")
        else:
            changes.append("build.sbt has no mcpPort; .kiro/settings/mcp.json left alone")
        server = name
    else:
        write_json(".mcp.json", put_server(d / ".mcp.json", "javadocs", JAVADOCS, changes),
                   ".mcp.json: javadocs MCP server")
        write_json(".kiro/settings/mcp.json", put_server(d / ".kiro/settings/mcp.json", "javadocs", JAVADOCS, changes),
                   ".kiro/settings/mcp.json: javadocs MCP server")
        server = "javadocs"

    st = load_json(d / ".claude/settings.json")
    if st is None:
        changes.append(".claude/settings.json: not valid JSON, left alone")
    else:
        before = json.dumps(st, sort_keys=True)
        en = st.setdefault("enabledMcpjsonServers", [])
        if server not in en:
            en.append(server)
        if repo in NO_SKILLS_DEP:
            allow = st.setdefault("permissions", {}).setdefault("allow", [])
            if f"Bash({FETCH_CMD})" not in allow:
                allow.append(f"Bash({FETCH_CMD})")
        if json.dumps(st, sort_keys=True) != before:
            write_json(".claude/settings.json", st, f".claude/settings.json: approve {server}")
    return kind, changes


# ---------- GitHub ----------

def ensure_label(repo, apply):
    names = {l["name"] for l in gh(f"repos/{repo}/labels?per_page=100")}
    if LABEL["name"] in names:
        return []
    if apply:
        gh(f"repos/{repo}/labels", "POST", LABEL)
    return ["create the needs-human label"]


def open_pr(repo):
    owner = repo.split("/")[0]
    prs = gh(f"repos/{repo}/pulls?state=open&head={owner}:{BRANCH}")
    return prs[0] if prs else None


def checks_state(repo, sha):
    runs = gh(f"repos/{repo}/commits/{sha}/check-runs?per_page=100").get("check_runs", [])
    statuses = gh(f"repos/{repo}/commits/{sha}/status").get("statuses", [])
    if not runs and not statuses:
        return "none"
    if any(r["status"] != "completed" for r in runs) or any(s["state"] == "pending" for s in statuses):
        return "pending"
    bad = [r["name"] for r in runs if r["conclusion"] not in ("success", "skipped", "neutral")]
    bad += [s["context"] for s in statuses if s["state"] != "success"]
    return "failure: " + ", ".join(bad) if bad else "success"


def needs_human(repo, number, why):
    gh(f"repos/{repo}/issues/{number}/labels", "POST", {"labels": ["needs-human"]})
    gh(f"repos/{repo}/issues/{number}/comments", "POST", {"body": f"Factory sync can't merge this PR: {why}"})


def clone(repo, branch, d, attempts=3):
    for i in range(attempts):
        r = run("git", "clone", "-q", "--depth", "1", "--branch", branch, f"https://github.com/{repo}", str(d), check=False)
        if r.returncode == 0:
            return
        run("rm", "-rf", str(d), check=False)
        if i == attempts - 1:
            raise RuntimeError(f"git clone failed: {(r.stderr or r.stdout).strip().splitlines()[-1]}")
        time.sleep(10 * (i + 1))


# ---------- main ----------

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    repos = managed_repos()
    if "--list" in sys.argv:
        print("\n".join(repos))
        return
    if args:
        unknown = set(args) - set(repos)
        if unknown:
            sys.exit(f"not managed (not in FACTORY.md's schedule tables): {', '.join(sorted(unknown))}")
        repos = args
    boot = bootstrap()
    pending_prs = []
    drifted = 0
    work = Path(tempfile.mkdtemp(prefix="factory-sync-"))
    for repo in repos:
        try:
            info = gh(f"repos/{repo}")
            if info.get("archived"):
                print(f".  {repo}: archived, skipped")
                continue
            default = info["default_branch"]
            d = work / repo.replace("/", "__")
            pr = open_pr(repo)
            clone(repo, default, d)
            kind, changes = desired(repo, d, boot)
            label = ensure_label(repo, apply)
            if not changes:
                print(f"=  {repo} ({kind}): in sync{'; ' + label[0] if label else ''}"
                      + (f"; open PR #{pr['number']} left for merge check" if pr else ""))
                if pr and apply:
                    pending_prs.append((repo, pr["number"]))
                continue
            drifted += 1
            print(f"~  {repo} ({kind}):" + "".join(f"\n     - {c}" for c in changes + label))
            if not apply:
                continue
            run("git", "checkout", "-q", "-B", BRANCH, cwd=d)
            run("git", "add", "-A", cwd=d)
            msg = "Factory sync: " + "; ".join(c.split(":")[0] for c in changes)
            body_lines = "\n".join(f"- {c}" for c in changes)
            run("git", "commit", "-q", "-m", msg[:72], "-m", body_lines, cwd=d)  # the environment's git identity
            # The branch is owned by this script and always rebuilt from the default branch.
            run("git", "push", "-q", "--force", "origin", f"HEAD:refs/heads/{BRANCH}", cwd=d)
            body = (f"Synced from the factory ([jamesward/projects](https://github.com/jamesward/projects)) by "
                    f"`factory-sync.py`. Changes:\n\n{body_lines}\n\n"
                    "Only factory-owned files and entries change. This PR merges once CI passes; it doesn't run "
                    "the maintenance routine.")
            if pr:
                gh(f"repos/{repo}/pulls/{pr['number']}", "PATCH", {"title": msg[:72], "body": body})
                number = pr["number"]
            else:
                number = gh(f"repos/{repo}/pulls", "POST",
                            {"title": msg[:72], "head": BRANCH, "base": default, "body": body})["number"]
            print(f"   PR #{number}: https://github.com/{repo}/pull/{number}")
            pending_prs.append((repo, number))
        except Exception as e:  # report and continue with the other repos
            print(f"!! {repo}: {e}")

    if apply and pending_prs:
        print(f"\nWaiting up to {CHECK_WAIT_SECONDS}s for CI on {len(pending_prs)} PR(s)...")
        started = time.time()
        deadline = started + CHECK_WAIT_SECONDS
        waiting = list(pending_prs)
        time.sleep(30)
        while waiting:
            still = []
            for repo, number in waiting:
                try:
                    pr = gh(f"repos/{repo}/pulls/{number}")
                    if pr["state"] != "open":
                        print(f"   {repo}#{number}: {pr['state']}")
                        continue
                    if "needs-human" in [l["name"] for l in pr["labels"]]:
                        print(f"   {repo}#{number}: labeled needs-human, left for a maintainer")
                        continue
                    state = checks_state(repo, pr["head"]["sha"])
                    if state == "success":
                        gh(f"repos/{repo}/pulls/{number}/merge", "PUT", {"merge_method": "squash"})
                        gh(f"repos/{repo}/git/refs/heads/{BRANCH}", "DELETE", check=False)
                        print(f"   {repo}#{number}: CI passed, merged")
                    elif state == "none":
                        if time.time() > started + 300:  # give checks 5 minutes to appear
                            needs_human(repo, number, "no CI checks ran on this PR.")
                            print(f"   {repo}#{number}: no CI checks, labeled needs-human")
                        else:
                            still.append((repo, number))
                    elif state == "pending":
                        still.append((repo, number))
                    else:
                        needs_human(repo, number, f"CI {state}.")
                        print(f"   {repo}#{number}: CI {state}, labeled needs-human")
                except Exception as e:
                    print(f"!! {repo}#{number}: {e}")
            waiting = still
            if waiting and time.time() > deadline:
                for repo, number in waiting:
                    print(f"   {repo}#{number}: CI still running, left for the next run")
                break
            if waiting:
                time.sleep(30)

    print(f"\n{drifted} of {len(repos)} repo(s) drifted." + ("" if apply or not drifted else " Run with --apply to fix."))
    run("rm", "-rf", str(work), check=False)


if __name__ == "__main__":
    main()

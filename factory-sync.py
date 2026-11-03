#!/usr/bin/env python3
"""Sync the factory's canonical files into every managed repo, without running any routine.

    ./factory-sync.py                  # report drift only (dry run)
    ./factory-sync.py --apply          # open/update a 'Factory sync:' PR per drifted repo, merge after CI
    ./factory-sync.py --apply --no-merge  # open/update the PRs only (the daily routine): each repo's next
                                          # maintenance run merges its PR once CI passes, or run --apply
    ./factory-sync.py --list           # print the managed repos (for add_repo in a cloud session)
    ./factory-sync.py owner/repo ...   # limit to these repos
    ./factory-sync.py --digest         # only list open items that need the owner (see below); Mondays also last week's numbers
    ./factory-sync.py --digest --weekly  # the last week's numbers any day

Managed repos are the ones in FACTORY.md's schedule tables. For each, the default branch is
compared with the canonical factory files:

  .factory/MAINTENANCE.md    (Node and buildpack repos get the no-Skills-dependency variant and no MCP files)
                             the bootstrap in the published zen-of-projects Skill (jamesward/skills main,
                             which start.jamesward.com serves);
                             a no-Skills-dependency variant for NO_SKILLS_DEP; CUSTOM_MAINTENANCE skipped
  sbt repos                  sbta: `sbta`/`sbta.bat` from its latest release, no `sbt`/`sbt.bat`, no
                             sbt-mcp plugin/settings/bridge, the `sbta` MCP server, ./sbta in CI and
                             docs (factory_sbta.py; not for SBT_KEEP_LAUNCHER)
  .mcp.json                  the factory-owned server entry (sbta, or javadocs); others kept
  .claude/settings.json      that server in enabledMcpjsonServers (+ the Skill fetch permission for
                             NO_SKILLS_DEP); other settings kept
  .kiro/settings/mcp.json    the factory-owned server entry; others kept
  heroku-ops MCP server      in .mcp.json, .kiro/settings/mcp.json and .claude/settings.json of the repos of the
                             watched Heroku apps (FACTORY.md's table); no credentials in the files
  .github/dependabot.yml     must not exist
  line endings               files stored as their .gitattributes say (no diff in a fresh clone)
  labels                     needs-human and factory-improvement must exist

AGENTS.md and everything else are left to each repo's maintenance routine. --apply commits to the
bot-owned branch claude/factory-sync, opens or updates one PR titled 'Factory sync: ...', and
squash-merges it once its CI checks have run and passed (not with --no-merge: the daily routine
uses it because auto mode denies its merges, so each repo's maintenance run merges the PR after CI,
or the owner runs --apply locally, which also merges sync PRs that are already open). A PR with failing or no checks gets the
needs-human label and a comment. A PR whose checks are still running is left for the next run.
It never triggers a routine.

A full run (no owner/repo arguments) then checks findings: GitHub settings that differ
(factory-github-settings.py's check, which includes Dependabot alerts being on), repos the sync
failed on, and "Factory sync:" PRs open more than 7 days. With --apply it keeps one needs-human issue per finding in
jamesward/projects (opened, updated, and closed once the finding is gone; left open when the run
couldn't check it); without --apply it prints what it would do.

Every run ends with a "Needs you" digest: the open PRs and issues labeled needs-human or
factory-improvement, or titled "Factory improvement:", in the managed repos plus jamesward/projects
and jamesward/skills; PRs that conflict with their base are marked as needing a rebase. The factory
opens them as the owner's own GitHub user, so GitHub never notifies the owner about them; the daily
routine's emailed reply carries this list instead. It reads each repo's issues endpoint (not the
search API), which works for the repos attached to a cloud session. Uses only git and `gh api` (REST), so it also works in cloud sessions.
"""
import concurrent.futures
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
FACTORY = HERE / "FACTORY.md"
sys.path.insert(0, str(HERE))
import factory_sbta  # noqa: E402

# sbt repos whose launcher and MCP setup the factory doesn't touch: sbta builds its own
# launchers (`./sbta sbtaInstall`).
SBT_KEEP_LAUNCHER = {"jamesward/sbta"}
SKILL_URL = "https://start.jamesward.com"
BRANCH = "claude/factory-sync"
CHECK_WAIT_SECONDS = int(os.environ.get("FACTORY_SYNC_CHECK_WAIT", "1200"))

# Site repos with their own MAINTENANCE.md (not the Skill's bootstrap) and no MCP servers.
CUSTOM_MAINTENANCE = {"jamesward/ai4jvm", "MindviewLLC/podcast"}
# Repos that deliberately don't depend on com.jamesward:skills (see their AGENTS.md).
# Libraries released by hand whose dependents adopt changes only from a release: the digest lists
# changes under these paths since the newest tag with this prefix (pklgha's action defaults reach
# cfn-pkl-extras and easyracer only through a pklgha release).
MANUAL_RELEASES = {"jamesward/pklgha": ("pklgha@", ("src/",))}

NO_SKILLS_DEP = {"skillsjars/skillsjars-gradle-plugin", "skillsjars/skillsjars-maven-plugin",
                 "skillsjars/skillsjars-example-spring-ai"}

JAVADOCS = {"type": "http", "url": "https://www.javadocs.dev/mcp"}
# Cloud sessions' proxy refuses start.jamesward.com's redirect to the raw file (HTTP 403), but serves
# git clones of public repos, so routines read the Skill from a clone of jamesward/skills (same content).
FETCH_CMD = ("git clone -q --depth 1 https://github.com/jamesward/skills /tmp/jamesward-skills "
             "|| git -C /tmp/jamesward-skills pull -q")
OLD_FETCH_CMDS = ["mkdir -p /tmp/zen-of-projects && curl -fsSL --retry 5 --retry-delay 10 --retry-all-errors "
                  "https://start.jamesward.com -o /tmp/zen-of-projects/SKILL.md"]
SKILL_FILE = "/tmp/jamesward-skills/skills/zen-of-projects/SKILL.md"
LABELS = [{"name": "needs-human", "color": "B60205",
           "description": "The maintenance routine needs a maintainer decision"},
          {"name": "factory-improvement", "color": "0E8A16",
           "description": "Proposed by a maintenance routine run; needs a maintainer to review"}]


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


SKILLS_REPO = "https://github.com/jamesward/skills"
SKILL_PATH = "skills/zen-of-projects/SKILL.md"


def skill_text():
    """The published zen-of-projects Skill (FACTORY_SKILL_FILE overrides it, for testing an
    unreleased Skill locally). start.jamesward.com redirects to the raw file on
    jamesward/skills main; cloud sessions' git proxy refuses that raw fetch (HTTP 403) but serves
    git clones, so read it from a shallow clone and fall back to HTTP."""
    if os.environ.get("FACTORY_SKILL_FILE"):
        return Path(os.environ["FACTORY_SKILL_FILE"]).read_text()
    with tempfile.TemporaryDirectory() as t:
        r = run("git", "clone", "-q", "--depth", "1", SKILLS_REPO, t, check=False)
        if r.returncode == 0 and (Path(t) / SKILL_PATH).exists():
            return (Path(t) / SKILL_PATH).read_text()
    req = urllib.request.Request(SKILL_URL, headers={"User-Agent": "factory-sync"})
    return urllib.request.urlopen(req, timeout=60).read().decode()


def bootstrap():
    skill = skill_text()
    m = re.search(r"^````markdown\n(.*?)^````$", skill, re.S | re.M)
    if not m:
        sys.exit(f"no ````markdown bootstrap block in {SKILL_URL}")
    return m.group(1)


def no_skills_bootstrap(boot):
    """Bootstrap steps 1-3 replaced by a fetch of the published Skill."""
    a = boot.index("1. Update the Skills dependency")
    b = boot.index("and don't delete it.", boot.index("3. Read `.kiro/skills"))
    b = boot.index("\n", b)
    return boot[:a] + f"""1. Get the zen-of-projects Skill. This repo has no `com.jamesward:skills` dependency (see
   `AGENTS.md`), so read the published Skill from its repository:

   ```bash
   {FETCH_CMD}
   ```

   If it fails, quote the exact error and stop.
2. Read `{SKILL_FILE}` and follow its "Maintenance Routine" section, using
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


def ops_mcp():
    """(MCP URL of heroku-ops, repos of the watched apps), from FACTORY.md. The URL is None until the heroku-ops entry has one."""
    md = FACTORY.read_text()
    entry = md[md.index("### heroku-ops"):] if "### heroku-ops" in md else ""
    entry = entry[:entry.index("\n### ", 4)] if "\n### " in entry[4:] else entry
    m = re.search(r"^URL: (https://\S+?)/?$", entry, re.M)
    repos = set()
    if "### Watched Heroku apps" in md:
        for line in md[md.index("### Watched Heroku apps"):].splitlines()[1:]:
            if line.startswith("#"):
                break
            cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
            if line.startswith("|") and len(cells) == 4 and "/" in cells[1]:
                repos.add(cells[1])
    return (m.group(1) + "/mcp" if m else None), repos


OPS_SERVER = "heroku-ops"


def ensure_ops_mcp(d, url, changes):
    """The heroku-ops server in the MCP configs and approved in .claude/settings.json. No credentials in the files: a
    cloud session gets the bearer token from a network secret on its environment, and a local session adds its own with
    `claude mcp add --scope local` (FACTORY.md "heroku-ops MCP server")."""
    entry = {"type": "http", "url": url}
    for rel in (".mcp.json", ".kiro/settings/mcp.json"):
        j = put_server(d / rel, OPS_SERVER, entry, changes)
        if j is not None:
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_text(json.dumps(j, indent=2) + "\n")
            changes.append(f"{rel}: heroku-ops MCP server")
    st = load_json(d / ".claude/settings.json")
    if st is None:
        changes.append(".claude/settings.json: not valid JSON, left alone")
    elif OPS_SERVER not in st.setdefault("enabledMcpjsonServers", []):
        st["enabledMcpjsonServers"].append(OPS_SERVER)
        (d / ".claude").mkdir(exist_ok=True)
        (d / ".claude/settings.json").write_text(json.dumps(st, indent=2) + "\n")
        changes.append(".claude/settings.json: approve heroku-ops")


def desired(repo, d, boot):
    kind, changes = desired_files(repo, d, boot)
    url, watched = ops_mcp()
    if url and repo in watched and kind != "site" and repo not in CUSTOM_MAINTENANCE:
        ensure_ops_mcp(Path(d), url, changes)
    return kind, changes


def desired_files(repo, d, boot):
    """Edit the checkout at d toward the canonical files; return a list of change descriptions."""
    d = Path(d)
    changes = []
    kind = "sbt" if (d / "build.sbt").exists() else (
        "jvm" if any((d / f).exists() for f in ("pom.xml", "build.gradle.kts", "build.gradle")) else (
        "node" if (d / "package.json").exists() else (
        "buildpack" if (d / "bin/compile").exists() and (d / "bin/detect").exists() else "site")))

    def write(rel, text, why):
        p = d / rel
        if not p.exists() or p.read_text() != text:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
            changes.append(why)

    def write_json(rel, obj, why):
        if obj is not None:
            write(rel, json.dumps(obj, indent=2) + "\n", why)

    # Files committed against their .gitattributes line-ending rules (e.g. gradlew.bat with
    # `*.bat text eol=crlf`) show as modified in every fresh clone, which trips the cloud
    # sessions' "uncommitted changes" Stop hook. Store them normalized.
    staged = set(run("git", "diff", "--cached", "--name-only", cwd=d).stdout.split())
    run("git", "add", "--renormalize", ".", cwd=d)
    renorm = [f for f in run("git", "diff", "--cached", "--name-only", cwd=d).stdout.split() if f not in staged]
    if renorm:
        changes.append(f"renormalize line endings per .gitattributes: {', '.join(renorm)}")

    for f in (".github/dependabot.yml", ".github/dependabot.yaml"):
        if (d / f).exists():
            (d / f).unlink()
            changes.append(f"remove {f} (the routine keeps dependencies current)")

    if repo in CUSTOM_MAINTENANCE or kind == "site":
        return kind, changes

    no_skills = repo in NO_SKILLS_DEP or kind in ("node", "buildpack")  # no SkillsJars for npm or bash
    text = no_skills_bootstrap(boot) if no_skills else boot
    write(".factory/MAINTENANCE.md", text, ".factory/MAINTENANCE.md: current bootstrap from the zen-of-projects Skill")
    if (d / ".factory/DAILY.md").exists():
        (d / ".factory/DAILY.md").unlink()
        changes.append("remove .factory/DAILY.md (renamed to MAINTENANCE.md)")

    if kind == "buildpack":
        # Buildpacks have sbt test fixtures: the javadocs server gives them get_latest_version
        # (Maven Central metadata is rate-limited in cloud sessions).
        write_json(".mcp.json", put_server(d / ".mcp.json", "javadocs", JAVADOCS, changes),
                   ".mcp.json: javadocs MCP server")
        write_json(".kiro/settings/mcp.json", put_server(d / ".kiro/settings/mcp.json", "javadocs", JAVADOCS, changes),
                   ".kiro/settings/mcp.json: javadocs MCP server")
    if kind in ("node", "buildpack"):
        # Only the Skill fetch (and, for buildpacks, javadocs) needs approving.
        st = load_json(d / ".claude/settings.json")
        if st is None:
            changes.append(".claude/settings.json: not valid JSON, left alone")
            return kind, changes
        before = json.dumps(st, sort_keys=True)
        allow = st.setdefault("permissions", {}).setdefault("allow", [])
        if f"Bash({FETCH_CMD})" not in allow:
            allow.append(f"Bash({FETCH_CMD})")
        if kind == "buildpack":
            en = st.setdefault("enabledMcpjsonServers", [])
            if "javadocs" not in en:
                en.append("javadocs")
        if json.dumps(st, sort_keys=True) != before:
            write_json(".claude/settings.json", st, ".claude/settings.json: approve the Skill fetch"
                       + (" and javadocs" if kind == "buildpack" else ""))
        return kind, changes

    if kind == "sbt":
        # sbta (https://github.com/jamesward/sbta) is the launcher and MCP server: latest release
        # scripts, no ./sbt / sbt.bat / sbt-mcp plugin, settings or bridge, the `sbta` server in the
        # MCP configs, ./sbta in CI and docs. sbta's own repo builds its launchers itself.
        if repo in SBT_KEEP_LAUNCHER:
            return kind, changes
        changes += factory_sbta.migrate(d)
        return kind, changes
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
            allow[:] = [a for a in allow if a not in [f"Bash({c})" for c in OLD_FETCH_CMDS]]
            if f"Bash({FETCH_CMD})" not in allow:
                allow.append(f"Bash({FETCH_CMD})")
        if json.dumps(st, sort_keys=True) != before:
            write_json(".claude/settings.json", st, f".claude/settings.json: approve {server}" + (" and the Skill fetch" if repo in NO_SKILLS_DEP else ""))
    return kind, changes


# ---------- GitHub ----------

def ensure_label(repo, apply):
    names = {l["name"] for l in gh(f"repos/{repo}/labels?per_page=100")}
    missing = [l for l in LABELS if l["name"] not in names]
    if apply:
        for l in missing:
            gh(f"repos/{repo}/labels", "POST", l)
    return [f"create the {l['name']} label" for l in missing]


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


DIGEST_LABELS = ("needs-human", "factory-improvement")
FACTORY_REPOS = ["jamesward/projects", "jamesward/skills"]


FACTORY_IMPROVEMENT_TITLE = "Factory improvement:"


def pr_conflicts(repo, number):
    """True if the PR can't merge into its base as is (GitHub computes this lazily: retry once)."""
    for attempt in range(3):
        pr = gh(f"repos/{repo}/pulls/{number}", check=False) or {}
        if pr.get("mergeable") is not None:
            return pr["mergeable"] is False
        time.sleep(3)
    return False  # unknown: don't claim a conflict


def unreleased(repo, prefix, paths):
    """A digest item when the default branch has commits touching `paths` since the newest
    `prefix` tag, or None."""
    def key(name):
        return [int(x) if x.isdigit() else x for x in re.split(r"[.-]", name[len(prefix):])]
    tags = [t["name"] for t in gh(f"repos/{repo}/tags?per_page=100") if t["name"].startswith(prefix)]
    if not tags:
        return None
    tag = max(tags, key=key)
    default = gh(f"repos/{repo}")["default_branch"]
    cmp = gh(f"repos/{repo}/compare/{tag}...{default}")
    files = [f["filename"] for f in cmp.get("files", []) if f["filename"].startswith(paths)]
    if not files:
        return None
    first = cmp["commits"][0]  # oldest commit since the tag
    created = time.mktime(time.strptime(first["commit"]["committer"]["date"], "%Y-%m-%dT%H:%M:%SZ")) - time.timezone
    i = {"number": "", "html_url": f"https://github.com/{repo}/compare/{tag}...{default}",
         "title": f"{len(files)} file(s) under {', '.join(paths)} changed since {tag}; release by hand so dependents can adopt them"}
    return (created, repo, i, ["unreleased"], [])


def weekly(repos, now=None):
    """The factory's last week from GitHub alone (routine sessions can't read run logs, and a run that changes nothing leaves no
    trace on GitHub): maintenance PRs, sync PRs, Factory improvement items and findings issues."""
    now = now or dt.datetime.now(dt.timezone.utc)
    since = now - dt.timedelta(days=7)
    iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    when = lambda t: dt.datetime.fromisoformat(t.replace("Z", "+00:00")) if t else None
    recent = lambda t: bool(t) and when(t) >= since

    def items(repo):
        try:
            return repo, gh(f"repos/{repo}/issues?state=all&since={iso}&per_page=100"), None
        except Exception as e:
            return repo, [], str(e).splitlines()[-1][:100]

    maint = {"merged": 0, "closed": 0, "open": 0}
    held, sync = [], {"merged": 0, "closed": 0, "open": 0}
    improved = {"opened": 0, "done": 0, "open": 0}
    found = {"opened": 0, "closed": 0}
    unreadable = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(items, sorted(set(repos) | set(FACTORY_REPOS))))
    for repo, page, error in results:
        if error:
            unreadable.append(repo)
        for i in page:
            title = i["title"]
            is_pr = "pull_request" in i
            labels = [l["name"] for l in i.get("labels", [])]
            merged = recent((i.get("pull_request") or {}).get("merged_at"))
            closed = recent(i.get("closed_at"))
            if is_pr and title.startswith("Maintenance:"):
                if merged:
                    maint["merged"] += 1
                elif closed:
                    maint["closed"] += 1
                if i["state"] == "open":
                    maint["open"] += 1
                    if "needs-human" in labels:
                        held.append((when(i["created_at"]), repo, i["number"], title))
            elif is_pr and title.startswith("Factory sync:"):
                if merged:
                    sync["merged"] += 1
                elif closed:
                    sync["closed"] += 1
                elif i["state"] == "open":
                    sync["open"] += 1
            elif title.startswith(FACTORY_IMPROVEMENT_TITLE):
                improved["opened"] += int(recent(i["created_at"]))
                improved["done"] += int(closed)
                improved["open"] += int(i["state"] == "open")
            elif repo == FINDINGS_REPO and not is_pr and "factory-finding:" in (i.get("body") or ""):
                found["opened"] += int(recent(i["created_at"]))
                found["closed"] += int(closed)
    local = ZoneInfo("America/Denver")
    print(f"\n## Last week ({since.astimezone(local):%Y-%m-%d} to {now.astimezone(local):%Y-%m-%d}, from GitHub)")
    print(f"- Maintenance PRs: {maint['merged']} merged, {maint['closed']} closed unmerged, {maint['open']} open"
          f" ({len(held)} waiting for you).")
    for created, repo, number, title in sorted(held)[:8]:
        print(f"  - [{repo}#{number}](https://github.com/{repo}/pull/{number}), {(now - created).days}d: {title[:80]}")
    print(f"- Factory sync PRs: {sync['merged']} merged, {sync['closed']} closed, {sync['open']} open.")
    print(f"- Factory improvements: {improved['opened']} opened, {improved['done']} closed or merged, {improved['open']} open now.")
    print(f"- Findings issues: {found['opened']} opened, {found['closed']} closed.")
    if unreadable:
        print(f"- (couldn't read {', '.join(unreadable[:5])}{' ...' if len(unreadable) > 5 else ''})")
    print("- Runs that change nothing leave no trace on GitHub, so they aren't counted.")


def is_monday():
    return dt.datetime.now(ZoneInfo("America/Denver")).weekday() == 0


def digest(repos):
    """Open PRs and issues that need the owner, oldest first: labeled with a DIGEST_LABELS label,
    or titled "Factory improvement:" (routines don't always manage to add the label). PRs that
    conflict with their base branch are marked, since they need a rebase before they can merge."""
    items, failed, sync_prs = [], [], []
    now = time.time()
    for repo in sorted(set(repos) | set(FACTORY_REPOS)):
        try:
            page = gh(f"repos/{repo}/issues?state=open&per_page=100")
        except Exception as e:
            failed.append(f"{repo}: {str(e).splitlines()[-1][:120]}")
            continue
        for i in page:
            if "pull_request" in i and i["title"].startswith("Factory sync:"):
                sync_prs.append((repo, i))
            labels = [l["name"] for l in i.get("labels", [])]
            hit = [l for l in labels if l in DIGEST_LABELS]
            if i["title"].startswith(FACTORY_IMPROVEMENT_TITLE) and "factory-improvement" not in hit:
                hit.append("factory-improvement (unlabeled)")
            if not hit:
                continue
            notes = []
            if "pull_request" in i and pr_conflicts(repo, i["number"]):
                notes.append("conflicts with the base branch: needs a rebase")
            created = time.mktime(time.strptime(i["created_at"], "%Y-%m-%dT%H:%M:%SZ")) - time.timezone
            items.append((created, repo, i, hit, notes))
    for repo, (prefix, paths) in MANUAL_RELEASES.items():
        try:
            item = unreleased(repo, prefix, paths)
        except Exception as e:
            failed.append(f"{repo} releases: {str(e).splitlines()[-1][:120]}")
            continue
        if item:
            items.append(item)
    items.sort(key=lambda t: t[0])
    print(f"\n## Needs you ({len(items)} open)")
    if not items:
        print("Nothing open is labeled needs-human or factory-improvement, or titled \"Factory improvement:\".")
    for created, repo, i, hit, notes in items:
        kind = "PR" if "pull_request" in i else ("release" if hit == ["unreleased"] else "issue")
        days = int((now - created) // 86400)
        extra = "".join(f"; **{n}**" for n in notes)
        ref = f"{repo}#{i['number']}" if i["number"] != "" else f"{repo} release"
        print(f"- [{ref}]({i['html_url']}) {kind}, {', '.join(hit)}, {days}d{extra}: {i['title']}")
    for f in failed:
        print(f"- (couldn't read {f})")
    if sync_prs:
        oldest = min(i["created_at"] for _, i in sync_prs)[:10]
        print(f"\n{len(sync_prs)} open \"Factory sync:\" PR(s), oldest from {oldest}. Each merges in its repo's next "
              "maintenance run once CI passes; to merge them now, run `./factory-sync.py --apply` locally.")


# ---------- findings: needs-human issues in the factory repo ----------

# Things that failed or aren't as the factory expects, found by a run. Each finding is one open
# issue in FINDINGS_REPO labeled needs-human (so the digest and the routine's email list it),
# identified by a hidden marker in its body. A run opens or updates the issue while the finding
# holds and closes it once the run could check and the finding is gone. Nothing is closed for a
# check the run couldn't make (cloud sessions can't read some settings).
FINDINGS_REPO = "jamesward/projects"
MARKER = "<!-- factory-finding: %s -->"
STALE_SYNC_DAYS = 7


def load_settings():
    import importlib.util
    spec = importlib.util.spec_from_file_location("factory_github_settings", HERE / "factory-github-settings.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def settings_finding():
    """(finding or None, complete): GitHub settings that differ, from factory-github-settings.py."""
    gs = load_settings()
    lines, unknown = [], []
    for repo in gs.repos():
        try:
            c = gs.check(repo, force_wiki=False)
        except Exception as e:
            unknown.append(f"{repo}: {str(e).splitlines()[-1][:120]}")
            continue
        items = [d for _, d in c["todo"]] + c["problems"]
        if c["skipped"] and c["skipped"] != "archived":
            unknown.append(f"{repo}: {c['skipped']}")
        if c["unknown"]:
            unknown.append(f"{c['repo']}: couldn't read {', '.join(c['unknown'])}")
        if items:
            lines.append(f"- `{c['repo']}`: " + "; ".join(items))
    for u in unknown:
        print(f"?  settings: {u}")
    if not lines:
        return None, not unknown
    body = ("GitHub settings on these repos differ from the factory's (see `factory-github-settings.py`):\n\n"
            + "\n".join(lines) + "\n\nFix: run `./factory-github-settings.py --apply` locally. Cloud sessions "
            "reach GitHub through the Claude GitHub App, which can't change repository settings.")
    return ("settings", f"Factory: GitHub settings differ on {len(lines)} repo(s)", body), not unknown


BAD_CONCLUSIONS = ("failure", "timed_out", "startup_failure")


def ci_finding(repo):
    """((key, title, body) or None, complete) for the latest commit on the repo's default branch: red CI is a finding. Checks still
    running, no checks at all, or a repo that can't be read leave an open finding as it is (complete False)."""
    key = f"ci-red:{repo}"
    try:
        info = gh(f"repos/{repo}")
        if info.get("archived"):
            return None, True
        branch = info["default_branch"]
        sha = gh(f"repos/{repo}/branches/{branch}")["commit"]["sha"]
        runs = gh(f"repos/{repo}/commits/{sha}/check-runs?per_page=100").get("check_runs", [])
        statuses = gh(f"repos/{repo}/commits/{sha}/status").get("statuses", [])
    except Exception:
        return None, False
    if any(r["status"] != "completed" for r in runs) or any(s["state"] == "pending" for s in statuses) or not (runs or statuses):
        return None, False
    bad = [r for r in runs if r["conclusion"] in BAD_CONCLUSIONS]
    bad_status = [s for s in statuses if s["state"] in ("failure", "error")]
    if not bad and not bad_status:
        return None, True
    names = ", ".join([f"`{r['name']}`" for r in bad] + [f"`{s['context']}`" for s in bad_status])
    return (key, f"CI is failing on {repo}'s default branch",
            f"The latest commit on `{branch}` of `{repo}` ([{sha[:7]}](https://github.com/{repo}/commit/{sha})) has failing checks: {names}.\n\n"
            f"See [the runs](https://github.com/{repo}/actions?query=branch%3A{branch}). A merge that holds only routine changes "
            "shouldn't leave the default branch red: look at what the last maintenance PR changed.", ), True


def findings(repos, failures, sync_prs):
    """(found {key: (title, body)}, checked {keys whose absence this run confirmed})."""
    found, checked = {}, set()

    def add(f, complete, key):
        if f:
            found[f[0]] = f[1:]
        if complete or f:
            checked.add(key)

    for repo in repos:
        key = f"sync-failed:{repo}"
        checked.add(key)
        if repo in failures:
            found[key] = (f"Factory sync failed for {repo}",
                          f"`factory-sync.py` failed on `{repo}`:\n\n```\n{failures[repo][:3000]}\n```\n\n"
                          f"Reproduce locally with `./factory-sync.py {repo}`.")
    now = time.time()
    stale = []
    for repo, (number, created) in sorted(sync_prs.items()):
        days = int((now - time.mktime(time.strptime(created, "%Y-%m-%dT%H:%M:%SZ")) + time.timezone) // 86400)
        if days > STALE_SYNC_DAYS:
            stale.append(f"- [{repo}#{number}](https://github.com/{repo}/pull/{number}), {days}d")
    checked.add("stale-sync-prs")
    if stale:
        found["stale-sync-prs"] = (
            f"Factory: {len(stale)} \"Factory sync:\" PR(s) open more than {STALE_SYNC_DAYS} days",
            "Each repo's maintenance run should merge its open `Factory sync:` PR once CI passes "
            "(`.factory/MAINTENANCE.md`), but these are still open:\n\n" + "\n".join(stale) +
            "\n\nOpen the repo's latest maintenance PR for the link to its run, or merge the sync PR by hand.")
    f, complete = settings_finding()
    add(f, complete, "settings")
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for repo, (f, complete) in zip(repos, pool.map(ci_finding, repos)):
            add(f, complete, f"ci-red:{repo}")
    return found, checked


def sync_issues(found, checked, apply):
    """Open, update or close the needs-human finding issues in FINDINGS_REPO."""
    if apply:
        ensure_label(FINDINGS_REPO, True)
    existing = {}
    for i in gh(f"repos/{FINDINGS_REPO}/issues?state=open&labels=needs-human&per_page=100"):
        m = re.search(r"<!-- factory-finding: (\S+) -->", i.get("body") or "")
        if m and "pull_request" not in i:
            existing[m.group(1)] = i
    verb = (lambda v: v) if apply else (lambda v: f"would {v}")
    print(f"\n## Findings ({len(found)}; issues in {FINDINGS_REPO}, labeled needs-human)")
    for key, (title, body) in sorted(found.items()):
        body = f"{body}\n\nOpened and kept current by the daily factory sync (`factory-sync.py`), which closes " \
               f"it once the finding is gone.\n\n{MARKER % key}"
        i = existing.get(key)
        if i is None:
            if apply:
                i = gh(f"repos/{FINDINGS_REPO}/issues", "POST", {"title": title, "body": body, "labels": ["needs-human"]})
            print(f"+  {verb('open')}: {title}" + (f" ({i['html_url']})" if i else ""))
        elif i["title"] != title or (i.get("body") or "").replace("\r\n", "\n") != body:
            if apply:
                gh(f"repos/{FINDINGS_REPO}/issues/{i['number']}", "PATCH", {"title": title, "body": body})
            print(f"*  {verb('update')} #{i['number']}: {title} ({i['html_url']})")
        else:
            print(f"=  #{i['number']}: {title} ({i['html_url']})")
    for key, i in sorted(existing.items()):
        if key in found:
            continue
        if key not in checked:
            print(f"?  #{i['number']}: couldn't check this run, left open: {i['title']}")
            continue
        if apply:
            gh(f"repos/{FINDINGS_REPO}/issues/{i['number']}/comments", "POST",
               {"body": "The factory sync no longer finds this; closing."})
            gh(f"repos/{FINDINGS_REPO}/issues/{i['number']}", "PATCH", {"state": "closed", "state_reason": "completed"})
        print(f"-  {verb('close')} #{i['number']}: {i['title']}")


# ---------- main ----------

def digest_and_weekly(repos):
    digest(repos)
    if is_monday() or "--weekly" in sys.argv:
        weekly(repos)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    merge = apply and "--no-merge" not in sys.argv
    repos = managed_repos()
    if "--list" in sys.argv:
        print("\n".join(repos + [r for r in FACTORY_REPOS if r not in repos]))
        return
    if "--digest" in sys.argv:
        digest_and_weekly(repos)
        return
    if args:
        unknown = set(args) - set(repos)
        if unknown:
            sys.exit(f"not managed (not in FACTORY.md's schedule tables): {', '.join(sorted(unknown))}")
        repos = args
    boot = bootstrap()
    pending_prs = []
    failures, sync_prs = {}, {}  # repo -> error; repo -> (open sync PR number, created_at)
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
            if pr:
                sync_prs[repo] = (pr["number"], pr["created_at"])
            clone(repo, default, d)
            kind, changes = desired(repo, d, boot)
            label = ensure_label(repo, apply)
            if not changes:
                print(f"=  {repo} ({kind}): in sync{'; ' + '; '.join(label) if label else ''}"
                      + (f"; open PR #{pr['number']} left for merge check" if pr else ""))
                if pr and merge:
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
                    "Only factory-owned files and entries change; it doesn't run the maintenance routine. It merges "
                    "once CI passes: in the repo's next maintenance run (see `.factory/MAINTENANCE.md`), or when "
                    "the owner runs `./factory-sync.py --apply`.")
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
            failures[repo] = str(e)

    if apply and not merge and pending_prs:
        print(f"\n{len(pending_prs)} PR(s) opened or updated, not merged (--no-merge).")
    if merge and pending_prs:
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
                        sync_prs.pop(repo, None)
                        continue
                    if "needs-human" in [l["name"] for l in pr["labels"]]:
                        print(f"   {repo}#{number}: labeled needs-human, left for a maintainer")
                        continue
                    state = checks_state(repo, pr["head"]["sha"])
                    if state == "success":
                        gh(f"repos/{repo}/pulls/{number}/merge", "PUT", {"merge_method": "squash"})
                        gh(f"repos/{repo}/git/refs/heads/{BRANCH}", "DELETE", check=False)
                        print(f"   {repo}#{number}: CI passed, merged")
                        sync_prs.pop(repo, None)
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
                    failures[repo] = f"merge check of #{number}: {e}"
            waiting = still
            if waiting and time.time() > deadline:
                for repo, number in waiting:
                    print(f"   {repo}#{number}: CI still running, left for the next run")
                break
            if waiting:
                time.sleep(30)

    print(f"\n{drifted} of {len(repos)} repo(s) drifted." + ("" if apply or not drifted else " Run with --apply to fix."))
    if args:
        print("\n(Findings issues are only synced when every managed repo is checked.)")
    else:
        try:
            sync_issues(*findings(repos, failures, sync_prs), apply)
        except Exception as e:
            print(f"!! findings: {e}")
    digest_and_weekly(repos)
    run("rm", "-rf", str(work), check=False)


if __name__ == "__main__":
    main()

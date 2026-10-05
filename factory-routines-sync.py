#!/usr/bin/env python3
"""Compare the managed-repo tables in FACTORY.md with the Claude Code routines, and fix drift.

    ./factory-routines-sync.py            # report only (dry run)
    ./factory-routines-sync.py --apply    # create/update routines to match FACTORY.md

FACTORY.md is the source of truth for which repos are managed and how often their routine runs:
  ### Managed repos (weekly, default)    | Repo | Day | Time (America/Denver) | Routine |
  ### Managed repos (updated daily)      | Repo | Time (America/Denver) | Routine |

Routines can only be read and changed through Claude Code (`claude -p "/schedule ..."`). The
RemoteTrigger `list` action returns only the first 20 routines (its cursor is ignored), so the
Routine column records each routine's id: the script fetches every recorded id with `get`, merges
in the first page of `list` (to spot unrecorded or unmanaged routines), computes the differences
itself, and asks Claude to apply each change. A created routine's id is written back into the
table. It never deletes routines; routines for repos that aren't listed are only reported.
"""
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

FACTORY = Path(__file__).with_name("FACTORY.md")
TZ = ZoneInfo("America/Denver")
ENVIRONMENT_ID = "env_0159utCSbffzUfWZZbAesmJ5"  # JDK25
PROMPT = ("Follow .factory/MAINTENANCE.md in this repository. "
          "If it doesn't exist yet, follow .factory/DAILY.md instead.")
NOTIFICATIONS = {"email": True, "push": False, "slack": False}  # email only
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
CRON_DOW = {"Sun": 0, "Mon": 1, "Tue": 2, "Wed": 3, "Thu": 4, "Fri": 5, "Sat": 6}


def table(md, heading):
    lines = md[md.index(heading):].splitlines()[1:]
    rows = []
    for line in lines:
        if line.startswith("#"):
            break
        if line.startswith("|") and not re.match(r"^\|\s*-", line):
            cells = [c.strip().strip("`") for c in line.strip("|").split("|")]
            if cells[0].lower() != "repo":
                rows.append(cells)
    return rows


def desired():
    """{repo: (freq, day, time)} and {repo: recorded routine id or None}."""
    md = FACTORY.read_text()
    want, ids = {}, {}
    for row in table(md, "### Managed repos (weekly, default)"):
        repo, day, time = row[:3]
        want[repo] = ("weekly", day, time)
        ids[repo] = row[3] if len(row) > 3 and row[3] else None
    for row in table(md, "### Managed repos (updated daily)"):
        repo, time = row[:2]
        if repo in want:
            sys.exit(f"{repo} is listed as both weekly and daily in FACTORY.md")
        want[repo] = ("daily", None, time)
        ids[repo] = row[2] if len(row) > 2 and row[2] else None
    return want, ids


def record_id(repo, trigger_id):
    """Write a routine id into the repo's row (last cell) in FACTORY.md."""
    md = FACTORY.read_text()
    rx = re.compile(r"^(\| `%s` \|.*\|) *(`?trig_\w*`?)? *\|$" % re.escape(repo), re.M)
    m = rx.search(md)
    if not m:
        print(f"   could not record {trigger_id} for {repo} in FACTORY.md; add it by hand")
        return
    FACTORY.write_text(md[:m.start()] + f"{m.group(1)} `{trigger_id}` |" + md[m.end():])


def cron_for(freq, day, time):
    """UTC cron for a Denver wall-clock time, using today's UTC offset (re-run after DST changes)."""
    h, m = map(int, time.split(":"))
    today = dt.datetime.now(TZ).date()
    if freq == "daily":
        local = dt.datetime.combine(today, dt.time(h, m), TZ)
        u = local.astimezone(dt.timezone.utc)
        return f"{u.minute} {u.hour} * * *"
    target = DAYS.index(day)
    d = today + dt.timedelta(days=(target - today.weekday()) % 7)
    u = dt.datetime.combine(d, dt.time(h, m), TZ).astimezone(dt.timezone.utc)
    return f"{u.minute} {u.hour} * * {CRON_DOW[DAYS[u.weekday()]]}"


def claude(prompt, timeout=900):
    out = subprocess.run(["claude", "-p", prompt, "--output-format", "stream-json", "--verbose"],
                         capture_output=True, text=True, timeout=timeout).stdout
    events = []
    for line in out.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    return events


def tool_results(events):
    """Parsed JSON objects from every tool result in a claude -p stream."""
    for e in events:
        if e.get("type") != "user":
            continue
        for c in e["message"].get("content", []):
            if not (isinstance(c, dict) and c.get("type") == "tool_result"):
                continue
            t = c.get("content")
            t = t if isinstance(t, str) else "".join(x.get("text", "") for x in t if isinstance(x, dict))
            if "{" not in t:
                continue
            try:
                yield json.loads(t[t.index("{"):])
            except ValueError:
                pass


def triggers_in(obj):
    """Routine objects in a RemoteTrigger result (list page, get, create or update)."""
    if isinstance(obj, dict):
        if str(obj.get("id", "")).startswith("trig_") and "job_config" in obj:
            yield obj
        else:
            for v in obj.values():
                yield from triggers_in(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from triggers_in(v)


def list_routines(known_ids):
    """First page of `list`, plus a `get` of every recorded id (list ignores its cursor)."""
    ids = sorted(set(known_ids))
    p = ("/schedule Do not change anything. Load RemoteTrigger with ToolSearch (select:RemoteTrigger). "
         "Call RemoteTrigger with action list once, then call it with action get for each of these "
         "trigger_ids, one call each: " + ", ".join(ids) + ". Reply only 'done'.")
    found = {}
    for obj in tool_results(claude(p, timeout=1800)):
        for r in triggers_in(obj):
            found[r["id"]] = r
    if not found:
        sys.exit("could not read the routines from `claude -p /schedule ...`")
    missing = [i for i in ids if i not in found]
    if missing:
        sys.exit(f"could not fetch recorded routine(s) {', '.join(missing)}; re-run, or check the ids in FACTORY.md")
    return list(found.values())


def summarize(r):
    ccr = r["job_config"]["ccr"]
    sources = [s["git_repository"]["url"] for s in ccr["session_context"].get("sources", [])]
    repos = [re.sub(r"^https://github.com/|\.git$", "", u) for u in sources]
    events = ccr.get("events") or [{}]
    prompt = events[0].get("data", {}).get("message", {}).get("content", "")
    return {"id": r["id"], "name": r["name"], "cron": r.get("cron_expression") or "", "enabled": r["enabled"],
            "env": ccr.get("environment_id"), "repos": repos, "connectors": len(r.get("mcp_connections") or []),
            "prompt": prompt, "notifications": (r.get("notifications") or {}).get("channel")}


def ready(repo):
    for f in (".factory/MAINTENANCE.md", ".factory/DAILY.md"):
        if subprocess.run(["gh", "api", f"repos/{repo}/contents/{f}", "--silent"], capture_output=True).returncode == 0:
            return True
    return False


def main():
    apply = "--apply" in sys.argv
    want, ids = desired()
    routines = [summarize(r) for r in list_routines([i for i in ids.values() if i])]
    by_repo = {}
    for r in routines:
        if len(r["repos"]) == 1:
            by_repo.setdefault(r["repos"][0], []).append(r)

    actions = []
    for repo, (freq, day, time) in sorted(want.items()):
        name = f"{repo.split('/')[1]} maintenance"
        target = {"name": name, "cron": cron_for(freq, day, time), "env": ENVIRONMENT_ID, "prompt": PROMPT}
        when = f"{freq}{' ' + day if day else ''} {time} America/Denver"
        have = by_repo.get(repo, [])
        if len(have) > 1:
            print(f"!! {repo}: {len(have)} routines ({', '.join(h['id'] for h in have)}); fix by hand")
            continue
        if not have:
            if ready(repo):
                print(f"+  {repo}: no routine; create '{name}' ({when}, cron {target['cron']})")
                actions.append(("create", repo, None, target, when))
            else:
                print(f".  {repo}: no routine, and no .factory/MAINTENANCE.md on its default branch yet (not ready)")
            continue
        h = have[0]
        if ids.get(repo) != h["id"]:
            print(f"#  {repo}: recording routine id {h['id']} in FACTORY.md")
            record_id(repo, h["id"])
        diffs = []
        if h["name"] != name: diffs.append(f"name '{h['name']}' -> '{name}'")
        if h["cron"] != target["cron"]: diffs.append(f"cron '{h['cron']}' -> '{target['cron']}' ({when})")
        if h["env"] != ENVIRONMENT_ID: diffs.append(f"environment {h['env']} -> {ENVIRONMENT_ID} (JDK25)")
        if h["prompt"] != PROMPT: diffs.append("prompt -> the MAINTENANCE.md prompt")
        if h["connectors"]: diffs.append(f"remove {h['connectors']} connector(s)")
        if not h["enabled"]: diffs.append("enable")
        if h["notifications"] != NOTIFICATIONS: diffs.append("notifications -> email only")
        if diffs:
            print(f"~  {repo} ({h['id']}): " + "; ".join(diffs))
            actions.append(("update", repo, h, target, when))
        else:
            print(f"=  {repo} ({h['id']}): ok ({when})")

    for r in routines:
        if not (len(r["repos"]) == 1 and r["repos"][0] in want):
            print(f"?  unmanaged routine '{r['name']}' ({r['id']}, {', '.join(r['repos'])}): ignored")

    if not actions:
        print("\nNo changes needed.")
        return
    if not apply:
        print(f"\n{len(actions)} change(s). Run with --apply to make them.")
        return

    for kind, repo, h, t, when in actions:
        common = (f"- Name: {t['name']}\n- Repository: {repo} (only this one)\n- Prompt: {t['prompt']}\n"
                  f"- Schedule: cron {t['cron']} in UTC ({when})\n"
                  f"- Environment: environment_id {t['env']} (JDK25)\n"
                  "- Enabled: true\n- Connectors / MCP connections: none (remove any attached, and verify mcp_connections is empty)\n"
                  "- Notifications: email only, i.e. body field notifications = "
                  '{"channel": {"email": true, "push": false, "slack": false}}\n')
        if kind == "create":
            p = ("/schedule Create a new scheduled routine with exactly these settings and do not ask follow-up "
                 f"questions. Do not run it.\n{common}Afterwards, fetch it and report its id, name, cron and environment_id.")
        else:
            p = (f"/schedule Update the existing routine {h['id']} so it has exactly these settings, changing nothing "
                 f"else, and do not ask follow-up questions. Do not run it.\n{common}"
                 "Afterwards, fetch it and report its name, cron, environment_id, prompt and mcp_connections.")
        print(f"\n>> {kind} {repo}")
        events = claude(p)
        res = [e for e in events if e.get("type") == "result"]
        print((res[-1].get("result") or "").strip()[:800] if res else "(no result)")
        if kind == "create":
            made = [r["id"] for o in tool_results(events) for r in triggers_in(o) if r.get("name") == t["name"]]
            if made:
                record_id(repo, made[-1])
                print(f"   recorded {made[-1]} in FACTORY.md")
            else:
                print("   !! could not find the new routine's id; add it to FACTORY.md by hand before re-running")

    print("\nRe-checking...")
    sys.argv = [a for a in sys.argv if a != "--apply"]
    main()


if __name__ == "__main__":
    main()

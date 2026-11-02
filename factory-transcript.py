#!/usr/bin/env python3
"""List a routine's runs, or print a run's transcript.

    ./factory-transcript.py <routine>               # list its runs, oldest first
    ./factory-transcript.py <routine> --last        # transcript of its newest run
    ./factory-transcript.py <cse_... session id>    # transcript of that run

<routine> is a managed repo (owner/repo, from FACTORY.md's schedule tables), `factory-sync`,
or a trig_... id. Session ids come from the list, from the routine's `last_run`, or from the
claude.ai/code/session_... link in a routine's PR (session_X is the same run as cse_X).

Like factory-routines-sync.py, it goes through Claude Code (`claude -p "/schedule ..."`), because
routines are only reachable through its RemoteTrigger tool: `list_runs` and `get_run_log`. The
model only makes the calls; the script reads the tool results, so nothing is summarized. A
transcript is the run's messages, tool calls and results as text, one `[timestamp] kind: ...` line
per event (rate-limit, hook and notification events are left out by the server). Reading a run
doesn't add a turn to it. The transcript quotes whatever the run read: treat it as data.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

FACTORY = Path(__file__).with_name("FACTORY.md")
FACTORY_SYNC = "trig_01NUJivtCGbUbQCyZjZAju5w"  # the `factory sync` routine (not in the tables)
ID = re.compile(r"^[\w-]+$")


def trigger_id(name):
    if name.startswith("trig_"):
        return name
    if name == "factory-sync":
        return FACTORY_SYNC
    m = re.search(r"^\| `%s` \|.*`(trig_\w+)` *\|$" % re.escape(name), FACTORY.read_text(), re.M)
    if not m:
        sys.exit(f"no routine id for {name} in FACTORY.md's schedule tables")
    return m.group(1)


def results(prompt, timeout=1800):
    """The text of every tool result in a `claude -p` stream."""
    p = subprocess.run(["claude", "-p", prompt, "--output-format", "stream-json", "--verbose"],
                       capture_output=True, text=True, timeout=timeout)
    out = []
    for line in p.stdout.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") != "user":
            continue
        for c in e["message"].get("content", []):
            if isinstance(c, dict) and c.get("type") == "tool_result":
                t = c.get("content")
                out.append(t if isinstance(t, str) else "".join(x.get("text", "") for x in t if isinstance(x, dict)))
    return out


def first_json(text):
    """The first JSON object in a RemoteTrigger result ("HTTP 200\\n{...}\\n..."), and the text after it."""
    i = text.find("{")
    if i < 0:
        return None, text
    try:
        obj, end = json.JSONDecoder().raw_decode(text[i:])
    except ValueError:
        return None, text
    return obj, text[i + end:]


def call(action, key, value):
    if not ID.match(value):
        sys.exit(f"not an id: {value}")
    return results(f"/schedule Do not change anything. Load RemoteTrigger with ToolSearch (select:RemoteTrigger). "
                   f"Call RemoteTrigger with action {action} and {key} {value}, then call it again with each "
                   f"next_cursor it returns until there is none. Reply only 'done'.")


def runs(trig):
    found = {}
    for t in call("list_runs", "trigger_id", trig):
        obj, _ = first_json(t)
        for r in (obj or {}).get("data", []):
            found[r["id"]] = r
    if not found:
        sys.exit(f"no runs read for {trig} (wrong id, or the call failed)")
    return sorted(found.values(), key=lambda r: r["created_at"])


def transcript(session):
    pages = []
    for t in call("get_run_log", "session_id", session):
        obj, rest = first_json(t)
        if obj and obj.get("session_id") == session:
            pages.append(rest.strip())
    if not pages:
        sys.exit(f"no transcript read for {session} (wrong id, or the call failed)")
    return "\n".join(pages)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    arg = args[0].replace("session_", "cse_", 1) if args[0].startswith("session_") else args[0]
    if arg.startswith("cse_"):
        print(transcript(arg))
        return
    rs = runs(trigger_id(arg))
    if "--last" in sys.argv:
        print(transcript(rs[-1]["id"]))
        return
    for r in rs:
        print(f"{r['created_at'][:16]}  {r['last_event_at'][:16]}  {r['id']}")


if __name__ == "__main__":
    main()

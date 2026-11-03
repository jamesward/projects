#!/usr/bin/env python3
"""Make each watched Heroku app send its logs and events to heroku-ops, as FACTORY.md says.

    ./factory-heroku.py --lint        # check the table in FACTORY.md only (no network, no token)
    OPS_SECRET=... ./factory-heroku.py --mcp-token   # the bearer token for heroku-ops' MCP server (no network)
    ./factory-heroku.py               # report drift (dry run)
    ./factory-heroku.py --apply       # add/replace/remove the drains and webhooks that differ
    ./factory-heroku.py --apply --rotate   # also replace every drain and webhook (after changing OPS_SECRET)

FACTORY.md's "### Watched Heroku apps" table is the source of truth:
  | App | Repo | URL | Probe |
For each row the app gets one log drain and one app webhook that point at heroku-ops (the
OPS_APP below), each URL carrying the app's name and a secret derived from OPS_SECRET:
  drain    https://drain:<hmac("drain:"+app)>@<ops host>/drain?app=<app>
  webhook  https://<ops host>/hook?app=<app>, signed with hmac("hook:"+app)
heroku-ops derives the same secrets, so it needs no per-app configuration. Drains and webhooks
that point at heroku-ops for apps that are no longer in the table are removed. heroku-ops itself is
managed like any other app (it can be in the table) with one exception: it gets no log drain, because
it would drain into itself. Drains and
webhooks that point anywhere else are left alone.

Needs OPS_SECRET (the same value as the config var on heroku-ops). The Heroku API token comes
from HEROKU_API_KEY when it is set (local runs: `HEROKU_API_KEY=$(heroku auth:token)`); in the
factory's control routine it isn't set, and the cloud environment's network secret adds the
Authorization header to requests to api.heroku.com, so the token never reaches the session.

Each watched app is also checked, read-only, for the Heroku Labs feature log-runtime-metrics (memory,
swap and load samples in its log stream, which heroku-ops and the owner need; zen-of-projects
"Production servers"). An app without it gets a warning line and the exit status stays 0: turning
it on is the owner's `heroku labs:enable log-runtime-metrics -a <app>` and a restart.

Every request goes through allowed(): a short list of reads, and writes limited to log drains and
webhooks. Nothing here can scale, resize, change config vars or touch add-ons (DESIGN.md 10).
Exit status is 1 if any app failed.
"""
import hashlib
import concurrent.futures
import hmac
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

FACTORY = Path(__file__).with_name("FACTORY.md")
API = os.environ.get("HEROKU_API_URL", "https://api.heroku.com")
OPS_APP = os.environ.get("HEROKU_OPS_APP", "jw-heroku-ops")
WEBHOOK_INCLUDE = ["api:build", "api:release", "dyno"]
WEBHOOK_LEVEL = "notify"
APP_NAME = re.compile(r"^[a-z][a-z0-9-]{2,29}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
APPLY = "--apply" in sys.argv
ROTATE = "--rotate" in sys.argv
LINT = "--lint" in sys.argv


# ---------- the table ----------

def watched_apps(text=None):
    """[(app, repo, url, probe)] from FACTORY.md's "Watched Heroku apps" table, and the errors."""
    md = FACTORY.read_text() if text is None else text
    i = md.find("### Watched Heroku apps")
    if i < 0:
        return [], ["FACTORY.md has no '### Watched Heroku apps' table"]
    rows, errors, seen = [], [], set()
    for line in md[i:].splitlines()[1:]:
        if line.startswith("#"):
            break
        if not line.startswith("|") or re.match(r"^\|\s*-", line):
            continue
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if cells and cells[0].lower() == "app":
            continue
        if len(cells) != 4:
            errors.append(f"row needs 4 cells (App, Repo, URL, Probe): {line.strip()}")
            continue
        app, repo, url, probe = cells
        if not APP_NAME.match(app):
            errors.append(f"{app!r}: not a Heroku app name")
        elif app in seen:
            errors.append(f"{app}: listed twice")
        elif not REPO.match(repo):
            errors.append(f"{app}: {repo!r} is not owner/repo")
        elif not re.match(r"^https://[A-Za-z0-9.-]+(:\d+)?(/\S*)?$", url):
            errors.append(f"{app}: URL {url!r} must be https://...")
        elif not probe.startswith("/"):
            errors.append(f"{app}: probe {probe!r} must be a path starting with /")
        else:
            rows.append((app, repo, url, probe))
        seen.add(app)
    return rows, errors


# ---------- Heroku API, restricted ----------

APP = r"[a-z][a-z0-9-]{2,29}"
ID = r"[A-Za-z0-9._:-]{1,80}"
ALLOWED = [
    ("GET", rf"^/apps$"),
    ("GET", rf"^/apps/{APP}$"),
    ("GET", rf"^/apps/{APP}/log-drains$"),
    ("GET", rf"^/apps/{APP}/webhooks$"),
    ("GET", rf"^/apps/{APP}/features/log-runtime-metrics$"),
    ("POST", rf"^/apps/{APP}/log-drains$"),
    ("DELETE", rf"^/apps/{APP}/log-drains/{ID}$"),
    ("POST", rf"^/apps/{APP}/webhooks$"),
    ("DELETE", rf"^/apps/{APP}/webhooks/{ID}$"),
]


def allowed(method, path):
    return any(m == method and re.match(p, path) for m, p in ALLOWED)


class ApiError(Exception):
    pass


def call(method, path, body=None):
    if not allowed(method, path):
        raise ApiError(f"not allowed: {method} {path}")
    accept = "application/vnd.heroku+json; version=3" + (".webhooks" if "/webhooks" in path else "")
    headers = {"Accept": accept, "Content-Type": "application/json"}
    if os.environ.get("HEROKU_API_KEY"):
        headers["Authorization"] = "Bearer " + os.environ["HEROKU_API_KEY"]
    req = urllib.request.Request(API + path, method=method, headers=headers,
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise ApiError(f"{method} {path}: HTTP {e.code} {detail}") from None
    except urllib.error.URLError as e:
        raise ApiError(f"{method} {path}: {e.reason}") from None


# ---------- desired state ----------

def runtime_metrics(app):
    """True or False for the app's log-runtime-metrics feature, None when it can't be read."""
    try:
        return bool(call("GET", f"/apps/{app}/features/log-runtime-metrics").get("enabled"))
    except ApiError:
        return None


def secret(kind, app):
    key = os.environ["OPS_SECRET"].encode()
    return hmac.new(key, f"{kind}:{app}".encode(), hashlib.sha256).hexdigest()


def host_of(url):
    return urllib.parse.urlsplit(url).hostname or ""


def mask(url):
    return re.sub(r"//[^@/]*@", "//***@", url)


def reconcile(app, ops_host, wanted):
    """Plan for one app: [(action, kind, detail, thunk)]. wanted=False removes our drain/webhook."""
    plan = []
    # heroku-ops gets no drain to itself; everything else it is managed like any other app.
    drain_url = f"https://drain:{secret('drain', app)}@{ops_host}/drain?app={app}" if wanted and app != OPS_APP else None
    hook_url = f"https://{ops_host}/hook?app={app}" if wanted else None

    drains = call("GET", f"/apps/{app}/log-drains") or []
    ours = [d for d in drains if host_of(d.get("url", "")) == ops_host]
    keep = None
    for d in ours:
        if drain_url and keep is None and d["url"] == drain_url and not ROTATE:
            keep = d
        else:
            plan.append(("remove", "drain", mask(d["url"]),
                         lambda d=d: call("DELETE", f"/apps/{app}/log-drains/{d['id']}")))
    if drain_url and keep is None:
        plan.append(("add", "drain", mask(drain_url), lambda: call("POST", f"/apps/{app}/log-drains", {"url": drain_url})))

    hooks = call("GET", f"/apps/{app}/webhooks") or []
    ours = [h for h in hooks if host_of(h.get("url", "")) == ops_host]
    keep = None
    for h in ours:
        same = (h["url"] == hook_url and sorted(h.get("include", [])) == sorted(WEBHOOK_INCLUDE)
                and h.get("level") == WEBHOOK_LEVEL)
        if wanted and keep is None and same and not ROTATE:
            keep = h
        else:
            plan.append(("remove", "webhook", h["url"],
                         lambda h=h: call("DELETE", f"/apps/{app}/webhooks/{h['id']}")))
    if wanted and keep is None:
        body = {"url": hook_url, "include": WEBHOOK_INCLUDE, "level": WEBHOOK_LEVEL, "secret": secret("hook", app)}
        plan.append(("add", "webhook", hook_url, lambda: call("POST", f"/apps/{app}/webhooks", body)))
    return plan


def main():
    if "--mcp-token" in sys.argv:
        if not os.environ.get("OPS_SECRET"):
            sys.exit("OPS_SECRET is not set")
        print(hmac.new(os.environ["OPS_SECRET"].encode(), b"mcp", hashlib.sha256).hexdigest())
        return
    rows, errors = watched_apps()
    for e in errors:
        print(f"!! FACTORY.md: {e}")
    if LINT:
        print(f"{len(rows)} watched app(s), {len(errors)} error(s).")
        sys.exit(1 if errors else 0)
    if errors:
        sys.exit("fix the table before running (./factory-heroku.py --lint)")
    if not os.environ.get("OPS_SECRET"):
        sys.exit("OPS_SECRET is not set (the same value as the config var on " + OPS_APP + ")")

    ops = call("GET", f"/apps/{OPS_APP}")
    ops_host = host_of(ops["web_url"])
    watched = {r[0] for r in rows}
    print(f"heroku-ops: {OPS_APP} at {ops_host}; {len(rows)} watched app(s)")

    failed = changes = 0
    targets = [(a, True) for a in sorted(watched)]
    stale = []
    for a in call("GET", "/apps"):
        n = a["name"]
        if n not in watched and APP_NAME.match(n):
            stale.append(n)
    targets += [(a, False) for a in sorted(stale)]

    def plan_for(target):
        app, wanted = target
        try:
            return app, wanted, reconcile(app, ops_host, wanted), None, runtime_metrics(app) if wanted else True
        except ApiError as e:
            return app, wanted, [], e, True

    # Each app needs three reads and the API answers slowly through the cloud proxy, so read in parallel.
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        planned = list(pool.map(plan_for, targets))

    warnings = 0
    for app, wanted, plan, error, metrics in planned:
        if metrics is False:
            print(f"?  {app}: log-runtime-metrics is off (owner: heroku labs:enable log-runtime-metrics -a {app}, then restart)")
            warnings += 1
        if error:
            if wanted:
                print(f"!! {app}: {error}")
                failed += 1
            continue
        if not plan:
            if wanted:
                print(f"=  {app}: ok")
            continue
        print(f"~  {app}: " + "; ".join(f"{a} {k}" for a, k, _, _ in plan))
        changes += len(plan)
        if APPLY:
            for a, k, detail, thunk in plan:
                try:
                    thunk()
                    print(f"   {a} {k} {detail}: done")
                except ApiError as e:
                    print(f"!! {app}: {a} {k}: {e}")
                    failed += 1
    verb = "made" if APPLY else "needed (run with --apply)"
    print(f"\n{changes} change(s) {verb}; {failed} app(s) failed; {warnings} warning(s).")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

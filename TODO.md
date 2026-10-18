# TODO

## Self-improving factory

Goal: every routine run is evaluated afterwards, and what it reveals improves the factory itself (FACTORY.md, the scripts, `.factory/MAINTENANCE.md`), the zen-of-projects Skill, or the tools the runs depend on (sbt-mcp, skillsjars plugins, cfn-pkl-extras, ...), not just the one repo.

### What to look for in a run

- **Tool friction:** fallbacks from MCP to the CLI, retries, timeouts, "no sbt channel", stale indexes, output a tool didn't return. Example (webjars, 2026-10-04): `sbt-task` returned only `Failed tests: <Spec>` because test frameworks print results to the test JVM's stdout, which never reaches the log sbt-mcp captures. `last` and `Test / fork := false` don't help, and a `set` restarts the MCP server mid-request.
- **Instruction gaps:** the agent guessed, asked, or did something the Skill doesn't cover (Docker not started for Testcontainers, a `testFull` run that outlived an MCP timeout, a release not on a mirror yet).
- **Policy outcomes:** `needs-human` PRs and why; merges that later broke CI or production; reverts.
- **Cost and time:** run duration, turns, the steps that dominated them, wasted work (for example the same failing download retried).
- **Repeats across repos:** the same problem in several runs points to a factory or Skill fix, not a per-repo `AGENTS.md` note.

### Ideas for how

1. **Run reports as data.** Make the end-of-run report in the Skill's "Maintenance Routine" structured, as a fixed section in the PR description or a comment: tools used, fallbacks with reasons, errors quoted, durations, and an "improvement suggestions" list. The agent already writes most of this; a fixed shape makes it parseable.
2. **Agent self-critique step.** (Started: zen-of-projects step 8.) Add a final routine step: "List what slowed you down or made you fall back, and which file (repo `AGENTS.md`, zen-of-projects, FACTORY.md, a tool) should change so the next run avoids it." Cheap, and it gets the perspective of the agent that hit the problem (the webjars transcript is exactly this).
3. **Evaluator routine.** A separate scheduled routine (weekly, after the maintenance runs), on the factory repo (`jamesward/projects`) plus the tool repos. It:
   - lists the week's runs (`RemoteTrigger list_runs` for each id in the FACTORY.md tables) and reads their logs (`get_run_log`) and the resulting PRs and comments;
   - clusters findings across repos and dedupes them against the open issues;
   - opens or updates one issue per finding in the repo that should change, labeled `factory-improvement`, with evidence (run links, quoted errors) and a proposed fix;
   - never changes things itself at first: a human triages.
4. **Graduated autonomy.** Once the evaluator's issues prove useful, let it open PRs for low-risk classes (documentation in FACTORY.md and `AGENTS.md`, Skill wording) and later for tool fixes with tests. Skill and tool changes still need a release, so a human stays in that loop.
5. **Measure it.** Track per-run metrics over time (duration, turns, fallbacks, `needs-human` rate, CI failures after merge) in a small file or issue, so it's visible whether changes actually improved runs.
6. **Feedback into the Skill.** Recurring fixes that apply to every repo go into zen-of-projects; repo-specific ones go into that repo's `AGENTS.md`. The evaluator should say which, following the Skill's "one source of truth" rule.

### Access to the factory and Skills repos

Done (2026-10-04): zen-of-projects Maintenance Routine step 8 has each run review itself and open `Factory improvement:` PRs (label `factory-improvement`, never merged) in `jamesward/skills` or `jamesward/projects`, attaching them with `add_repo` (`access: "push"`). Verified in a routine run: no prompts or denials, clones, push dry-run and `gh api` all work. Extra routine sources were rejected because they stop `.mcp.json` from loading. Applies once the Skill is released (after 0.0.10) and each repo's routine picks it up.

- **Later:** other maintained dependencies (sbta, SkillsJars plugins, cfn-pkl-extras, ...). Step 7 currently only suggests fixes for them in the PR description.
- **Watch for:** duplicate or noisy PRs across 44 weekly runs. If it happens, move to the evaluator routine (idea 3) or issues instead of PRs.

### Open questions

- Where do findings live: issues per affected repo, or one tracking issue in `jamesward/projects`?
- `RemoteTrigger list` only returns 20 routines (its cursor is ignored); check whether `list_runs` / `get_run_log` paginate, or whether the evaluator has to work per routine id.
- Should the evaluator also read local (non-routine) agent sessions, like the webjars one, or only routine runs?
- How to evaluate cost (subscription usage per run) if the run logs don't expose it?

## Production alerting for Heroku apps (ops routine)

Goal: standard alerts on every factory Heroku app, defined by the factory, that start a Claude Code **ops routine** to triage, instead of the owner noticing outages.

### What exists (checked 2026-10-16)

- **Heroku app webhooks** (`heroku webhooks:add -a <app> -i <entities> -l notify|sync -u <url> -t <authorization header> -s <hmac secret>`): HTTP POSTs on app events. Entities include `api:release`, `api:build`, `api:formation` and `dyno` (dyno state changes, likely including crashes: verify). The body is Heroku's own JSON; the only custom header is `Authorization`.
- **Routine API trigger**: `POST https://api.anthropic.com/v1/claude_code/routines/<trig_id>/fire` with `Authorization: Bearer <routine token>`, `anthropic-beta: experimental-cc-routine-2026-04-01`, `anthropic-version: 2023-06-01`, and body `{"text": "..."}`. The text reaches the run wrapped in `<routine-fire-payload>` as untrusted data, so the routine's prompt must say to investigate it. API triggers (and their tokens) can only be added in the web UI. Research preview: shapes may change.
- **Heroku threshold alerting** (response time and 5xx rate, from Application Metrics) only exists on professional dynos (Standard/Performance): today javadocs, webjars and webjars-file-service (Standard-2X). The rest are Basic/Eco. As far as I know it notifies by email/Dashboard, not webhook, and it's configured in the Dashboard (no CLI; check for an API).
- **Log drains** (`heroku drains:add https://...`): every log line, including router and dyno error codes (H10 app crashed, H12 timeout, H13, R14/R15 memory, which `-XX:+ExitOnOutOfMemoryError` now turns into crashes/restarts).

### The gap

Heroku can't call `/fire` directly: it can't send the `anthropic-beta`/`anthropic-version` headers or a `{"text": ...}` body. So we need a small **relay**: receives Heroku webhooks (verify `Heroku-Webhook-Hmac-SHA256`) and/or an HTTPS log drain, filters (crash, H1x/R1x bursts, failed release), debounces per app (one fire per incident, not per log line), and POSTs `/fire` with a summary (app, event, recent error lines, last release). Options: a tiny service on Heroku itself (then it can't report its own outage), or something outside Heroku (AWS Lambda behind a function URL, Cloudflare Worker). The relay holds the routine token as a secret.

### Factory-defined standard alerts (sketch)

- A `factory-heroku.py` (like `factory-github-settings.py`): reads the Heroku apps in FACTORY.md, reports/fixes drift: the relay webhook (`dyno,api:release,api:build`), the relay log drain, the buildpacks rule (zen-of-projects "Heroku deploys"), `JAVA_TOOL_OPTIONS` ExitOnOutOfMemoryError for non-Scala JVM apps, and threshold alerts where the dyno tier supports them (reported only, if there's no API).
- Optionally an uptime check: a URL per app in FACTORY.md, probed by the relay on a schedule, since a dead app that emits no events alerts nothing.

### The ops routine (to design)

- One routine (`ops`) on `jamesward/projects`, API trigger only. Prompt: investigate the incident in the `routine-fire-payload` block; find the app's repo from FACTORY.md (`add_repo`); correlate with the last release/merge and the PR that caused it; check the production URL.
- Output: an issue in the app's repo labeled `needs-human` and `incident` with the evidence and a proposed fix (or a fix PR, never merged automatically), plus the routine's email. It must not roll back, restart or change config on its own, at least at first.
- Heroku access: routines have no Heroku credentials, and environment variables are visible to anyone using the environment. Options: the relay includes recent log lines and release info in the fire text (no credentials in the routine), or a separate cloud environment for ops with a read-scoped token (`heroku authorizations:create --scope read`; check whether logs need more than `read`).

### Open questions

- Which Heroku events really signal "down": does the `dyno` webhook fire on crashes and R14/R15 restarts?
- Where the relay runs, and who watches the relay.
- Debounce and rate limits: routine runs count against the subscription (100 scheduled runs/hour; check API-trigger limits).
- Pricing: threshold alerts need professional dynos; log volume for a drain.

## Open work

- **Re-runs on skills 0.0.15 (2026-10-15):** the 429 fix holds for sbt (sbt-mcp, sbt-sass, skillsjars-sbt-plugin: no 429s). Gradle repos stopped on a 429 for `skills-0.0.15.pom` because the Google mirror didn't have a 1-hour-old release yet (404), so Gradle fell back to Central; the Skill now treats that like "Not found". Step 8 still filed nothing in 3 runs that had findings: the bootstrap now requires a link per finding before merging (zen-of-projects main, after 0.0.15). Re-check next week.
- **webjars CI:** tests call the live GitHub API and fail on its rate limit (`Response was 429 - API rate limit exceeded`); third time in two weeks. Needs a token in CI or the tests should treat 429 as skip.

- **Health check 2026-10-14** (44 runs since 10-06): ~34 merged after CI, 5 stopped on Maven Central 429 (all before the Gradle/Maven mirror and `JDK_JAVA_OPTIONS` fixes), 2 need-human. Only 1 `Factory improvement:` PR came out of ~40 runs; most findings were written only into each repo's PR description. Step 8 is now required and stricter (zen-of-projects after 0.0.14). Re-check after the next release: re-run the 429 routines (sbt-mcp, sbt-sass, skillsjars-sbt-plugin, login-jamesward-dev, spring-ai-mcp-demo) and count `Factory improvement:` PRs and issues a week later.

- **Dependabot alerts in cloud runs:** `gh api .../dependabot/alerts` gets `403 Resource not accessible by integration`, so routines can't do step 4 there. Options: a local scheduled check, or ask whether the GitHub proxy can grant `security_events` read.
- **Push notifications** are still sent by some failing runs despite the bootstrap saying not to.

- **Factory sync** (done 2026-10-05): `factory-sync.py` plus the daily `factory sync` routine keep factory-owned files current in all managed repos without running their routines (see FACTORY.md). Watch the first few daily runs; the cloud `--apply` path (PR, CI wait, merge through `gh api`) is only verified locally.


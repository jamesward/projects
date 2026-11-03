# TODO

## Self-improving factory

Goal: every routine run is evaluated afterwards, and what it reveals improves the factory itself (FACTORY.md, the scripts, `.factory/MAINTENANCE.md`), the zen-of-projects Skill, or the tools the runs depend on (sbt-mcp, skillsjars plugins, cfn-pkl-extras, ...), not just the one repo.

### What to look for in a run

- **Tool friction:** fallbacks from MCP to the CLI, retries, timeouts, "no sbt channel", stale indexes, output a tool didn't return. Example (webjars, 2026-10-04, sbt-mcp before sbta replaced it): `sbt-task` returned only `Failed tests: <Spec>` because test frameworks print results to the test JVM's stdout, which never reaches the log sbt-mcp captures. `last` and `Test / fork := false` don't help, and a `set` restarts the MCP server mid-request.
- **Instruction gaps:** the agent guessed, asked, or did something the Skill doesn't cover (Docker not started for Testcontainers, a `testFull` run that outlived an MCP timeout, a release not on a mirror yet).
- **Policy outcomes:** `needs-human` PRs and why; merges that later broke CI or production; reverts.
- **Cost and time:** run duration, turns, the steps that dominated them, wasted work (for example the same failing download retried).
- **Repeats across repos:** the same problem in several runs points to a factory or Skill fix, not a per-repo `AGENTS.md` note.

### Ideas for how

1. **Run reports as data.** Make the end-of-run report in the Skill's "Maintenance Routine" structured, as a fixed section in the PR description or a comment: tools used, fallbacks with reasons, errors quoted, durations, and an "improvement suggestions" list. The agent already writes most of this; a fixed shape makes it parseable.
2. **Agent self-critique step.** (Started: zen-of-projects step 8.) Add a final routine step: "List what slowed you down or made you fall back, and which file (repo `AGENTS.md`, zen-of-projects, FACTORY.md, a tool) should change so the next run avoids it." Cheap, and it gets the perspective of the agent that hit the problem (the webjars transcript is exactly this).
3. **Evaluator routine.** A separate scheduled routine (weekly, after the maintenance runs), on the factory repo (`jamesward/projects`) plus the tool repos. It:
   - lists the week's runs and reads their transcripts (`factory-transcript.py`, which pages through `list_runs` and `get_run_log` per routine id) and the resulting PRs and comments;
   - clusters findings across repos and dedupes them against the open issues;
   - opens or updates one issue per finding in the repo that should change, labeled `factory-improvement`, with evidence (run links, quoted errors) and a proposed fix;
   - never changes things itself at first: a human triages.
4. **Graduated autonomy.** Once the evaluator's issues prove useful, let it open PRs for low-risk classes (documentation in FACTORY.md and `AGENTS.md`, Skill wording) and later for tool fixes with tests. Skill and tool changes still need a release, so a human stays in that loop.
5. **Measure it.** Track per-run metrics over time (duration, turns, fallbacks, `needs-human` rate, CI failures after merge) in a small file or issue, so it's visible whether changes actually improved runs.
6. **Feedback into the Skill.** Recurring fixes that apply to every repo go into zen-of-projects; repo-specific ones go into that repo's `AGENTS.md`. The evaluator should say which, following the Skill's "one source of truth" rule.

### Access to the factory and Skills repos

Done: zen-of-projects Maintenance Routine step 8 has each run review itself and open `Factory improvement:` PRs (label `factory-improvement`, never merged) in `jamesward/skills` or `jamesward/projects`, attaching them with `add_repo` (`access: "push"`). Since 2026-10-15 runs have opened 11 of them (7 merged).

- **Verify:** step 8 pushes to `jamesward/skills` were denied as "Create Public Surface" (jevlm's 2026-10-28 run then held its validated changes unpushed). 19196c8 gives maintenance routines an auto mode environment naming the owners' accounts; check the next week's runs for denials.
- **Later:** other maintained dependencies (sbta, SkillsJars plugins, cfn-pkl-extras, ...). Step 7 currently only suggests fixes for them in the PR description.
- **Watch for:** duplicate or noisy PRs across 47 weekly runs. If it happens, move to the evaluator routine (idea 3) or issues instead of PRs.

### Open questions

- Where do findings live: issues per affected repo, or one tracking issue in `jamesward/projects`?
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

## Hill climbing and open-ended tasks (later)

Goal: start open-ended work on one project (improve a metric, explore a change) on demand, without it draining the subscription quota that interactive use shares.

### What exists (checked 2026-10-30)

- Starting runs: a routine's schedule, `RemoteTrigger` `run` (used to re-run routines on 2026-10-30), the `/fire` API with a text payload (see the ops routine section), or an interactive `claude --cloud` session.
- Hard limits: the number of runs started, the routine's model (Sonnet is the default; Opus uses much more quota), and `claude -p --max-budget-usd` (print mode only; probably only meaningful with an API key, untested with subscription login). An API key with a Console spend limit gives a hard dollar cap, billed separately.
- No per-run token or dollar cap for routines, and no `--max-turns` in the CLI. Inside a run, only the prompt limits it, which is soft. Routines share the 5-hour and weekly pool with interactive Claude Code and claude.ai, so a runaway climb can lock out your own work.

### Sketch

1. **Goal file** `.factory/goals/<slug>.md`, owner-written on the default branch (not issue text): objective, a metric command that prints a number (without one the run writes a proposal PR instead of iterating), constraints (validation still passes), budget (iterations per run, max runs, stop rule such as no gain in 2 iterations or a target value), and a log the agent appends to (attempt, metric, kept or reverted). Each run starts from the log, not from earlier context.
2. **A "climb" routine per repo**, separate from maintenance and with no schedule, created by `factory-routines-sync.py`. A zen-of-projects "Hill climb" section: read goal and log, make one change at a time, measure it, keep or revert it, commit the best state to a `claude/climb-<slug>` PR labeled `needs-human`, stop at the iteration cap, never schedule itself.
3. **`factory-climb.py <repo> <slug>`** checks the goal's remaining runs, fires the routine, and decrements the count. At 0 it refuses to fire.
4. **Token limits:** Sonnet unless the goal allows Opus; short runs; fire when you aren't using Claude; for a hard dollar cap run locally with `claude -p --max-budget-usd N` and a spend-limited API key.

### Open questions

- Quota: the subscription with run caps, or a separate API key with a spend limit?
- Starting runs: only by hand with `factory-climb.py`, or also on a schedule until the run count reaches 0?
- Goal source: the goal file, or a `hill-climb` issue (easy from a phone, but safe only if the routine checks that the owner wrote it)?
- Which project to try it on first? Pick one with a fast, objective metric.
- Check whether one-off routine runs really are exempt from the daily routine cap (one third-party guide says so during the research preview).

## Open work

- **webjars CI flakes on live network tests:** 3 of 25 runs since 2026-10-01 failed (10-07, 10-15, 10-24), each in tests that call GitHub or git hosts live (`GitHub - tags - work with paging`, `inflight 1.0.4 has the correct github url`, `work with versionless git npm deps` and a `bower-angular-touch.git` clone timing out at 30 s). CI already passes `GITHUB_TOKEN` (since 2022); the `429 - API rate limit exceeded` lines in those logs come from a test fixture (IP 192.0.2.1), not GitHub. Options: `TestAspect.flaky`/retries on the live tests, or a separate non-blocking job for them.
- **Factory sync merges:** since 2026-11-02 the routine runs `--apply --no-merge` (auto mode denied its merges daily from 10-25). Check that maintenance runs merge their repo's `Factory sync:` PR after CI and that the digest's count of open sync PRs goes down.


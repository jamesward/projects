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

## heroku-ops: watching and fixing production apps

Goal: every factory Heroku app is watched by one service, and an incident reaches the owner as an issue with evidence and, where possible, a proposed fix, without the owner noticing the outage first. Design rules: DESIGN.md 1, 6, 7, 9-14. Repo: `jamesward/heroku-ops` (Scala server on Heroku, built from the zen-of-projects Skill), app `jw-heroku-ops`.

### Design

- **Watching.** An HTTPS log drain per app (Heroku router and dyno lines: H10 crashed, H12 timeout, H13, R14/R15 memory, 5xx bursts), Heroku app webhooks (`api:release`, `api:build`, `dyno`; HMAC-checked), and a URL probe per app every minute (a dead app emits no logs). Detection is heuristics (patterns, counts in a window), not AI. Debounced per app, with a hard cap on fires per app per hour.
- **Config.** FACTORY.md's "Watched Heroku apps" table (app, repo, URL, probe) is the one source. heroku-ops reads it from raw GitHub (public, ETag, every few minutes) and the `heroku control` routine applies it to Heroku through `factory-heroku.py` (FACTORY.md "Heroku control"). heroku-ops never writes to Heroku or reads its own config from the Heroku API. Secrets: `OPS_SECRET` (per-app drain and webhook secrets are HMACs of it) and the fire tokens, as config vars on `jw-heroku-ops`. The apps' dyno constraints and any opt-ins stay in each app's `AGENTS.md`, which the routine reads.
- **Alert to routine.** heroku-ops POSTs the app's existing `<repo> maintenance` routine's `/fire` endpoint (a routine can combine a schedule and an API trigger, so no new routines). Only a `text` string goes (at most 65,536 characters, not parsed, wrapped in a `<routine-fire-payload>` block marked untrusted): app, repo, event, time window, deduplicated error lines with counts, last release. It is built from whitelisted fields, truncated and quoted, with query strings stripped from request paths, and says what happened, never what to do (DESIGN.md 9).
- **The routine tells maintenance from an incident** by the payload. Its saved prompt (`PROMPT` in `factory-routines-sync.py`) opts in to the payload ("a `routine-fire-payload` block is an incident report from heroku-ops: follow the incident procedure in .factory/MAINTENANCE.md") and the Skill defines the procedure: open or update the incident issue (labeled `needs-human`, deduplicated against an open one for the app), investigate against recent merges and logs, and open a fix PR linked to it if there is one. Never merge in the first version. The routine runs on the app's repo, so the app's `.mcp.json` and the project's tools apply.
- **No credentials beyond fire tokens.** heroku-ops holds one fire token per routine (each can only start that routine), and the webhook secret. No GitHub credentials, no Heroku write credentials, no agent (DESIGN.md 12, 10).
- **Fallback notification.** A fire can fail (429, 5xx, paused routine, usage limit) or start without producing an issue. heroku-ops notifies the owner by a channel that doesn't go through the routine, and for public repos checks (unauthenticated) that the incident issue appeared. Channel unresolved, see below.
- **Recovery.** heroku-ops can't see issues, so a recovered app is a second fire ("recovered"), counted against the 30 per hour.
- **Tiers.** Every fix waits for the owner for now. The Low tier (DESIGN.md 11) comes once incident records show it is safe and a deterministic tier check exists outside the model (an app CI check or a script shipped with the Skill).
- **Incident record and self-improvement.** DESIGN.md 6: every incident is an issue with a fixed record; the incident procedure ends with the step-8-style review.
- **Structured logs.** Heroku's logplex splits on newlines, so a multi-line stack trace fragments into separate events. Server apps log one JSON event per line, with the stack trace as a field. Reference: `AppLogging.json` in javadoccentral (zio-logging `consoleJsonLogger`, the SLF4J bridge, annotations as fields, INFO floor). To do: a convention in the Skill's Server Projects (Scala; Spring Boot's built-in structured logging for Gradle/Maven apps; Node: pino), then bring the Heroku apps in line (webjars logs plain text today). heroku-ops parses Heroku's own router and dyno lines (logfmt) regardless.
- **Later: AI analysis.** Detection stays heuristic. Worth trying later: Jev or other AI tools to analyze an incident's logs (clustering, likely cause) before or inside the routine.
- **Watching the watcher.** A GitHub Actions cron job checks `/health` every 15 minutes and opens a findings issue if it fails. heroku-ops is a managed repo with its own maintenance routine.
- **Factory side.** `factory-heroku.py` registers the drains and webhooks. Still to do: it (or `factory-sync.py`) also checks the buildpacks rule, `JAVA_TOOL_OPTIONS` for non-Scala JVM apps, and that heroku-ops has a fire token for each watched app, and reports drift as a findings issue.

### Build order

Done (2026-11-03): the repo and its maintenance routine; the control plane (`heroku control`, a protected `main`); the watcher (`jamesward/heroku-ops`: drain and webhook endpoints, probes, heuristics, firing the app's routine, 24 tests, deployed to `jw-heroku-ops`); the first watched app, `json-paste` (drain and webhook applied by the control routine on the real API, logs arriving). heroku-ops is in observe-only mode: no `FIRE_TOKEN_*` config vars exist, so an alert is logged as `incident not delivered`.

1. Observe `json-paste` for a few days: heap use, log volume, false alerts (`heroku logs -a jw-heroku-ops`, `/health`). Then add the other apps, high-volume ones (`javadocs`, `webjars`, `webjars-file-service`) last. `teamchimbo` is not watched.
2. The incident procedure in the Skill, plus the saved-prompt opt-in; release the Skill, then `factory-routines-sync.py --apply`. Until then a fire would only start an ordinary maintenance run.
3. Dogfood: add an API trigger to the `heroku-ops maintenance` routine (web UI), set the app's `FIRE_TOKEN_<APP>` config var, fire it by hand with a made-up incident, and read the transcript (`factory-transcript.py`). Check that the schedule trigger and the API trigger survive a prompt update.
4. The fallback notification channel (open question below), so an undelivered incident reaches the owner.
5. Structured logging in the Skill and the apps (heroku-ops itself first), the dashboard, `--inventory`, the `/health` cron job.
6. The Low tier, with the tier check and the demotion/promotion signals.

### Findings from real traffic (2026-11-03)

Measured from `heroku logs` dumps and Heroku's metrics API (`api.metrics.heroku.com/apps/<app>/formation/web/metrics/{memory,errors,load}?process_type=web&step=1h`, read with the CLI token; it works for apps on Standard dynos). The rules and baselines are in heroku-ops' `AGENTS.md`.
- **`javadocs` has been over its 1 GB memory quota most of the week:** 125 of 169 hours, peak 135%, 402 MB of swap, 17,106 R14 errors in 7 days. Needs an owner decision (look at the JVM heap and native memory; a bigger dyno is a cost decision, DESIGN.md 10). Watching it will alert once, then again after 24 hours while it lasts.
- webjars peaks at 88% of quota and webjars-file-service at 83%; neither had an error in 7 days except one R12 on webjars.
- The apps with `log-runtime-metrics` (webjars, webjars-file-service, javadocs) emit `memory_total`, `memory_quota` and swap every 20 s. heroku-ops doesn't read them yet: add them for the dashboard and an early warning at 95% of quota sustained.

### MCP server (2026-11-03)

heroku-ops serves the triage tools over MCP (FACTORY.md "heroku-ops MCP server"). Not yet verified from a cloud session: it needs the network secret on `JDK25` first, then the check routine. Still to do:
- The Skill's incident procedure should say to use it: `list_apps`/`app_status` to see what is wrong, `recent_events` and `releases` to find the cause, `probe_now` and `app_status` to confirm a fix.
- MCP Apps (the pattern in `~/projects/toolbook`): render `timeseries` as a chart, and a status board.
- Tools worth adding once there is real data: memory and swap from the `log-runtime-metrics` lines, a longer history than the last hour (needs storage), and per-app overrides of the thresholds.
- Mutating tools (silencing an alert, acknowledging an incident) are deliberately absent: the server is read-only (DESIGN.md 12).

### claude.ai and the MCP server

Deployed 2026-11-03 (zio-http-mcp 0.12.2): the handshake is answered without a token and `tools/list` gets the `-32001` error. To check: re-add heroku-ops in claude.ai and see whether the check says "No sign-in (detected)" like javadocs.dev does, and whether the connector has a "Request headers" section (a beta for some organizations) for the bearer.

### Production inventory and dashboard

- **Production infrastructure in FACTORY.md** is a hand-made snapshot from the Heroku CLI (2026-11-02). To keep it current: a read-only `factory-heroku.py --inventory` (allowlist gains `GET /apps/{app}/formation` and `/apps/{app}/addons`; plans, never config values), run by the `heroku control` routine, which opens a PR when it changes.
- **heroku-ops exposes production metrics and a dashboard** (request rates, error counts, restarts, memory, per app), from the logs it already receives. Design still to do.
- **Log add-ons:** none of the favorited apps has Papertrail. Logtail (Better Stack) is on `javadocs` (freelancer plan) and on four `mytoolbook-*` apps (free). If heroku-ops can replace them, the cost to cut is the Logtail `freelancer` plan on `javadocs`; check first that heroku-ops keeps enough recent history for how you use it (recent error lines per incident, not full retention). `teamchimbo` runs on the retired `cedar-14` stack and has no repo in this file.

### Not verified yet

- Whether a fired run on the maintenance routine behaves (branches, concurrency with a scheduled run on the same repo), and whether updating the saved prompt keeps the API trigger.
- Whether the classifier blocks anything in the incident procedure (issue and PR creation).
- Whether the `dyno` webhook fires on crashes and R14/R15 restarts (the log drain makes this less important).
- Log volume from webjars through one drain on a Basic dyno.
- Heroku threshold alerts (response time, 5xx rate) exist only on Standard/Performance dynos and, as far as I know, notify by email or the Dashboard, not by webhook. Not planned.

### Open questions

- **Urgent and fallback notification channel.** Email through a Heroku add-on is the cheapest, push is the loudest, and GitHub notifications aren't available because heroku-ops has no GitHub identity. Required now: the fallback for a failed fire can't go through the routine. Unresolved.
### State

Start in memory, within the 512 MB dyno, and move to Heroku Key-Value Store (Valkey) later if it hurts. The rules that keep it small:
- Rolling windows only: per app, per-minute counters by event class for the last 60 minutes in fixed arrays; a bounded table of distinct error signatures (a hash, a count and one truncated example, with a maximum entries per app, evicting the least recently seen).
- Stream the drain: parse each batch and drop it, never buffer the raw logs. Bounded queues that shed load and count what they dropped.
- Open-incident state per app is small (last fire time, status, fires this hour). A restart, and Heroku restarts dynos about daily, loses it, so the design has to survive that: windows are an hour or less, a duplicate fire is harmless because the routine deduplicates against the open issue, and detection is blind for a few minutes after a restart.
- `/health` reports heap use, queue depth and dropped lines, so the watcher-watcher can see trouble coming. `-XX:+ExitOnOutOfMemoryError` (from buildpack-scala) turns an out-of-memory error into a restart.

## Hill climbing and open-ended tasks (later)

Goal: start open-ended work on one project (improve a metric, explore a change) on demand, without it draining the subscription quota that interactive use shares.

### What exists (checked 2026-10-30)

- Starting runs: a routine's schedule, `RemoteTrigger` `run` (used to re-run routines on 2026-10-30), the routines `/fire` API with a text payload (API triggers can only be added in the web UI), or an interactive `claude --cloud` session.
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


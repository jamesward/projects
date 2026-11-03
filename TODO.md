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

Done: the docs, the repo skeleton (`jamesward/heroku-ops`: `GET /health`, CI) and its maintenance routine.

1. Finish wiring heroku-ops: buildpacks (`heroku/jvm`, then buildpack-scala), a deploy of `main`, its URL in the repo's `AGENTS.md`. Also verify the routines can push: the first heroku-ops run (2026-11-03) changed nothing, and the repo is public, so the clone proves nothing.
   Control plane: done and verified in routine runs (2026-11-03): the `heroku control` routine runs on a merged PR and daily, the token reaches the Heroku API through the proxy, `main` has no bypass (a routine's push is rejected), and the report takes about 12 s. Not yet exercised on the real API: `--apply` (the table is empty). Next: heroku-ops receives drain and webhook requests, then the first watched app goes into the table.
2. The incident procedure in the Skill, plus the saved-prompt opt-in; release the Skill, then `factory-routines-sync.py --apply`.
3. Dogfood: add an API trigger to the `heroku-ops maintenance` routine (web UI), fire it by hand with a made-up incident, and read the transcript (`factory-transcript.py`). Check that the schedule trigger and the API trigger survive a prompt update.
4. The watcher: drain, webhooks, probes, heuristics, debounce, fire, fallback notification.
5. Roll out per app: log drain, webhook, API trigger and token in heroku-ops' config.
6. Structured logging in the Skill and the apps; `factory-heroku.py`; the `/health` cron job.
7. The Low tier, with the tier check and the demotion/promotion signals.

### Production inventory and dashboard

- **FACTORY.md should list each production app's infrastructure:** dyno type and size per process, add-ons and plans, stack and region, so routines and agents have the constraints DESIGN.md 10 relies on. Plan: a read-only `factory-heroku.py --inventory` (allowlist gains `GET /apps/{app}/formation` and `/apps/{app}/addons`; the add-on list has plans and prices, never config values) that prints the table; the `heroku control` routine's daily run could open a PR when it changes.
- **heroku-ops exposes production metrics and a dashboard** (request rates, error counts, restarts, memory, per app), from the logs it already receives. Design still to do.
- **Papertrail:** with the drains going to heroku-ops, the add-on can be removed to cut cost. Check first that heroku-ops keeps enough searchable history for what Papertrail is used for (recent raw error lines per incident, not full retention), then remove the add-on app by app.

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


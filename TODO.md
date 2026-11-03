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

Goal: every factory Heroku app is watched by one service, and an incident gets investigated and, within the risk rules, fixed without the owner noticing the outage first. Design rules: DESIGN.md 1, 10, 11, 12 (and 6 for self-improvement). Repo: `jamesward/heroku-ops` (Scala server on Heroku, built from the zen-of-projects Skill). Heroku can't call a Claude Code routine's `/fire` endpoint (no custom headers or body), so heroku-ops runs the agent itself instead of firing a routine.

### Design

- **Watching.** An HTTPS log drain per app (router and dyno errors: H10 crashed, H12 timeout, H13, R14/R15 memory, 5xx bursts), Heroku app webhooks (`api:release`, `api:build`, `dyno`; HMAC-checked), and a URL probe per app every minute (a dead app emits no logs). Debounced per app: one incident, not one per log line. The log drain and webhooks need no Heroku credentials.
- **Agent.** `kiro-cli acp` with `KIRO_API_KEY` (headless mode), driven through [zio-acp](https://github.com/jamesward/zio-acp) the way zio-evals' `AcpAgentLoop` does it. It runs in a clone of the app's repo, so that repo's `.kiro/settings/mcp.json` and skills apply. Scrubbed environment, a tool policy (not allow-everything), a temporary working directory.
- **Credentials.** A GitHub App of its own: the agent's token pushes `claude/` branches and opens PRs; a separate merge token stays in heroku-ops code. No Heroku write credentials anywhere. Branch protection on the apps' default branches.
- **Tiers.** Low: revert of the causing merge, or a small test-covered fix; merges after green CI. High: everything else, PR plus `needs-human` issue, the owner merges. A script decides the tier (forced High list in DESIGN.md 11). Each app starts High-only; `AGENTS.md` opts in.
- **Validation.** In the app repo's CI, not on the dyno (a Basic dyno can't build Scala and run an agent). Low needs green CI.
- **Reminders.** A High PR is reported again after 4 hours while the app is still unhealthy; otherwise the daily digest covers it.
- **Incident record and self-improvement.** DESIGN.md 6. The agent's instructions are a Skill (`zen-of-ops`) in `jamesward/skills`, delivered through the `com.jamesward:skills` dependency.
- **Watching the watcher.** A GitHub Actions cron job checks `/health` every 15 minutes and opens a findings issue if it fails. heroku-ops is a managed repo with its own maintenance routine.
- **Factory side.** `factory-heroku.py` (like `factory-github-settings.py`) checks each Heroku app listed in FACTORY.md for its drain, webhook and probe entry, the buildpacks rule, and `JAVA_TOOL_OPTIONS` for non-Scala JVM apps, and reports drift as a findings issue.

### Build order

1. Docs (this section, DESIGN.md) and the repo skeleton.
2. A watcher with no agent: drain, webhooks, probes, debounce, and an incident issue per incident. Catches outages with no AI cost.
3. Triage only: the agent investigates and writes up the issue.
4. High-tier fix PRs.
5. The Low tier, and the demotion/promotion signals.
6. `factory-heroku.py`, the `/health` cron job, and registering heroku-ops as a managed repo (browser step for the Claude App).

### Not verified yet

- `kiro-cli` on a Heroku dyno (installing it during the build), its memory use, and what Kiro charges for API-key usage this way.
- How ACP permission requests behave under a restricted tool policy (`AcpAgentLoop` allows the first option every time).
- Whether the `dyno` webhook fires on crashes and R14/R15 restarts (the log drain makes this less important).
- Log volume from webjars through one drain on a Basic dyno.
- Heroku threshold alerts (response time, 5xx rate) exist only on Standard/Performance dynos and, as far as I know, notify by email or the Dashboard, not by webhook. Not planned.

### Open questions

- **Urgent notification channel.** GitHub notifications from the App identity, email through an add-on, or push? A production outage may deserve more than a GitHub notification, and the choice is hard. Unresolved.
- Limits on rate and cost: how many agent runs a bad day could start. Cap the fires per hour and merge simultaneous incidents into one report.
- Where heroku-ops keeps state (open incidents, debounce): memory only (lost on restart), or a small add-on.

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


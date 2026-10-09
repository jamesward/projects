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

- **Later:** other maintained dependencies (sbt-mcp, SkillsJars plugins, cfn-pkl-extras, ...). Step 7 currently only suggests fixes for them in the PR description.
- **Watch for:** duplicate or noisy PRs across 44 weekly runs. If it happens, move to the evaluator routine (idea 3) or issues instead of PRs.

### Open questions

- Where do findings live: issues per affected repo, or one tracking issue in `jamesward/projects`?
- `RemoteTrigger list` only returns 20 routines (its cursor is ignored); check whether `list_runs` / `get_run_log` paginate, or whether the evaluator has to work per routine id.
- Should the evaluator also read local (non-routine) agent sessions, like the webjars one, or only routine runs?
- How to evaluate cost (subscription usage per run) if the run logs don't expose it?

## Open work

- **Factory sync** (done 2026-10-05): `factory-sync.py` plus the daily `factory sync` routine keep factory-owned files current in all managed repos without running their routines (see FACTORY.md). Watch the first few daily runs; the cloud `--apply` path (PR, CI wait, merge through `gh api`) is only verified locally.

- **sbt-mcp: test failure details in `sbt-task` responses.** Done in sbt-mcp 0.1.4/0.1.5; verified through MCP in webjars (`sbt-mcp test FAILED: webjars.GzipSpec / ... 8 was not equal to 9`). Skill guidance committed (unreleased); webjars on 0.1.5. Other repos pick up 0.1.5 on their next routine run.
- **sbt-mcp: `set` and `reload` restart the MCP server** and drop the in-flight request. Documented in the Skill; a fix would keep the server across session reloads.
- **sbt-mcp: "no sbt channel available yet"** at session start. Have `sbt-task` wait briefly for a channel instead of failing.

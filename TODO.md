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
2. **Agent self-critique step.** Add a final routine step: "List what slowed you down or made you fall back, and which file (repo `AGENTS.md`, zen-of-projects, FACTORY.md, a tool) should change so the next run avoids it." Cheap, and it gets the perspective of the agent that hit the problem (the webjars transcript is exactly this).
3. **Evaluator routine.** A separate scheduled routine (weekly, after the maintenance runs), on the factory repo (`jamesward/projects`) plus the tool repos. It:
   - lists the week's runs (`RemoteTrigger list_runs` for each id in the FACTORY.md tables) and reads their logs (`get_run_log`) and the resulting PRs and comments;
   - clusters findings across repos and dedupes them against the open issues;
   - opens or updates one issue per finding in the repo that should change, labeled `factory-improvement`, with evidence (run links, quoted errors) and a proposed fix;
   - never changes things itself at first: a human triages.
4. **Graduated autonomy.** Once the evaluator's issues prove useful, let it open PRs for low-risk classes (documentation in FACTORY.md and `AGENTS.md`, Skill wording) and later for tool fixes with tests. Skill and tool changes still need a release, so a human stays in that loop.
5. **Measure it.** Track per-run metrics over time (duration, turns, fallbacks, `needs-human` rate, CI failures after merge) in a small file or issue, so it's visible whether changes actually improved runs.
6. **Feedback into the Skill.** Recurring fixes that apply to every repo go into zen-of-projects; repo-specific ones go into that repo's `AGENTS.md`. The evaluator should say which, following the Skill's "one source of truth" rule.

### Access to the factory and Skills repos

Every routine should be able to read, and propose changes to, `jamesward/projects` (this factory) and `jamesward/skills` (zen-of-projects and friends). Findings from a diagnostic routine run (2026-10-04, `trig_01Rq62FE9XKNfZjbJxq2LWrR`):

- **Extra routine sources break sbt-mcp.** With zio-mavencentral plus both repos as sources, all three were cloned, but the repo's `.mcp.json` wasn't loaded (`sbt-mcp-zio-mavencentral` tools missing). The docs agree: a committed `.mcp.json` is only used by single-repo routines. So keep one source per routine.
- **Single-repo sessions are scoped to that repo.** `gh api repos/jamesward/skills` failed with `GitHub access to this repository is not enabled for this session. Use add_repo to request access.` A `git clone` of the other repos was blocked by the auto-mode classifier ("Exfil Scouting").
- **Plan:** keep single-repo routines, and add a `MAINTENANCE.md` step that calls `add_repo` for `jamesward/projects` and `jamesward/skills`, then clones them under `/tmp`. Untested: whether `add_repo` works unattended in a routine, or needs approval.
- **Prerequisites (human):**
  - `jamesward/projects` exists on GitHub but is empty: this directory was never pushed. It's public, so check FACTORY.md first (it has routine, installation and Heroku app ids, no secrets found).
  - Add `jamesward/projects` and `jamesward/skills` to the Claude GitHub App (personal installation). The run got `remote: Claude doesn't have GitHub access to jamesward/skills` (403).
- **Later:** what to do about other maintained dependencies (sbt-mcp, skillsjars plugins, cfn-pkl-extras, ...) and whether routines get access to those too.

### Open questions

- Where do findings live: issues per affected repo, or one tracking issue in `jamesward/projects`?
- `RemoteTrigger list` only returns 20 routines (its cursor is ignored); check whether `list_runs` / `get_run_log` paginate, or whether the evaluator has to work per routine id.
- Should the evaluator also read local (non-routine) agent sessions, like the webjars one, or only routine runs?
- How to evaluate cost (subscription usage per run) if the run logs don't expose it?

## Open work

- **sbt-mcp: test failure details in `sbt-task` responses.** Done in sbt-mcp 0.1.4/0.1.5; verified through MCP in webjars (`sbt-mcp test FAILED: webjars.GzipSpec / ... 8 was not equal to 9`). Skill guidance committed (unreleased); webjars on 0.1.5. Other repos pick up 0.1.5 on their next routine run.
- **sbt-mcp: `set` and `reload` restart the MCP server** and drop the in-flight request. Documented in the Skill; a fix would keep the server across session reloads.
- **sbt-mcp: "no sbt channel available yet"** at session start. Have `sbt-task` wait briefly for a channel instead of failing.

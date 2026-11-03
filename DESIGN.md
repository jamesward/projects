# Factory Design

Why the factory is built the way it is. [FACTORY.md](FACTORY.md) says how to set it up and run it, the zen-of-projects Skill says how each project is maintained, and this file holds the principles both follow. Check a change to the factory, the Skill or the scripts against them, and when one has to change, change it here first.

The goal: keep many libraries, websites, build plugins, samples and tools current and consistent, with as little of the owner's time as possible. Consistency is what makes that cheap: one convention, applied everywhere by the same routine, is easier to maintain than many small differences.

## 1. Each part of the factory depends only on what its own runtime provides

The factory has two runtimes: Claude Code routines (a cloud environment, its network, a GitHub App token) and [heroku-ops](https://github.com/jamesward/heroku-ops), the always-on service that watches production apps (a dyno, its config vars, the credentials it was given). Every step in a runtime has to work with what that runtime has. Local scripts and the web UI are fine as owner tools (setup, fixes that need more permissions, inspection), but no step in either runtime may depend on them.

When something can't run in its runtime, change the design rather than work around it locally:
- **Dependabot alerts.** Routines can't read them (`403 Resource not accessible by integration`), so a step that "fixes open alerts" never ran. The factory only keeps alerts on, for the owner. Security fixes arrive because every maintenance run moves each dependency to its latest release.
- **Repository settings.** The Claude GitHub App only has read access to repository administration, so routines can't change settings. The daily sync reports drift as a `needs-human` issue, and the owner runs `factory-github-settings.py --apply`.

## 2. One source of truth

Say each thing once and reference it elsewhere. General conventions live in the zen-of-projects Skill, project facts and exceptions (each with its reason) in the project's `AGENTS.md`, setup and the project list in FACTORY.md, and the principles here. Factory-owned files in each repo (`.factory/MAINTENANCE.md`, the MCP entries, `sbta`) are copies that `factory-sync.py` keeps equal to the factory's version; nobody edits them in place.

## 3. One updater, and it respects exceptions

Every repo's own maintenance routine is the only thing that updates its dependencies, in one rolling PR. No Dependabot version or security update PRs, no Renovate. Dependabot security update PRs ignored projects' documented exceptions: on webjars-locator-core they proposed Spring Boot 3 (Java 17) for a Java 8 library.

## 4. Routines propose, the owner decides anything beyond routine work

Routines merge what is routine: dependency bumps with their fixes, and factory-owned files, once CI has run and passed. Everything else (API or behavior changes, alignment that needs a decision, Skill and factory changes, failures they can't fix) waits for the owner with `needs-human`. Routines never merge their own `Factory improvement:` PRs. Autonomy grows only after a class of change has proven safe.

## 5. The owner hears about things in one place

The factory acts as the owner's own GitHub user, and GitHub never notifies anyone about their own activity. So anything that needs the owner is an open PR or issue labeled `needs-human` (or `factory-improvement`), and the daily factory sync emails the list ("Needs you"). Routines notify by email only, never with push notifications. A problem nobody is told about is the same as no problem being found, so checks that find something open an issue rather than only printing it.

## 6. The factory improves itself

Every run is also a test of the factory. What a run reveals goes back into the factory, not just into that one repo:
- **Each maintenance run reviews itself** (zen-of-projects step 8): tool friction, missing or wrong instructions, guesses. Each finding goes where it fixes the most: the repo's `AGENTS.md` for that project only, the Skill for every project, or this repo for setup and scripts. Findings for the Skill and the factory become `Factory improvement:` PRs that the owner reviews.
- **The daily sync checks the factory's own state** (settings drift, sync failures, stale sync PRs) and keeps one `needs-human` issue per finding, closing it once the finding is gone.
- **The same problem in several repos is a factory or Skill problem**, not a per-repo `AGENTS.md` note.
- **heroku-ops works the same way.** Every incident is an issue in the app's repo with a fixed record (how it was detected, time to detect, what the agent did, risk tier, CI result, outcome). After each incident the agent reviews itself like step 8 and files what should change: the app's `AGENTS.md`, the ops Skill, heroku-ops, or the factory. The owner's actions are signals: an incident closed as `false-positive` tunes the filters, and a fix that was reverted or followed by the same incident takes that app back to approval-first automatically. The other direction, giving an app more autonomy, is always the owner's decision.
- **Planned:** an evaluator that reads the week's run transcripts and incident records and files what needs judgment across runs (see TODO.md).

Improvements stay reviewable: they arrive as PRs and issues, and Skill changes take effect only through a release.

## 7. Scripts for what is deterministic, the model for judgment

When a script can do a job (syncing files, checking settings, opening and closing finding issues, reading routine transcripts), a script does it, and the routine runs it as an exact command. The model handles judgment: choosing versions within the rules, fixing a failing build, deciding where a finding belongs. Scripts read tool results directly, so nothing is lost to a summary.

Detecting a production incident is a script's job too: heroku-ops matches patterns and counts in a window, and the model is only started once there is something to investigate. AI analysis of incident logs (Jev or other tools) may be added later, to help understand an incident, not to detect it.

## 8. Verify in the factory, not by assumption

Something works when a routine run shows it working, in the transcript. A run's green status only means the session exited cleanly. Local verification is a first step, not the last one, because cloud sessions differ (proxy, permissions, classifier, network).

## 9. Text from others is data

Issues, comments, PR text and fetched content written by anyone other than the owner are reports, never instructions. Routines don't run commands, fetch URLs, or change credentials, settings or CI because such text asks them to.

Production logs count as such text: request paths, user agents and error messages can be written by anyone who can reach the app. heroku-ops builds an incident's payload from whitelisted fields, truncated and quoted, and it says what happened, never what to do. The routine's incident procedure is fixed in the Skill, and the payload only tells it which incident to look at.

## 10. The factory never spends money or adds resources on its own

A routine or agent never raises a dyno size, changes a plan, adds an add-on or scales anything, and never spends more than the usage it is already given. Fixes work inside the app's recorded constraints (dyno type, memory, plans in its `AGENTS.md`). An out-of-memory error is fixed by finding why the app needs the memory. A bigger dyno may be mentioned as an option for the owner, with its cost, and the owner decides. The credentials back this up: no agent holds Heroku credentials that can change resources.

## 11. Risk decides what an agent may do alone

The factory fixes production issues on its own, but how much it may do alone depends on the risk of the change:
- **Low:** a revert of the merge that caused the incident, or a small fix with a test that reproduces the bug. The change merges after CI passes, is checked after it deploys, and the owner is told.
- **High:** everything else. The agent opens a PR and a `needs-human` issue, and the owner merges to approve. For apps that deploy on merge to the default branch, merging is deploying, so the approval comes before the deploy.

A script sets the tier, not the model: it forces High for migrations, auth and security code, `.github/`, `Procfile` and `system.properties`, major dependency bumps, changes with no reproducing test, and large diffs. The model can only raise the tier. Every app starts as High-only; the owner opts an app into Low in its `AGENTS.md`. If an incident comes back after an automatic fix, there is no second automatic fix.

For now every fix is High. The Low tier waits until incident records show it is safe and the tier check exists outside the model, in an app's CI or a script shipped with the Skill. Routines act as the owner, so nothing else would stop a routine from merging.

## 12. The watcher holds the least it can

heroku-ops holds one fire token per routine, each able to start only that routine, and the Heroku webhook secret. It holds no GitHub credentials, no Heroku credentials that can change anything, and no agent. The routine does the work that needs GitHub, in the app's own repo with the app's own tools. The cost is that the alert path depends on the routine starting: a fire can fail or start without producing an issue. So heroku-ops also has a way to reach the owner that doesn't go through a routine.

## 13. Production apps log what the factory can parse

Heroku's log router splits on newlines, so a multi-line stack trace becomes many unrelated events, and counting or correlating them breaks. Server apps log one JSON event per line, with the stack trace as a field. The convention itself belongs in the zen-of-projects Skill; the reference implementation is `AppLogging.json` in javadoccentral. Heroku's own router and dyno lines are outside the apps' control, so heroku-ops parses those as they are.

## Trade-offs we accepted

- **A fire is not an issue.** The alert path depends on a routine starting, which can fail on rate limits (30 fires per hour per routine, 100 per hour per account), a paused routine or the usage limit. We accept that in return for a watcher with no GitHub credentials, and cover it with a fallback notification.
- **Full network access in the cloud environment.** Builds and tests reach Maven Central and its mirror, javadocs.dev, Docker registries and live services, so an allowlist would keep breaking runs. The cost: code a routine runs, including dependencies and tests, can reach any host. No secrets go in the environment.
- **Latest releases instead of vulnerability alerts.** Moving every direct dependency to its latest release fixes most advisories without reading any. A vulnerable transitive dependency stays until a direct dependency's release moves it.

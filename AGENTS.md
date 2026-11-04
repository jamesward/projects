# AGENTS.md

This repo is the factory: the setup, scripts and project list behind the Claude Code routines that maintain James Ward's projects. Before changing anything, read [DESIGN.md](DESIGN.md); every change has to fit its principles.

## Where things go

Say each thing once, in the one place it belongs, and link to it from anywhere else. When you find something in the wrong place, move it there in the same change.

| What | Where |
|---|---|
| What the factory is and how its parts fit together, for humans (diagrams, components, flows) | [README.md](README.md). Link to the other docs for detail; don't repeat them. |
| Principles, and why the factory is built the way it is (decisions, trade-offs) | [DESIGN.md](DESIGN.md). When a principle changes, change it there first. |
| How to set up and run the factory: setup steps, commands, and the operational facts an agent needs to avoid a known mistake | [FACTORY.md](FACTORY.md) |
| The project list, schedules, registries and production identifiers | [FACTORY.md](FACTORY.md) |
| Conventions for every project, and the maintenance routine itself | the zen-of-projects Skill, in `jamesward/skills` (`skills/zen-of-projects/SKILL.md`, locally `~/projects/jamesward-skills`), never here. It reaches the routines only through a release. |
| Facts about one project and its exceptions to the Skill, each with its reason | that project's `AGENTS.md` |
| Open work, plans and open questions | [TODO.md](TODO.md). Remove an item once it's done or no longer needed; don't keep a done log. |
| How to use a script | the script's docstring; FACTORY.md links to the script and says when to run it |
| History: what happened when, what was tried, verification evidence | the commit message. Keep it in a doc only when it stops someone from repeating a mistake. |

FACTORY.md holds no guidelines and no design reasoning beyond what an agent needs to act correctly. If a sentence explains why the factory is designed some way, it belongs in DESIGN.md; if it says how every project should be, it belongs in the Skill.

## Changing the factory

- Changes reach `main` only through a pull request (DESIGN.md 14): `./factory-land.sh "message" path...` commits the listed files on a branch, opens the PR and squash-merges it. The factory routines run from `main`.
- After editing a schedule table, run `./factory-routines-sync.py` (then `--apply`).
- After changing a factory-owned file or `factory-sync.py`, run `./factory-sync.py` (report only) before `--apply`.
- After editing the "Watched Heroku apps" table or `factory-heroku.py`, run `./factory-heroku.py --lint`. The `heroku control` routine applies the table when a PR merges (FACTORY.md "Heroku control").
- After changing `jdk25-setup.sh`, the owner has to re-paste it into the `JDK25` environment; say so.
- A change works once a routine run shows it working in its transcript (`./factory-transcript.py`), not before. Wait for that run in short, separate polls, never one long loop (FACTORY.md "Waiting for a run without getting stuck").

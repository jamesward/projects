# James Ward Projects

I maintain numerous libraries, websites, build plugins, code samples, IaC tooling, and Nix Packages.
Consistency helps reduce the maintenance burden.

This file holds only three things:
1. How to set up the factory (automation) for each type of project.
2. Shared registries and production identifiers.
3. The project list.

**All guidance and conventions live in the zen-of-projects Skill** (`com.jamesward:skills`, source `~/projects/jamesward-skills`, published at https://start.jamesward.com). Project-specific facts and exceptions live in each project's `AGENTS.md`. Don't add guidelines here; add them to the Skill.

## Branches

- **Factory files go on the default branch.** Routines clone the repository's default branch (usually `main`) and only see what is committed there. So `.factory/`, `AGENTS.md`, `.mcp.json`, `.claude/` and the build changes have to be committed and pushed to the default branch, not to whatever branch the local checkout is on.
- **Before seeding a repo, check out its default branch:** run `gh repo view <owner>/<repo> --json defaultBranchRef -q .defaultBranchRef.name`, then `git checkout <default> && git pull --ff-only`. If the checkout is on a feature branch with uncommitted work, stash that work first (`git stash push -u -m "<why>"`). Never commit it to the default branch along with the setup.
- **Feature branches are left alone.** The routine works only from the default branch, through its rolling `claude/…` PR branch. It doesn't rebase, merge or update long-lived feature branches. Bring setup changes into a feature branch yourself (`git merge main`) when you pick it back up.
- **What a routine is allowed to push:** pushes to `claude/`-prefixed branches always work. Pushes to other branches are rejected if the branch is protected, has someone else's open PR, or carries commits by another author. Keep routine work on `claude/` branches and merge it through PRs.

## Factory Setup: sbt Projects

Each managed sbt repo runs its own `.factory/MAINTENANCE.md` as a scheduled Claude Code routine, one routine per repo, weekly or daily as set in "Managed Repos & Schedules". The routine's behavior is defined by the zen-of-projects Skill ("Daily Routine"). Steps 1–3 below are one-time setup; step 4 is per repo.

Single-repo sessions are the only ones that load the repo's `.mcp.json` and `.claude/settings.json`, so each routine gets exactly one repo.

### GitHub repo settings (all maintained repos)

Run [`factory-github-settings.py`](factory-github-settings.py), and add `--apply` to fix what it finds. It covers every repo in "Maintained Projects" and the schedule tables, and checks that:
- you're watching the repo with **All activity** (GitHub defaults to "Participating and @mentions");
- **Wikis** are off. A wiki that has pages is reported and left on unless you pass `--force-wiki`;
- **Projects** are off.
- **Dependabot alerts** are on and **Dependabot security update PRs** are off. The maintenance routine fixes open alerts in its rolling PR (zen-of-projects step 3), within each project's exceptions. Security update PRs ignored those exceptions: on webjars-locator-core they proposed Spring Boot 3 (Java 17) for a Java 8 library.

Archived repos are skipped. Settings on repos you don't administer are only reported.

### Per-repo checklist

For any repo you put under the factory, whatever its build tool, run `~/projects/projects/factory-repo-check.sh owner/repo`. It reports:
1. Which factory files are present on the default branch.
2. The browser step that grants the Claude App access to the repo (step 1 below).
3. The routine creation command, filled in for the repo (step 4).
4. How to verify with a first run. Do the browser step before the first run: nothing can check it from the CLI, and a run without it does all the work and then fails at `git push`.

### 1. GitHub access

- Install the Claude GitHub App (https://github.com/apps/claude) on every owner that has managed repos: `jamesward`, `skillsjars`, `webjars`, `EffectOrientedProgramming` and `MindviewLLC`. Every installation uses **Only select repositories**, so the App reaches only managed repos.
  - **Each new repo must be added to its owner's list in the browser before its routine runs.** GitHub only allows this change in its UI with a normal login: gh's token gets `403 You do not have permission to modify this app`. Without it, the routine can clone but not push: `remote: Claude doesn't have GitHub access to <repo>` or `403 Resource not accessible by integration`.
  - [`factory-repo-check.sh`](factory-repo-check.sh) `owner/repo` prints the exact link and clicks for that repo. Installation settings:
    - webjars: https://github.com/organizations/webjars/settings/installations/145261926
    - skillsjars: https://github.com/organizations/skillsjars/settings/installations/117903129
    - EffectOrientedProgramming: https://github.com/organizations/EffectOrientedProgramming/settings/installations/141580718
    - MindviewLLC: https://github.com/organizations/MindviewLLC/settings/installations/151367270
    - jamesward (personal): https://github.com/settings/installations → Configure next to Claude
  - Then: **Repository access → Only select repositories → Select repositories → add the repo → Save.**
  - **Check it:** `gh` can't read the App's repository list (403), so use the disabled routine `github access check (on demand)` (`trig_01Rq62FE9XKNfZjbJxq2LWrR`). It clones every managed repo and runs `git push --dry-run` to a `claude/` branch through the App, creating nothing. Add new repos to it, then run it with `claude -p "/schedule run trig_01Rq62FE9XKNfZjbJxq2LWrR"` and read its reply. A missing repo fails with `remote: Claude doesn't have GitHub access to <repo>` (verified against a repo outside the App's list). It isn't in the schedule tables, so `factory-routines-sync.py` reports it as unmanaged and leaves it alone.
- Routines act as you: commits, PRs, merges and comments carry your GitHub identity.
- **Factory and Skills repos.** Every routine can also propose changes to `jamesward/projects` (this factory) and `jamesward/skills` (zen-of-projects step 7, "Improve the factory"). It attaches them at run time with the `add_repo` tool (`access: "push"`), which needs both repos in the personal App installation. They aren't routine sources: a routine with more than one source doesn't load the repo's `.mcp.json`, so sbt-mcp disappears (verified 2026-10-04). The PRs are titled `Factory improvement:`, labeled `factory-improvement`, and never merged by a routine. Review them like any other PR.
- Routines push only to `claude/`-prefixed branches. The rolling `Maintenance:` PR branch is one of these, so later runs can keep pushing to it.
- In the cloud, `gh` authenticates through the GitHub proxy, so don't set `GH_TOKEN`/`GITHUB_TOKEN` in the environment. GraphQL-based `gh` commands such as `gh pr list` fail with a 403. Routines use the built-in GitHub tools or the REST API instead, as described in the Skill.
- Branch protection: auto-merge needs your account to be allowed to merge after CI passes. Required reviews block it, and the PR is then left with `needs-human`.

### 2. Cloud environment `JDK25`

One reusable environment for all managed repos (claude.ai/code → environment selector → `JDK25` → settings):

- **Network access:** Full. Routines run builds and tests that reach Maven Central and its mirror, javadocs.dev, Docker registries and live services (for example `login.jamesward.dev` and `cimd.now` for zio-http-mcp), so an allowlist would keep breaking runs. The tradeoff is that code a routine runs, including dependencies and tests, can reach any host.
- **Setup script:** paste the contents of [`jdk25-setup.sh`](jdk25-setup.sh) (in this directory) into the environment's Setup script field, e.g. `wl-copy < ~/projects/projects/jdk25-setup.sh`. It does three things:
  - Installs Java 25, the default Java for every managed repo. The base image only has OpenJDK 21.
  - Applies the resolver setup from zen-of-projects "Resolvers". The sbt launcher and builds then download from the Google mirror and fall back to Maven Central.
  - Pre-downloads sbt into the environment cache.

  Re-paste it after every change here (last: Gradle and Maven mirrors, 2026-10-07).

  Every command in it is on a single line, with no indentation or backslash continuations. A pasted continuation once merged lines and corrupted `~/.sbt/repositories` (`duplicate label 'local'`). The script fails if that file doesn't come out as exactly 4 lines. Edit the file, not the environment, then re-paste it.

  The script must exit 0 and finish in about 5 minutes to be cached; this block took about 25 seconds locally. Its output is cached for about 7 days, and the cache is rebuilt when the script or the allowed hosts change. To check a session, look for the `--- /root/.sbt/repositories:` listing and the `ls` of `~/.sbt/boot` in the setup output, or run `cat ~/.sbt/repositories ~/.config/sbt/sbtopts`. A launcher error that lists `repo.scala-sbt.org` and `repo.typesafe.com` means the file isn't in effect.
- **Environment variables:**

  ```text
  JAVA_HOME=/usr/lib/jvm/java-25-openjdk-amd64
  SBT_LAUNCH_REPO=https://maven-central.storage-download.googleapis.com/maven2
  BASH_DEFAULT_TIMEOUT_MS=600000
  BASH_MAX_TIMEOUT_MS=1800000
  MCP_TIMEOUT=600000
  CLAUDE_CODE_MCP_STARTUP_WAIT_MS=600000
  ```

  `JAVA_HOME` pins sessions to the Java 25 the script installs. `SBT_LAUNCH_REPO` makes the `./sbt` script download `sbt-launch.jar` from the mirror. The timeouts give long sbt test runs room; the defaults are 2 minutes per command and 10 minutes at most. Don't put secrets here, because anyone using the environment can read them. Paid and integration test keys stay unset, so those tests are skipped.

### 3. MCP in routines

- Claude.ai connectors run through Anthropic's servers, not the session VM. A connector pointed at sbt-mcp (`127.0.0.1:<port>` inside the VM) can't reach it.
- For version lookup and API docs, add javadocs.dev as a connector at claude.ai/customize/connectors with URL `https://www.javadocs.dev/mcp`, and include it in each routine. This supplies the `get_latest_version` / `get_source_file` tools the Skill refers to, without running sbt.
- **sbt-mcp in routines.** A plain HTTP entry in `.mcp.json` fails with `ECONNREFUSED`, because Claude Code connects to MCP servers before anything could start sbt. Instead, each repo uses a stdio bridge, [`sbt-mcp-stdio.sh`](sbt-mcp-stdio.sh) in this directory:
  - In cloud sessions (`CLAUDE_CODE_REMOTE=true`), it starts sbt in the foreground (`./sbt --server`, kept alive with a stdin that never closes) and waits for the port.
    - It has to be a foreground sbt, because `sbt-task` needs an attached console channel. A daemon started by a one-off `./sbt <cmd>` answers `no sbt channel available yet`.
    - Plain `./sbt <task>` calls still connect to the same server.
  - It then relays each MCP message to sbt-mcp over HTTP, using a small stateless Python relay inside the script. When `build.sbt` changes, sbt reloads the build, which restarts the sbt-mcp HTTP server. `mcp-remote` never recovered from that (`fetch failed`); the relay waits for the server to come back. A request that is in flight during the reload returns an error asking the agent to retry.
  - It reads the port from `mcpPort := <port>` in `build.sbt`, so the file is identical in every repo.
  - Locally it only connects to an sbt you already started.
  - Diagnostics go to `/tmp/sbt-mcp-stdio.log` and `/tmp/sbt-mcp-server.log`.

  This is verified in a cloud routine for javadoccentral: the server connected and `get_latest_version` worked. The tools are deferred, so the agent must load them with ToolSearch; `MAINTENANCE.md` step 0 says so.
- With the bridge, the javadocs.dev connector is optional, because sbt-mcp proxies the same tools. Use the connector only for repos without the bridge.

#### Set up the sbt-mcp bridge in a repo

Run from the repo root. `<name>` is the server name already in `.kiro/settings/mcp.json`, for example `sbt-mcp-zio-mavencentral`.

1. Copy the bridge verbatim:

   ```bash
   mkdir -p .claude && cp ~/projects/projects/sbt-mcp-stdio.sh .claude/sbt-mcp-stdio.sh
   ```

2. Register it in `.mcp.json`, next to any servers already listed there:

   ```json
   { "mcpServers": { "<name>": { "type": "stdio", "command": "bash", "args": [".claude/sbt-mcp-stdio.sh"], "timeout": 1800000 } } }
   ```

   The 30-minute `timeout` (what `mcpInstall` recommends) lets long `sbt-task` calls such as `testFull` finish; without it a routine saw `tool "sbt-task" timed out after 60s`.

3. Approve it in `.claude/settings.json`, merging with any settings already there: `{ "enabledMcpjsonServers": ["<name>"] }`. Without this the server stays `pending`.
4. In `AGENTS.md`'s sbt-mcp section, note that Claude Code uses this bridge, that its tools are deferred (load them with ToolSearch, searching `<name>`), and where the diagnostics go.
5. Verify locally with no sbt running (`./sbt shutdown` first). The run should list the server as `connected`, run `show name`, and return a version:

   ```bash
   CLAUDE_CODE_REMOTE=true MCP_TIMEOUT=600000 CLAUDE_CODE_MCP_STARTUP_WAIT_MS=600000 claude -p "Using only the MCP server <name>, call sbt-task with 'show name' and get_latest_version for com.jamesward:skills; reply with both results." --model haiku --max-turns 8 --allowedTools 'mcp__<name>__sbt-task' 'mcp__<name>__get_latest_version'
   ./sbt shutdown
   ```

   This starts sbt the way a cloud session does, and the `claude -p` call makes a small paid request.
6. Commit and push `.claude/sbt-mcp-stdio.sh`, `.claude/settings.json`, `.mcp.json`, `AGENTS.md` and `.factory/MAINTENANCE.md` to the default branch. The routine only sees what is on GitHub.

### 4. Create the routine

Requires a claude.ai login, not an API key or Bedrock. First make sure that:
- the repo's `.factory/MAINTENANCE.md` and `AGENTS.md` are pushed to its default branch, because the routine clones from GitHub, not your checkout;
- the browser App step from step 1 is done.

Then add the repo to one of the tables in "Managed Repos & Schedules" and run `~/projects/projects/factory-routines-sync.py --apply`. The script creates the routine with the standard name, prompt, `JDK25` environment and no connectors. The server attaches every claude.ai connector to a new routine, and the script removes them.
- Pick a time a few minutes past the hour, and stagger repos so they don't all hit Maven Central at once.
- Repos with the sbt-mcp bridge get the javadocs.dev tools through sbt-mcp. Maven and Gradle repos get them from the `javadocs` server in `.mcp.json`.

Manage routines with `/schedule list`, `/schedule update` and `/schedule run`, and ask `/schedule why did <routine> fail?` to read a run's log. API triggers can only be added on the web (claude.ai/code/routines). A green run status only means the session exited cleanly; read the transcript to see whether the work succeeded.

Runs count against your subscription usage. Scheduled runs are limited to 100 per hour per account.

## Factory Setup: Maven & Gradle Projects

These use the same routine, environment and `MAINTENANCE.md` as sbt projects. The conventions are in zen-of-projects ("Maven and Gradle Projects"). There is no sbt-mcp, so each repo registers the javadocs.dev MCP server directly.

1. **One-time:** GitHub access and the `JDK25` environment, as in sbt steps 1–2. `jdk25-setup.sh` also prefers the Google mirror for Gradle (an init script in `~/.gradle/init.d/` that puts it first in the build's own repositories) and Maven (an active profile in `~/.m2/settings.xml`), with Maven Central as the fallback. Before that, spring-ai-mcp-demo and mcp-apps-demo routines failed on `Received status code 429 from server: Too Many Requests` from Maven Central (2026-10-06). Verified locally with fresh caches: every download came from the mirror, for settings-level, project-level and Maven repositories.
2. **Seed the repo,** using the snippets in the Skill. The first routine run aligns the rest.
   - Add the SkillsJars plugin with the `com.jamesward:skills` dependency (Maven: `com.skillsjars:maven-plugin` with `<dir>.kiro/skills</dir>`; Gradle: `com.skillsjars.gradle-plugin` with `skill(...)`), and add `.kiro/skills/` to `.gitignore`.
   - Add a `javadocs` HTTP server (`https://www.javadocs.dev/mcp`) to `.mcp.json` and `.kiro/settings/mcp.json`, and approve it in `.claude/settings.json` (`enabledMcpjsonServers`).
   - Copy `.factory/MAINTENANCE.md` from any sbt repo. It's the same file for every build tool.
   - Write a minimal `AGENTS.md`: what the project is, the Skills, the exact wrapper commands, the `javadocs` MCP server, and any exceptions (for example a library that targets Java 8).
   - Verify that `./mvnw -q skillsjars:extract` or `./gradlew extractSkillsJars` fills `.kiro/skills/`. Then commit and push.
3. **Create the routine** exactly as in sbt step 4.

Verified end to end after the browser App step. In each case the run pushed, opened a PR, waited for its CI to pass, and squash-merged it:
- webjars-locator-lite (Maven, routine `trig_01Q2pMzUC7gDg1RG8NEzDVd2`): PR #26.
- hello-spring-ai-bedrock (Gradle/Kotlin, routine `trig_01XQvq7iqTV3hXCod3eXWHij`): PR #10, which enabled `allWarningsAsErrors`.

**Testing an unreleased Skill:** copy `~/projects/jamesward-skills/skills/zen-of-projects/SKILL.md` to `.factory/skills/zen-of-projects/SKILL.md` in the repo under test. `MAINTENANCE.md` step 3 reads that copy instead of the extracted one. Delete it once the Skill is released and the repo's `com.jamesward:skills` pin includes the change.

**Repos without the Skills dependency:** the SkillsJars plugins themselves and their examples (`skillsjars-gradle-plugin`, `skillsjars-maven-plugin`, `skillsjars-example-spring-ai`) don't depend on `com.jamesward:skills`: in a plugin's own build or a published example it would muddy what the project demonstrates. Their `.factory/MAINTENANCE.md` replaces bootstrap steps 1–3 with a shallow clone of jamesward/skills into `/tmp/jamesward-skills` (pre-approved in `.claude/settings.json`), and `AGENTS.md` records the exception. A `curl` of https://start.jamesward.com got HTTP 403 from the cloud proxy (its redirect to the raw file is refused), so all three routines stopped at step 1 (2026-10-06/07).

## Factory Setup: Websites (draft)

The guidance is the "Website Projects" section of zen-of-projects. Static sites have no build, so their routine loads the Skill from https://start.jamesward.com instead of SkillsJars. They don't use MCP servers. Sites set up this way: `jamesward/ai4jvm` (daily) and `MindviewLLC/podcast` (happypathprogramming.com, weekly; its regeneration rules live in its `AGENTS.md` and `.scripts/`).

1. **Infrastructure:** each site's hosting is defined in `~/projects/domains/domains.pkl` (repo `jamesward/domains`) as a `staticSite` entry with `githubRepo = "<owner>/<repo>"`. The `staticSite` pattern comes from `cfn-pkl-extras`. It creates the S3 bucket, CloudFront distribution and DNS, plus a CodeBuild project that runs on every push to the site repo's default branch:
   - it syncs the repo to S3 (`aws s3 sync --delete`, skipping the globs listed in `.slugignore`)
   - it invalidates CloudFront

   So **a merge to the default branch is a production deploy**. To add or move a site, change `domains.pkl` and deploy that repo; the site repo needs nothing else.
2. **`.slugignore`:** list every non-site file in it: `AGENTS.md`, `SPEC.md`, `.factory/*`, `.github/*`, `.claude/*` and so on. Since cfn-pkl-extras 0.2.6, every deploy also deletes bucket objects that match an ignored pattern. So adding a file to `.slugignore` removes it from the live site on the next push; it now returns 403.
3. **Seed the repo:**
   - a site-specific `.factory/MAINTENANCE.md` (use `ai4jvm/.factory/MAINTENANCE.md` as the template);
   - a structural check script, plus a CI workflow that runs it on push and PR;
   - `AGENTS.md` covering the spec, the generated files, publishing, and exceptions.

   Remove any old comment-triggered workflows. The routine now triages PRs.
4. **GitHub access and routine:** the browser App step and the sync are the same as for sbt projects (`factory-repo-check.sh`, then add the repo to a schedule table and run `factory-routines-sync.py --apply`). The `JDK25` environment works for sites as well; it has full network access.

## Factory sync

[`factory-sync.py`](factory-sync.py) keeps the factory-owned files in every managed repo (the repos in "Managed Repos & Schedules") equal to the factory's current versions, without running any repo's routine:
- `.factory/MAINTENANCE.md`: the bootstrap from the published zen-of-projects Skill (jamesward/skills `main`), or the no-Skills-dependency variant. ai4jvm and podcast keep their own.
- `.claude/sbt-mcp-stdio.sh`: [`sbt-mcp-stdio.sh`](sbt-mcp-stdio.sh) here, for sbt repos.
- The factory-owned entries in `.mcp.json`, `.claude/settings.json` and `.kiro/settings/mcp.json` (the sbt-mcp bridge or `javadocs`). Other servers and settings are kept.
- No `.github/dependabot.yml`; a `needs-human` label.

`AGENTS.md` and everything else stay with each repo's maintenance routine. Without arguments the script only reports; `--apply` opens or updates one `Factory sync:` PR per drifted repo, from the branch `claude/factory-sync`, and squash-merges it once its CI has run and passed. Failing or missing CI gets `needs-human` and a comment; checks still running are left for the next run. Pass `owner/repo` arguments to limit it.

The routine `factory sync` (`trig_01NUJivtCGbUbQCyZjZAju5w`, daily 05:07 America/Denver, before the maintenance routines) runs it. It isn't in the schedule tables, so `factory-routines-sync.py` lists it as unmanaged. In that routine:

1. Run `./factory-sync.py --list`. For each repo, call the `add_repo` tool (load it with ToolSearch) with `access: "push"`, one call at a time, and don't clone them; the script clones what it needs.
2. Run `python3 -u ./factory-sync.py --apply` with a 30-minute command timeout.
3. Reply with the script's summary line and every line starting with `~`, `!!` or `   ` (PR numbers and merge results). If a repo failed (`!!`) or a PR got `needs-human`, say why. Change nothing else: don't edit files in this repo or in the managed repos by hand, and don't run any repo's maintenance routine.

Run it locally the same way after editing the factory (`./factory-sync.py`, then `--apply`). Verified 2026-10-05: a cloud session `add_repo`'d all 44 repos without prompts and the report took 88s; locally `--apply` opened, CI-checked and merged toolbook PR #99. In cloud sessions the script reads the Skill from a clone of jamesward/skills, because the git proxy refuses start.jamesward.com's redirect to the raw file (HTTP 403).

## Managed Repos & Schedules

Every managed repo has one routine, `<repo name> maintenance`, that runs `.factory/MAINTENANCE.md` on the `JDK25` environment. These tables are the source of truth for which repos are managed and how often their routine runs. **Weekly is the default.** Move a repo to the daily table when it needs closer attention, for example a production service or a repo under active test.

After editing the tables, run [`factory-routines-sync.py`](factory-routines-sync.py). It reads both tables, fetches each routine by the id in the Routine column (the routines API `list` returns only the first 20 and ignores its cursor), and reports drift:
- a missing routine (one is created only once the repo's factory files are on its default branch)
- the wrong schedule, which also covers moving a repo between weekly and daily
- the wrong name, prompt, environment or notifications (email only)
- attached connectors, or a disabled routine
- routines for repos that aren't listed, which it leaves alone

It only reports by default. `--apply` creates or updates routines to match the tables, writes a new routine's id into its row, then checks again. Leave the Routine cell empty for a new repo; never copy an id between rows. It never deletes a routine. Times are America/Denver. Cron is stored in UTC, so re-run `--apply` after each daylight-saving change to keep the local times right.

### Managed repos (updated daily)

| Repo | Time (America/Denver) | Routine |
|---|---|---|
| `jamesward/ai4jvm` | 09:07 | `trig_01FtHoNd7padgAc6chZwGdGH` |

### Managed repos (weekly, default)

| Repo | Day | Time (America/Denver) | Routine |
|---|---|---|---|
| `jamesward/cimdnow` | Mon | 06:07 | `trig_017ceRKyFqxt5Bdg7AZx4MSi` |
| `jamesward/evals-demo` | Tue | 06:07 | `trig_01KJiZbz3s79JdZCStvmFHkW` |
| `jamesward/hello-zio-bedrock` | Wed | 06:07 | `trig_012ciycBPmMMB7mA1MHFWanu` |
| `jamesward/hello-zio-http` | Thu | 06:07 | `trig_01SPY7Zw8aARTuQx29xwVyFZ` |
| `jamesward/hello-zio-mcp` | Fri | 06:07 | `trig_01SeFGuH1odTGC5KyaWJ1oak` |
| `jamesward/hello-zio-typesafe-ai` | Mon | 06:17 | `trig_01DSKfoetJzLVFYRkea9PGkK` |
| `jamesward/jev-llm-c4` | Tue | 06:17 | `trig_01Kk7rN2xfEQZ8Z9RRkMSXzU` |
| `jamesward/jevlm` | Wed | 06:17 | `trig_014mdtwSnD7rwhc2V4Y5776C` |
| `jamesward/json-paste` | Thu | 06:17 | `trig_01E264FBCwMsUogtU2QdMXHN` |
| `jamesward/sbt-mcp` | Fri | 06:17 | `trig_01225Q5bDreRDz21kP46AY2n` |
| `jamesward/sbt-reload` | Mon | 06:27 | `trig_01EgRxaWB4NrEFqDNX6xGNd7` |
| `jamesward/sbt-sass` | Tue | 06:27 | `trig_01NSc4mKG4sXe3uUwLLer5Mv` |
| `jamesward/sbt-tdepver` | Wed | 06:27 | `trig_01AF4H87AquwQAepJUDWHYN1` |
| `jamesward/zio-bedrock` | Thu | 06:27 | `trig_01PvBPG39EyvrjVHi8sXHZSj` |
| `jamesward/zio-evals` | Fri | 06:27 | `trig_017HvSe3wYQ6XFAx5gjPqmEi` |
| `jamesward/zio-git` | Mon | 06:37 | `trig_01PTC5VWi3kxB95f5cSYSjvM` |
| `jamesward/zio-http-guard` | Tue | 06:37 | `trig_01RfJLrdtmNYHQbWwKbhErow` |
| `jamesward/zio-http-mcp` | Wed | 06:37 | `trig_01QKdyXLkSSGPRuTKrQPwSkh` |
| `jamesward/zio-typesafe-ai` | Thu | 06:37 | `trig_01T1YEe5fcQWSVUFDYLhj5R5` |
| `jamesward/javadoccentral` | Tue | 06:57 | `trig_015gFmnB5JMkaq6p3BGx7LwM` |
| `jamesward/zio-mavencentral` | Wed | 06:57 | `trig_01R8SF1ciT7FGtmFsNi1gRJV` |
| `jamesward/hello-spring-ai-bedrock` | Fri | 06:57 | `trig_01XQvq7iqTV3hXCod3eXWHij` |
| `skillsjars/skillsjars` | Fri | 06:37 | `trig_01BJxuujQNczmayem2HYCRVb` |
| `skillsjars/skillsjars-sbt-plugin` | Mon | 06:47 | `trig_01QXX7eMu84C4SmAKGGkFVS3` |
| `skillsjars/skillsjars-gradle-plugin` | Tue | 07:07 | `trig_01CeDWwecFZp6JnCo8S8tVCd` |
| `skillsjars/skillsjars-maven-plugin` | Wed | 07:07 | `trig_01VgzqFH6WP5qeMBnWSrcFFf` |
| `skillsjars/skillsjars-example-spring-ai` | Thu | 07:07 | `trig_01ApVieaP8rfgPxC95GWUSwA` |
| `webjars/sbt-webjars` | Tue | 06:47 | `trig_01KJicXFw9usuKRGqPJbZmxb` |
| `webjars/webjars` | Wed | 06:47 | `trig_0129h28dMtfdoGpjCShqSAW4` |
| `webjars/webjars-file-service` | Thu | 06:47 | `trig_01FHbSrPMoVr1THjuu7yUyWC` |
| `webjars/webjars-locator-lite` | Thu | 06:57 | `trig_01Q2pMzUC7gDg1RG8NEzDVd2` |
| `EffectOrientedProgramming/toolbook` | Mon | 06:57 | `trig_014ivo7aeT7zKQerQrHKqQpy` |
| `MindviewLLC/podcast` | Mon | 09:07 | `trig_01LkjfDGz34nWNFaESCHt5WJ` |
| `jamesward/agent-integration-demo` | Mon | 07:07 | `trig_0185qVQ7U4Qx2geqfmxMN5vK` |
| `jamesward/hello-spring-ai-agentcore` | Fri | 07:07 | `trig_01MHuEZ2Dydx4KJyCRCPfJaF` |
| `jamesward/hello-spring-mcp-server` | Mon | 07:17 | `trig_019UyKcDaELqVzUSfqpXL8Aj` |
| `jamesward/mcp-apps-demo` | Tue | 07:17 | `trig_01C8kZmDtkafRnwmxHdb4njS` |
| `jamesward/spring-ai-mcp-demo` | Wed | 07:17 | `trig_019Lys9aGEZiztQSSQLhcVPA` |
| `jamesward/login-jamesward-dev` | Thu | 07:17 | `trig_011TWmHUb8RF1erf4n8Jk53T` |
| `webjars/webjars-locator` | Fri | 07:17 | `trig_01XMEwZic2oTRBx1wuYb1BoR` |
| `webjars/webjars-locator-core` | Mon | 07:27 | `trig_015oFBdU7npQ6HpdkLPRRQch` |
| `jamesward/cfn-pkl-extras` | Tue | 07:27 | `trig_01EtjTMoEEM3A7mDVT2svqgx` |
| `jamesward/pklgha` | Wed | 07:27 | `trig_01RPBKeF8x8DcuCuVKYH1kqL` |

## Registries & Production Identifiers

### sbt-mcp port registry

Each project gets one stable loopback port:

| Port | Project | Port | Project |
|------|---------|------|---------|
| 5011 | sbt-mcp/test-project | 5110 | sbt-sass |
| 5012 | toolbook | 5111 | sbt-tdepver |
| 5014 | jev-llm-c4 | 5112 | skillsjars |
| 5015 | jevlm | 5113 | skillsjars-sbt-plugin |
| 5055 | webjars | 5114 | sbt-webjars |
| 5100 | cimd.now (cimdtest) | 5115 | webjars-file-service |
| 5101 | evals-demo | 5116 | zio-bedrock |
| 5102 | hello-zio-bedrock | 5117 | zio-evals |
| 5103 | hello-zio-http | 5118 | zio-git |
| 5104 | hello-zio-mcp | 5119 | zio-http-guard |
| 5105 | hello-zio-typesafe-ai | 5120 | zio-http-mcp |
| 5106 | javadoccentral | 5121 | zio-mavencentral |
| 5107 | json-paste | 5122 | zio-typesafe-ai |
| 5108 | sbt-mcp | | |
| 5109 | sbt-reload | | |

Next free port: 5123

### Production service versions (Heroku, run locally)

Container images in tests track the production service they stand in for (zen-of-projects "Container images track production"), so routines never bump them. Check production from this machine, where the Heroku CLI is logged in (`heroku login`), and update the image plus the `AGENTS.md` note only when production changed:

```bash
heroku addons --app <app>              # which add-ons and plans
heroku redis:info --app <app>          # Key-Value Store (Valkey) version
heroku pg:info --app <app>             # Postgres version ("PG Version")
```

| Repo | Test image | Production service (checked 2026-10-01) |
|---|---|---|
| javadoccentral | `valkey/valkey:8.1.9` | Heroku Key-Value Store `redis-angular-97987` on `javadocs`: 8.1.9 |
| webjars | `valkey/valkey:8.1` | Heroku Key-Value Store `redis-deep-72942` on `webjars`: 8.1.9 |
| toolbook | `postgres:17.9-alpine` | Heroku Postgres on `mytoolbook-api`: 17.9 |

## Maintained Projects

### Agent Integration Demo

Source: https://github.com/jamesward/agent-integration-demo


### ai4jvm.com

Source: https://github.com/jamesward/ai4jvm
AWS Infra: https://github.com/jamesward/domains (`domains.pkl`, `["ai4jvm.com"] { staticSite { githubRepo = "jamesward/ai4jvm" } }`). Deploys on every push to `main`.


### cfn-extras-resource

CloudFormation Extras Resource

Source: https://github.com/jamesward/cfn-extras-resource
S3 Bucket: s3://cfn-extras-resource
Replaces (archived): https://github.com/jamesward/cfn-domain-resource (now the Domain resource) and https://github.com/jamesward/cfn-connectionlookup-resource (now the Connection lookup resource)


### cimd.now

Enable CIMD testing

Source: https://github.com/jamesward/cimdnow (local: `~/projects/cimdtest`)
Heroku App: cimdapp


### CloudFormation Pkl Extras

Source: https://github.com/jamesward/cfn-pkl-extras


### EasyRacer

Examples of structured concurrency

Source: https://github.com/jamesward/easyracer
Container: ghcr.io/jamesward/easyracer:latest


### evals-demo

Sample A/B agent eval built on zio-evals

Source: https://github.com/jamesward/evals-demo


### Happy Path Programming

Source: https://github.com/MindviewLLC/podcast
AWS Infra: https://github.com/jamesward/domains


### hello-spring-ai-agentcore

Source: https://github.com/jamesward/hello-spring-ai-agentcore


### hello-spring-ai-bedrock

Minimal Spring AI Bedrock example

Source: https://github.com/jamesward/hello-spring-ai-bedrock


### hello-zio-http

Small sample of ZIO HTTP

Source: https://github.com/jamesward/hello-zio-http


### Heroku Buildpack Scala

Source: https://github.com/jamesward/buildpack-scala


### Heroku Buildpack Scala Native

Source: https://github.com/jamesward/buildpack-scala-native


### James Ward Agent Skills

Source: https://github.com/jamesward/skills
Maven Central: com.jamesward:skills


### James Ward Domains & Websites

Pkl CloudFormation IaC for domains & websites on AWS

Source: https://github.com/jamesward/domains


### Jev demos

Scala 3 / ZIO HTTP servers showing Jev (TypeSafe AI)

#### Jev Word Stream

Source: https://github.com/jamesward/jevlm

#### Jev vs LLM Connect Four

Source: https://github.com/jamesward/jev-llm-c4


### jamesward.com

Source: https://github.com/jamesward/jamesward
AWS Infra: https://github.com/jamesward/domains


### javadocs.dev

Website & MCP for Java/Kotlin/Scala docs

Source: https://github.com/jamesward/javadoccentral
Heroku App: javadocs


### json-paste.herokuapp.com

Source: https://github.com/jamesward/json-paste
Heroku App: json-paste


### Leanpub GitHub Actions

Source: https://github.com/jamesward/leanpub-actions


### presos.jamesward.com

Presentation slides, one git submodule per talk (for example `jamesward/agent_skills`)

Source: https://github.com/jamesward/presos.jamesward.com
Hosting: GitHub Pages (`CNAME` presos.jamesward.com)


### login.jamesward.dev

Demo IDP

Source: https://github.com/jamesward/login-jamesward-dev
Heroku App: login-jamesward-dev


### mcp-demo.jamesward.com

Source: https://github.com/jamesward/mcp-apps-demo
Heroku App: mcp-apps-demo


### mcp-test.jamesward.com

Source: https://github.com/jamesward/hello-spring-mcp-server
Heroku App: mcp-sample


### mytoolbook.ai

ToolBooks

Source: https://github.com/EffectOrientedProgramming/toolbook
Heroku Apps:
- mytoolbook-api (private via API PSK) api.mytoolbook.ai
- mytoolbook-login login.mytoolbook.ai
- mytoolbook-mcp mcp.mytoolbook.ai
- mytoolbook-proxy proxy.mytoolbook.ai
- mytoolbook-www www.mytoolbook.ai


### Pkl GitHub Actions

Source: https://github.com/jamesward/pklgha


### sbt-mcp

Source: https://github.com/jamesward/sbt-mcp
Maven Central: com.jamesward:sbt-mcp_sbt2_3


### sbt-reload

Source: https://github.com/jamesward/sbt-reload
Maven Central: com.jamesward:sbt-reload_sbt2_3


### sbt-sass

Source: https://github.com/jamesward/sbt-sass
Maven Central: com.jamesward:sbt-sass_sbt2_3 (sbt 2), com.jamesward:sbt-sass_2.12_1.0 (sbt 1)


### sbt-tdepver

Pin explicit dependency versions to the version supplied by a transitive dependency

Source: https://github.com/jamesward/sbt-tdepver
Maven Central: com.jamesward:sbt-tdepver_sbt2_3


### SkillsJars

Agent Skills in JARs

#### www.skillsjars.com

Source: https://github.com/skillsjars/skillsjars
Heroku App: skillsjars

#### SkillsJars Gradle Plugin

https://github.com/skillsjars/skillsjars-gradle-plugin

#### SkillsJars Maven Plugin

https://github.com/skillsjars/skillsjars-maven-plugin

#### SkillsJars sbt Plugin

https://github.com/skillsjars/skillsjars-sbt-plugin
Maven Central: com.skillsjars:skillsjars-sbt-plugin_sbt2_3 (sbt 2), com.skillsjars:skillsjars-sbt-plugin_2.12_1.0 (sbt 1)

#### SkillsJars Spring Example

https://github.com/skillsjars/skillsjars-example-spring-ai


### Spring AI MCP Demo

Source: https://github.com/jamesward/spring-ai-mcp-demo


### WebJars

#### webjars.org

Search & Deploy WebJars

Source: https://github.com/webjars/webjars
Heroku App: webjars

#### WebJars CDN

Serves https://www.jsdelivr.com/ WebJar Contents

Source: https://github.com/webjars/webjars-file-service
Heroku App: webjars-file-service

#### Classic WebJars Builds

Old Classic WebJars each had a GitHub repo in: https://github.com/webjars
The new Classic WebJars have metadata in: https://github.com/webjars/webjars-classic

#### Legacy WebJars Locator

https://github.com/webjars/webjars-locator
https://github.com/webjars/webjars-locator-core

#### Lite WebJars Locator

https://github.com/webjars/webjars-locator-lite

#### WebJars sbt Plugin

https://github.com/webjars/sbt-webjars

#### semver.webjars.org

Uses the Node SemVer Library to resolve version range things for WebJars

Source: https://github.com/jamesward/semver-as-a-service
Heroku App: semver-as-a-service


### zio-bedrock

ZIO Bedrock Library (successor to the archived https://github.com/jamesward/zio-bedrock-converse)

Source: https://github.com/jamesward/zio-bedrock
Maven Central: com.jamesward:zio-bedrock_3

#### Hello ZIO Bedrock

Source: https://github.com/jamesward/hello-zio-bedrock


### zio-typesafe-ai

ZIO TypeSafe AI Library

Source: https://github.com/jamesward/zio-typesafe-ai
Maven Central: com.jamesward:zio-typesafe-ai_3

#### hello-zio-typesafe-ai

Source: https://github.com/jamesward/hello-zio-typesafe-ai


### zio-evals

ZIO Agent Evals Library

Source: https://github.com/jamesward/zio-evals
Maven Central: com.jamesward:zio-evals_3


### zio-git

Minimal ZIO Git Library

Source: https://github.com/jamesward/zio-git
Maven Central: com.jamesward:zio-git_3


### zio-http-guard

Abuse protection middleware for ZIO HTTP

Source: https://github.com/jamesward/zio-http-guard
Maven Central: com.jamesward:zio-http-guard_3


### zio-http-mcp

ZIO HTTP MCP library

Source: https://github.com/jamesward/zio-http-mcp
Maven Central: com.jamesward:zio-http-mcp_3

Requires human review:
- Changes to the end-user/developer facing interfaces/APIs

#### hello-zio-mcp

Small sample of ZIO HTTP MCP

Source: https://github.com/jamesward/hello-zio-mcp


### zio-mavencentral

Read & deploy to Maven Central

Source: https://github.com/jamesward/zio-mavencentral
Maven Central: com.jamesward:zio-mavencentral_3


## No Longer Maintained

Projects that left the factory. They keep their entries for reference, but have no routine and aren't checked by the factory scripts.

### Bootiful Spring AI Book & MCP

In progress book with Josh Long about Spring AI. MCP server for the book with IDP.

Superseded by mytoolbook.ai (EffectOrientedProgramming/toolbook). Repos archived 2026-10-02.

#### mcp.bootifulspringai.com

Source: https://github.com/agentic-spring-ai-book/mcp-server
Heroku App: spring-ai-mcp

#### login.bootifulspringai.com

Source: https://github.com/agentic-spring-ai-book/login-server
Heroku App: spring-ai-login


### Effect Oriented Programming Book & MCP

Book & MCP about Effect Oriented Programming

Superseded by mytoolbook.ai (EffectOrientedProgramming/toolbook). Repos archived 2026-10-02.

#### login.effectorientedprogramming.com

Source: https://github.com/EffectOrientedProgramming/login
Heroku App: eop-login

#### mcp.effectorientedprogramming.com

Source: https://github.com/EffectOrientedProgramming/mcp
Heroku App: eop-mcp

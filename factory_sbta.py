"""sbta migration for an sbt repo checkout: replaces sbt-mcp and ./sbt with sbta.

Used by factory-sync.py (kind "sbt"). Pure file edits on a checkout; returns change descriptions.
"""
import json
import os
import re
import urllib.request
from pathlib import Path

SBTA_RELEASES = "https://github.com/jamesward/sbta/releases/latest/download"
SBTA_SERVER = {"type": "stdio", "command": "./sbta", "args": ["--mcp"], "timeout": 1800000}

# sbt-mcp settings and their comment lines in *.sbt files.
MCP_SETTING = re.compile(
    r"^[ \t]*(?:(?:Global|ThisBuild)\s*/\s*)?(?:mcpEnabled|mcpHost|mcpPort|mcpDisableInCI|mcpDocsUrl)\s*:=.*(?:\n|$)",
    re.M)
MCP_COMMENT = re.compile(r"^[ \t]*//[^\n]*\bsbt-mcp\b[^\n]*\n", re.M)
MCP_PLUGIN = re.compile(r'^[ \t]*(?://[^\n]*\n[ \t]*)?addSbtPlugin\("com\.jamesward"\s*%\s*"sbt-mcp"\s*%\s*"[^"]*"\)[^\n]*(?:\n|$)', re.M)
# ./sbt (and sbt.bat) as a launcher, not ./sbta, ./sbt-something or ./sbt.foo
DOT_SBT = re.compile(r"(?<![\w.\-/])\./sbt(?![\w.\-])")
SBT_BAT = re.compile(r"(?<![\w.\-/])sbt\.bat\b")
# text files where ./sbt references are rewritten
TEXT_GLOBS = ("AGENTS.md", "CLAUDE.md", "README.md", "DEV*.md", "*.md", ".github/workflows/*.yml",
              ".github/workflows/*.yaml", ".jvmopts", ".sbtopts", "*.sbt", "project/*.scala", "infra/*.sh",
              "bin/*.sh", "scripts/*.sh", "*.sh", "Procfile", "app.json", "system.properties")
SKIP_DIRS = {".git", "target", "node_modules", ".bsp", ".idea", ".kiro", "src"}

_cache = {}


def release_scripts():
    """(sbta, sbta.bat) bytes of the latest sbta release."""
    if "s" not in _cache:
        out = []
        for name in ("sbta", "sbta.bat"):
            req = urllib.request.Request(f"{SBTA_RELEASES}/{name}", headers={"User-Agent": "factory-sync"})
            out.append(urllib.request.urlopen(req, timeout=60).read())
        _cache["s"] = tuple(out)
    return _cache["s"]


def release_version():
    m = re.search(rb'declare sbta_version="([^"]+)"', release_scripts()[0])
    return m.group(1).decode() if m else "?"


def _load(p):
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except ValueError:
        return None


def _write_json(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2) + "\n")


def _same_script(a, b):
    """Equal ignoring line endings (git may check .bat files out with LF or CRLF)."""
    return a.replace(b"\r\n", b"\n") == b.replace(b"\r\n", b"\n")


def strip_mcp_settings(text):
    """Remove sbt-mcp setting lines and the comment block directly above them when it's about MCP."""
    lines = text.split("\n")
    drop = set()
    for i, l in enumerate(lines):
        if MCP_SETTING.match(l + "\n"):
            drop.add(i)
            j = i - 1
            block = []
            while j >= 0 and (j in drop or lines[j].lstrip().startswith("//")):
                if j not in drop:
                    block.append(j)
                j -= 1
            if any(re.search(r"mcp", lines[k], re.I) for k in block):
                drop.update(block)
    for i, l in enumerate(lines):
        if MCP_COMMENT.match(l + "\n"):
            drop.add(i)
    out = "\n".join(l for i, l in enumerate(lines) if i not in drop)
    return re.sub(r"\n{3,}", "\n\n", out)


def _text_files(d):
    seen = set()
    for g in TEXT_GLOBS:
        for f in d.glob(g):
            if f.is_file() and not (set(f.relative_to(d).parts[:-1]) & SKIP_DIRS) and f not in seen:
                seen.add(f)
                yield f


def migrate(d):
    d = Path(d)
    changes = []
    sbta, sbta_bat = release_scripts()
    v = release_version()

    # 1. launchers: the latest sbta release, executable; no ./sbt or sbt.bat
    for name, data in (("sbta", sbta), ("sbta.bat", sbta_bat)):
        p = d / name
        if not p.exists() or not _same_script(p.read_bytes(), data):
            p.write_bytes(data)
            changes.append(f"{name}: sbta {v} (latest release)")
    if not os.access(d / "sbta", os.X_OK):
        os.chmod(d / "sbta", 0o755)
        changes.append("sbta: executable")
    for name in ("sbt", "sbt.bat"):
        if (d / name).exists():
            (d / name).unlink()
            changes.append(f"remove {name} (sbta replaces it)")

    # 2. sbt-mcp: plugin, settings, stdio bridge
    pl = d / "project/plugins.sbt"
    if pl.exists():
        s = pl.read_text()
        s2 = MCP_PLUGIN.sub("", s)
        if s2 != s:
            pl.write_text(s2)
            changes.append("project/plugins.sbt: remove the sbt-mcp plugin (sbta needs none)")
    for f in [d / "build.sbt", *d.glob("*.sbt")]:
        if not f.is_file():
            continue
        s = f.read_text()
        if not MCP_SETTING.search(s):
            continue
        s2 = strip_mcp_settings(s)
        if s2 != s:
            f.write_text(s2)
            changes.append(f"{f.name}: remove the sbt-mcp settings")
    if (d / ".claude/sbt-mcp-stdio.sh").exists():
        (d / ".claude/sbt-mcp-stdio.sh").unlink()
        changes.append("remove .claude/sbt-mcp-stdio.sh (sbta is the MCP server)")

    # 3. MCP config: the sbta server, sbt-mcp* entries removed, other servers kept
    for rel in (".mcp.json", ".kiro/settings/mcp.json"):
        p = d / rel
        j = _load(p)
        if j is None:
            changes.append(f"{rel}: not valid JSON, left alone")
            continue
        servers = j.setdefault("mcpServers", {})
        old = [k for k in servers if k.startswith("sbt-mcp")]
        before = json.dumps(servers, sort_keys=True)
        for k in old:
            del servers[k]
        servers["sbta"] = dict(SBTA_SERVER)
        if json.dumps(servers, sort_keys=True) != before:
            _write_json(p, j)
            changes.append(f"{rel}: MCP server sbta (./sbta --mcp)" + (f", replacing {', '.join(old)}" if old else ""))
    p = d / ".claude/settings.json"
    st = _load(p)
    if st is None:
        changes.append(".claude/settings.json: not valid JSON, left alone")
    else:
        en = st.get("enabledMcpjsonServers", [])
        en2 = [s for s in en if not s.startswith("sbt-mcp")]
        if "sbta" not in en2:
            en2.append("sbta")
        if en2 != en:
            st["enabledMcpjsonServers"] = en2
            _write_json(p, st)
            changes.append(".claude/settings.json: approve sbta")

    # 4. AGENTS.md's factory-written MCP bullet, then ./sbt -> ./sbta in CI, docs and scripts
    # (not sources or test fixtures)
    changes += agents_md(d)
    touched = []
    for f in _text_files(d):
        if f.name in ("sbta", "sbta.bat"):
            continue
        try:
            s = f.read_text()
        except UnicodeDecodeError:
            continue
        s2 = SBT_BAT.sub("sbta.bat", DOT_SBT.sub("./sbta", s))
        # the MCP server is now named `sbta` in every project
        s2 = re.sub(r"`sbt-mcp-[A-Za-z0-9_.-]+`", "`sbta`", s2)
        if s2 != s:
            f.write_text(s2)
            touched.append(str(f.relative_to(d)))
    if touched:
        changes.append("./sbt -> ./sbta in " + ", ".join(sorted(touched)))
    return changes


SBTA_AGENTS_BULLET = ("- MCP server `sbta` (this build's `./sbta --mcp`, configured in `.mcp.json` and "
    "`.kiro/settings/mcp.json`, approved in `.claude/settings.json`): use it for all sbt work: `compile`, `test` "
    "(`full` for all), `run`, `check` after editing Scala 3 sources, `glob-search` / `inspect` / `symbol-location` "
    "for symbols, `sbt-task` for any other command. Its tools are deferred in Claude Code: load them with "
    "ToolSearch (search `sbta`). If it's unavailable, say so and use `./sbta <command>`. Logs: "
    "`project/target/sbta/mcp.log`.")
# The factory-written AGENTS.md bullet about the sbt-mcp server (seeded by the factory setup).
FACTORY_MCP_BULLET = re.compile(r"^- (?:MCP server )?`sbt-mcp-[^`]+`[^\n]*?(?:listens on|stdio bridge)[^\n]*$", re.M)


def agents_md(d):
    """Replace the factory-written sbt-mcp bullet in AGENTS.md with the sbta one."""
    p = Path(d) / "AGENTS.md"
    if not p.exists():
        return []
    s = p.read_text()
    s2, n = FACTORY_MCP_BULLET.subn(SBTA_AGENTS_BULLET.replace("\\", "\\\\"), s, count=1)
    if n:
        s2 = FACTORY_MCP_BULLET.sub("", s2)  # any second copy
        p.write_text(s2)
        return ["AGENTS.md: the MCP bullet describes sbta instead of sbt-mcp"]
    return []


def agents_leftovers(d):
    """AGENTS.md lines that still describe sbt-mcp (for the report; the routine's Align step rewrites them)."""
    p = Path(d) / "AGENTS.md"
    if not p.exists():
        return []
    return [l for l in p.read_text().splitlines() if re.search(r"sbt-mcp|mcpPort|sbt-mcp-stdio", l)]

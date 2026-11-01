#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""One round of a release, from a clean main whose CHANGELOG.md and READMEs already say the version:
  tools/release.py check X.Y.Z     the identity free on the hub, every test, the release package
  tools/release.py install X.Y.Z   that package onto the connected FM-1 (it asks first), then listen
  tools/release.py listen X.Y.Z    the FM-1 plays presets over MIDI, its USB audio held against the host build
      ... play it yourself, leave it and come back (the hub's checklist): the hub's page takes it back to V15
  tools/release.py publish X.Y.Z   the tag (it asks first; a tag publishes to players), verify, the notes
  tools/release.py verify X.Y.Z    the release's package against the one played, and its signature; changes nothing
  tools/release.py hub X.Y.Z       what the hub lists
check --quick leaves out tests/run.sh and fm1/run.py (a few minutes each). publish --dry-run prints what it would do.
GitHub builds and signs the release (.github/workflows/release.yml), so a release's .fwsc is never replaced by hand:
verify only compares it with the local build, which is bit for bit the same. V15 stays manual: fm1_install.py refuses
its package. publish wants a passed listen of this very package, built (check) from HEAD, on an FM-1 that runs it. Needs a python with numpy and Pillow, gh signed in,
uv for the FM-1."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "joakimeriksson/scintilla-fm1"
HUB = "https://thefirmwarehub.com/catalog.json"
HUB_ID = "scintilla"
SIGNER = "zvenson/fm1-build"                    # the shared workflow signs, so gh's default check fails
ORIGIN = f"https://github.com/{REPO}.git"
GIT = ["git", "-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential"]
FOOTER = """**Install:** [Install on my FM-1](https://joakimeriksson.github.io/scintilla-fm1/), the \
[FM-1 Firmware Hub](https://thefirmwarehub.com), or `firmware/tools/fm1_install.py scintilla-{v}.fwsc`. Hold **OCT-** \
while switching on for the USB rescue; the hub takes it back to the official firmware. It reports the identity \
`{ident}`. Built and signed on GitHub from this tag.

Free and open source (GPL-3.0-only). Not affiliated with or endorsed by Elka, Generalmusic, Behringer / Music Tribe \
or M-VAVE."""


def die(why):
    raise SystemExit(f"release: {why}")


def rosetta():
    """a Rosetta python (x86-64 conda) cannot start Apple's shims (git, cc): fm1/run.py's trap too"""
    r = subprocess.run(["/usr/sbin/sysctl", "-n", "sysctl.proc_translated"], capture_output=True, text=True)
    return r.stdout.strip() == "1"


ARCH = ["arch", "-arm64"] if sys.platform == "darwin" and rosetta() else []


def run(cmd, cwd=ROOT, capture=False):
    if not capture:
        print("$", " ".join(str(c) for c in cmd), flush=True)
    r = subprocess.run(ARCH + [str(c) for c in cmd], cwd=cwd, text=True, capture_output=capture)
    if r.returncode:
        die(f"{cmd[0]} failed ({r.returncode}): {(r.stderr or '')[-400:]}")
    return r.stdout.strip() if capture else ""


def out(*cmd, cwd=ROOT):
    return run(cmd, cwd, capture=True)


def identity(v):
    """tools/build.py's: FM-1_963XYYZZ"""
    m = re.fullmatch(r"(\d)\.(\d{1,2})\.(\d{1,2})", v)
    if not m:
        die(f"{v}: use X.Y.Z (X one digit, Y and Z up to two)")
    return f"FM-1_963{m[1]}{int(m[2]):02d}{int(m[3]):02d}"


def package(v):
    return ROOT / "firmware" / "build" / f"scintilla-{v}.fwsc"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def catalog():
    req = urllib.request.Request(HUB, headers={"User-Agent": "scintilla-release"})   # (python's own gets a 403)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def identity_taken(ident, c):
    """the hub's own check (its submit page): the same number, or inside another firmware's pattern; ours may be"""
    return [f["id"] for f in c["firmwares"] if f["id"] != HUB_ID and
            (f.get("product") == ident or f.get("ident") and f["ident"] != r"FM-1_\d{3,8}" and
             re.fullmatch(f["ident"], ident))]


def changes(v):
    """CHANGELOG.md's section for v"""
    m = re.search(rf"^## {re.escape(v)}\b.*?\n(.*?)(?=^## |\Z)", (ROOT / "CHANGELOG.md").read_text(), re.M | re.S)
    return m[1].strip() if m else ""


def tagged(v):
    return bool(out(*GIT, "ls-remote", "--tags", ORIGIN, f"refs/tags/v{v}"))


def clean_main():
    if out("git", "status", "--porcelain"):
        die("the tree is not clean: a release is built from a commit")
    run(GIT + ["fetch", "-q", ORIGIN, "main:refs/remotes/origin/main"])
    if out("git", "rev-parse", "HEAD") != out("git", "rev-parse", "origin/main"):
        die("not at origin/main: merge first, the tag goes on main")


def preflight(v):
    ident = identity(v)
    clean_main()
    if tagged(v):
        die(f"v{v} is already tagged")
    if not changes(v):
        die(f"CHANGELOG.md has no section '## {v}'")
    for f in ("README.md", "firmware/README.md"):
        if f"Status: {v}," not in (ROOT / f).read_text():
            die(f"{f}: its status line does not say {v}")
    taken = identity_taken(ident, catalog())
    if taken:
        die(f"{ident} is taken on the hub: {taken}")
    print(f"ok   {v}: not tagged, in the changelog and the READMEs; {ident} free on the hub")


def check(a):
    preflight(a.version)
    for mod in ("numpy", "PIL"):
        try:
            __import__(mod)
        except ImportError:
            die(f"this python has no {mod}: {sys.executable}")
    py = Path(sys.executable).parent
    env = f"PATH={py}:$PATH"
    if not a.quick:
        run(["sh", "-c", f"{env} sh tests/run.sh"])
        run(["sh", "-c", f"{env} python3 fm1/run.py"])
    fw = ROOT / "firmware"
    run(["sh", "-c", f"{env} PYTHON={sys.executable} ./build.sh --release {a.version}"], fw)
    run(["sh", "-c", f"{env} sh tests/run_host.sh"], fw)
    shutil.copy(package(a.version), fw / "build" / "scintilla.fwsc")   # (what tests/emu_test.py boots: this package)
    run(["sh", "-c", f"{env} python3 tests/emu_test.py"], fw)
    built(a.version).write_text(f"{head()}\n{sha(package(a.version))}\n")
    print(f"ok   {package(a.version)}\n     sha256 {sha(package(a.version))}\n"
          f"next: tools/release.py install {a.version}")


def ask(q, yes):
    if yes:
        return
    if input(f"{q} [y/N] ").strip().lower() != "y":
        die("stopped")


def install_tool(*args):
    return ["uv", "run", "-q", "--with", "mido", "--with", "python-rtmidi", "python",
            "firmware/tools/fm1_install.py", *args]


def stamp(v):
    return ROOT / "firmware" / "build" / f"listened-{v}.txt"


def built(v):
    """check's record: the commit the package was built from, and its sha"""
    return ROOT / "firmware" / "build" / f"built-{v}.txt"


def head():
    return out("git", "rev-parse", "HEAD")


def built_from(v):
    """the commit check built this package from, if the package is still that build"""
    pkg = package(v)
    if not built(v).exists() or not pkg.exists():
        return None
    commit, digest = (built(v).read_text().split() + ["", ""])[:2]
    return commit if digest == sha(pkg) else None


def running_identity():
    """fm1_install.py --info's line: the identity, and whether the firmware runs (not the update loader)"""
    line = out(*install_tool("--info")).splitlines()[-1]
    return line.split()[0], "[running]" in line


def listen(a):
    """fm1_listen.py on the connected FM-1, which must be running this version"""
    pkg = package(a.version)
    if not pkg.exists():
        die(f"no {pkg}: tools/release.py check {a.version}")
    ident, running = running_identity()
    if ident != identity(a.version) or not running:
        die(f"the FM-1 runs {ident}{'' if running else ' (in update mode)'}, not {identity(a.version)}: "
            f"tools/release.py install {a.version}")
    deps = ["--with", "sounddevice", "--with", "numpy", "--with", "mido", "--with", "python-rtmidi"]
    run(["uv", "run", "-q", "--no-project"] + deps + ["python", "-I", "tools/fm1_listen.py"])
    stamp(a.version).write_text(sha(pkg) + "\n")
    print(f"ok   heard: the FM-1 plays what the host build plays\nnext: tools/release.py publish {a.version}")


def install(a):
    pkg = package(a.version)
    if not pkg.exists():
        die(f"no {pkg}: tools/release.py check {a.version}")
    print(out(*install_tool("--info")).splitlines()[-1])
    ask(f"Install {pkg.name} ({sha(pkg)[:12]}) on this FM-1?", a.yes)
    run(install_tool(pkg, "--yes"))
    listen(a)
    print("""The hub's checklist, still yours on the FM-1:
  play it (what this release changed; fm1_listen.py cannot hear what is musically wrong);
  leave it, and come back from V15 and from another firmware (the hub's page goes to V15).""")


def notes(v):
    """the changelog's section, its lines joined: a release's body keeps every line break"""
    body = re.sub(r"(?<=\S)\n(?!\n|- )\s*", " ", changes(v))
    return f"{body}\n\n{FOOTER.format(v=v, ident=identity(v))}\n"


def wait_for_build(v):
    tag = f"v{v}"
    for _ in range(90):
        r = json.loads(out("gh", "run", "list", "-R", REPO, "--workflow", "release.yml", "--branch", tag,
                           "--json", "status,conclusion,url") or "[]")
        if r and r[0]["status"] == "completed":
            if r[0]["conclusion"] != "success":
                die(f"the release's build: {r[0]['conclusion']}: {r[0]['url']}")
            return
        time.sleep(10)
    die("the release's build did not finish in 15 minutes")


def publish(a):
    v = a.version
    identity(v)
    clean_main()
    if tagged(v):
        die(f"v{v} is already tagged")
    pkg = package(v)
    if not pkg.exists():
        die(f"no {pkg}: tools/release.py check {v}")
    if not stamp(v).exists() or stamp(v).read_text().strip() != sha(pkg):
        die(f"this package has not been heard on an FM-1: tools/release.py install {v}")
    if built_from(v) != head():
        die(f"this package was not built from HEAD ({head()[:12]}): GitHub builds the tag from HEAD, so its package "
            f"would differ; tools/release.py check {v}, then install it again")
    head_ = out("git", "rev-parse", "--short", "HEAD")
    if a.dry_run:
        print(f"would tag {head_} v{v}, push it, wait for the build, then verify\nthe notes:\n\n{notes(v)}")
        return
    ask(f"Tag {head_} v{v}? This publishes it, and the hub lists it within three hours", a.yes)
    run(["git", "tag", "-a", f"v{v}", "-m", f"Scintilla {v}"])
    try:
        run(GIT + ["push", "-q", ORIGIN, f"v{v}"])
    except SystemExit:
        run(["git", "tag", "-d", f"v{v}"])      # (the push failed: nothing is published, a rerun can tag again)
        raise
    try:
        wait_for_build(v)
        verify(a)
    except SystemExit as e:
        raise SystemExit(f"{e}\nv{v} is tagged and its release is public: look at the release's build, then either fix "
                         f"and release the next version, or delete the release and the tag (gh release delete v{v} "
                         f"-R {REPO} --cleanup-tag)") from None
    with tempfile.NamedTemporaryFile("w", suffix=".md") as f:
        f.write(notes(v))
        f.flush()
        run(["gh", "release", "edit", f"v{v}", "-R", REPO, "--title", f"Scintilla {v}", "--notes-file", f.name])
    print(f"ok   https://github.com/{REPO}/releases/tag/v{v}\nnext, in a few hours: tools/release.py hub {v}")


def verify(a):
    """fails if the release is not the package built here (and played)"""
    v = a.version
    pkg = package(v)
    if not pkg.exists():
        die(f"no {pkg}")
    with tempfile.TemporaryDirectory() as td:
        run(["gh", "release", "download", f"v{v}", "-R", REPO, "-p", pkg.name, "-D", td])
        got = Path(td) / pkg.name
        if sha(got) != sha(pkg):
            die(f"the release's {pkg.name} is not the one built here: {sha(got)} / {sha(pkg)}")
        print(f"ok   the release's package is the one built here: {sha(pkg)}")
        out("gh", "attestation", "verify", got, "-R", REPO, "--signer-repo", SIGNER)
        print(f"ok   signed by {SIGNER}")


def hub(a):
    c = catalog()
    f = [e for e in c["firmwares"] if e["id"] == HUB_ID]
    print(f"the hub ({c['updated']}): {f[0]['version'] if f else 'not listed'}")
    if not f or f[0]["version"] != a.version:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="One round of a release: see the top of this file")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("check", check), ("install", install), ("listen", listen), ("publish", publish), ("verify", verify),
                     ("hub", hub)):
        p = sub.add_parser(name)
        p.add_argument("version", metavar="X.Y.Z")
        p.set_defaults(fn=fn)
        if name == "check":
            p.add_argument("--quick", action="store_true", help="without tests/run.sh and fm1/run.py")
        if name in ("install", "publish"):
            p.add_argument("--yes", action="store_true", help="do not ask")
        if name == "publish":
            p.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

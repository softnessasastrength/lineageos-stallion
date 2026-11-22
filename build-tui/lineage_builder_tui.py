#!/usr/bin/env python3
"""LineageOS build TUI for stallion (Google Pixel 10a).

Built for Branden Algozino by Ember, 2026-11-16.

A curses front-end over the standard LineageOS build flow, with a live
telemetry header in the spirit of btop: per-core CPU bars, memory/swap,
disk, load, plus build-phase awareness (ninja progress, elapsed time,
ccache hit rate) while a job runs.

Design rules:
- stdlib only. No pip installs. Telemetry is read straight from /proc.
- Long jobs (sync, build) stream into the output pane and a log file.
  Interactive steps (sudo apt, git identity) drop out of curses to the
  real terminal and come back.
- The plain-text fallback (--plain, or no curses) keeps every function.

Run inside Ubuntu (WSL on the Windows PC is fine):
    ./run-tui.sh
"""

import codecs
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections import deque

# ---------------------------------------------------------------- config

DEVICE = "stallion"                       # Google Pixel 10a
BRANCH = "lineage-24.0"                   # LineageOS 24.0 / Android 17
MANIFEST_URL = "https://github.com/LineageOS/android.git"
GITHUB_USER = "softnessasastrength"
BUILD_DIR = os.path.expanduser("~/android/lineage")
LOG_DIR = os.path.join(BUILD_DIR, "build-logs")
CCACHE_SIZE = "50G"

# The stallion fork set (forked from LineageOS on 2026-11-16):
# device tree, its shared platform tree, and its prebuilt-kernels repo.
FORK_PROJECTS = [
    ("LineageOS/android_device_google_stallion",
     "softnessasastrength/android_device_google_stallion",
     "device/google/stallion"),
    ("LineageOS/android_device_google_zumapro",
     "softnessasastrength/android_device_google_zumapro",
     "device/google/zumapro"),
    ("LineageOS/android_device_google_stallion-kernels",
     "softnessasastrength/android_device_google_stallion-kernels",
     "device/google/stallion-kernels"),
]

# LineageOS wiki build-package list for current Ubuntu LTS.
APT_PACKAGES = [
    "bc", "bison", "build-essential", "ccache", "curl", "flex",
    "g++-multilib", "gcc-multilib", "git", "git-lfs", "gnupg", "gperf",
    "imagemagick", "lib32ncurses-dev", "lib32readline-dev", "lib32z1-dev",
    "libelf-dev", "lz4", "libncurses-dev", "libncurses6",
    "libsdl1.2-dev", "libssl-dev", "libxml2-utils", "lzop",
    "pngcrush", "rsync", "schedtool", "squashfs-tools", "xsltproc",
    "zip", "zlib1g-dev", "python3", "python-is-python3",
    "openjdk-21-jdk-headless", "adb", "fastboot",
]

# ---------------------------------------------------------------- telemetry

def _read_net_totals():
    """Total (rx, tx) bytes across all non-loopback interfaces."""
    rx = tx = 0
    try:
        with open("/proc/net/dev") as fh:
            for line in fh:
                iface, _, rest = line.partition(":")
                if iface.strip() == "lo" or not rest.strip():
                    continue
                fields = rest.split()
                rx += int(fields[0])
                tx += int(fields[8])
    except Exception:
        pass
    return rx, tx


def _read_cpu_times():
    cores = []
    with open("/proc/stat") as fh:
        for line in fh:
            if line.startswith("cpu") and line[3:4].isdigit():
                parts = [int(x) for x in line.split()[1:]]
                idle = parts[3] + parts[4]
                cores.append((sum(parts), idle))
    return cores


class Telemetry:
    """btop-flavoured system telemetry, sampled from /proc once a second."""

    def __init__(self):
        self._prev = _read_cpu_times()
        self.cpu_pct = [0.0] * len(self._prev)
        self.mem = (0, 0)          # used, total (bytes)
        self.swap = (0, 0)
        self.load = (0.0, 0.0, 0.0)
        self.disk = (0, 0)         # free, total (bytes) on BUILD_DIR fs
        self.ccache = ""           # "hits 1234/5678 (21.7%)"
        self._ccache_at = 0.0
        self.net = (0.0, 0.0)      # rx, tx (bytes/sec, all non-loopback)
        self._prev_net = None
        self._prev_net_at = 0.0

    def sample(self):
        now = _read_cpu_times()
        pct = []
        for (t1, i1), (t0, i0) in zip(now, self._prev):
            dt, di = t1 - t0, i1 - i0
            pct.append(0.0 if dt <= 0 else max(0.0, min(100.0, 100.0 * (1 - di / dt))))
        self._prev, self.cpu_pct = now, pct

        info = {}
        with open("/proc/meminfo") as fh:
            for line in fh:
                k, _, v = line.partition(":")
                info[k.strip()] = int(v.split()[0]) * 1024
        self.mem = (info.get("MemTotal", 0) - info.get("MemAvailable", 0),
                    info.get("MemTotal", 0))
        self.swap = (info.get("SwapTotal", 0) - info.get("SwapFree", 0),
                     info.get("SwapTotal", 0))
        with open("/proc/loadavg") as fh:
            p = fh.read().split()
            self.load = (float(p[0]), float(p[1]), float(p[2]))
        probe = BUILD_DIR if os.path.exists(BUILD_DIR) else os.path.expanduser("~")
        du = shutil.disk_usage(probe)
        self.disk = (du.free, du.total)

        now_t = time.time()
        totals = _read_net_totals()
        if self._prev_net is not None:
            dt = now_t - self._prev_net_at
            if dt > 0:
                self.net = (max(0.0, (totals[0] - self._prev_net[0]) / dt),
                            max(0.0, (totals[1] - self._prev_net[1]) / dt))
        self._prev_net, self._prev_net_at = totals, now_t

        if time.time() - self._ccache_at > 10:
            self._ccache_at = time.time()
            try:
                out = subprocess.run(["ccache", "-s"], capture_output=True,
                                     text=True, timeout=5).stdout
                m = re.search(r"[Hh]its:\s*(\d+)\s*/\s*(\d+)\s*\(([\d.]+)\s*%\)", out)
                if m:
                    self.ccache = f"ccache hits {m.group(1)}/{m.group(2)} ({m.group(3)}%)"
            except Exception:
                pass


def bar(pct, width):
    filled = int(round(pct / 100.0 * width))
    return "#" * filled + "-" * (width - filled)


def gib(n):
    return n / (1024 ** 3)


def fmt_rate(bps):
    if bps < 1024:
        return f"{bps:.0f} B/s"
    if bps < 1024 ** 2:
        return f"{bps / 1024:.1f} KB/s"
    if bps < 1024 ** 3:
        return f"{bps / 1024 ** 2:.1f} MB/s"
    return f"{bps / 1024 ** 3:.2f} GB/s"

# ---------------------------------------------------------------- job runner

NINJA_RE = re.compile(r"\[\s*(\d+)\s*/\s*(\d+)\s*\]")
SYNC_RE = re.compile(r"Syncing:\s*([\d.]+)%")
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][0-9A-B]|\x1b[=>]")
CTRL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def clean_line(text):
    """Make one raw output segment safe to draw in curses and to log."""
    return CTRL_RE.sub("", ANSI_RE.sub("", text)).rstrip()


class Job:
    """One long-running shell job, streamed line by line."""

    def __init__(self, title, argv, cwd=None, env_extra=None):
        self.title = title
        self.argv = argv
        self.cwd = cwd
        self.env_extra = env_extra or {}
        self.lines = deque(maxlen=4000)
        self.proc = None
        self.started = None
        self.ended = None
        self.returncode = None
        self.progress = ""        # human progress note (ninja/sync)
        self.log_path = None
        self._thread = None

    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    @property
    def elapsed(self):
        if self.started is None:
            return 0.0
        return (self.ended or time.time()) - self.started

    def start(self):
        os.makedirs(LOG_DIR, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        safe = re.sub(r"[^A-Za-z0-9]+", "-", self.title).strip("-").lower()
        self.log_path = os.path.join(LOG_DIR, f"{stamp}-{safe}.log")
        env = dict(os.environ)
        env.update(self.env_extra)
        env.setdefault("USE_CCACHE", "1")
        env.setdefault("CCACHE_EXEC", shutil.which("ccache") or "/usr/bin/ccache")
        self.started = time.time()
        self.proc = subprocess.Popen(
            self.argv, cwd=self.cwd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            bufsize=0, start_new_session=True)
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _emit(self, log, segment):
        line = clean_line(segment)
        if not line:
            return
        self.lines.append(line)
        log.write(line + "\n")
        log.flush()
        m = NINJA_RE.search(line)
        if m:
            done, total = int(m.group(1)), int(m.group(2))
            pct = 100.0 * done / total if total else 0.0
            self.progress = f"ninja {done}/{total} ({pct:.1f}%)"
        else:
            s = SYNC_RE.search(line)
            if s:
                self.progress = f"sync {s.group(1)}%"

    def _pump(self):
        # Read the raw byte stream in chunks and split on BOTH \r and \n.
        # repo/git/ninja write their live progress with carriage returns
        # and no newline for long stretches; a line-based reader sits
        # silent through all of it, which made the pane look frozen.
        log = open(self.log_path, "a", encoding="utf-8", errors="replace")
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        pending = ""
        try:
            while True:
                chunk = self.proc.stdout.read(4096)
                if not chunk:
                    break
                pending += decoder.decode(chunk)
                parts = re.split(r"[\r\n]+", pending)
                pending = parts.pop()
                for segment in parts:
                    self._emit(log, segment)
            pending += decoder.decode(b"", final=True)
            if pending:
                self._emit(log, pending)
        finally:
            log.close()
            self.proc.wait()
            self.returncode = self.proc.returncode
            self.ended = time.time()

    def stop(self):
        if self.running:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGINT)
            except Exception:
                pass

# ---------------------------------------------------------------- steps

def job_env():
    home_bin = os.path.expanduser("~/bin")
    return {"PATH": home_bin + os.pathsep + os.environ.get("PATH", "")}


def step_env_check():
    """Returns a list of report lines about this machine."""
    lines = []
    cores = os.cpu_count() or 0
    tel = Telemetry()
    tel.sample()
    lines.append(f"Device target : {DEVICE} (Google Pixel 10a) - branch {BRANCH}")
    lines.append(f"Build dir     : {BUILD_DIR}")
    lines.append(f"CPU cores     : {cores}")
    lines.append(f"RAM total     : {gib(tel.mem[1]):.1f} GiB"
                 + ("   <-- under 16 GiB: expect a slow, swap-heavy build"
                    if tel.mem[1] < 15 * 1024 ** 3 else ""))
    lines.append(f"Disk free     : {gib(tel.disk[0]):.0f} GiB of {gib(tel.disk[1]):.0f} GiB"
                 + ("   <-- a full tree + build wants ~350 GiB free"
                    if tel.disk[0] < 320 * 1024 ** 3 else ""))
    for tool in ("git", "repo", "ccache", "java", "adb", "python3"):
        path = shutil.which(tool) or (os.path.expanduser("~/bin/repo")
                                      if tool == "repo" and os.path.exists(
                                          os.path.expanduser("~/bin/repo")) else None)
        lines.append(f"  {tool:8s}: {path or 'MISSING - run step 2 (Install dependencies)'}")
    git_name = subprocess.run(["git", "config", "--global", "user.name"],
                              capture_output=True, text=True).stdout.strip()
    git_mail = subprocess.run(["git", "config", "--global", "user.email"],
                              capture_output=True, text=True).stdout.strip()
    lines.append(f"git identity  : {git_name or '(unset)'} <{git_mail or 'unset'}>"
                 + ("" if git_name and git_mail else "   <-- repo init will ask; step 2 sets it"))
    lines.append(f"Source tree   : {'present' if os.path.isdir(os.path.join(BUILD_DIR, '.repo')) else 'not initialised yet - run step 3, then 4'}")
    return lines


def forks_manifest_xml():
    rows = ['<?xml version="1.0" encoding="UTF-8"?>', "<manifest>"]
    for upstream, fork, path in FORK_PROJECTS:
        rows.append(f'  <remove-project name="{upstream}" />')
        rows.append(f'  <project path="{path}" name="{fork}" '
                    f'remote="github" revision="{BRANCH}" />')
    rows.append("</manifest>")
    return "\n".join(rows) + "\n"


def forks_overlay_path():
    return os.path.join(BUILD_DIR, ".repo", "local_manifests", "stallion_forks.xml")


def forks_overlay_on():
    return os.path.exists(forks_overlay_path())

# ---------------------------------------------------------------- curses UI

MENU = [
    ("1", "Environment check", "report"),
    ("2", "Install dependencies (apt + repo tool + git identity)", "terminal"),
    ("3", "Initialise source tree (repo init)", "job"),
    ("4", "Sync source (repo sync - the big download)", "job"),
    ("5", "Toggle forks overlay (build from YOUR forks)", "action"),
    ("6", "Extract proprietary blobs from phone via adb (optional)", "terminal"),
    ("7", "BUILD stallion (breakfast + brunch)", "job"),
    ("8", "Show build outputs (zips in $OUT)", "report"),
    ("q", "Quit", "quit"),
]


def fmt_elapsed(sec):
    sec = int(sec)
    return f"{sec // 3600}:{(sec % 3600) // 60:02d}:{sec % 60:02d}"


def draw_header(win, tel, job):
    h, w = win.getmaxyx()
    tel.sample()
    win.addstr(0, 0, f" LINEAGE BUILDER - {DEVICE} ({BRANCH}) ".ljust(w)[:w], )
    per = max(6, min(14, (w - 30) // max(1, len(tel.cpu_pct))))
    cells = " ".join(f"{bar(p, 5)} {p:3.0f}%" for p in tel.cpu_pct[:8])
    win.addstr(1, 0, f"CPU {cells}"[:w])
    if len(tel.cpu_pct) > 8:
        cells2 = " ".join(f"{bar(p, 5)} {p:3.0f}%" for p in tel.cpu_pct[8:16])
        win.addstr(2, 0, f"    {cells2}"[:w])
        row = 3
    else:
        row = 2
    win.addstr(row, 0,
               f"MEM {bar(100 * tel.mem[0] / max(1, tel.mem[1]), 18)} "
               f"{gib(tel.mem[0]):.1f}/{gib(tel.mem[1]):.1f} GiB   "
               f"SWAP {gib(tel.swap[0]):.1f}/{gib(tel.swap[1]):.1f} GiB   "
               f"LOAD {tel.load[0]:.2f} {tel.load[1]:.2f} {tel.load[2]:.2f}"[:w])
    win.addstr(row + 1, 0,
               f"DISK free {gib(tel.disk[0]):.0f} GiB   "
               f"NET dn {fmt_rate(tel.net[0])}  up {fmt_rate(tel.net[1])}   "
               f"{tel.ccache or 'ccache: n/a'}"[:w])
    status = "idle"
    if job is not None and job.started is not None:
        state = "RUNNING" if job.running else f"done rc={job.returncode}"
        status = (f"{job.title}: {state}  elapsed {fmt_elapsed(job.elapsed)}"
                  + (f"  {job.progress}" if job.progress else "")
                  + (f"  log: {job.log_path}" if job.log_path else ""))
    win.addstr(row + 2, 0, f"JOB {status}"[:w])
    win.addstr(row + 3, 0, "-" * (w - 1))
    return row + 4


def run_job_screen(stdscr, job):
    tel = Telemetry()
    stdscr.nodelay(True)
    offset = 0
    job.start()
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        top = draw_header(stdscr, tel, job)
        lines = list(job.lines)
        view = max(1, h - top - 2)
        start = max(0, len(lines) - view - offset)
        for i, line in enumerate(lines[start:start + view]):
            try:
                stdscr.addstr(top + i, 0, line[:w - 1])
            except Exception:
                pass
        hint = ("Ctrl-C: stop job    PgUp/PgDn: scroll    "
                + ("job running..." if job.running else "job finished - any key: back"))
        try:
            stdscr.addstr(h - 1, 0, hint[:w - 1])
        except Exception:
            pass
        stdscr.refresh()
        try:
            key = stdscr.getch()
        except Exception:
            key = -1
        if key == 3:  # Ctrl-C
            job.stop()
        elif key == 339:  # PgUp
            offset = min(offset + 10, max(0, len(lines) - view))
        elif key == 338:  # PgDn
            offset = max(0, offset - 10)
        elif key != -1 and not job.running:
            return
        time.sleep(0.25)


def show_report(stdscr, title, lines):
    stdscr.nodelay(False)
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    stdscr.addstr(0, 0, f" {title} "[:w])
    stdscr.addstr(1, 0, "-" * (w - 1))
    for i, line in enumerate(lines[:h - 4]):
        stdscr.addstr(2 + i, 0, str(line)[:w - 1])
    stdscr.addstr(h - 1, 0, "any key: back")
    stdscr.refresh()
    stdscr.getch()


def run_terminal(stdscr, argv, note):
    """Drop out of curses and run an interactive command on the real tty."""
    import curses
    curses.def_prog_mode()
    curses.endwin()
    print(f"\n--- {note} ---")
    print("$ " + " ".join(argv))
    try:
        subprocess.run(argv)
    except Exception as exc:
        print(f"(failed to launch: {exc})")
    input("\nPress Enter to return to the TUI... ")
    curses.reset_prog_mode()
    stdscr.refresh()


def make_job(key):
    jobs = os.cpu_count() or 4
    if key == "3":
        os.makedirs(BUILD_DIR, exist_ok=True)
        return Job("repo init",
                   ["repo", "init", "-u", MANIFEST_URL, "-b", BRANCH, "--git-lfs"],
                   cwd=BUILD_DIR, env_extra=job_env())
    if key == "4":
        return Job("repo sync",
                   ["repo", "sync", "-c", f"-j{jobs}", "--force-sync", "--no-tags"],
                   cwd=BUILD_DIR, env_extra=job_env())
    if key == "7":
        script = ("source build/envsetup.sh && breakfast " + DEVICE +
                  " && brunch " + DEVICE)
        return Job("build " + DEVICE, ["bash", "-c", script],
                   cwd=BUILD_DIR, env_extra=job_env())
    return None


def toggle_forks(stdscr):
    path = forks_overlay_path()
    if forks_overlay_on():
        os.remove(path)
        msg = "Forks overlay OFF - the three device projects track LineageOS upstream."
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(forks_manifest_xml())
        msg = ("Forks overlay ON - device/google/stallion, zumapro and stallion-kernels "
               "now resolve to github.com/" + GITHUB_USER + "/*. Run Sync (4) to apply.")
    show_report(stdscr, "Forks overlay", [msg, "", f"File: {path}"])


def outputs_report():
    out = os.path.join(BUILD_DIR, "out", "target", "product", DEVICE)
    if not os.path.isdir(out):
        return [f"No output directory yet: {out}", "Run a build (7) first."]
    zips = sorted((os.path.join(out, f) for f in os.listdir(out)
                   if f.endswith(".zip")), key=os.path.getmtime)
    if not zips:
        return [f"No zips in {out} yet."]
    lines = [f"Output dir: {out}", ""]
    for z in zips[-10:]:
        lines.append(f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(z)))}"
                     f"  {gib(os.path.getsize(z)):.2f} GiB  {os.path.basename(z)}")
    return lines


def curses_main(stdscr):
    import curses
    curses.curs_set(0)
    stdscr.timeout(1000)   # wake once a second so telemetry stays live
    tel = Telemetry()
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        top = draw_header(stdscr, tel, None)
        stdscr.addstr(top, 0, "Send this computer to suffering, in a few clicks:")
        for i, (key, label, _kind) in enumerate(MENU):
            mark = ""
            if key == "5" and forks_overlay_on():
                mark = "   [currently: YOUR FORKS]"
            elif key == "5":
                mark = "   [currently: upstream]"
            stdscr.addstr(top + 2 + i, 2, f"[{key}] {label}{mark}"[:w - 1])
        stdscr.addstr(h - 1, 0, "Pick a number. Telemetry up top is live (/proc, 1s).")
        stdscr.refresh()
        stdscr.timeout(1000)
        ch = stdscr.getch()
        try:
            key = chr(ch)
        except Exception:
            continue
        entry = next((m for m in MENU if m[0] == key), None)
        if entry is None:
            continue
        kind = entry[2]
        if kind == "quit":
            return
        if key == "1":
            show_report(stdscr, "Environment check", step_env_check())
        elif key == "8":
            show_report(stdscr, "Build outputs", outputs_report())
        elif key == "5":
            toggle_forks(stdscr)
        elif key == "2":
            run_terminal(stdscr,
                         ["bash", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                               "install_deps.sh")],
                         "Installing build dependencies (sudo will ask for your password)")
        elif key == "6":
            run_terminal(stdscr,
                         ["bash", "-c",
                          f"cd {BUILD_DIR} && source build/envsetup.sh && "
                          f"breakfast {DEVICE} && cd device/google/stallion && "
                          "./extract-files.py"],
                         "Extract blobs: phone on STOCK firmware, USB debugging on, "
                         "plugged in, unlocked. Optional - only needed if the build "
                         "complains about missing vendor files.")
        elif kind == "job":
            job = make_job(key)
            if job is not None:
                run_job_screen(stdscr, job)

# ---------------------------------------------------------------- plain fallback

def plain_main():
    print(f"LineageOS builder TUI (plain mode) - {DEVICE} / {BRANCH}")
    while True:
        tel = Telemetry()
        tel.sample()
        print("\n--- menu ---")
        for key, label, _ in MENU:
            print(f" [{key}] {label}")
        print(f" telemetry: load {tel.load[0]:.2f}  mem {gib(tel.mem[0]):.1f}/"
              f"{gib(tel.mem[1]):.1f} GiB  disk free {gib(tel.disk[0]):.0f} GiB")
        choice = input("> ").strip()
        if choice == "q":
            return
        if choice == "1":
            print("\n".join(step_env_check()))
        elif choice == "8":
            print("\n".join(outputs_report()))
        elif choice == "5":
            path = forks_overlay_path()
            if forks_overlay_on():
                os.remove(path)
                print("Forks overlay OFF")
            else:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "w").write(forks_manifest_xml())
                print("Forks overlay ON - run sync to apply")
        elif choice == "2":
            subprocess.run(["bash", os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "install_deps.sh")])
        elif choice in ("3", "4", "7"):
            job = make_job(choice)
            job.start()
            try:
                while job.running:
                    time.sleep(2)
                    print(f"  [{job.title}] elapsed {fmt_elapsed(job.elapsed)} "
                          f"{job.progress}")
            except KeyboardInterrupt:
                job.stop()
            print(f"done rc={job.returncode}  log: {job.log_path}")
        else:
            print("unknown choice")


if __name__ == "__main__":
    if "--plain" in sys.argv:
        plain_main()
    else:
        try:
            import curses
            curses.wrapper(curses_main)
        except Exception as exc:
            print(f"(curses unavailable: {exc} - falling back to plain mode)")
            plain_main()

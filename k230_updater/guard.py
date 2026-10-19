"""Watchdog-backed launcher with automatic rollback and fix-forward updates.

Boot flow
---------
1. Start the hardware WDT (fed during downloads too).
2. If the previous run was never confirmed healthy ("trial"), count a failure.
   After `max_fails` failures that version is blacklisted and the previous
   version is restored.
3. Check the remote repo; install a newer version unless it is blacklisted.
   A corrected release therefore replaces a bad one automatically.
4. Run the app. The app must call `guard.feed()` regularly (Thermal.pace()
   does it for you). If it hangs, the WDT resets the board. After
   `confirm_after` seconds of continuous feeding the version is marked good.
"""
import os
import sys
import time

from machine import WDT
import machine

from . import util
from .updater import Updater


class Guard:
    def __init__(self, repo, token, root="/sdcard/app", branch="main",
                 wdt_timeout=10, wdt_id=1, max_fails=3, confirm_after=60,
                 retry_interval=60, connect=None, update_url=None):
        """connect: optional callable that brings the network up (may raise).
        update_url: use the HTTP/zip update source instead of GitHub (see Updater)."""
        self.root = root
        self.max_fails = max_fails
        self.confirm_after = confirm_after
        self.retry_interval = retry_interval
        self.connect = connect
        self.wdt_timeout = wdt_timeout
        self.wdt_id = wdt_id
        self._wdt = None
        self._trial_start = None
        self.state_path = root + "/state.json"
        util.makedirs(root)
        self.updater = Updater(repo, token, root, branch, feed=self.feed,
                               url=update_url)
        self.state = util.read_json(self.state_path, {}) or {}
        self.state.setdefault("status", "ok")
        self.state.setdefault("fails", 0)
        self.state.setdefault("bad", [])

    # ---- watchdog -------------------------------------------------------
    def start_wdt(self):
        if self._wdt is None:
            self._wdt = WDT(id=self.wdt_id, timeout=self.wdt_timeout)

    def stop_wdt(self):
        if self._wdt is not None:
            self._wdt.stop()
            self._wdt = None

    def feed(self):
        """Feed the watchdog; confirms the running version once stable."""
        if self._wdt is not None:
            self._wdt.feed()
        if (self._trial_start is not None and
                time.ticks_diff(time.ticks_ms(), self._trial_start)
                >= self.confirm_after * 1000):
            self.confirm()

    # ---- state ----------------------------------------------------------
    def _save(self):
        util.write_json(self.state_path, self.state)

    def _current_version(self):
        m = self.updater.local_manifest()
        return str(m["version"]) if m else None

    def confirm(self):
        self._trial_start = None
        self.state["status"] = "ok"
        self.state["fails"] = 0
        self._save()

    def _register_failure(self):
        self.state["fails"] += 1
        if self.state["fails"] >= self.max_fails:
            bad = self._current_version()
            if bad and bad not in self.state["bad"]:
                self.state["bad"].append(bad)
            self.updater.rollback()
            self.state["fails"] = 0
        self.state["status"] = "ok"
        self._save()

    # ---- update ---------------------------------------------------------
    def try_update(self):
        """Returns installed version or None. Never raises."""
        try:
            if self.connect:
                self.connect()
            version = self.updater.check_and_install(self.state["bad"])
        except Exception as e:
            print("update skipped:", e)
            return None
        if version:
            self.state["status"] = "ok"
            self.state["fails"] = 0
            self._save()
        return version

    def update_and_reset(self):
        """For use from the running app: install a new release and reboot."""
        if self.try_update():
            self.reset()

    def reset(self):
        time.sleep_ms(200)
        machine.reset()

    # ---- main entry -----------------------------------------------------
    def boot(self):
        self.start_wdt()
        if self.state["status"] == "trial":
            self._register_failure()
        self.try_update()

        entry = self._entry()
        while entry is None:
            # Nothing runnable (no app yet, or only blacklisted versions):
            # stay alive and wait for a fixed release.
            t0 = time.ticks_ms()
            while time.ticks_diff(time.ticks_ms(), t0) < self.retry_interval * 1000:
                self.feed()
                time.sleep_ms(500)
            self.try_update()
            entry = self._entry()

        self.state["status"] = "trial"
        self._save()
        self._trial_start = time.ticks_ms()
        self._run(entry)

    def _entry(self):
        m = self.updater.local_manifest()
        if not m or str(m["version"]) in self.state["bad"]:
            return None
        path = self.updater.current + "/" + m.get("entry", "main.py")
        return path if util.exists(path) else None

    def _run(self, path):
        base = self.updater.current
        if base not in sys.path:
            sys.path.insert(0, base)
        os.chdir(base)
        try:
            with open(path) as f:
                code = f.read()
            exec(compile(code, path, "exec"), {"__name__": "__main__"})
        except (KeyboardInterrupt, SystemExit):
            # Developer stopped the app: leave the board usable.
            self.stop_wdt()
            self.state["status"] = "ok"
            self._save()
            raise
        except Exception as e:
            sys.print_exception(e)
            self.state["fails"] += 1
            self._save()
            self.reset()
        # App returned normally: restart it (it is expected to run forever).
        self.reset()

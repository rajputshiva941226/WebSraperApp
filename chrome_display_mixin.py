"""
chrome_display_mixin.py
═══════════════════════════════════════════════════════════════════════════════
Shared Chrome + virtual-display initialisation logic, extracted from
MDPIScraper and generalised for ALL Selenium-based scrapers in this project.

Usage — inherit alongside your scraper class:

    from chrome_display_mixin import ChromeDisplayMixin
    import undetected_chromedriver as uc

    class MyScraper(ChromeDisplayMixin):
        def __init__(self, ...):
            self._vdisplay  = None          # REQUIRED: mixin manages this
            self.driver     = None          # REQUIRED: mixin sets this
            self.output_dir = "/some/path"  # used for download prefs + debug logs
            self.logger     = logging.getLogger("MyScraper")   # use your own logger

            # 1. Build your ChromeOptions however you like
            opts = self._build_default_chrome_options(download_dir=self.output_dir)
            opts.add_argument("--your-extra-flag")

            # 2. Launch Chrome (handles display :0 → Xvfb :99 fallback automatically)
            self._launch_chrome(opts, driver_path=None)

            # 3. Done — self.driver is ready.

        def run(self):
            ...
            self._save_cookies("~/.my_scraper.json")   # optional
            ...

        def cleanup(self):
            self._quit_chrome()   # closes Chrome + stops Xvfb

══════════════════════════════════════════════════════════════════════════════
What this module replaces / unifies
────────────────────────────────────
Scraper        | Had display? | Had XAUTH? | Had :0→Xvfb? | Had cookies? | Had diag?
────────────────────────────────────────────────────────────────────────────────────
MDPI           |  YES (full)  |  YES       |  YES         |  YES         |  YES
Oxford         |  YES (good)  |  YES       |  YES         |  YES         |  NO
Sage           |  YES (basic) |  NO        |  NO (:99 only)|  NO         |  NO
Lippincott     |  NO          |  NO        |  NO          |  NO          |  NO
Emerald        |  NO          |  NO        |  NO          |  NO          |  NO
BMJ            |  (commented) |  NO        |  NO          |  NO          |  NO
════════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import time
from typing import Optional

import undetected_chromedriver as uc

# ---------------------------------------------------------------------------
# Module-level fallback logger — scrapers normally supply self.logger
# ---------------------------------------------------------------------------
_log = logging.getLogger(__name__)


class ChromeDisplayMixin:
    """
    Mixin that provides:

      _diagnose_environment()          → log full env snapshot before Chrome launch
      _build_default_chrome_options()  → sensible uc.ChromeOptions for EC2/Linux
      _launch_chrome()                 → display :0 → Xvfb :99 fallback strategy
      _quit_chrome()                   → clean Chrome + Xvfb teardown
      _save_chrome_log()               → dump dmesg / ps / env on Chrome failure
      _save_cookies()                  → persist driver cookies to JSON file
      _load_cookies()                  → restore cookies from JSON file

    The mixin expects the concrete class to have:
      self.logger     — a standard logging.Logger
      self.driver     — set to None before calling _launch_chrome()
      self._vdisplay  — set to None before calling _launch_chrome()
      self.output_dir — (optional) used for download prefs and debug logs
    """

    # =========================================================================
    # SECTION 1 — Environment diagnostics
    # =========================================================================

    def _diagnose_environment(self) -> None:
        """
        Log a full snapshot of the process environment *before* Chrome launch.

        Covers: OS, Python, UID/GID, DISPLAY, XAUTHORITY, xdpyinfo check,
        Chrome binary, chromedriver, /dev/shm, undetected_chromedriver version.

        Identical to MDPIScraper._diagnose_environment() but scraper-agnostic.
        Also auto-fixes XAUTHORITY env var when it is unset (probes common
        GNOME3 locations) so the XAUTHORITY fix is applied once here rather
        than separately in every scraper.
        """
        import shutil
        try:
            import pwd, grp
        except ImportError:
            pwd = grp = None  # Windows

        tag = getattr(self, '_diag_tag', '[ChromeMixin]')
        logger = getattr(self, 'logger', _log)

        diag: list[str] = [f"{tag}[DIAG] ══════ Environment Diagnostic ══════"]

        # ── OS / Python ──────────────────────────────────────────────────────
        diag.append(f"{tag}[DIAG] OS          : {platform.platform()}")
        diag.append(f"{tag}[DIAG] Python      : {platform.python_version()} "
                    f"@ {platform.python_implementation()}")

        # ── Process identity ─────────────────────────────────────────────────
        try:
            if pwd and grp and hasattr(os, 'getuid'):
                uid   = os.getuid()
                gid   = os.getgid()
                uname = pwd.getpwuid(uid).pw_name
                gname = grp.getgrgid(gid).gr_name
                diag.append(f"{tag}[DIAG] UID/GID     : {uid}/{gid} ({uname}/{gname})")
            diag.append(f"{tag}[DIAG] HOME        : {os.path.expanduser('~')}")
        except Exception as e:
            diag.append(f"{tag}[DIAG] UID/GID     : unknown ({e})")

        # ── X display ────────────────────────────────────────────────────────
        display = os.environ.get('DISPLAY', '<NOT SET>')
        xauth   = os.environ.get('XAUTHORITY', '<NOT SET>')
        dbus    = os.environ.get('DBUS_SESSION_BUS_ADDRESS', '<NOT SET>')
        diag.append(f"{tag}[DIAG] DISPLAY     : {display}")
        diag.append(f"{tag}[DIAG] XAUTHORITY  : {xauth}")
        diag.append(f"{tag}[DIAG] DBUS_SESSION: {dbus}")

        # Auto-probe XAUTHORITY if unset — same logic as MDPI
        if xauth == '<NOT SET>' or not os.path.exists(xauth):
            uid_str = str(os.getuid()) if hasattr(os, 'getuid') else '1000'
            candidates = [
                f"/run/user/{uid_str}/gdm/Xauthority",
                os.path.expanduser("~/.Xauthority"),
                "/home/ubuntu/.Xauthority",
                "/root/.Xauthority",
            ]
            found_xauth = next(
                (p for p in candidates if os.path.exists(p) and os.access(p, os.R_OK)),
                None
            )
            if found_xauth:
                diag.append(f"{tag}[DIAG] XAUTH probe : found → {found_xauth}")
                diag.append(f"{tag}[DIAG] XAUTH FIX   : setting XAUTHORITY={found_xauth}")
                os.environ['XAUTHORITY'] = found_xauth
            else:
                diag.append(f"{tag}[DIAG] XAUTH probe : NOT FOUND — Chrome may fail on :0")
        else:
            exists   = os.path.exists(xauth)
            readable = os.access(xauth, os.R_OK) if exists else False
            diag.append(f"{tag}[DIAG] XAUTH file  : exists={exists}  readable={readable}")

        # ── xdpyinfo — verify X server is reachable ──────────────────────────
        try:
            r = subprocess.run(
                ['xdpyinfo', '-display', display],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                first_line = (r.stdout.strip().splitlines() or ['connected'])[0]
                diag.append(f"{tag}[DIAG] xdpyinfo    : OK — {first_line}")
            else:
                diag.append(f"{tag}[DIAG] xdpyinfo    : FAILED (rc={r.returncode}) "
                             f"— {r.stderr.strip()[:120]}")
                diag.append(f"{tag}[DIAG] *** Chrome WILL FAIL on :0 — X server unreachable ***")
                diag.append(f"{tag}[DIAG] Fix: run  DISPLAY=:0 xhost +local:  on GNOME3 desktop")
        except FileNotFoundError:
            diag.append(f"{tag}[DIAG] xdpyinfo    : not installed (apt install x11-utils)")
        except Exception as e:
            diag.append(f"{tag}[DIAG] xdpyinfo    : error ({e})")

        # ── Chrome binary ─────────────────────────────────────────────────────
        chrome_candidates = [
            '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable',
            '/usr/bin/chromium-browser', '/usr/bin/chromium', '/snap/bin/chromium',
        ]
        chrome_found = next((p for p in chrome_candidates if os.path.isfile(p)), None)
        if not chrome_found:
            chrome_found = shutil.which('google-chrome') or shutil.which('chromium-browser')
        diag.append(f"{tag}[DIAG] Chrome bin  : {chrome_found or 'NOT FOUND'}")
        if chrome_found:
            try:
                rv = subprocess.run([chrome_found, '--version'],
                                    capture_output=True, text=True, timeout=10)
                diag.append(f"{tag}[DIAG] Chrome ver  : {rv.stdout.strip()}")
            except Exception as e:
                diag.append(f"{tag}[DIAG] Chrome ver  : error ({e})")

        # ── chromedriver ─────────────────────────────────────────────────────
        cd = shutil.which('chromedriver')
        diag.append(f"{tag}[DIAG] chromedriver: {cd or 'not in PATH'}")
        if cd:
            try:
                rv = subprocess.run([cd, '--version'],
                                    capture_output=True, text=True, timeout=10)
                diag.append(f"{tag}[DIAG] cdvr version: {rv.stdout.strip()}")
            except Exception as e:
                diag.append(f"{tag}[DIAG] cdvr version: error ({e})")

        # ── /dev/shm ─────────────────────────────────────────────────────────
        try:
            st = os.statvfs('/dev/shm')
            mb = st.f_frsize * st.f_bavail // (1024 * 1024)
            diag.append(f"{tag}[DIAG] /dev/shm    : {mb} MB free")
        except Exception:
            diag.append(f"{tag}[DIAG] /dev/shm    : not available")

        # ── undetected_chromedriver version ──────────────────────────────────
        try:
            diag.append(f"{tag}[DIAG] uc version  : "
                        f"{getattr(uc, '__version__', 'unknown')}")
        except Exception:
            diag.append(f"{tag}[DIAG] uc version  : import error")

        diag.append(f"{tag}[DIAG] ══════════════════════════════════════")
        for line in diag:
            logger.info(line)

    # =========================================================================
    # SECTION 2 — Chrome options builder
    # =========================================================================

    def _build_default_chrome_options(
        self,
        download_dir: Optional[str] = None,
        extra_args: Optional[list[str]] = None,
    ) -> uc.ChromeOptions:
        """
        Return a uc.ChromeOptions pre-loaded with the same flags MDPI uses.

        Parameters
        ----------
        download_dir : str, optional
            If provided, sets Chrome's automatic download directory so
            downloaded files land in the scraper's output folder.
        extra_args : list[str], optional
            Additional --flags to append (e.g. site-specific needs).

        Notes
        -----
        --headless is deliberately ABSENT.  All supported sites (MDPI, Sage,
        Oxford, Emerald, Lippincott, BMJ) use Akamai / Cloudflare bot
        detection that fingerprints headless Chrome's TLS handshake and
        blocks it.  Always run with a real or virtual (Xvfb) display.
        """
        opts = uc.ChromeOptions()

        # Download preferences (only when output_dir is supplied)
        if download_dir:
            opts.add_experimental_option("prefs", {
                "download.default_directory":        download_dir,
                "download.prompt_for_download":       False,
                "download.directory_upgrade":         True,
                "safebrowsing.enabled":               False,
                "plugins.always_open_pdf_externally": True,
            })

        # Standard EC2/server flags — mirrors MDPI exactly
        standard_args = [
            "--disable-lazy-loading",
            "--remote-allow-origins=*",
            "--disable-print-preview",
            "--disable-stack-profiler",
            "--disable-background-networking",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-browser-side-navigation",
            "--disable-notifications",
            "--disable-blink-features=AutomationControlled",
            "--disable-popup-blocking",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--window-size=1400,900",
            "--start-maximized",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
        ]
        for arg in standard_args:
            opts.add_argument(arg)

        if extra_args:
            for arg in extra_args:
                opts.add_argument(arg)
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
        return opts

    # =========================================================================
    # SECTION 3 — Chrome launch (display :0 → Xvfb :99 fallback)
    # =========================================================================

    def _launch_chrome(
        self,
        opts: uc.ChromeOptions,
        driver_path: Optional[str] = None,
    ) -> None:
        """
        Launch Chrome with automatic display fallback — mirrors MDPI exactly.

        Strategy (Linux / EC2 with GNOME3 desktop):
          1. Try real GNOME3 display :0 with auto-detected XAUTHORITY.
             This is the "GUI visible on the desktop" path — what MDPI uses
             successfully when a GNOME3 session is active.
          2. If Chrome crashes/fails on :0 (common when the Celery worker
             process lacks permission to the X11 socket), automatically
             start Xvfb on :99 and retry there.  Xvfb requires no XAUTHORITY
             and always works on servers.

        On Windows the display logic is skipped entirely.

        After return, self.driver is ready and self._vdisplay holds the
        Xvfb handle (or None if :0 was used).
        """
        logger = getattr(self, 'logger', _log)
        tag    = getattr(self, '_diag_tag', '[ChromeMixin]')

        logger.info("%s ── _launch_chrome START ──", tag)
        self._diagnose_environment()

        # ── Windows: no display juggling needed ──────────────────────────────
        if platform.system() == 'Windows':
            self._try_launch_chrome_on_display(opts, driver_path, display=None)
            return

        # ── Step 1: try real GNOME3 display :0 ───────────────────────────────
        if not os.environ.get('DISPLAY'):
            os.environ['DISPLAY'] = ':0'
        display = os.environ['DISPLAY']

        # XAUTHORITY probe (also done in _diagnose_environment, but kept here
        # so the right value is in env at launch time)
        xauth = os.environ.get('XAUTHORITY', '')
        if not xauth or not os.path.exists(xauth):
            uid_str = str(os.getuid()) if hasattr(os, 'getuid') else '1000'
            for candidate in [
                f"/run/user/{uid_str}/gdm/Xauthority",
                os.path.expanduser("~/.Xauthority"),
                "/home/ubuntu/.Xauthority",
                "/root/.Xauthority",
            ]:
                if os.path.exists(candidate) and os.access(candidate, os.R_OK):
                    os.environ['XAUTHORITY'] = candidate
                    logger.info("%s XAUTHORITY → %s", tag, candidate)
                    break

        logger.info("%s Trying DISPLAY=%s  XAUTHORITY=%s",
                    tag, os.environ.get('DISPLAY'), os.environ.get('XAUTHORITY', '<unset>'))
        try:
            self._try_launch_chrome_on_display(opts, driver_path, display)
            logger.info("%s Chrome launched on GNOME3 display %s ✓", tag, display)
            return
        except Exception as e1:
            logger.warning(
                "%s Chrome failed on %s: %s — falling back to Xvfb",
                tag, display, type(e1).__name__,
            )

        # ── Step 2: Xvfb fallback ─────────────────────────────────────────────
        xvfb_display = self._start_xvfb()           # populates self._vdisplay
        os.environ['DISPLAY']    = xvfb_display
        os.environ.pop('XAUTHORITY', None)           # Xvfb -ac needs no auth

        logger.info("%s Retrying Chrome on Xvfb %s (no XAUTHORITY)", tag, xvfb_display)
        # uc.Chrome mutates the opts object on first use — cloning prevents
        # "you cannot reuse the ChromeOptions object" on the fallback attempt.
        fresh_opts = self._clone_chrome_options(opts)
        try:
            self._try_launch_chrome_on_display(fresh_opts, driver_path, xvfb_display)
            logger.info("%s Chrome launched on Xvfb %s ✓", tag, xvfb_display)
        except Exception as e2:
            logger.error(
                "%s Chrome ALSO failed on Xvfb: %s\n"
                "  Install Xvfb  : sudo apt install xvfb\n"
                "  Install lib   : pip install pyvirtualdisplay\n"
                "  Or allow xhost: DISPLAY=:0 xhost +local:",
                tag, e2,
            )
            self._save_chrome_log()
            raise

    # =========================================================================
    # SECTION 3a — Chrome version detection
    # =========================================================================

    @staticmethod
    def _detect_chrome_major_version() -> Optional[int]:
        """
        Return the installed Chrome's major version number, or None.

        WHY THIS EXISTS
        ───────────────
        undetected_chromedriver (uc) tries to auto-detect the Chrome version
        and download a matching chromedriver.  Starting with Chrome 115+, and
        especially Chrome 145, this auto-detection can go wrong and causes:

            'Runtime.evaluate' wasn't found

        Passing `version_main` explicitly bypasses the broken auto-detection
        and forces uc to download the correct chromedriver for the installed
        Chrome binary.
        """
        import shutil
        candidates = [
            '/usr/bin/google-chrome',
            '/usr/bin/google-chrome-stable',
            '/usr/bin/chromium-browser',
            '/usr/bin/chromium',
            '/snap/bin/chromium',
        ]
        chrome_bin = next(
            (p for p in candidates if os.path.isfile(p)),
            shutil.which('google-chrome') or shutil.which('chromium-browser'),
        )
        if not chrome_bin:
            return None
        try:
            r = subprocess.run(
                [chrome_bin, '--version'],
                capture_output=True, text=True, timeout=10,
            )
            # Output: "Google Chrome 145.0.7632.159"
            parts = r.stdout.strip().split()
            for part in parts:
                if part[0].isdigit():
                    return int(part.split('.')[0])
        except Exception:
            pass
        return None

    def _try_launch_chrome_on_display(
        self,
        opts: uc.ChromeOptions,
        driver_path: Optional[str],
        display: Optional[str],
    ) -> None:
        """
        Attempt uc.Chrome() on *display*.  Raises on failure so the caller
        can retry on a different display.

        Chrome 115+ / 145 fix
        ─────────────────────
        Chrome 145 introduced a regression where undetected_chromedriver's
        internal CDP patcher fails to inject its hook, causing:

            "JavaScript code failed from unknown command:
             'Runtime.evaluate' wasn't found"

        Two mitigations applied here (both are needed together):

          1. use_subprocess=True  — launches chromedriver as a real child
             process instead of in-process, bypassing the broken CDP hook
             injection path.

          2. version_main=<N>     — skips uc's broken auto-detection logic
             and tells it exactly which chromedriver to fetch.  Without this,
             uc sometimes downloads a driver for the wrong Chrome major version
             and the subprocess still fails.

        After success waits up to 15 s for the first window handle to appear
        (same guard as MDPI).
        """
        logger = getattr(self, 'logger', _log)
        tag    = getattr(self, '_diag_tag', '[ChromeMixin]')

        kwargs: dict = dict(
            options=opts,
            use_subprocess=False,   # ← Chrome 145 CDP fix (key mitigation)
        )
        if driver_path:
            kwargs['driver_executable_path'] = driver_path

        # Detect and pass version_main to avoid broken auto-detection
        chrome_ver = self._detect_chrome_major_version()
        if chrome_ver:
            kwargs['version_main'] = chrome_ver
            logger.info("%s Chrome major version detected: %d", tag, chrome_ver)
        else:
            logger.warning("%s Could not detect Chrome version — uc will auto-detect", tag)

        logger.info("%s uc.Chrome(use_subprocess=True, version_main=%s) DISPLAY=%s",
                    tag, chrome_ver, os.environ.get('DISPLAY'))
        self.driver = uc.Chrome(**kwargs)
        logger.info("%s uc.Chrome() succeeded", tag)

        # Wait for window handle — avoids "no such window" on slow EC2 instances
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                if self.driver.window_handles:
                    self.driver.switch_to.window(self.driver.window_handles[0])
                    logger.info("%s Chrome window handle ready", tag)
                    return
            except Exception:
                pass
            time.sleep(0.5)
        logger.warning("%s Chrome window handle not ready within 15 s — continuing anyway", tag)

    # =========================================================================
    # SECTION 3b — ChromeOptions clone helper
    # =========================================================================

    def _clone_chrome_options(self, opts: uc.ChromeOptions) -> uc.ChromeOptions:
        """
        Return a **brand-new** uc.ChromeOptions that carries the same
        arguments and experimental_options as *opts*.

        WHY THIS EXISTS
        ───────────────
        undetected_chromedriver mutates a ChromeOptions object the first
        time uc.Chrome() consumes it (it writes internal keys into
        _experimental_options and/or _caps).  Passing the same object to a
        second uc.Chrome() call — e.g. when the :0 attempt fails and we
        fall back to Xvfb — raises:

            "you cannot reuse the ChromeOptions object"

        Calling this before the Xvfb retry gives uc.Chrome() a pristine
        object and avoids the error entirely.

        Parameters
        ----------
        opts : uc.ChromeOptions
            The options object that was (or may have been) passed to a
            previous uc.Chrome() call.

        Returns
        -------
        uc.ChromeOptions
            A fresh object with the same --flags and experimental prefs.
        """
        new_opts = uc.ChromeOptions()

        # Copy --flag arguments
        for arg in getattr(opts, 'arguments', []):
            try:
                new_opts.add_argument(arg)
            except Exception:
                pass

        # Copy experimental options (e.g. download prefs)
        for key, val in (getattr(opts, '_experimental_options', {}) or {}).items():
            try:
                new_opts.add_experimental_option(key, val)
            except Exception:
                pass

        return new_opts

    # =========================================================================
    # SECTION 4 — Xvfb helpers
    # =========================================================================

    def _start_xvfb(self) -> str:
        """
        Start a virtual framebuffer and return the display string (e.g. ':99').
        Sets self._vdisplay to either a pyvirtualdisplay.Display or a
        subprocess.Popen so _quit_chrome() can clean up either.
        """
        logger = getattr(self, 'logger', _log)
        tag    = getattr(self, '_diag_tag', '[ChromeMixin]')

        logger.info("%s Starting Xvfb virtual display…", tag)

        # Preferred: pyvirtualdisplay (Python API, cleaner lifecycle)
        try:
            from pyvirtualdisplay import Display as VDisplay
            self._vdisplay = VDisplay(visible=False, size=(1400, 900), backend='xvfb')
            self._vdisplay.start()
            xvfb_display = f":{self._vdisplay.display}"
            logger.info("%s pyvirtualdisplay on %s", tag, xvfb_display)
            return xvfb_display
        except ImportError:
            logger.info("%s pyvirtualdisplay not installed — using raw Xvfb on :99", tag)
        except Exception as e:
            logger.warning("%s pyvirtualdisplay failed (%s) — using raw Xvfb on :99", tag, e)

        # Fallback: raw Xvfb subprocess on :99
        subprocess.run(['pkill', '-f', 'Xvfb :99'], capture_output=True)
        time.sleep(0.5)
        proc = subprocess.Popen(
            ['Xvfb', ':99', '-screen', '0', '1400x900x24', '-ac'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._vdisplay = proc
        time.sleep(1.5)
        logger.info("%s Raw Xvfb PID=%d on :99", tag, proc.pid)
        return ':99'

    # =========================================================================
    # SECTION 5 — Teardown
    # =========================================================================

    def _quit_chrome(self) -> None:
        """
        Cleanly close Chrome and stop the virtual display.
        Safe to call multiple times (idempotent).
        Always call this in a finally block.
        """
        logger = getattr(self, 'logger', _log)
        tag    = getattr(self, '_diag_tag', '[ChromeMixin]')

        # ── Quit Chrome ───────────────────────────────────────────────────────
        if getattr(self, 'driver', None) is not None:
            try:
                self.driver.quit()
                logger.info("%s Chrome session closed", tag)
            except Exception as exc:
                logger.warning("%s Error closing Chrome: %s", tag, exc)
            finally:
                self.driver = None

        # ── Stop Xvfb ─────────────────────────────────────────────────────────
        vd = getattr(self, '_vdisplay', None)
        if vd is not None:
            try:
                if hasattr(vd, 'stop'):          # pyvirtualdisplay.Display
                    vd.stop()
                    logger.info("%s pyvirtualdisplay stopped", tag)
                elif hasattr(vd, 'terminate'):   # subprocess.Popen
                    vd.terminate()
                    logger.info("%s Xvfb process terminated", tag)
            except Exception as e:
                logger.debug("%s Error stopping Xvfb: %s", tag, e)
            finally:
                self._vdisplay = None

    # =========================================================================
    # SECTION 6 — Debug log dump on Chrome failure
    # =========================================================================

    def _save_chrome_log(self) -> None:
        """
        Dump dmesg / running chrome processes / env vars to output_dir/debug/.
        Called automatically when Chrome fails on BOTH :0 and Xvfb so you
        can diagnose "session not created" without SSH access.
        """
        logger    = getattr(self, 'logger', _log)
        tag       = getattr(self, '_diag_tag', '[ChromeMixin]')
        out_dir   = getattr(self, 'output_dir', '/tmp')
        debug_dir = os.path.join(out_dir, 'debug')
        os.makedirs(debug_dir, exist_ok=True)

        # ── dmesg — OOM / permission errors ──────────────────────────────────
        try:
            r = subprocess.run(
                ['dmesg', '-T', '--level=err,warn'],
                capture_output=True, text=True, timeout=10,
            )
            with open(os.path.join(debug_dir, 'dmesg.txt'), 'w') as f:
                f.write(r.stdout[-8000:])
            logger.info("%s[DEBUG] dmesg saved → %s/dmesg.txt", tag, debug_dir)
        except Exception as e:
            logger.debug("%s[DEBUG] dmesg failed: %s", tag, e)

        # ── running Chrome / Chromium processes ───────────────────────────────
        try:
            r = subprocess.run(['ps', 'aux', '--no-headers'],
                               capture_output=True, text=True, timeout=5)
            procs = [l for l in r.stdout.splitlines()
                     if 'chrome' in l.lower() or 'chromium' in l.lower()]
            with open(os.path.join(debug_dir, 'chrome_procs.txt'), 'w') as f:
                f.write('\n'.join(procs) or '(none found)')
            logger.info("%s[DEBUG] %d Chrome procs logged", tag, len(procs))
        except Exception as e:
            logger.debug("%s[DEBUG] ps failed: %s", tag, e)

        # ── env snapshot ──────────────────────────────────────────────────────
        env_keys = [
            'DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS',
            'HOME', 'USER', 'PATH', 'XDG_RUNTIME_DIR',
        ]
        with open(os.path.join(debug_dir, 'env_snapshot.txt'), 'w') as f:
            for k in env_keys:
                f.write(f"{k}={os.environ.get(k, '<not set>')}\n")
        logger.info("%s[DEBUG] env snapshot → %s/env_snapshot.txt", tag, debug_dir)

    # =========================================================================
    # SECTION 7 — Cookie persistence
    # =========================================================================

    def _save_cookies(self, cookie_file: str) -> None:
        """
        Persist the current driver session cookies to *cookie_file* (JSON).

        Parameters
        ----------
        cookie_file : str
            Path to the JSON file, e.g. "~/.sage_scraper_cookies.json".
            The path is expanded via os.path.expanduser().

        Usage example
        -------------
            # After successful login:
            self._save_cookies("~/.mysite_cookies.json")
        """
        logger = getattr(self, 'logger', _log)
        tag    = getattr(self, '_diag_tag', '[ChromeMixin]')
        path   = os.path.expanduser(cookie_file)

        if not getattr(self, 'driver', None):
            logger.warning("%s _save_cookies: driver not active", tag)
            return
        try:
            cookies = self.driver.get_cookies()
            with open(path, 'w') as f:
                json.dump(cookies, f)
            logger.info("%s Cookies saved (%d) → %s", tag, len(cookies), path)
        except Exception as exc:
            logger.warning("%s Could not save cookies: %s", tag, exc)

    def _load_cookies(
        self,
        cookie_file: str,
        navigate_to: Optional[str] = None,
    ) -> bool:
        """
        Restore cookies from *cookie_file* into the current driver session.

        Parameters
        ----------
        cookie_file : str
            Path written by _save_cookies().
        navigate_to : str, optional
            URL to navigate to before injecting cookies.  Selenium requires
            the driver to be on the cookie's domain before add_cookie().
            If omitted the driver stays on whatever page it is already on.

        Returns
        -------
        bool
            True if cookies were loaded successfully, False otherwise.

        Usage example
        -------------
            if self._load_cookies("~/.mysite_cookies.json",
                                   navigate_to="https://journals.sagepub.com"):
                self.driver.refresh()
                # check if still logged in
        """
        logger = getattr(self, 'logger', _log)
        tag    = getattr(self, '_diag_tag', '[ChromeMixin]')
        path   = os.path.expanduser(cookie_file)

        if not os.path.exists(path):
            logger.info("%s No saved cookies at %s", tag, path)
            return False
        if not getattr(self, 'driver', None):
            logger.warning("%s _load_cookies: driver not active", tag)
            return False

        try:
            with open(path) as f:
                cookies = json.load(f)

            if navigate_to:
                self.driver.get(navigate_to)
                time.sleep(2)

            loaded = 0
            for cookie in cookies:
                cookie.pop('sameSite', None)   # avoids InvalidCookieDomainException
                try:
                    self.driver.add_cookie(cookie)
                    loaded += 1
                except Exception:
                    pass   # skip cookies that don't match current domain

            logger.info("%s Loaded %d/%d cookies from %s", tag, loaded, len(cookies), path)
            return loaded > 0
        except Exception as exc:
            logger.warning("%s Could not load cookies: %s", tag, exc)
            return False

    def _delete_cookie_file(self, cookie_file: str) -> None:
        """Remove a stale cookie file so the next run does a fresh login."""
        path = os.path.expanduser(cookie_file)
        try:
            if os.path.exists(path):
                os.remove(path)
                getattr(self, 'logger', _log).info(
                    "%s Deleted stale cookie file: %s",
                    getattr(self, '_diag_tag', '[ChromeMixin]'), path,
                )
        except Exception as e:
            getattr(self, 'logger', _log).warning("Could not delete cookie file: %s", e)


# =============================================================================
# QUICK-START TEMPLATES
# =============================================================================
#
# Copy the relevant block into your scraper class, then swap in your own
# Chrome options / cookie file path.
#
# ── Template A: Lippincott / Emerald / BMJ (currently NO display logic) ──────
#
#   from chrome_display_mixin import ChromeDisplayMixin
#
#   class LippincottScraper(ChromeDisplayMixin):
#       _diag_tag = '[Lippincott]'          # appears in every log line
#
#       def __init__(self, keyword, start_year, end_year,
#                    driver_path=None, output_dir=None, progress_callback=None):
#           self.keyword    = keyword
#           self.start_year = start_year
#           self.end_year   = end_year
#           self.driver_path = driver_path
#           self.output_dir  = output_dir or os.getcwd()
#           self._cb         = progress_callback
#           self._vdisplay   = None    # ← required by mixin
#           self.driver      = None    # ← required by mixin
#           self._setup_logger()
#           # __init__ does NOT call run()
#
#       def run(self):
#           try:
#               opts = self._build_default_chrome_options(
#                   download_dir=self.output_dir,
#                   extra_args=["--disable-logging"],
#               )
#               self._launch_chrome(opts, driver_path=self.driver_path)
#               # --- your scraping logic here ---
#           except Exception as exc:
#               self.logger.error("Fatal: %s", exc, exc_info=True)
#               raise
#           finally:
#               self._quit_chrome()
#
#
# ── Template B: Sage (has basic Xvfb, needs :0 fallback + cookies) ────────────
#
#   from chrome_display_mixin import ChromeDisplayMixin
#
#   class SageScraper(ChromeDisplayMixin):
#       _diag_tag = '[Sage]'
#
#       COOKIE_FILE = '~/.sage_scraper_cookies.json'
#
#       def __init__(self, keyword, start_year, end_year,
#                    driver_path=None, output_dir=None, progress_callback=None):
#           ...
#           self._vdisplay = None
#           self.driver    = None
#           self._setup_logger()
#           # __init__ does NOT call run()
#
#       def run(self):
#           try:
#               opts = self._build_default_chrome_options()
#               self._launch_chrome(opts, driver_path=self.driver_path)
#               self.driver.get('https://journals.sagepub.com')
#               if self._load_cookies(self.COOKIE_FILE,
#                                     navigate_to='https://journals.sagepub.com'):
#                   self.driver.refresh()
#               # ── login if needed ──
#               # ── scrape ──
#               self._save_cookies(self.COOKIE_FILE)
#           finally:
#               self._quit_chrome()
#
#
# ── Template C: Oxford (already close — just drop _diagnose + _save_chrome_log)
#
#   Replace _start_virtual_display / _stop_virtual_display with ChromeDisplayMixin,
#   keep _save_cookies / _load_cookies as-is (they match the mixin signature),
#   and delete the duplicated XAUTHORITY probe in _launch_chrome.
#
# =============================================================================
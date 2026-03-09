"""
MDPIScraper — Flask-webapp-compatible MDPI scraper.

Flow:
  1. Launch Chrome (visible, NOT headless — Akamai/auth.mdpi.com blocks headless)
  2. Login to mdpi.com
  3. Detect total result pages for the query
  4. For each page, click "Export → Tab-delimited" and save the .txt download
  5. Combine all .txt files → parse authors + emails → write CSV
  6. Quit Chrome (always, in finally block)

On any Selenium error a screenshot is saved to output_dir/screenshots/
for post-run debugging.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import time
from datetime import datetime
from typing import Callable, Optional

import pandas as pd
import selenium.webdriver.support.expected_conditions as EC
import undetected_chromedriver as uc
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.wait import WebDriverWait

logger = logging.getLogger(__name__)


# ── Credentials (override via env vars for production) ───────────
MDPI_USERNAME = os.environ.get("MDPI_USERNAME", "pritham.pgc@gmail.com")
MDPI_PASSWORD = os.environ.get("MDPI_PASSWORD", "PgC@500072")

# ── Timing constants ─────────────────────────────────────────────
_PAGE_LOAD_WAIT   = 20   # seconds — WebDriverWait for slow page elements
_AFTER_CLICK_WAIT =  3   # seconds — settle time after each UI click
_DOWNLOAD_WAIT    =  8   # seconds — wait for .txt download to land on disk


class MDPIScraper:
    """
    MDPI author/email scraper compatible with the Flask webapp ScraperAdapter.
    """

    def __init__(
        self,
        keyword:           str,
        start_year:        str,
        end_year:          str,
        output_dir:        Optional[str]      = None,
        progress_callback: Optional[Callable] = None,
        driver_path:       Optional[str]      = None,
    ):
        self.keyword     = keyword
        self.start_year  = str(start_year)
        self.end_year    = str(end_year)
        self.driver_path = driver_path

        ts   = datetime.now().strftime('%Y%m%d_%H%M%S')
        slug = keyword.replace(' ', '_')
        self.output_dir = output_dir or os.path.join(
            os.getcwd(), f"mdpi_{slug}_{ts}"
        )
        os.makedirs(self.output_dir, exist_ok=True)

        self.screenshot_dir = os.path.join(self.output_dir, 'screenshots')
        os.makedirs(self.screenshot_dir, exist_ok=True)

        self._cb     = progress_callback
        self._driver: Optional[uc.Chrome] = None

        # ── File log handler — always write to output_dir/mdpi_debug.log ────
        # Celery may suppress or buffer stdout/stderr.  This guarantees a
        # persistent on-disk record of every step, screenshot path, and error.
        self._log_path = os.path.join(self.output_dir, 'mdpi_debug.log')
        _fh = logging.FileHandler(self._log_path, encoding='utf-8')
        _fh.setLevel(logging.DEBUG)
        _fh.setFormatter(logging.Formatter(
            '%(asctime)s  %(levelname)-8s  %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        # Attach to both the module logger and root logger so uc/selenium
        # messages also land in the file.
        logging.getLogger('undetected_chromedriver').addHandler(_fh)
        logging.getLogger('selenium').addHandler(_fh)
        logger.addHandler(_fh)
        logging.getLogger().addHandler(_fh)   # root logger
        self._file_handler = _fh
        # ────────────────────────────────────────────────────────────────────

        logger.info(
            "[MDPI] Initialised — keyword=%r  years=%s-%s  out=%s  log=%s",
            keyword, start_year, end_year, self.output_dir, self._log_path,
        )

    # ── Progress helper ──────────────────────────────────────────

    def _progress(self, pct: int, msg: str,
                  authors: int = 0, emails: int = 0, current_url: str = '') -> None:
        logger.info("[MDPI][%d%%] %s", pct, msg)
        print(f"  [{pct:3d}%] {msg}  ")
        if self._cb:
            try:
                self._cb(pct, msg, current_url=current_url,
                         authors_count=authors, emails_count=emails)
            except Exception:
                pass

    # ── Screenshot helper ────────────────────────────────────────

    def _save_screenshot(self, label: str) -> Optional[str]:
        if not self._driver:
            return None
        try:
            ts   = datetime.now().strftime('%H%M%S')
            path = os.path.join(self.screenshot_dir, f"{label}_{ts}.png")
            self._driver.save_screenshot(path)
            logger.info("[MDPI] Screenshot saved → %s", path)
            return path
        except Exception as exc:
            logger.warning("[MDPI] Could not save screenshot: %s", exc)
            return None

    # ── Chrome lifecycle ─────────────────────────────────────────

    @staticmethod
    def _diagnose_environment() -> None:
        """
        Log a full diagnostic snapshot of the process environment before
        Chrome launch so that 'session not created' errors can be debugged
        from the Celery/Flask log without SSH access.

        Covers: OS, Python, Chrome binary, chromedriver, DISPLAY,
        XAUTHORITY, running X sessions, /dev/shm size, and UID/GID.
        """
        import platform, shutil, subprocess, pwd, grp

        diag: list[str] = ["[MDPI][DIAG] ══════ Environment Diagnostic ══════"]

        # ── OS / Python ──────────────────────────────────────────────────────
        diag.append(f"[MDPI][DIAG] OS          : {platform.platform()}")
        diag.append(f"[MDPI][DIAG] Python      : {platform.python_version()} "
                    f"@ {platform.python_implementation()}")

        # ── Process identity ─────────────────────────────────────────────────
        try:
            uid  = os.getuid()
            gid  = os.getgid()
            uname = pwd.getpwuid(uid).pw_name
            gname = grp.getgrgid(gid).gr_name
            diag.append(f"[MDPI][DIAG] UID/GID     : {uid}/{gid} ({uname}/{gname})")
            diag.append(f"[MDPI][DIAG] HOME        : {os.path.expanduser('~')}")
        except Exception as e:
            diag.append(f"[MDPI][DIAG] UID/GID     : unknown ({e})")

        # ── X display ────────────────────────────────────────────────────────
        display    = os.environ.get('DISPLAY', '<NOT SET>')
        xauth      = os.environ.get('XAUTHORITY', '<NOT SET>')
        dbus       = os.environ.get('DBUS_SESSION_BUS_ADDRESS', '<NOT SET>')
        diag.append(f"[MDPI][DIAG] DISPLAY     : {display}")
        diag.append(f"[MDPI][DIAG] XAUTHORITY  : {xauth}")
        diag.append(f"[MDPI][DIAG] DBUS_SESSION: {dbus}")

        # Check if XAUTHORITY file actually exists and is readable
        if xauth and xauth != '<NOT SET>':
            exists   = os.path.exists(xauth)
            readable = os.access(xauth, os.R_OK) if exists else False
            diag.append(f"[MDPI][DIAG] XAUTH file  : exists={exists}  readable={readable}")
        else:
            # Try common GNOME3 XAUTHORITY locations
            uid_str  = str(os.getuid()) if hasattr(os, 'getuid') else '1000'
            candidates = [
                f"/run/user/{uid_str}/gdm/Xauthority",
                os.path.expanduser("~/.Xauthority"),
                f"/home/ubuntu/.Xauthority",
                f"/root/.Xauthority",
            ]
            found_xauth = None
            for p in candidates:
                if os.path.exists(p) and os.access(p, os.R_OK):
                    found_xauth = p
                    break
            diag.append(f"[MDPI][DIAG] XAUTH probe : {found_xauth or 'NOT FOUND — Chrome WILL FAIL'}")
            if found_xauth:
                diag.append(f"[MDPI][DIAG] XAUTH FIX   : setting XAUTHORITY={found_xauth}")
                os.environ['XAUTHORITY'] = found_xauth

        # ── Check xhost / X accessibility ────────────────────────────────────
        try:
            r = subprocess.run(['xdpyinfo', '-display', display],
                               capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                lines = r.stdout.strip().splitlines()
                diag.append(f"[MDPI][DIAG] xdpyinfo    : OK — {lines[0] if lines else 'connected'}")
            else:
                diag.append(f"[MDPI][DIAG] xdpyinfo    : FAILED (rc={r.returncode}) — "
                             f"{r.stderr.strip()[:120]}")
                diag.append("[MDPI][DIAG] *** Chrome WILL FAIL — X server not reachable ***")
                diag.append("[MDPI][DIAG] Fix: run  xhost +local:  on the GNOME3 desktop, OR")
                diag.append("[MDPI][DIAG]      copy XAUTHORITY from the logged-in user session")
        except FileNotFoundError:
            diag.append("[MDPI][DIAG] xdpyinfo    : not installed (apt install x11-utils)")
        except Exception as e:
            diag.append(f"[MDPI][DIAG] xdpyinfo    : error ({e})")

        # ── Chrome binary ─────────────────────────────────────────────────────
        chrome_candidates = [
            '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable',
            '/usr/bin/chromium-browser', '/usr/bin/chromium', '/snap/bin/chromium',
        ]
        chrome_found = None
        for p in chrome_candidates:
            if os.path.isfile(p):
                chrome_found = p
                break
        if not chrome_found:
            chrome_found = shutil.which('google-chrome') or shutil.which('chromium-browser')
        diag.append(f"[MDPI][DIAG] Chrome bin  : {chrome_found or 'NOT FOUND'}")
        if chrome_found:
            try:
                rv = subprocess.run([chrome_found, '--version'],
                                    capture_output=True, text=True, timeout=10)
                diag.append(f"[MDPI][DIAG] Chrome ver  : {rv.stdout.strip()}")
            except Exception as e:
                diag.append(f"[MDPI][DIAG] Chrome ver  : error ({e})")

        # ── chromedriver ─────────────────────────────────────────────────────
        cd = shutil.which('chromedriver')
        diag.append(f"[MDPI][DIAG] chromedriver: {cd or 'not in PATH'}")
        if cd:
            try:
                rv = subprocess.run([cd, '--version'],
                                    capture_output=True, text=True, timeout=10)
                diag.append(f"[MDPI][DIAG] cdvr version: {rv.stdout.strip()}")
            except Exception as e:
                diag.append(f"[MDPI][DIAG] cdvr version: error ({e})")

        # ── /dev/shm ─────────────────────────────────────────────────────────
        try:
            st = os.statvfs('/dev/shm')
            mb = st.f_frsize * st.f_bavail // (1024 * 1024)
            diag.append(f"[MDPI][DIAG] /dev/shm    : {mb} MB free")
        except Exception:
            diag.append("[MDPI][DIAG] /dev/shm    : not available")

        # ── undetected_chromedriver version ──────────────────────────────────
        try:
            import undetected_chromedriver as _uc
            diag.append(f"[MDPI][DIAG] uc version  : {getattr(_uc, '__version__', 'unknown')}")
        except Exception:
            diag.append("[MDPI][DIAG] uc version  : import failed")

        # ── Log everything in one shot ────────────────────────────────────────
        diag.append("[MDPI][DIAG] ══════════════════════════════════════")
        for line in diag:
            logger.info(line)
            print(line)

    def _launch_chrome(self) -> None:
        """
        Launch undetected Chrome — NO headless.

        auth.mdpi.com is protected by Akamai Bot Manager which fingerprints
        headless Chrome at the TLS level. Visible mode is the only option.

        On EC2/Ubuntu with GNOME3: Chrome needs both DISPLAY and XAUTHORITY.
        DISPLAY=:0 is the GNOME3 display; XAUTHORITY is the MIT-MAGIC-COOKIE
        file that grants access to that display.  Celery workers running as
        a different UID often have DISPLAY but NOT XAUTHORITY — causing the
        'session not created: cannot connect to chrome' error.

        We auto-detect and set XAUTHORITY before launching Chrome.
        """
        import platform, subprocess, shutil

        logger.info("[MDPI] ── _launch_chrome START ──")

        # ── Run full environment diagnostic before attempting Chrome ─────────
        self._diagnose_environment()

        # ── Ensure DISPLAY is set ────────────────────────────────────────────
        if platform.system() != 'Windows':
            if not os.environ.get('DISPLAY'):
                os.environ['DISPLAY'] = ':0'
                logger.info("[MDPI] DISPLAY not set — forcing :0")
            else:
                logger.info("[MDPI] DISPLAY=%s (already set)", os.environ['DISPLAY'])

            # ── GNOME3 XAUTHORITY fix ────────────────────────────────────────
            # If XAUTHORITY is already set and readable, use it.
            # Otherwise probe known GNOME3/GDM locations and set it.
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
                        logger.info("[MDPI] XAUTHORITY set → %s", candidate)
                        break
                else:
                    logger.warning(
                        "[MDPI] XAUTHORITY not found in any standard location. "
                        "Chrome may fail with 'session not created'. "
                        "Fix: run  xhost +local:  on the GNOME3 desktop, OR "
                        "set XAUTHORITY=/home/<user>/.Xauthority in the "
                        "Celery worker's systemd/supervisor environment."
                    )
            else:
                logger.info("[MDPI] XAUTHORITY=%s (already set, file exists)", xauth)

        # ── Build Chrome options ─────────────────────────────────────────────
        logger.info("[MDPI] Building Chrome options…")
        opts = uc.ChromeOptions()
        prefs = {
            "download.default_directory":        self.output_dir,
            "download.prompt_for_download":       False,
            "download.directory_upgrade":         True,
            "safebrowsing.enabled":               False,
            "plugins.always_open_pdf_externally": True,
        }
        opts.add_experimental_option("prefs", prefs)
        logger.info("[MDPI] Download dir prefs → %s", self.output_dir)

        # ── NO --headless flag ─────────────────────────────────────────────
        # Akamai Bot Manager blocks headless at TLS fingerprint level.
        chrome_args = [
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
        ]
        for arg in chrome_args:
            opts.add_argument(arg)
        logger.info("[MDPI] Chrome args: %s", chrome_args)

        kwargs: dict = dict(options=opts)
        if self.driver_path:
            kwargs['driver_executable_path'] = self.driver_path
            logger.info("[MDPI] Using driver_path=%s", self.driver_path)
        else:
            logger.info("[MDPI] driver_path not set — uc will auto-locate chromedriver")

        # ── Launch Chrome ────────────────────────────────────────────────────
        logger.info("[MDPI] Calling uc.Chrome(**kwargs) …  "
                    "DISPLAY=%s  XAUTHORITY=%s",
                    os.environ.get('DISPLAY', '<unset>'),
                    os.environ.get('XAUTHORITY', '<unset>'))
        try:
            self._driver = uc.Chrome(**kwargs)
            logger.info("[MDPI] uc.Chrome() returned successfully")
        except Exception as exc:
            logger.error(
                "[MDPI] Chrome launch FAILED: %s\n"
                "  DISPLAY=%s  XAUTHORITY=%s\n"
                "  Hint: check that DISPLAY and XAUTHORITY are correct in\n"
                "  the Celery worker systemd unit, e.g.:\n"
                "    Environment=DISPLAY=:0\n"
                "    Environment=XAUTHORITY=/home/ubuntu/.Xauthority\n"
                "  Also verify xhost +local: has been run on the GNOME3 desktop.",
                exc,
                os.environ.get('DISPLAY', '<unset>'),
                os.environ.get('XAUTHORITY', '<unset>'),
            )
            self._save_chrome_log()
            raise

        # ── Wait for Chrome window to be ready ───────────────────────────────
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                if self._driver.window_handles:
                    self._driver.switch_to.window(self._driver.window_handles[0])
                    logger.info("[MDPI] Chrome window ready — handle=%s",
                                self._driver.window_handles[0])
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            logger.warning("[MDPI] Chrome window did not become ready within 15 s")

        logger.info("[MDPI] ── _launch_chrome DONE ──")

    def _quit_chrome(self) -> None:
        if self._driver is None:
            return
        try:
            self._driver.quit()
            logger.info("[MDPI] Chrome session closed.")
        except Exception as exc:
            logger.warning("[MDPI] Error closing Chrome: %s", exc)
        finally:
            self._driver = None

    def _save_chrome_log(self) -> None:
        """
        Dump Chrome/chromedriver log files to output_dir/debug/ when
        Chrome fails to start — helps diagnose 'session not created' errors
        without SSH access.
        """
        import subprocess, shutil
        debug_dir = os.path.join(self.output_dir, 'debug')
        os.makedirs(debug_dir, exist_ok=True)

        # ── dmesg for OOM / permission errors ───────────────────────────────
        try:
            r = subprocess.run(['dmesg', '-T', '--level=err,warn'],
                               capture_output=True, text=True, timeout=10)
            with open(os.path.join(debug_dir, 'dmesg.txt'), 'w') as f:
                f.write(r.stdout[-8000:])   # last 8 KB
            logger.info("[MDPI][DEBUG] dmesg saved → %s/dmesg.txt", debug_dir)
        except Exception as e:
            logger.debug("[MDPI][DEBUG] dmesg failed: %s", e)

        # ── running Chrome/chromedriver processes ────────────────────────────
        try:
            r = subprocess.run(['ps', 'aux', '--no-headers'],
                               capture_output=True, text=True, timeout=5)
            chrome_procs = [l for l in r.stdout.splitlines()
                            if 'chrome' in l.lower() or 'chromium' in l.lower()]
            with open(os.path.join(debug_dir, 'chrome_procs.txt'), 'w') as f:
                f.write('\n'.join(chrome_procs) or '(none found)')
            logger.info("[MDPI][DEBUG] chrome procs: %d found", len(chrome_procs))
        except Exception as e:
            logger.debug("[MDPI][DEBUG] ps failed: %s", e)

        # ── env vars snapshot ────────────────────────────────────────────────
        env_keys = ['DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS',
                    'HOME', 'USER', 'PATH', 'XDG_RUNTIME_DIR']
        env_dump = {k: os.environ.get(k, '<not set>') for k in env_keys}
        with open(os.path.join(debug_dir, 'env_snapshot.txt'), 'w') as f:
            for k, v in env_dump.items():
                f.write(f"{k}={v}\n")
        logger.info("[MDPI][DEBUG] env snapshot → %s/env_snapshot.txt", debug_dir)

    # ── Cookie consent ───────────────────────────────────────────

    def _dismiss_cookie_consent(self) -> None:
        d = self._driver
        try:
            WebDriverWait(d, 5).until(
                EC.presence_of_element_located((By.ID, "usercentrics-cmp-ui"))
            )
            logger.info("[MDPI] Cookie consent dialog detected.")
        except Exception:
            pass  # No banner — fine
        # Always nuke any consent overlay via JS regardless of whether
        # the wait succeeded — belt-and-suspenders so it never blocks clicks.
        d.execute_script("""
            // Try clicking accept button first
            var btn = document.querySelector(
                'button[data-action="consent"][data-action-type="accept"]') ||
                document.querySelector('button.uc-accept-button') ||
                document.getElementById('accept') ||
                document.querySelector('button[aria-label*="Accept"]') ||
                document.querySelector('button[class*="accept"]');
            if (btn) { btn.click(); }
            // Then forcibly remove the overlay elements so they can't intercept clicks
            var ids = ['usercentrics-cmp-ui', 'uc-overlay', 'uc-backdrop'];
            ids.forEach(function(id) {
                var el = document.getElementById(id);
                if (el) el.remove();
            });
            // Remove any fixed/absolute overlays from Usercentrics
            document.querySelectorAll('[data-nosnippet], [class*="uc-"], [id*="uc-"]')
                .forEach(function(el) {
                    var s = window.getComputedStyle(el);
                    if (s.position === 'fixed' || s.position === 'absolute') el.remove();
                });
            // Re-enable scrolling that consent dialogs often lock
            document.body.style.overflow = '';
            document.documentElement.style.overflow = '';
        """)
        time.sleep(1)

    # ── JS click helper ──────────────────────────────────────────

    def _js_click(self, element) -> None:
        self._driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'}); arguments[0].click();",
            element,
        )

    # ── Cookie persistence ───────────────────────────────────────

    _COOKIE_FILE = os.path.join(
        os.path.expanduser('~'), '.mdpi_scraper_cookies.json'
    )

    def _save_cookies(self) -> None:
        try:
            cookies = self._driver.get_cookies()
            with open(self._COOKIE_FILE, 'w') as f:
                json.dump(cookies, f)
            logger.info("[MDPI] Cookies saved (%d) → %s", len(cookies), self._COOKIE_FILE)
        except Exception as exc:
            logger.warning("[MDPI] Could not save cookies: %s", exc)

    def _load_cookies(self) -> bool:
        if not os.path.exists(self._COOKIE_FILE):
            return False
        try:
            with open(self._COOKIE_FILE) as f:
                cookies = json.load(f)
            for cookie in cookies:
                cookie.pop('sameSite', None)
                try:
                    self._driver.add_cookie(cookie)
                except Exception:
                    pass
            logger.info("[MDPI] Loaded %d cookies from %s", len(cookies), self._COOKIE_FILE)
            return True
        except Exception as exc:
            logger.warning("[MDPI] Could not load cookies: %s", exc)
            return False

    def _is_logged_in(self) -> bool:
        try:
            cur = self._driver.current_url.lower()
            if 'auth.mdpi.com' in cur or 'login.mdpi.com' in cur:
                return False
            els = self._driver.find_elements(
                By.XPATH, '//a[contains(@href,"logout") or contains(@href,"signout")]'
            )
            return len(els) > 0
        except Exception:
            return False

    # ── Login ────────────────────────────────────────────────────

    def _login(self) -> None:
        """
        Log in to mdpi.com.

        Strategy:
          1. Inject saved cookies → refresh → if session still valid, done.
          2. If stale/missing: fill SSO form, submit, save cookies on success.

        Cookies are stored at ~/.mdpi_scraper_cookies.json and reused across
        runs so MDPI's rate-limiter never sees repeated form submissions.
        Delete that file to force a fresh login.
        """
        d = self._driver
        try:
            self._progress(2, "Logging in to MDPI…")
            time.sleep(3)

            # ── Step 1: Try cookie-based login ───────────────────────────
            logger.info("[MDPI] Trying cookie-based login…")
            d.get('https://www.mdpi.com/')
            self._dismiss_cookie_consent()
            time.sleep(2)

            if self._load_cookies():
                d.refresh()
                time.sleep(4)
                self._dismiss_cookie_consent()
                if self._is_logged_in():
                    logger.info("[MDPI] Cookie login successful → %s", d.current_url)
                    self._progress(5, "Login successful (cookies).")
                    return
                logger.info("[MDPI] Saved cookies invalid — doing fresh form login")
                # Delete stale cookie file
                try:
                    os.remove(self._COOKIE_FILE)
                except Exception:
                    pass

            # ── Step 2: Full form login ──────────────────────────────────
            d.get('https://www.mdpi.com/user/login/')
            self._dismiss_cookie_consent()
            WebDriverWait(d, _PAGE_LOAD_WAIT).until(
                EC.presence_of_element_located((By.XPATH, '//input'))
            )
            time.sleep(2)

            current_url = d.current_url
            logger.info("[MDPI] Login page URL: %s", current_url)
            self._save_screenshot('login_page_loaded')

            on_new_sso = any(h in current_url.lower()
                             for h in ('auth.mdpi.com', 'login.mdpi.com'))

            if not on_new_sso:
                logger.info("[MDPI] Old login UI (www.mdpi.com)")
                d.find_element(By.ID, 'username').send_keys(MDPI_USERNAME)
                d.find_element(By.ID, 'password').send_keys(MDPI_PASSWORD)
                d.find_element(By.XPATH, '//input[@class="button submit-btn"]').click()
            else:
                logger.info("[MDPI] New SSO single-step login (%s)", current_url)
                actions = ActionChains(d)

                email_el = WebDriverWait(d, 10).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, '//input[@type="email" or '
                         'contains(translate(@placeholder,'
                         '"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"),"mail")]')
                    )
                )
                actions.move_to_element(email_el).click().click().click().perform()
                time.sleep(0.3)
                email_el.send_keys(Keys.CONTROL + 'a')
                email_el.send_keys(MDPI_USERNAME)
                time.sleep(0.5)

                pass_el = WebDriverWait(d, 10).until(
                    EC.element_to_be_clickable((By.XPATH, '//input[@type="password"]'))
                )
                actions.move_to_element(pass_el).click().click().click().perform()
                time.sleep(0.3)
                pass_el.send_keys(Keys.CONTROL + 'a')
                pass_el.send_keys(MDPI_PASSWORD)
                time.sleep(0.5)

                val_email = d.execute_script("return arguments[0].value;", email_el)
                val_pass  = d.execute_script("return arguments[0].value;", pass_el)
                logger.info("[MDPI] Pre-submit — email=%d chars, password=%d chars",
                            len(val_email), len(val_pass))
                self._save_screenshot('pre_submit')

                if len(val_email) == 0 or len(val_pass) == 0:
                    raise RuntimeError(
                        f"Login fields empty — email={len(val_email)}, "
                        f"password={len(val_pass)} chars"
                    )
                # Press Enter — most natural submission, avoids button-click bot detection
                pass_el.send_keys(Keys.RETURN)

            # Poll for redirect away from SSO domains (up to 40s)
            logger.info("[MDPI] Waiting for SSO redirect…")
            for i in range(40):
                time.sleep(1)
                cur = d.current_url.lower()
                if 'auth.mdpi.com' not in cur and 'login.mdpi.com' not in cur:
                    logger.info("[MDPI] SSO redirect done after %ds → %s", i+1, d.current_url)
                    break
            else:
                self._save_screenshot('login_failed')
                raise RuntimeError(
                    f"MDPI login failed after 40s — still on: {d.current_url}\n"
                    "MDPI may be rate-limiting. Wait a few minutes and retry,\n"
                    "or delete ~/.mdpi_scraper_cookies.json and try again."
                )

            time.sleep(2)
            self._save_cookies()   # persist for next run
            logger.info("[MDPI] Login successful → %s", d.current_url)
            self._progress(5, "Login successful.")

        except RuntimeError:
            raise
        except Exception as exc:
            self._save_screenshot('login_error')
            raise RuntimeError(f"MDPI login error: {exc}") from exc

    # ── Page count detection ─────────────────────────────────────

    def _get_total_pages(self) -> int:
        d   = self._driver
        url = (
            f"https://www.mdpi.com/search"
            f"?sort=pubdate&page_count=200"
            f"&year_from={self.start_year}&year_to={self.end_year}"
            f"&q={self.keyword}&view=compact"
        )
        self._progress(7, "Detecting total result pages…", current_url=url)
        d.get(url)
        self._dismiss_cookie_consent()

        try:
            header = WebDriverWait(d, _PAGE_LOAD_WAIT).until(
                EC.presence_of_element_located(
                    (By.XPATH, '//div[@class="columns large-6 medium-6 small-12"]')
                )
            )
            text = header.text.strip()
            logger.info("[MDPI] Page-count header text: %r", text)

            parts   = text.split('of')
            last_of = parts[-1].replace(',', '').replace('.', '').split()[0].strip()
            if last_of.isdigit() and int(last_of) <= 5_000:
                pages_from_last = int(last_of)
                if len(parts) >= 2:
                    mid = parts[1].replace(',', '').replace('.', '').split()
                    if mid and mid[0].isdigit():
                        result_count = int(mid[0])
                        if result_count > 200:
                            pages_computed = max(1, -(-result_count // 200))
                            pages = max(pages_from_last, pages_computed)
                            logger.info(
                                "[MDPI] Result count %d → %d pages; header says %d → using %d",
                                result_count, pages_computed, pages_from_last, pages,
                            )
                            return pages
                logger.info("[MDPI] Parsed page count directly: %d", pages_from_last)
                return max(1, pages_from_last)

            first_of = parts[1].replace(',', '').replace('.', '').split()[0].strip()
            if first_of.isdigit():
                result_count = int(first_of)
                pages = max(1, -(-result_count // 200))
                logger.info("[MDPI] Result count %d → %d page(s)", result_count, pages)
                return pages

        except Exception as exc:
            logger.warning("[MDPI] Primary page-count parse failed: %s", exc)

        try:
            pager = d.find_elements(
                By.XPATH, '//ul[contains(@class,"pagination")]//a[@class="page-link"]'
            )
            nums = [int(a.text.strip()) for a in pager if a.text.strip().isdigit()]
            if nums:
                pages = max(nums)
                logger.info("[MDPI] Pagination widget: %d page(s)", pages)
                return pages
        except Exception:
            pass

        self._save_screenshot('page_count_error')
        logger.warning("[MDPI] Could not determine page count — defaulting to 1")
        return 1

    # ── Single-page download ─────────────────────────────────────

    def _download_page(self, page_no: int, total_pages: int) -> bool:
        """
        Direct port of the working extractEmails() from the original script.

        CRITICAL: ALL clicks use plain .click() — NOT JS click.
        Chosen.js dropdown relies on native browser mousedown/mouseup events.
        JS click fires only the click event, which leaves the dropdown open
        but then immediately closes it before the li item can be selected.
        Plain .click() is the only approach that works with Chosen.js.
        """
        d           = self._driver
        max_retries = 3

        for attempt in range(1, max_retries + 1):
            url = (
                f"https://www.mdpi.com/search"
                f"?sort=pubdate&page_no={page_no + 1}&page_count=200"
                f"&year_from={self.start_year}&year_to={self.end_year}"
                f"&q={self.keyword}&view=compact"
            )
            logger.info("[MDPI] Page %d (attempt %d)", page_no + 1, attempt)
            try:
                d.get(url)
                self._dismiss_cookie_consent()
                time.sleep(3)   # let page fully settle — same as working script

                # All UI interactions use JS clicks — window does NOT need focus.
                # Plain .click() fails when Chrome is in the background because
                # overlays (cookie banners, etc.) intercept the events.
                # JS scrollIntoView+click bypasses all overlay interception.

                # ① Show export panel
                el = WebDriverWait(d, 10).until(
                    EC.presence_of_element_located(
                        (By.XPATH, '//a[contains(@class,"export-options-show")]')
                    )
                )
                d.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el)
                time.sleep(2)

                # ② Select all
                el = WebDriverWait(d, 10).until(
                    EC.presence_of_element_located((By.ID, 'selectUnselectAll'))
                )
                d.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el)
                time.sleep(2)

                # ③+④ Set Tab-delimited on native <select> — bypasses Chosen.js entirely
                selected = d.execute_script("""
                    var selects = document.querySelectorAll('select');
                    for (var i = 0; i < selects.length; i++) {
                        var sel = selects[i];
                        for (var j = 0; j < sel.options.length; j++) {
                            if (sel.options[j].text.indexOf('Tab-delimited') !== -1) {
                                sel.value = sel.options[j].value;
                                sel.dispatchEvent(new Event('change', {bubbles: true}));
                                return sel.options[j].value;
                            }
                        }
                    }
                    return null;
                """)
                if not selected:
                    raise RuntimeError("Tab-delimited option not found in any <select> on page")
                logger.info("[MDPI] Tab-delimited selected via JS (value=%s)", selected)
                time.sleep(1)

                # ⑤ Click Export button
                el = WebDriverWait(d, 10).until(
                    EC.presence_of_element_located((By.ID, 'articleBrowserExport_top'))
                )
                d.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", el)

                time.sleep(_DOWNLOAD_WAIT)
                logger.info("[MDPI] Page %d downloaded successfully.", page_no + 1)
                return True

            except Exception as exc:
                logger.warning(
                    "[MDPI] Page %d attempt %d error: %s", page_no + 1, attempt, exc
                )
                self._save_screenshot(f'page{page_no + 1}_attempt{attempt}_error')
                if attempt < max_retries:
                    logger.info("[MDPI] Retrying in 5 seconds…")
                    time.sleep(5)
                    try:
                        d.refresh()
                        time.sleep(3)
                    except Exception:
                        pass

        logger.error("[MDPI] Page %d failed after %d attempts", page_no + 1, max_retries)
        return False

    # ── Parse downloaded .txt files → CSV ────────────────────────

    def _build_csv(self) -> Optional[str]:
        """
        Merge all MDPI tab-delimited .txt downloads into a rich CSV matching
        the PubMed scraper column layout, plus MDPI-specific extras.

        MDPI tab-delimited export columns (actual):
          AUTHOR, TITLE, JOURNAL, LANGUANGE (sic), DOCTYPE, KEYWORDS,
          ABSTRACT, AFFILIATION, EMAIL, DOI, PUBYEAR, PUBVOL, PUBISSUE,
          FPAGE, LPAGE, ARTNUMBER, PAGENUM

        Output CSV columns (one row per unique email):
          email, first_name, last_name, full_name,        ← same as PubMed
          title, doi, pub_url, pub_date,                  ← same as PubMed
          journal, volume, issue, pages,                  ← same as PubMed
          affiliation, keywords,                          ← same as PubMed
          abstract, language, doc_type                    ← MDPI extras

        pages is built from FPAGE-LPAGE when both are present and non-empty,
        then ARTNUMBER, then PAGENUM, in that order.
        """
        txt_files = glob.glob(os.path.join(self.output_dir, '*.txt'))
        if not txt_files:
            logger.warning("[MDPI] No .txt files found in %s", self.output_dir)
            return None

        slug     = self.keyword.replace(' ', '_')
        ts       = datetime.now().strftime('%Y%m%d_%H%M%S')
        combined = os.path.join(self.output_dir, f"mdpi_{slug}_combined_{ts}.txt")

        with open(combined, 'w', encoding='utf-8') as out_f:
            for i, fp in enumerate(sorted(txt_files)):
                with open(fp, encoding='utf-8', errors='replace') as in_f:
                    lines = in_f.readlines()
                    if i > 0 and lines:
                        lines = lines[1:]
                    out_f.writelines(lines)

        try:
            df = pd.read_csv(combined, sep='\t', skip_blank_lines=True,
                             skipinitialspace=True, dtype=str)
        except Exception as exc:
            logger.error("[MDPI] Could not read combined txt: %s", exc)
            return None

        # Normalise column names — strip whitespace, uppercase for matching
        df.columns = df.columns.str.strip()
        cu = {c: c.upper().strip() for c in df.columns}  # original → upper map

        def _find_col(*candidates):
            """Return the first df column whose upper name matches any candidate."""
            for cand in candidates:
                for orig, up in cu.items():
                    if up == cand or up.startswith(cand):
                        return orig
            return None

        col_author    = _find_col('AUTHOR')
        col_email     = _find_col('EMAIL')
        col_title     = _find_col('TITLE')
        col_doi       = _find_col('DOI')
        col_url       = _find_col('URL', 'LINK', 'PUB_URL')
        # MDPI exports PUBYEAR (not YEAR); support both
        col_year      = _find_col('PUBYEAR', 'YEAR', 'PUB YEAR', 'PUBLICATION YEAR')
        col_journal   = _find_col('JOURNAL', 'SOURCE')
        col_volume    = _find_col('PUBVOL', 'VOLUME')
        col_issue     = _find_col('PUBISSUE', 'ISSUE', 'NUMBER')
        # MDPI exports FPAGE, LPAGE, ARTNUMBER — we build pages from these
        col_fpage     = _find_col('FPAGE')
        col_lpage     = _find_col('LPAGE')
        col_artnumber = _find_col('ARTNUMBER', 'ARTICLENUM')
        col_pages_raw = _find_col('PAGES', 'PAGE', 'PAGENUM')
        col_affil     = _find_col('AFFILIATION', 'INSTITUTION')
        col_kw        = _find_col('KEYWORDS', 'KEYWORD')
        # MDPI-specific extra columns (not in PubMed output)
        col_abstract  = _find_col('ABSTRACT')
        col_language  = _find_col('LANGUANGE', 'LANGUAGE', 'LANG')  # MDPI has typo: LANGUANGE
        col_doctype   = _find_col('DOCTYPE', 'DOCUMENT TYPE', 'TYPE')

        logger.info("[MDPI] Detected columns: author=%s email=%s title=%s doi=%s "
                    "url=%s year=%s journal=%s vol=%s issue=%s affil=%s "
                    "abstract=%s lang=%s doctype=%s",
                    col_author, col_email, col_title, col_doi,
                    col_url, col_year, col_journal, col_volume, col_issue, col_affil,
                    col_abstract, col_language, col_doctype)

        if not col_author or not col_email:
            logger.error("[MDPI] Required AUTHOR/EMAIL columns not found. "
                         "Available: %s", list(df.columns))
            return None

        # ── Helper: get scalar column value safely ────────────────────────────
        def _col(row, col, default='N/A'):
            if col and col in row.index:
                v = str(row[col]).strip()
                return v if v and v.lower() not in ('nan', 'none', '') else default
            return default

        # ── Explode per-author semicolon-separated lists ──────────────────────
        def _split_semi(val):
            if pd.isna(val) or str(val).strip() in ('', 'nan'):
                return []
            return [x.strip() for x in str(val).split(';') if x.strip()]

        rows_out = []
        seen_emails = set()

        for _, row in df.iterrows():
            authors = _split_semi(row[col_author])
            emails  = _split_semi(row[col_email])

            if not emails:
                continue

            # Pair authors with emails by position.
            # If counts differ, zip truncates to shorter — remaining emails
            # are attached to the last author.
            if len(authors) == len(emails):
                pairs = list(zip(authors, emails))
            elif len(authors) < len(emails):
                # More emails than authors — pair what we can, rest to last author
                pairs = list(zip(authors, emails[:len(authors)]))
                for extra_email in emails[len(authors):]:
                    pairs.append((authors[-1] if authors else 'N/A', extra_email))
            else:
                # More authors than emails — attach all emails to first author
                pairs = [(authors[0], e) for e in emails]

            # Article-level fields (same for all authors on this row)
            title    = _col(row, col_title)
            doi      = _col(row, col_doi)
            pub_url  = _col(row, col_url)
            year     = _col(row, col_year)
            journal  = _col(row, col_journal)
            volume   = _col(row, col_volume)
            issue    = _col(row, col_issue)
            affil    = _col(row, col_affil)
            keywords = _col(row, col_kw)
            abstract = _col(row, col_abstract)
            language = _col(row, col_language)
            doc_type = _col(row, col_doctype)

            # Build pages from FPAGE-LPAGE or fall back to ARTNUMBER then PAGES
            fpage = _col(row, col_fpage)
            lpage = _col(row, col_lpage)
            artn  = _col(row, col_artnumber)
            pages_raw = _col(row, col_pages_raw)
            if fpage != 'N/A' and fpage != '-' and lpage != 'N/A' and lpage != '-':
                pages = f"{fpage}-{lpage}"
            elif artn != 'N/A' and artn != '-':
                pages = artn
            elif pages_raw != 'N/A' and pages_raw != '-':
                pages = pages_raw
            else:
                pages = 'N/A'

            # Build DOI URL if url column missing but DOI exists
            if pub_url == 'N/A' and doi != 'N/A':
                pub_url = f"https://doi.org/{doi}"

            for author_name, email in pairs:
                email = email.rstrip('.')
                if not email or '@' not in email:
                    continue
                email_lc = email.lower()
                if email_lc in seen_emails:
                    continue
                seen_emails.add(email_lc)

                # Split "Last, First" → first_name / last_name
                if ',' in author_name:
                    last, _, first = author_name.partition(',')
                    last  = last.strip()
                    first = first.strip()
                else:
                    parts = author_name.split()
                    first = ' '.join(parts[:-1]) if len(parts) > 1 else ''
                    last  = parts[-1] if parts else author_name
                full_name = f"{first} {last}".strip() or author_name

                rows_out.append({
                    'email'      : email,
                    'first_name' : first  or 'N/A',
                    'last_name'  : last   or 'N/A',
                    'full_name'  : full_name,
                    'title'      : title,
                    'doi'        : doi,
                    'pub_url'    : pub_url,
                    'pub_date'   : year,
                    'journal'    : journal,
                    'volume'     : volume,
                    'issue'      : issue,
                    'pages'      : pages,
                    'affiliation': affil,
                    'keywords'   : keywords,
                    'abstract'   : abstract,
                    'language'   : language,
                    'doc_type'   : doc_type,
                })

        if not rows_out:
            logger.error("[MDPI] No email rows extracted after processing")
            return None

        result = pd.DataFrame(rows_out, columns=[
            'email', 'first_name', 'last_name', 'full_name',
            'title', 'doi', 'pub_url', 'pub_date',
            'journal', 'volume', 'issue', 'pages',
            'affiliation', 'keywords',
            'abstract', 'language', 'doc_type',
        ])

        csv_path = os.path.join(self.output_dir, f"mdpi_{slug}_authors_{ts}.csv")
        result.to_csv(csv_path, index=False, encoding='utf-8')
        logger.info("[MDPI] CSV written: %s  (%d unique emails, %d columns)",
                    csv_path, len(result), len(result.columns))
        return csv_path

    # ── Main entry point ─────────────────────────────────────────

    def run(self) -> tuple[Optional[str], dict]:
        self._progress(1, f"Starting MDPI scraper for '{self.keyword}'…")
        try:
            self._launch_chrome()
            self._progress(3, "Chrome launched")
            time.sleep(4)   # let UC Chrome fully initialise before any navigation

            self._login()

            self._progress(5, "Detecting total result pages…")
            total_pages = self._get_total_pages()
            self._progress(7, f"Found {total_pages} page(s) to download")

            downloaded = 0
            failed     = 0
            for i in range(total_pages):
                pct = 10 + int(70 * i / total_pages)
                self._progress(pct, f"Downloading page {i + 1}/{total_pages}…")
                ok = self._download_page(i, total_pages)
                if ok:
                    downloaded += 1
                else:
                    failed += 1

            self._progress(82, f"Pages downloaded: {downloaded}/{total_pages}"
                           + (f"  ({failed} failed)" if failed else ""))

            if downloaded == 0:
                self._progress(85, "All page downloads failed — no data collected")
                return None, {
                    'status': 'failed',
                    'message': 'All page downloads failed — no data collected',
                    'pages': total_pages, 'downloaded': 0, 'failed': failed,
                }

            self._progress(88, "Parsing downloaded files…")
            csv_path = self._build_csv()

            if csv_path:
                email_count = 0
                try:
                    email_count = len(pd.read_csv(csv_path))
                except Exception:
                    pass
                self._progress(100, f"Done — {email_count} unique emails saved.",
                               emails=email_count)
                return csv_path, {
                    'status': 'success', 'output_file': csv_path,
                    'pages': total_pages, 'downloaded': downloaded,
                    'failed': failed, 'emails': email_count,
                }
            else:
                self._progress(95, "Downloaded files parsed but no emails extracted.")
                return None, {
                    'status': 'partial',
                    'message': 'No emails extracted from downloaded files',
                    'pages': total_pages, 'downloaded': downloaded,
                }

        except Exception as exc:
            logger.error("[MDPI] Fatal error: %s", exc, exc_info=True)
            self._save_screenshot('fatal_error')
            raise

        finally:
            self._progress(99, "Closing Chrome session…")
            self._quit_chrome()
            # Flush and close the per-job file log handler
            try:
                if self._file_handler:
                    self._file_handler.flush()
                    self._file_handler.close()
                    logger.info("[MDPI] Debug log written → %s", self._log_path)
            except Exception:
                pass


# ── Standalone runner ────────────────────────────────────────────

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
    )

    keyword_input = input('Keyword:    ').strip()
    start_year    = input('Start year: ').strip()
    end_year      = input('End year:   ').strip()

    scraper = MDPIScraper(
        keyword=keyword_input,
        start_year=start_year,
        end_year=end_year,
    )
    output, summary = scraper.run()

    print("\n" + "=" * 60)
    print(f"Output : {output}")
    print(f"Summary: {summary.get('message') or summary}")
    print("=" * 60)
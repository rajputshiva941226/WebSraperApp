from chrome_display_mixin import ChromeDisplayMixin
# Fix for Python 3.12+ distutils compatibility
try:
    import setuptools
    import sys as _sys
    if _sys.version_info >= (3, 12):
        import importlib.util
        spec = importlib.util.find_spec('setuptools._distutils')
        if spec:
            _sys.modules['distutils'] = importlib.import_module('setuptools._distutils')
except ImportError:
    pass

import os, csv, logging, time, math, sys, tempfile
from typing import Optional, Callable
from urllib.parse import urlencode

from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc


class SageScraper(ChromeDisplayMixin):
    """
    Sage Journals scraper — Celery-compatible.

    Key design decisions vs the original:
    ───────────────────────────────────────
    • __init__ only sets up the logger and Chrome driver — it does NOT call run().
      SeleniumScraperWrapper calls run() explicitly after instantiation.

    • Chrome runs in NON-HEADLESS mode using a Xvfb virtual display
      (pyvirtualdisplay).  Sage aggressively blocks headless Chrome.
      Xvfb provides a real off-screen X11 display that Chrome is happy with.

    • output_dir  : directory for all CSV output (injected by Celery adapter).
    • progress_callback : callable(pct, msg, **kwargs) for live UI updates.

    • Logger is set up FIRST so any Chrome init crash is captured in the log file.

    • Per-article error handling — a single failing article never exits the loop.
    • Driver liveness check + reinit on consecutive failures.
    """

    def __init__(
        self,
        keyword:           str,
        start_year:        str,
        end_year:          str,
        driver_path:       str,
        output_dir:        Optional[str]      = None,
        progress_callback: Optional[Callable] = None,
    ):
        self._vdisplay = None
        self.driver = None
        self.keyword           = keyword
        self.start_year        = start_year
        self.end_year          = end_year
        self.driver_path       = driver_path
        self.output_dir        = output_dir
        self.progress_callback = progress_callback

        # Safe name for files / log
        self.directory = keyword.replace(" ", "-")
        safe_sd = start_year.replace("/", "-")
        safe_ed = end_year.replace("/", "-")
        self.url_csv     = f"Sage_{self.directory}-{safe_sd}-{safe_ed}_urls.csv"
        self.authors_csv = f"Sage_{self.directory}-{safe_sd}-{safe_ed}_authors.csv"

        self._display = None   # pyvirtualdisplay handle
        self.driver   = None

        # ── Logger MUST come before uc.Chrome() so init errors are captured ──
        self._setup_logger()
        # NOTE: Do NOT call _start_virtual_display() here.
        # The ChromeDisplayMixin._launch_chrome() handles display selection:
        #   • If DISPLAY=:99 is set (via Celery systemd env), Chrome goes there directly.
        #   • If DISPLAY is unset, mixin defaults to :99 (our persistent Xvfb).
        # This guarantees x11vnc always sees Chrome since x11vnc watches :99.
        self._init_driver()
        # NOTE: run() is NOT called here — SeleniumScraperWrapper calls it.

    # ─────────────────────────────────────────────────────────────────────
    # Logger
    # ─────────────────────────────────────────────────────────────────────

    def _setup_logger(self):
        """File + stdout logger, UTF-8 safe. Called before Chrome init."""
        self.logger = logging.getLogger(f"Sage-{id(self)}")
        self.logger.setLevel(logging.INFO)

        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(
            log_dir,
            f"SageScraper-{self.directory}-"
            f"{self.start_year.replace('/', '-')}-{self.end_year.replace('/', '-')}.log"
        )

        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        try:
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setLevel(logging.INFO)
            fh.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            self.logger.addHandler(fh)
        except Exception as e:
            print(f"[Sage] Could not create log file {log_file}: {e}")

        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(logging.INFO)
        sh.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        self.logger.addHandler(sh)
        self.logger.info(f"Sage ==> Logger initialised → {log_file}")

    # ─────────────────────────────────────────────────────────────────────
    # Virtual display (Xvfb) — required for non-headless Chrome on EC2
    # ─────────────────────────────────────────────────────────────────────

    def _start_virtual_display(self):
        """
        DEPRECATED — no longer called from __init__.
        ChromeDisplayMixin handles display selection and always uses :99.
        Kept only for backwards compatibility if called externally.
        """
        # If :99 is already running (persistent systemd service), reuse it
        if os.path.exists('/tmp/.X99-lock'):
            os.environ['DISPLAY'] = ':99'
            self.logger.info("Sage ==> Reusing persistent Xvfb on :99")
            return

        # Start Xvfb on :99 specifically — never use a random display number
        try:
            from pyvirtualdisplay import Display
            self._display = Display(
                visible=False, size=(1920, 1080), backend='xvfb',
                display=99,    # ← ALWAYS :99, never random
            )
            self._display.start()
            os.environ['DISPLAY'] = ':99'
            self.logger.info("Sage ==> Virtual display started on :99 via pyvirtualdisplay")
            return
        except ImportError:
            self.logger.warning("Sage ==> pyvirtualdisplay not installed — using raw Xvfb on :99")
        except Exception as e:
            self.logger.warning(f"Sage ==> pyvirtualdisplay failed: {e} — trying raw Xvfb")

        # Fallback: raw Xvfb on :99
        try:
            import subprocess
            subprocess.run(["pkill", "-f", "Xvfb :99"], capture_output=True)
            time.sleep(0.5)
            self._xvfb_proc = subprocess.Popen(
                ["Xvfb", ":99", "-screen", "0", "1920x1080x24", "-ac"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            os.environ["DISPLAY"] = ":99"
            time.sleep(1)
            self.logger.info("Sage ==> Raw Xvfb started on :99")
        except Exception as e:
            self.logger.error(f"Sage ==> Could not start Xvfb: {e}")

    def _stop_virtual_display(self):
        """
        Stop the virtual display IF we started it ourselves.
        Never kills the persistent :99 managed by systemd.
        """
        try:
            if self._display is not None:
                self._display.stop()
                self._display = None
                self.logger.info("Sage ==> pyvirtualdisplay stopped")
        except Exception:
            pass
        try:
            if hasattr(self, '_xvfb_proc') and self._xvfb_proc:
                self._xvfb_proc.terminate()
                self._xvfb_proc = None
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────
    # Chrome driver
    # ─────────────────────────────────────────────────────────────────────

    def _init_driver(self):
        """
        Start Chrome in NON-HEADLESS mode using the Xvfb virtual display.
        Sage blocks headless Chrome — the virtual display lets us use the
        real browser UI without a physical screen.
        """
        self.logger.info(f"Sage ==> Initialising Chrome (driver={self.driver_path})")
        options = Options()

        # ── NOT headless — Xvfb provides the display ──
        # Do NOT add --headless or --headless=new here.
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-crash-reporter")
        options.add_argument("--disable-logging")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--start-maximized")

        self.uc_temp_dir = tempfile.mkdtemp(prefix="Sage_")

        try:
            self._launch_chrome(self._build_default_chrome_options(), driver_path=self.driver_path)
            self.driver.set_page_load_timeout(120)
            self.driver.set_script_timeout(60)
            self.wait = WebDriverWait(self.driver, 30)

            time.sleep(2)
            _ = self.driver.current_url
            self.logger.info("Sage ==> Chrome initialised successfully (non-headless via Xvfb)")
        except Exception as exc:
            self.logger.exception(f"Sage ==> Chrome init FAILED: {exc}")
            raise

    def _is_driver_alive(self) -> bool:
        try:
            _ = self.driver.current_url
            return True
        except Exception:
            return False

    def _reinit_driver(self):
        """Kill the dead Chrome session and start a fresh one."""
        self.logger.warning("Sage ==> Reinitialising Chrome after session failure...")
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass
        self.driver = None
        time.sleep(3)
        self._init_driver()
        self.logger.info("Sage ==> Chrome reinitialised")

    # ─────────────────────────────────────────────────────────────────────
    # Progress helper
    # ─────────────────────────────────────────────────────────────────────

    def _progress(self, pct: int, msg: str, **kwargs):
        self.logger.info(f"Sage ==> [{pct}%] {msg}")
        if self.progress_callback:
            try:
                self.progress_callback(pct, msg, **kwargs)
            except KeyboardInterrupt:
                raise
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────
    # CSV helpers
    # ─────────────────────────────────────────────────────────────────────

    def _work_dir(self) -> str:
        """Return the directory where output CSVs are written."""
        d = self.output_dir if self.output_dir else self.directory
        os.makedirs(d, exist_ok=True)
        return d

    def save_to_csv(self, data, filename, header=None):
        """Append rows to a CSV inside the work directory."""
        try:
            work_dir = self._work_dir()
            filepath = os.path.join(work_dir, filename)
            with open(filepath, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if os.path.getsize(filepath) == 0 and header:
                    writer.writerow(header)
                writer.writerows(data)
            self.logger.debug(f"Sage ==> Saved {len(data)} rows → {filepath}")
        except Exception as e:
            self.logger.error(f"Sage ==> Failed to save CSV: {e}")

    def _init_csv(self, filename, header):
        """Create the CSV file with a header row (truncates if exists)."""
        work_dir = self._work_dir()
        filepath = os.path.join(work_dir, filename)
        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)
        self.logger.info(f"Sage ==> Initialised {filepath}")
        return filepath

    # ─────────────────────────────────────────────────────────────────────
    # Cookie / page helpers
    # ─────────────────────────────────────────────────────────────────────

    def _bypass_cloudflare(self, timeout: int = 90) -> bool:
        """
        Bypass Cloudflare Turnstile using ActionChains + JS click on the checkbox.

        The checkbox IS visible in the browser (confirmed in VNC screenshots).
        Problem was our click wasn't reaching it. Solution:

        1. Switch into each iframe one level at a time (not recursive — Selenium
           loses frame context on switch_to.default_content inside recursion)
        2. Use ActionChains.move_to_element().click() — this sends real
           synthetic mouse events through ChromeDriver, not JS dispatchEvent
        3. JS click as fallback if ActionChains fails
        4. Human activity (mousemove + scroll) every 2s to keep managed
           challenge alive while waiting for auto-verification
        """
        import random
        from selenium.webdriver.common.action_chains import ActionChains

        CHALLENGE_PHRASES = [
            "just a moment", "verifying you are human",
            "performing security verification", "checking your browser",
            "cf-browser-verification",
        ]
        tag = "Sage ==>"

        CF_SELECTORS = [
            "input[type='checkbox']",
            "div.ctp-checkbox-label",
            ".mark", "span.mark",
            "label[for='cf-stage']",
            "div[id*='challenge']",
            "div[class*='checkbox']",
        ]

        def _on_challenge():
            try:
                t = self.driver.title.lower()
                s = self.driver.page_source.lower()[:800]
                return any(p in t or p in s for p in CHALLENGE_PHRASES)
            except Exception:
                return False

        def _wait_ready(sec=10):
            end = time.time() + sec
            while time.time() < end:
                try:
                    if self.driver.execute_script("return document.readyState") == "complete":
                        return
                except Exception:
                    pass
                time.sleep(0.5)

        def _human_activity():
            """Fire random JS mouse events to satisfy managed-challenge fingerprint."""
            try:
                self.driver.execute_script("""
                    (function(){
                        var x=300+Math.floor(Math.random()*500);
                        var y=200+Math.floor(Math.random()*350);
                        document.dispatchEvent(new MouseEvent('mousemove',
                            {bubbles:true,cancelable:true,clientX:x,clientY:y}));
                        window.scrollBy(0, Math.floor(Math.random()*40+5));
                        setTimeout(function(){ window.scrollBy(0, -20); }, 300);
                    })();
                """)
            except Exception:
                pass

        def _action_click(el):
            """Click using ActionChains — sends real ChromeDriver mouse events."""
            try:
                ActionChains(self.driver).move_to_element(el).pause(
                    random.uniform(0.3, 0.8)
                ).click().perform()
                return True
            except Exception:
                return False

        def _js_click(el):
            """JS dispatchEvent fallback."""
            try:
                self.driver.execute_script("""
                    var el=arguments[0], r=el.getBoundingClientRect();
                    var cx=r.left+r.width/2+(Math.random()-0.5)*3;
                    var cy=r.top+r.height/2+(Math.random()-0.5)*3;
                    ['mousedown','mouseup','click'].forEach(function(t){
                        el.dispatchEvent(new MouseEvent(t,{
                            bubbles:true,cancelable:true,
                            clientX:cx,clientY:cy,view:window
                        }));
                    });
                """, el)
                return True
            except Exception:
                return False

        def _click_element(el, label):
            """Try ActionChains first, fall back to JS click."""
            time.sleep(random.uniform(0.4, 0.9))
            if _action_click(el):
                self.logger.info(f"{tag} ActionChains clicked: {label}")
                return True
            if _js_click(el):
                self.logger.info(f"{tag} JS clicked: {label}")
                return True
            return False

        def _try_in_frame(level=0):
            """
            Try clicking checkbox in current frame context, then walk child iframes.
            Returns True if a click was fired.
            IMPORTANT: always call switch_to.default_content() in the main loop
            before calling this — frame context must be clean.
            """
            # Try selectors in current frame
            for sel in CF_SELECTORS:
                try:
                    for el in self.driver.find_elements(By.CSS_SELECTOR, sel):
                        if el.is_displayed():
                            if _click_element(el, f"depth{level}:{sel}"):
                                return True
                except Exception:
                    pass

            if level >= 3:
                return False

            # Walk child iframes
            try:
                frames = self.driver.find_elements(By.TAG_NAME, "iframe")
                self.logger.info(f"{tag} Found {len(frames)} iframes at depth {level}")
                for idx, frame in enumerate(frames):
                    try:
                        self.driver.switch_to.frame(frame)
                        time.sleep(0.6)
                        src = ""
                        try:
                            src = self.driver.execute_script("return window.location.href") or ""
                        except Exception:
                            pass
                        self.logger.info(f"{tag} Entered iframe {idx} depth={level+1} src={src[:60]}")
                        if _try_in_frame(level + 1):
                            return True
                        self.driver.switch_to.parent_frame()
                        time.sleep(0.3)
                    except Exception as e:
                        self.logger.debug(f"{tag} Frame {idx} error: {e}")
                        try:
                            self.driver.switch_to.default_content()
                        except Exception:
                            pass
            except Exception:
                pass
            return False

        # ── Initial wait ─────────────────────────────────────────────────────
        _wait_ready()
        time.sleep(2)

        if not _on_challenge():
            self.logger.info(f"{tag} No Cloudflare challenge — page ready ✓")
            return True

        self.logger.info(f"{tag} Cloudflare detected — ActionChains+JS bypass starting...")
        deadline = time.time() + timeout
        last_click = 0
        attempt = 0

        while time.time() < deadline:
            _wait_ready(sec=5)

            if not _on_challenge():
                self.logger.info(f"{tag} Cloudflare cleared ✓")
                return True

            # Always keep human activity going
            _human_activity()

            # Every 5s: attempt to click the checkbox
            if time.time() - last_click > 5:
                last_click = time.time()
                attempt += 1
                self.logger.info(f"{tag} Click attempt #{attempt}...")
                try:
                    self.driver.switch_to.default_content()
                except Exception:
                    pass
                try:
                    clicked = _try_in_frame()
                except Exception as e:
                    self.logger.debug(f"{tag} Click attempt error: {e}")
                    clicked = False
                finally:
                    try:
                        self.driver.switch_to.default_content()
                    except Exception:
                        pass
                if clicked:
                    self.logger.info(f"{tag} Clicked! Waiting 4s for resolution...")
                    time.sleep(4)
                    if not _on_challenge():
                        self.logger.info(f"{tag} Cloudflare cleared after click ✓")
                        return True

            remaining = int(deadline - time.time())
            self.logger.info(f"{tag} Cloudflare active — human-sim ({remaining}s left)...")
            time.sleep(2)

        self.logger.warning(f"{tag} Cloudflare bypass timed out after {timeout}s")
        try:
            os.makedirs("logs", exist_ok=True)
            self.driver.save_screenshot("logs/sage_debug_cloudflare_timeout.png")
        except Exception:
            pass
        return False


    def _accept_cookies(self):
        """Accept OneTrust cookie banner if present."""
        selectors = [
            "#onetrust-accept-btn-handler",
            "button#onetrust-accept-btn-handler",
            "button.onetrust-close-btn-handler",
        ]
        for sel in selectors:
            try:
                btn = WebDriverWait(self.driver, 8).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                )
                btn.click()
                self.logger.info(f"Sage ==> Cookie banner accepted ({sel})")
                time.sleep(1)
                return
            except Exception:
                continue
        self.logger.info("Sage ==> No cookie banner found (or already dismissed)")

    # ─────────────────────────────────────────────────────────────────────
    # Phase 1 — collect article URLs
    # ─────────────────────────────────────────────────────────────────────

    def _debug_screenshot(self, label: str):
        """Save a screenshot to help diagnose page-loading issues."""
        try:
            screenshot_dir = "logs"
            os.makedirs(screenshot_dir, exist_ok=True)
            path = os.path.join(screenshot_dir, f"sage_debug_{label}.png")
            self.driver.save_screenshot(path)
            self.logger.info(f"Sage ==> Debug screenshot saved → {path}")
        except Exception as e:
            self.logger.warning(f"Sage ==> Could not save screenshot: {e}")

    def _wait_for_results_page(self, timeout: int = 45):
        """
        Wait for the Sage results page to fully load.
        Detects CAPTCHA / bot-detection pages and logs a clear warning.
        """
        import time as _time
        deadline = _time.monotonic() + timeout

        while _time.monotonic() < deadline:
            try:
                title = self.driver.title.lower()
                url   = self.driver.current_url.lower()

                # Detected bot-challenge pages — wait for them to pass, don't abort
                if any(kw in title for kw in ["captcha", "access denied", "blocked", "robot"]):
                    self.logger.error(
                        f"Sage ==> Hard bot block detected: title='{self.driver.title}'"
                    )
                    self._debug_screenshot("captcha")
                    return False

                # Cloudflare auto-challenge — keep waiting, don't abort
                if any(kw in title for kw in ["just a moment", "verifying", "security verification"]):
                    self.logger.info("Sage ==> Cloudflare challenge in progress — waiting...")
                    _time.sleep(2)
                    continue

                # Check if results count element exists
                try:
                    el = self.driver.find_element(By.CSS_SELECTOR, "span.result__count")
                    if el and el.text.strip():
                        return True
                except Exception:
                    pass

                # Try alternative selectors
                for sel in [
                    "span.result__count",
                    "div[class*='result-count']",
                    "span[class*='result-count']",
                    "div[class*='results-count']",
                    "[data-test='results-count']",
                ]:
                    try:
                        el = self.driver.find_element(By.CSS_SELECTOR, sel)
                        if el and el.text.strip():
                            return True
                    except Exception:
                        pass

                _time.sleep(1)
            except Exception:
                _time.sleep(1)

        return False

    def get_total_pages(self) -> int:
        """
        Get total result count with multi-selector fallback.
        Saves a debug screenshot if nothing is found so you can see
        exactly what Sage returned.
        """
        # All known selectors for Sage result count across layout versions
        COUNT_SELECTORS = [
            ("span.result__count",              lambda t: t.split()[-1]),
            ("div[class*='result-count']",      lambda t: t.strip().split()[-1]),
            ("span[class*='result-count']",     lambda t: t.strip().split()[-1]),
            ("div[class*='results-count']",     lambda t: t.strip().split()[-1]),
            ("[data-test='results-count']",     lambda t: t.strip().split()[-1]),
            ("p.results-desc",                  lambda t: t.strip().split()[0]),
        ]

        for selector, extractor in COUNT_SELECTORS:
            try:
                el = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                raw_text = el.text.strip()
                if not raw_text:
                    continue
                num_str = extractor(raw_text).replace(",", "").replace(".", "")
                total_results = int(num_str)
                total_pages   = math.ceil(total_results / 100)
                self.logger.info(
                    f"Sage ==> [{selector}] Total results: {total_results}, "
                    f"pages: {total_pages}"
                )
                return total_pages
            except Exception:
                continue

        # Nothing found — save debug screenshot + page source snippet
        self.logger.error(
            "Sage ==> Could not find result count with any known selector. "
            f"Current URL: {self.driver.current_url}"
        )
        self._debug_screenshot("no_results")
        try:
            # Log first 2000 chars of page source for debugging
            src = self.driver.page_source[:2000]
            self.logger.error("Sage ==> Page source snippet:\n" + src)
        except Exception:
            pass
        return 0

    def extract_article_links(self, total_pages: int, base_url: str, query_params: dict):
        """
        Walk result pages and save article URLs to CSV.
        Progress: 5 → 40%.
        """
        total_saved = 0
        for page in range(total_pages):
            if not self._is_driver_alive():
                self.logger.warning("Sage ==> Driver dead during URL extraction — reinitialising")
                self._reinit_driver()

            query_params["startPage"] = page
            page_url = f"{base_url}?{urlencode(query_params)}"

            try:
                self.driver.get(page_url)
                time.sleep(2)

                links = self.wait.until(
                    EC.presence_of_all_elements_located(
                        (By.CSS_SELECTOR,
                         'div.issue-item__title > a[data-id="srp-article-title"]')
                    )
                )
                page_links = [
                    [lnk.get_attribute("href")]
                    for lnk in links
                    if lnk.get_attribute("href")
                ]
                self.save_to_csv(page_links, self.url_csv, header=["Article_URL"])
                total_saved += len(page_links)
                self.logger.info(
                    f"Sage ==> Page {page + 1}/{total_pages}: "
                    f"{len(page_links)} links (total: {total_saved})"
                )
            except Exception as e:
                self.logger.error(f"Sage ==> Error on page {page + 1}: {e}")

            pct = int(5 + ((page + 1) / total_pages) * 35)   # 5 → 40%
            self._progress(
                pct,
                f"URL collection: page {page + 1}/{total_pages} ({total_saved} URLs)",
            )

    # ─────────────────────────────────────────────────────────────────────
    # Phase 2 — extract author emails from each article
    # ─────────────────────────────────────────────────────────────────────

    def extract_author_info(self):
        """
        Read URLs from CSV and scrape author name + email for each article.
        Progress: 40 → 95%.
        Per-article errors are caught individually — loop never exits early.
        Driver liveness checked before every article; reinit on 3 consecutive fails.
        """
        filepath = os.path.join(self._work_dir(), self.url_csv)
        if not os.path.exists(filepath):
            self.logger.error("Sage ==> URL file not found — run Phase 1 first.")
            return

        try:
            with open(filepath, mode="r", encoding="utf-8") as f:
                urls = [row[0].strip() for row in csv.reader(f) if row and row[0].strip()]
            urls = urls[1:] if urls and urls[0].lower() == "article_url" else urls  # skip header
        except Exception as e:
            self.logger.error(f"Sage ==> Cannot read URL file: {e}")
            return

        total = len(urls)
        self.logger.info(f"Sage ==> Processing {total} articles")

        consecutive_failures = 0
        MAX_CONSECUTIVE = 3

        for idx, article_url in enumerate(urls, 1):
            # Driver liveness check
            if not self._is_driver_alive():
                self.logger.warning("Sage ==> Driver dead — reinitialising...")
                try:
                    self._reinit_driver()
                    consecutive_failures = 0
                except Exception as e:
                    self.logger.error(f"Sage ==> Driver reinit failed: {e} — stopping")
                    break

            try:
                self._scrape_article(article_url)
                consecutive_failures = 0
            except KeyboardInterrupt:
                raise
            except Exception as e:
                self.logger.error(f"Sage ==> Article {idx}/{total} failed: {e}")
                consecutive_failures += 1
                self.save_to_csv(
                    [[article_url, "N/A", "N/A"]], self.authors_csv,
                    header=["Article_URL", "Author_Name", "Email"]
                )
                if consecutive_failures >= MAX_CONSECUTIVE:
                    self.logger.warning(
                        f"Sage ==> {consecutive_failures} consecutive failures — reinitialising driver"
                    )
                    try:
                        self._reinit_driver()
                        consecutive_failures = 0
                    except Exception as reinit_err:
                        self.logger.error(f"Sage ==> Reinit failed: {reinit_err} — stopping")
                        break
                continue

            pct = int(40 + (idx / total) * 55)   # 40 → 95%
            self._progress(
                pct,
                f"Author extraction: {idx}/{total}",
                current_url=article_url,
            )

    def _scrape_article(self, article_url: str):
        """
        Scrape one article page — expand the author list and collect emails.
        Raises on WebDriver errors so the caller can trigger driver recovery.
        """
        self.logger.info(f"Sage ==> Scraping: {article_url}")
        self.driver.get(article_url)
        time.sleep(2)

        # ── Open the author / affiliations section ────────────────────────
        try:
            author_section = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a.to-authors-affiliations"))
            )
            author_section.click()
            time.sleep(1)
        except Exception:
            self.logger.warning(f"Sage ==> No author section tab on {article_url}")
            return

        # ── Click "Show all" if present ────────────────────────────────────
        try:
            show_all = WebDriverWait(self.driver, 8).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR,
                     'div.expand-all-wrapper > button[data-label-expand="Show all"]')
                )
            )
            self.driver.execute_script("arguments[0].scrollIntoView();", show_all)
            time.sleep(0.5)
            try:
                show_all.click()
            except Exception:
                self.driver.execute_script("arguments[0].click();", show_all)
            time.sleep(2)
            self.logger.info("Sage ==> 'Show all' clicked")
        except Exception:
            self.logger.info("Sage ==> No 'Show all' button (all authors already visible)")

        # ── Collect author info ────────────────────────────────────────────
        authors = self.driver.find_elements(
            By.CSS_SELECTOR, "section.core-authors div[property='author']"
        )

        found_any = False
        for author in authors:
            try:
                given  = author.find_element(
                    By.CSS_SELECTOR, "span[property='givenName']"
                ).text.strip()
                family = author.find_element(
                    By.CSS_SELECTOR, "span[property='familyName']"
                ).text.strip()
                full_name = f"{given} {family}".strip()
            except Exception:
                full_name = "N/A"

            email = None
            try:
                email_el = author.find_element(
                    By.CSS_SELECTOR, "div.core-email > a[property='email']"
                )
                email = email_el.get_attribute("href").replace("mailto:", "").strip()
            except Exception:
                pass

            if email:
                self.save_to_csv(
                    [[article_url, full_name, email]], self.authors_csv,
                    header=["Article_URL", "Author_Name", "Email"]
                )
                self.logger.info(f"Sage ==> ✅ {full_name}: {email}")
                found_any = True

        if not found_any:
            self.logger.info(f"Sage ==> No emails found on {article_url}")

    # ─────────────────────────────────────────────────────────────────────
    # Main entry point — called by SeleniumScraperWrapper
    # ─────────────────────────────────────────────────────────────────────

    def run(self):
        """
        Execute full scrape: Phase 1 (URL collection) → Phase 2 (email extraction).
        Returns (output_file_path, summary_string).
        """
        authors_path = os.path.join(self._work_dir(), self.authors_csv)

        try:
            start_parts  = self.start_year.split("/")
            end_parts    = self.end_year.split("/")
            after_month  = start_parts[0]
            after_year   = start_parts[-1]
            before_month = end_parts[0]
            before_year  = end_parts[-1]

            query_params = {
                "field1":      "AllField",
                "text1":       self.keyword,
                "AfterMonth":  after_month,
                "AfterYear":   after_year,
                "BeforeMonth": before_month,
                "BeforeYear":  before_year,
                "pageSize":    100,
                "startPage":   0,
            }
            base_url   = "https://journals.sagepub.com/action/doSearch"
            search_url = f"{base_url}?{urlencode(query_params)}"
            self.logger.info(
                f"Sage ==> Search params: keyword={self.keyword}, "
                f"dates={after_month}/{after_year} → {before_month}/{before_year}"
            )

            self._init_csv(self.url_csv,     ["Article_URL"])
            self._init_csv(self.authors_csv, ["Article_URL", "Author_Name", "Email"])

            # ── Step 1: homepage — bypass Cloudflare with JS clicks ──────────
            self._progress(2, "Opening Sage Journals homepage...")
            self.logger.info("Sage ==> Loading homepage...")
            self.driver.get("https://journals.sagepub.com")
            self._bypass_cloudflare(timeout=60)

            # Accept cookie banner after challenge clears
            try:
                cookie_btn = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
                )
                time.sleep(1)
                self.driver.execute_script("arguments[0].click();", cookie_btn)
                self.logger.info("Sage ==> Cookie banner accepted (JS click)")
                time.sleep(2)
            except Exception:
                self.logger.info("Sage ==> No cookie banner found")

            # ── Step 2: Navigate to search URL via JS (keeps trusted session) ──
            # driver.get() on the search URL triggers Cloudflare's managed challenge
            # because it starts a fresh navigation from an EC2 IP.
            # window.location.href from within the already-verified homepage session
            # inherits the trust token Cloudflare issued for this session.
            self._progress(5, "PHASE 1: Collecting article URLs...")
            self.logger.info(f"Sage ==> Navigating to search via JS: {search_url[:80]}...")
            self.driver.execute_script(f"window.location.href = '{search_url}';")
            time.sleep(8)   # wait for page to load after JS navigation
            self._bypass_cloudflare(timeout=60)

            total_pages = self.get_total_pages()
            if total_pages == 0:
                self.logger.warning("Sage ==> No results found — aborting.")
                return authors_path, "No results found"

            self.extract_article_links(total_pages, base_url, query_params)

            self._progress(40, "PHASE 2: Extracting author emails...")
            self.extract_author_info()

            self._progress(100, "Sage scraping completed.")
            self.logger.info("Sage ==> Scraping complete.")
            return authors_path, f"Sage scrape complete: {total_pages} pages"

        finally:
            self._quit_chrome()
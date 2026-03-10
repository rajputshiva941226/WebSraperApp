"""
Oxford Academic Scraper
- Non-headless Chrome (Xvfb virtual display on EC2/Linux servers)
- Xvfb fallback when GNOME3/DISPLAY:0 is not accessible via SSH
- Cookie-based captcha bypass for academic.oup.com
- Graceful Chrome session cleanup on finish or error
"""

try:
    import setuptools, sys
    if sys.version_info >= (3, 12):
        import importlib.util
        spec = importlib.util.find_spec('setuptools._distutils')
        if spec:
            sys.modules['distutils'] = importlib.import_module('setuptools._distutils')
except ImportError:
    pass

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import os, time, sys, platform, json, subprocess, csv, math, logging
from urllib.parse import urlencode, urljoin
from fuzzywuzzy import fuzz, process
import undetected_chromedriver as uc

_OXFORD_COOKIE_FILE = os.path.expanduser("~/.oxford_scraper_cookies.json")


class OxfordScraper:
    def __init__(self, keyword, start_year, end_year, driver_path=None,
                 output_dir=None, progress_callback=None):
        self.keyword     = keyword
        self.start_year  = start_year
        self.end_year    = end_year
        self.driver_path = driver_path
        self.output_dir  = output_dir or os.getcwd()
        self._vdisplay   = None
        self.driver      = None
        self.directory   = keyword.replace(" ", "-")
        self._setup_logger()
        self._launch_chrome()
        self.wait = WebDriverWait(self.driver, 20)
        try:
            self.run()
        finally:
            self._quit()

    # ── Logging ──────────────────────────────────────────────────────────────

    def _setup_logger(self):
        self.logger = logging.getLogger(f"Oxford.{self.keyword[:20]}")
        self.logger.setLevel(logging.INFO)
        if self.logger.hasHandlers():
            self.logger.handlers.clear()
        fmt = logging.Formatter('%(asctime)s  %(levelname)-8s %(message)s',
                                datefmt='%Y-%m-%d %H:%M:%S')
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        self.logger.addHandler(sh)

    # ── Virtual display (Xvfb) ───────────────────────────────────────────────

    def _start_virtual_display(self):
        try:
            from pyvirtualdisplay import Display
            self._vdisplay = Display(visible=False, size=(1400, 900), backend='xvfb')
            self._vdisplay.start()
            disp = f":{self._vdisplay.display}"
            self.logger.info("[Oxford] pyvirtualdisplay on %s", disp)
            return disp
        except ImportError:
            self.logger.info("[Oxford] pyvirtualdisplay not installed — using Xvfb directly")
            subprocess.run(['pkill', '-f', 'Xvfb :99'], capture_output=True)
            time.sleep(0.5)
            proc = subprocess.Popen(
                ['Xvfb', ':99', '-screen', '0', '1400x900x24', '-ac'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._vdisplay = proc
            time.sleep(1.5)
            self.logger.info("[Oxford] Xvfb PID=%d on :99", proc.pid)
            return ':99'

    def _stop_virtual_display(self):
        if self._vdisplay is None:
            return
        try:
            if hasattr(self._vdisplay, 'stop'):
                self._vdisplay.stop()
            elif hasattr(self._vdisplay, 'terminate'):
                self._vdisplay.terminate()
        except Exception:
            pass
        finally:
            self._vdisplay = None
        self.logger.info("[Oxford] Virtual display stopped")

    # ── Chrome launch ─────────────────────────────────────────────────────────

    def _build_chrome_options(self):
        opts = uc.ChromeOptions()
        # NO --headless: Oxford captcha blocks headless TLS fingerprint
        for arg in [
            "--disable-gpu", "--no-sandbox", "--window-size=1400,900",
            "--disable-notifications", "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding", "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled", "--start-maximized",
        ]:
            opts.add_argument(arg)
        return opts

    def _try_launch_chrome(self):
        opts   = self._build_chrome_options()
        kwargs = dict(options=opts, use_subprocess=False)
        if self.driver_path:
            kwargs['driver_executable_path'] = self.driver_path
        self.logger.info("[Oxford] uc.Chrome() DISPLAY=%s", os.environ.get('DISPLAY'))
        self.driver = uc.Chrome(**kwargs)
        self.logger.info("[Oxford] Chrome launched OK")

    def _launch_chrome(self):
        if platform.system() == 'Windows':
            self._try_launch_chrome()
            return

        if not os.environ.get('DISPLAY'):
            os.environ['DISPLAY'] = ':0'
        uid_str = str(os.getuid()) if hasattr(os, 'getuid') else '1000'
        xauth   = os.environ.get('XAUTHORITY', '')
        if not xauth or not os.path.exists(xauth):
            for c in [f"/run/user/{uid_str}/gdm/Xauthority",
                      os.path.expanduser("~/.Xauthority"),
                      "/home/ubuntu/.Xauthority", "/root/.Xauthority"]:
                if os.path.exists(c) and os.access(c, os.R_OK):
                    os.environ['XAUTHORITY'] = c
                    self.logger.info("[Oxford] XAUTHORITY -> %s", c)
                    break

        try:
            self._try_launch_chrome()
            return
        except Exception as e1:
            self.logger.warning("[Oxford] Chrome failed on :0 (%s) -> trying Xvfb",
                                type(e1).__name__)

        xvfb = self._start_virtual_display()
        os.environ['DISPLAY'] = xvfb
        os.environ.pop('XAUTHORITY', None)
        try:
            self._try_launch_chrome()
            self.logger.info("[Oxford] Chrome on Xvfb %s OK", xvfb)
        except Exception as e2:
            self.logger.error("[Oxford] Chrome also failed on Xvfb: %s\n"
                              "  Install: sudo apt install xvfb && pip install pyvirtualdisplay", e2)
            raise

    def _quit(self):
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("[Oxford] Chrome session closed")
            except Exception:
                pass
            finally:
                self.driver = None
        self._stop_virtual_display()

    # ── Cookie handling ───────────────────────────────────────────────────────

    def _save_cookies(self):
        try:
            cookies = self.driver.get_cookies()
            with open(_OXFORD_COOKIE_FILE, 'w') as f:
                json.dump(cookies, f)
            self.logger.info("[Oxford] Cookies saved")
        except Exception as e:
            self.logger.warning("[Oxford] Could not save cookies: %s", e)

    def _load_cookies(self):
        if not os.path.exists(_OXFORD_COOKIE_FILE):
            return False
        try:
            with open(_OXFORD_COOKIE_FILE) as f:
                cookies = json.load(f)
            self.driver.get("https://academic.oup.com/")
            time.sleep(2)
            for cookie in cookies:
                cookie.pop('sameSite', None)
                try:
                    self.driver.add_cookie(cookie)
                except Exception:
                    pass
            self.driver.refresh()
            time.sleep(2)
            self.logger.info("[Oxford] Cookies loaded")
            return True
        except Exception as e:
            self.logger.warning("[Oxford] Could not load cookies: %s", e)
            return False

    # ── Captcha handling ──────────────────────────────────────────────────────

    def detect_and_handle_captcha(self):
        """
        Oxford 'crawlprevention/governor' soft-block handler.
        Waits up to 60s for auto-resolution, then tries a cookie reload.
        Saves cookies after passing so future sessions are faster.
        """
        if 'crawlprevention' not in self.driver.current_url.lower():
            return

        self.logger.warning("[Oxford] Crawler-prevention page detected: %s",
                            self.driver.current_url)
        self.logger.info("[Oxford] Waiting up to 60s for block to clear...")

        for i in range(60):
            time.sleep(1)
            if 'crawlprevention' not in self.driver.current_url.lower():
                self.logger.info("[Oxford] Block cleared after %ds", i + 1)
                self._save_cookies()
                return

        self.logger.warning("[Oxford] Still blocked after 60s — reloading cookies")
        self._load_cookies()
        time.sleep(3)

        if 'crawlprevention' in self.driver.current_url.lower():
            self.logger.error(
                "[Oxford] Captcha still present. Scraper will continue but results may be limited.\n"
                "  Tip: wait a few minutes and retry, or clear %s", _OXFORD_COOKIE_FILE)

    def accept_cookies(self):
        for selector in [
            "button#onetrust-accept-btn-handler",
            "button[id='onetrust-accept-btn-handler']",
            "div#onetrust-button-group button:nth-child(2)",
        ]:
            try:
                btn = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
                btn.click()
                self.logger.info("[Oxford] Cookie banner accepted")
                time.sleep(1)
                self._save_cookies()
                return
            except Exception:
                continue

    # ── Scraping helpers ──────────────────────────────────────────────────────

    def get_total_pages(self):
        try:
            stats = self.wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div.sr-statistics.at-sr-statistics")))
            total = int(stats.text.split()[2].replace(",", ""))
            pages = math.ceil(total / 20)
            self.logger.info("[Oxford] %d results -> %d pages", total, pages)
            return pages
        except Exception as e:
            self.logger.error("[Oxford] get_total_pages error: %s", e)
            return 0

    def extract_links(self):
        links = []
        try:
            articles = self.wait.until(EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, "div.sr-list.al-article-box.al-normal.clearfix")))
            for article in articles:
                try:
                    el = article.find_element(
                        By.CSS_SELECTOR, "a.article-link.at-sr-article-title-link")
                    links.append(el.get_attribute("href"))
                except Exception:
                    pass
            self.logger.info("[Oxford] Extracted %d links", len(links))
        except Exception as e:
            self.logger.error("[Oxford] extract_links error: %s", e)
        return links

    def get_next_url(self):
        try:
            nxt    = self.driver.find_element(By.CSS_SELECTOR, "a.sr-nav-next.al-nav-next")
            params = nxt.get_attribute("data-url")
            base   = self.driver.current_url.split("?")[0]
            return urljoin(base, "?" + params)
        except Exception:
            return None

    def save_to_csv(self, data, directory, filename, header=None):
        try:
            os.makedirs(directory, exist_ok=True)
            filepath = os.path.join(directory, filename)
            with open(filepath, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if os.path.getsize(filepath) == 0 and header:
                    writer.writerow(header)
                writer.writerows(data)
        except Exception as e:
            self.logger.error("[Oxford] save_to_csv error: %s", e)

    def scrape_author_emails(self, input_csv, output_csv):
        try:
            with open(input_csv, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader)
                urls = [row[0] for row in reader]
        except Exception as e:
            self.logger.error("[Oxford] Cannot read input CSV: %s", e)
            return

        for url in urls:
            self.driver.get(url)
            self.detect_and_handle_captcha()
            if not self.driver.current_url.startswith("https://academic.oup.com/"):
                continue
            try:
                self.accept_cookies()
            except Exception:
                pass

            author_names = []
            try:
                try:
                    show_more = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "a#show-meta-authors")))
                    show_more.click()
                except Exception:
                    pass

                for link in self.driver.find_elements(
                        By.CSS_SELECTOR,
                        "span.al-author-name-more a.js-linked-name-trigger"):
                    try:
                        author_name = link.text.strip()
                        author_names.append(author_name)
                        link.click()
                        popup = self.wait.until(EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "span.al-author-info-wrap.open")))
                        for el in popup.find_elements(By.CSS_SELECTOR, "a[href^='mailto']"):
                            email      = el.get_attribute("href").replace("mailto:", "")
                            best, score = process.extractOne(
                                email.split("@")[0], author_names, scorer=fuzz.ratio)
                            self.save_to_csv(
                                [[url, author_name, email, best, score]],
                                os.path.dirname(output_csv),
                                os.path.basename(output_csv),
                                header=["url", "author", "email", "best_match", "match_score"])
                    except Exception as e:
                        self.logger.warning("[Oxford] Author link error: %s", e)

                # Fallback: Author Notes footnotes
                try:
                    self.driver.find_element(
                        By.CSS_SELECTOR, "a.js-linked-footnotes").click()
                    for popup in WebDriverWait(self.driver, 5).until(
                            EC.presence_of_all_elements_located(
                                (By.CSS_SELECTOR, "p.footnote-compatibility"))):
                        for el in popup.find_elements(By.CSS_SELECTOR, "a[href^='mailto']"):
                            email      = el.get_attribute("href").replace("mailto:", "")
                            best, score = process.extractOne(
                                email.split("@")[0], author_names or ["unknown"],
                                scorer=fuzz.ratio)
                            self.save_to_csv(
                                [[url, None, email, best, score]],
                                os.path.dirname(output_csv),
                                os.path.basename(output_csv),
                                header=["url", "author", "email", "best_match", "match_score"])
                except Exception:
                    pass

            except Exception as e:
                self.logger.error("[Oxford] Error on %s: %s", url, e)

    # ── Run ───────────────────────────────────────────────────────────────────

    def run(self):
        try:
            qp = {
                "q":                          self.keyword,
                "f_ContentType":              "Journal Article",
                "f_ContentSubTypeDisplayName":
                    "Research ArticleANDReview ArticleANDOtherANDAbstract",
                "fl_SiteID":                  "191",
                "rg_ArticleDate":             f"{self.start_year} TO {self.end_year}",
                "rg_AllPublicationDates":     f"{self.start_year} TO {self.end_year}",
                "rg_VersionDate":             f"{self.start_year} TO {self.end_year}",
                "dateFilterType":             "range",
                "noDateTypes":                "true",
            }
            base_url   = "https://academic.oup.com/search-results"
            search_url = f"{base_url}?{urlencode(qp)}"
            out_dir    = self.output_dir or self.directory
            slug       = self.directory
            s          = self.start_year.replace('/', '-')
            e          = self.end_year.replace('/', '-')

            self._load_cookies()
            self.driver.get(base_url)
            time.sleep(3)
            self.accept_cookies()
            self.detect_and_handle_captcha()

            self.driver.get(search_url)
            time.sleep(3)
            self.detect_and_handle_captcha()

            total_pages = self.get_total_pages()
            all_links   = []

            for _ in range(total_pages):
                self.detect_and_handle_captcha()
                links    = self.extract_links()
                all_links.extend(links)
                next_url = self.get_next_url()
                if next_url:
                    self.driver.get(next_url)
                    time.sleep(2)
                else:
                    break

            url_file   = f"Oxford_{slug}_{s}_to_{e}_urls.csv"
            email_file = f"Oxford_{slug}_{s}_to_{e}_authors_emails.csv"
            self.save_to_csv([[lnk] for lnk in all_links],
                             out_dir, url_file, header=["Article_URL"])
            self.scrape_author_emails(
                os.path.join(out_dir, url_file),
                os.path.join(out_dir, email_file))
            self._save_cookies()
            self.logger.info("[Oxford] Done — %d articles", len(all_links))

        except Exception as e:
            self.logger.error("[Oxford] Fatal error: %s", e)
            raise
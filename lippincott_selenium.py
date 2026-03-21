from chrome_display_mixin import ChromeDisplayMixin

try:
    import setuptools, sys
    if sys.version_info >= (3, 12):
        import importlib.util
        spec = importlib.util.find_spec('setuptools._distutils')
        if spec:
            sys.modules['distutils'] = importlib.import_module('setuptools._distutils')
except ImportError:
    pass

import os, csv, logging, time, math, re, sys
from selenium.common.exceptions import WebDriverException, TimeoutException, NoSuchWindowException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from urllib.parse import urlencode
import undetected_chromedriver as uc
from datetime import datetime
import tempfile


class LippincottScraper(ChromeDisplayMixin):
    def __init__(self, keyword, start_year, end_year, driver_path,
                 output_dir=None, progress_callback=None,
                 conference_name=""):
        # ── Mixin attrs ───────────────────────────────────────────────────────
        self._vdisplay        = None
        self.driver           = None
        self.wait             = None
        self.output_dir       = output_dir
        self.progress_callback = progress_callback
        self.driver_path      = driver_path

        # ── Scraper attrs ─────────────────────────────────────────────────────
        self.keyword        = keyword
        self.conference_name = conference_name
        self.directory      = keyword.replace(" ", "-")

        # Raw dates first (logger uses them for filename)
        self.start_year = start_year
        self.end_year   = end_year
        self._setup_logger()

        # Convert dates for URLs / CSV names
        self.start_year = self.convert_date_format(start_year)
        self.end_year   = self.convert_date_format(end_year)

        from datetime import datetime as _dt
        _ts = _dt.now().strftime("%H-%M-%S")
        _conf  = f"_{conference_name}" if conference_name else ""
        _kw    = self.directory
        _sd    = self.start_year.replace("/", "-").replace(":", "-")
        _ed    = self.end_year.replace("/", "-").replace(":", "-")
        _base  = f"Lippincott{_conf}_{_kw}_{_sd}_{_ed}_{_ts}"
        self.url_csv     = f"{_base}_urls.csv"
        self.authors_csv = f"{_base}_authors.csv"
        # run() is called by SeleniumScraperWrapper — NOT here

    # ── Logger ────────────────────────────────────────────────────────────────

    def _setup_logger(self):
        self.logger = logging.getLogger(
            f"{self.__class__.__name__}-{id(self)}"
        )
        self.logger.setLevel(logging.INFO)

        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(
            log_dir,
            f"{self.__class__.__name__}-{self.directory}"
            f"-{self.start_year.replace('/', '-')}"
            f"-{self.end_year.replace('/', '-')}.log"
        )

        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.INFO)
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(logging.INFO)
        fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fh.setFormatter(fmt)
        sh.setFormatter(fmt)
        self.logger.addHandler(fh)
        self.logger.addHandler(sh)
        self.logger.info(
            f"Lippincott ==> Logger initialised → {log_file}"
        )

    def _progress(self, pct, msg, **kwargs):
        self.logger.info(f"Lippincott ==> [{pct}%] {msg}")
        if self.progress_callback:
            try:
                self.progress_callback(pct, msg, **kwargs)
            except Exception:
                pass

    # ── Helpers ───────────────────────────────────────────────────────────────

    def convert_date_format(self, date_str):
        try:
            return datetime.strptime(date_str, "%m/%d/%Y").strftime("%Y-%m-%d")
        except ValueError as e:
            self.logger.error(f"Lippincott ==> Invalid date: {date_str} — {e}")
            return date_str

    def save_to_csv(self, data, filename, header=None):
        try:
            work_dir = self.output_dir if self.output_dir else self.directory
            os.makedirs(work_dir, exist_ok=True)
            filepath = os.path.join(work_dir, filename)
            file_exists = os.path.exists(filepath) and os.path.getsize(filepath) > 0
            with open(filepath, mode="a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if not file_exists and header:
                    w.writerow(header)
                w.writerows(data)
            self.logger.info(f"Lippincott ==> Saved → {filepath}")
        except Exception as e:
            self.logger.error(f"Lippincott ==> CSV save failed: {e}")

    # ── Scraping ──────────────────────────────────────────────────────────────

    def get_total_pages(self):
        try:
            el = self.wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "span.primary-search-results-text")
                )
            )
            total = int(el.text.split(" ")[1].replace(",", "").strip())
            pages = math.ceil(total / 100)
            self.logger.info(f"Lippincott ==> {total} results → {pages} pages")
            return pages
        except Exception as e:
            self.logger.error(f"Lippincott ==> get_total_pages failed: {e}")
            return 0

    def extract_article_links(self, total_pages, query_params):
        loop_until = min(total_pages, 11)
        total_saved = 0

        for page in range(0, loop_until):
            time.sleep(5)
            try:
                self.wait.until(
                    EC.presence_of_all_elements_located((By.ID, "checkBoxListContainer"))
                )
                article_links = self.wait.until(
                    EC.presence_of_all_elements_located(
                        (By.XPATH, "//header//a[@href]")
                    )
                )
                unique = [
                    [lnk.get_attribute("href").strip()]
                    for lnk in article_links
                    if (lnk.get_attribute("href") or "").startswith(
                        "https://journals.lww.com"
                    )
                ]
                self.save_to_csv(unique, self.url_csv, header=["Article_URL"])
                total_saved += len(unique)
                self.logger.info(
                    f"Lippincott ==> Page {page+1}/{loop_until}: "
                    f"{len(unique)} links (total {total_saved})"
                )
                pct = int(5 + ((page + 1) / loop_until) * 33)
                self._progress(
                    pct,
                    f"URL collection: page {page+1}/{loop_until} ({total_saved} URLs)",
                    current_url=self.driver.current_url,
                    links_count=total_saved,
                )

                if page >= loop_until - 1:
                    break

                # Navigate to next page
                navigated = False
                for method_name, method in [
                    ("JS next-btn", lambda: self._click_next_js()),
                    ("postback",    lambda p=page: self._postback_next(p + 2)),
                    ("page-link",   lambda p=page: self._click_page_link(p + 2)),
                ]:
                    try:
                        if method():
                            self.logger.info(f"Lippincott ==> Navigated via {method_name}")
                            navigated = True
                            time.sleep(3)
                            break
                    except Exception:
                        pass

                if not navigated:
                    self.logger.error("Lippincott ==> Could not navigate to next page")
                    break

            except Exception as e:
                self.logger.error(f"Lippincott ==> Page {page+1} error: {e}")
                break

    def _click_next_js(self):
        btn = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "a.element__nav--next"))
        )
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        time.sleep(1)
        self.driver.execute_script("arguments[0].click();", btn)
        return True

    def _postback_next(self, page_num):
        script = (
            f"__doPostBack('ctl00$ctl30$g_3e59ddb2_821c_45f2_8a16_6a9672a5d882"
            f"$ctl00$listItemActionToolbarControlBottom$pagingControl"
            f"$pagingControl$pageno{page_num}', '');"
        )
        self.driver.execute_script(script)
        return True

    def _click_page_link(self, page_num):
        lnk = self.wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, f"//a[@aria-label='Goto Page {page_num}']")
            )
        )
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", lnk)
        time.sleep(1)
        self.driver.execute_script("arguments[0].click();", lnk)
        return True

    def extract_author_info(self):
        work_dir = self.output_dir if self.output_dir else self.directory
        filepath = os.path.join(work_dir, self.url_csv)
        if not os.path.exists(filepath):
            self.logger.error("Lippincott ==> URL file not found!")
            return

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                rows = list(csv.reader(f))
            urls = [r[0].strip() for r in rows[1:] if r and r[0].strip()]
        except Exception as e:
            self.logger.error(f"Lippincott ==> Cannot read URL file: {e}")
            return

        total = len(urls)
        authors_found = 0

        for idx, article_url in enumerate(urls, 1):
            author_info = []
            try:
                self.driver.get(article_url)
                time.sleep(2)

                author_details = self.wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "#ejp-article-authors-link")
                    )
                )
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", author_details
                )
                author_details.click()

                author_notes = self.driver.find_element(
                    By.CSS_SELECTOR, "#ejp-article-authors-info"
                )
                span_elements = WebDriverWait(author_notes, 10).until(
                    EC.presence_of_all_elements_located(
                        (By.CSS_SELECTOR, "span a[href^='mailto:']")
                    )
                )

                emails, text_parts = [], []
                for span in span_elements:
                    email = span.get_attribute("href").replace("mailto:mailto:", "").replace("mailto:", "").strip()
                    emails.append(email)
                    parent_p = span.find_element(By.XPATH, "./ancestor::p")
                    parent_text = self.driver.execute_script(
                        "return arguments[0].textContent;", parent_p
                    ).strip()
                    text_parts = re.split(r'[\w\.-]+@[\w\.-]+\.\w+', parent_text)

                REMOVE = [
                    "Correspondence to", "Dr", "Professor", ":", ";", "\n",
                    "is corresponding author.", "Address", "Corresponding Author",
                    "Corresponding author", "Send reprint requests to",
                ]
                for i, email in enumerate(emails):
                    name_part = text_parts[i].strip() if i < len(text_parts) else ""
                    if i + 1 < len(text_parts) and text_parts[i + 1].startswith("("):
                        author_name = text_parts[i + 1].strip().replace(").", "").removeprefix("(")
                    elif "is corresponding author." in name_part:
                        for seg in name_part.split(","):
                            if "is corresponding author." in seg:
                                author_name = seg.replace("is corresponding author.", "").strip()
                                break
                        else:
                            author_name = name_part
                    else:
                        author_name = name_part.split(",")[0].replace("Correspondence to", "").strip()
                        for phrase in REMOVE:
                            author_name = author_name.replace(phrase, "").strip().strip(".")
                    author_info.append([article_url, author_name, email])
                    self.logger.info(f"Lippincott ==> {author_name} — {email}")

            except WebDriverException as e:
                self.logger.error(f"Lippincott ==> WebDriver error on {article_url}: {e}")
                self._quit_chrome()
                self._launch_chrome(self._build_default_chrome_options(), driver_path=self.driver_path)
                self.wait = WebDriverWait(self.driver, 60)
            except Exception as e:
                self.logger.error(f"Lippincott ==> Error on {article_url}: {e}")

            if author_info:
                self.save_to_csv(author_info, self.authors_csv, header=["Article_URL", "Author_Name", "Email"])
                authors_found += len(author_info)
            else:
                self.save_to_csv([[article_url, "N/A", "N/A"]], self.authors_csv, header=["Article_URL", "Author_Name", "Email"])

            pct = int(40 + (idx / total) * 55)
            self._progress(
                pct,
                f"Author extraction: {idx}/{total} ({authors_found} found)",
                current_url=article_url,
                authors_count=authors_found,
                links_count=total,
            )


    # ── Cookie helpers ────────────────────────────────────────────────────────
    _COOKIE_DIR = "/home/ubuntu/.scraper_cookies"

    def _cookie_path(self, domain: str) -> str:
        os.makedirs(self._COOKIE_DIR, exist_ok=True)
        safe = domain.replace(".", "_").replace("/", "_")
        return os.path.join(self._COOKIE_DIR, f"{safe}.json")

    def _save_cf_cookies(self, domain: str) -> None:
        """Persist cookies after a successful Cloudflare solve."""
        import json
        path = self._cookie_path(domain)
        try:
            cookies = self.driver.get_cookies()
            with open(path, "w") as f:
                json.dump(cookies, f)
            self.logger.info(f"CF cookies saved ({len(cookies)}) → {path}")
        except Exception as e:
            self.logger.warning(f"CF cookie save failed: {e}")

    def _load_cf_cookies(self, url: str) -> bool:
        """Load saved cookies before navigating to *url*. Returns True if loaded."""
        import json
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        path = self._cookie_path(domain)
        if not os.path.exists(path):
            return False
        try:
            self.driver.get(f"https://{domain}")
            time.sleep(2)
            with open(path) as f:
                cookies = json.load(f)
            loaded = 0
            for c in cookies:
                c.pop("sameSite", None)
                try:
                    self.driver.add_cookie(c)
                    loaded += 1
                except Exception:
                    pass
            self.logger.info(f"CF cookies loaded ({loaded}/{len(cookies)}) from {path}")
            return loaded > 0
        except Exception as e:
            self.logger.warning(f"CF cookie load failed: {e}")
            return False

    def _bypass_cloudflare(self, timeout: int = 120, target_url: str = "") -> bool:
        """
        Wait for user to solve Cloudflare captcha in VNC.
        Saves cookies after a successful solve.
        RAISES RuntimeError if captcha is not solved within timeout — this marks
        the Celery job as FAILED instead of COMPLETED with 0 results.
        """
        from urllib.parse import urlparse
        PHRASES = [
            "just a moment", "verifying you are human",
            "performing security verification", "checking your browser",
            "cf-browser-verification",
        ]

        def _on_cf():
            try:
                t = self.driver.title.lower()
                s = self.driver.page_source.lower()[:600]
                return any(p in t or p in s for p in PHRASES)
            except Exception:
                return False

        if not _on_cf():
            self.logger.info("CF bypass: no challenge — page ready ✓")
            return True

        self.logger.warning(
            f"⚠️  Cloudflare challenge detected — open VNC and click 'Verify you are human' "
            f"within {timeout}s.  URL: {self.driver.current_url}"
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(3)
            if not _on_cf():
                self.logger.info("CF bypass: challenge cleared ✓")
                # Save cookies so future runs skip the captcha
                try:
                    domain = urlparse(self.driver.current_url).netloc or urlparse(target_url).netloc
                    if domain:
                        self._save_cf_cookies(domain)
                except Exception:
                    pass
                return True
            remaining = int(deadline - time.time())
            self.logger.info(f"CF bypass: waiting for solve... ({remaining}s left)")

        # Screenshot before raising
        try:
            os.makedirs("logs", exist_ok=True)
            self.driver.save_screenshot(
                f"logs/{self.__class__.__name__}_cf_timeout.png"
            )
        except Exception:
            pass

        raise RuntimeError(
            f"Cloudflare captcha was not solved within {timeout}s. "
            f"Open VNC at http://3.108.210.45:6080/vnc.html, run the scraper again, "
            f"and click the checkbox when prompted."
        )


    def run(self):
        try:
            self.logger.info("Lippincott ==> Initialising Chrome via ChromeDisplayMixin...")
            self._launch_chrome(
                self._build_default_chrome_options(), driver_path=self.driver_path
            )
            self.wait = WebDriverWait(self.driver, 60)

            from urllib.parse import quote
            keyword_encoded = quote(self.keyword, safe="")
            search_url = (
                f"https://lww.com/pages/results.aspx"
                f"?txtKeywords={keyword_encoded}"
            )

            # ── Step 1: Homepage → establish session + bypass Cloudflare ──────
            self._load_cf_cookies("https://lww.com")
            self.logger.info("Lippincott ==> GET https://lww.com (homepage for session)")
            self.driver.get("https://lww.com")
            time.sleep(8)
            self._bypass_cloudflare(timeout=120, target_url="https://lww.com")

            try:
                btn = self.wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "#onetrust-accept-btn-handler")
                    )
                )
                self.driver.execute_script("arguments[0].click();", btn)
                self.logger.info("Lippincott ==> Cookie accepted")
                time.sleep(2)
            except Exception:
                self.logger.info("Lippincott ==> No cookie banner on homepage")

            # ── Step 2: Navigate to search via JS (inherits session trust) ────
            self.logger.info(f"Lippincott ==> JS navigating to: {search_url}")
            self.driver.execute_script("window.location.href = arguments[0];", search_url)
            time.sleep(10)
            self._bypass_cloudflare(timeout=120, target_url="https://lww.com")

            # Accept cookie if shown on results page
            try:
                btn2 = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "#onetrust-accept-btn-handler")
                    )
                )
                self.driver.execute_script("arguments[0].click();", btn2)
                time.sleep(2)
            except Exception:
                pass

            self._progress(5, "Getting result count...")
            total_pages = self.get_total_pages()
            if total_pages == 0:
                self.logger.warning("Lippincott ==> No results found — aborting")
                return

            # Set 100 results per page via JS dropdown
            try:
                dropdown_id = (
                    "ctl00_ctl30_g_3e59ddb2_821c_45f2_8a16_6a9672a5d882_ctl00"
                    "_listItemActionToolbarControlBottom_pagingControl"
                    "_itemsOnPageControl_ddOptionsMobile"
                )
                container = self.wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "div.wp-items-on-page")
                    )
                )
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", container
                )
                time.sleep(1)
                self.driver.execute_script(
                    f"var dd=document.getElementById('{dropdown_id}');"
                    "dd.value='100';"
                    "dd.dispatchEvent(new Event('change'));"
                )
                self.logger.info("Lippincott ==> Results per page set to 100")
                time.sleep(3)
            except Exception as e:
                self.logger.warning(f"Lippincott ==> Could not set page size: {e}")

            self._progress(10, f"Collecting URLs from {total_pages} pages...")
            self.extract_article_links(total_pages, {})

            self._progress(40, "PHASE 2: Extracting author emails...")
            self.extract_author_info()

            self._progress(100, "Lippincott scraping completed.")
            self.logger.info("Lippincott ==> Done.")

        except Exception as e:
            self.logger.error(f"Lippincott ==> run() error: {e}", exc_info=True)
            raise   # propagate so SeleniumScraperWrapper marks job FAILED
        finally:
            self._quit_chrome()
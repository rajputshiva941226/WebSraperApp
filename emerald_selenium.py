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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urlencode, quote
from datetime import datetime
import tempfile
from utils import sanitize_filename, safe_log_file_path


class EmeraldInsights(ChromeDisplayMixin):
    def __init__(self, keyword, start_year, end_year, driver_path,
                 output_dir=None, progress_callback=None,
                 conference_name=""):
        # ── Mixin attrs ───────────────────────────────────────────────────────
        self._vdisplay         = None
        self.driver            = None
        self.wait              = None
        self.output_dir        = output_dir
        self.progress_callback = progress_callback
        self.driver_path       = driver_path

        # ── Scraper attrs ─────────────────────────────────────────────────────
        self.keyword        = keyword
        self.conference_name = conference_name
        self.directory      = sanitize_filename(keyword)

        # Raw dates for logger filename
        self.start_year = start_year
        self.end_year   = end_year
        self._setup_logger()

        # Keep raw dates (Emerald uses them directly for URL params)

        from datetime import datetime as _dt
        _ts = _dt.now().strftime("%H-%M-%S")
        _conf  = f"_{conference_name}" if conference_name else ""
        _kw    = self.directory
        _sd    = self.start_year.replace("/", "-").replace(":", "-")
        _ed    = self.end_year.replace("/", "-").replace(":", "-")
        _base  = f"Emerald{_conf}_{_kw}_{_sd}_{_ed}_{_ts}"
        self.url_csv     = f"{_base}_urls.csv"
        self.authors_csv = f"{_base}_authors.csv"
        # run() called by SeleniumScraperWrapper — NOT here

    # ── Logger ────────────────────────────────────────────────────────────────

    def _setup_logger(self):
        self.logger = logging.getLogger(
            f"{self.__class__.__name__}-{id(self)}"
        )
        self.logger.setLevel(logging.INFO)
        log_file = safe_log_file_path(
            self.__class__.__name__, self.directory,
            self.start_year, self.end_year
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
        self.logger.info(f"Emerald ==> Logger initialised → {log_file}")

    def _progress(self, pct, msg, **kwargs):
        self.logger.info(f"Emerald ==> [{pct}%] {msg}")
        if self.progress_callback:
            try:
                self.progress_callback(pct, msg, **kwargs)
            except Exception:
                pass

    # ── Helpers ───────────────────────────────────────────────────────────────

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
            self.logger.info(f"Emerald ==> Saved → {filepath}")
        except Exception as e:
            self.logger.error(f"Emerald ==> CSV save failed: {e}")

    def accept_cookies(self):
        time.sleep(2)
        for sel in [
            "button#onetrust-accept-btn-handler",
            "button[id='onetrust-accept-btn-handler']",
            "div#onetrust-button-group button:nth-child(2)",
        ]:
            try:
                btn = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                )
                btn.click()
                self.logger.info(f"Emerald ==> Cookie accepted ({sel})")
                time.sleep(2)
                return
            except Exception:
                continue
        self.logger.info("Emerald ==> No cookie banner found")

    def get_total_pages(self):
        self.accept_cookies()
        try:
            el = self.wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.sr-statistics.at-sr-statistics")
                )
            )
            total = int(el.get_attribute("data-total-item-count"))
            pages = math.ceil(total / 20)
            self.logger.info(f"Emerald ==> {total} results → {pages} pages (20/page)")
            return pages
        except Exception as e:
            self.logger.warning(f"Emerald ==> Primary selector failed: {e}")
        # Fallback: text extraction
        try:
            txt = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.sr-statistics"))
            ).text
            match = re.search(r'of\s+([\d,]+)', txt)
            if match:
                total = int(match.group(1).replace(',', ''))
                pages = math.ceil(total / 20)
                self.logger.info(f"Emerald ==> Fallback: {total} results → {pages} pages")
                return pages
        except Exception as e2:
            self.logger.error(f"Emerald ==> get_total_pages failed: {e2}")
        return 0

    def extract_article_links(self, total_pages, base_url, query_params):
        all_links = []
        total_saved = 0

        for page in range(1, total_pages + 1):
            query_params["page"] = page
            page_url = f"{base_url}?{urlencode(query_params)}"
            self.driver.get(page_url)
            time.sleep(3)

            try:
                # Stop if no results
                try:
                    if self.driver.find_element(
                        By.XPATH, "//*[contains(text(),'No results found')]"
                    ):
                        self.logger.warning("Emerald ==> No results — stopping")
                        break
                except Exception:
                    pass

                articles = self.wait.until(
                    EC.presence_of_all_elements_located(
                        (By.CSS_SELECTOR, "div.content-type-journal-articles")
                    )
                )
                page_links = []
                for art in articles:
                    try:
                        href = art.find_element(
                            By.CSS_SELECTOR, ".sri-title h4 a"
                        ).get_attribute("href")
                        if href.startswith("/"):
                            href = "https://www.emerald.com" + href
                        page_links.append([href])
                    except Exception:
                        pass

                if not page_links:
                    self.logger.warning(f"Emerald ==> No links on page {page} — stopping")
                    break

                all_links.extend(page_links)
                total_saved += len(page_links)
                self.save_to_csv(page_links, self.url_csv, header=["Article URL"])
                self.logger.info(
                    f"Emerald ==> Page {page}/{total_pages}: "
                    f"{len(page_links)} links (total {total_saved})"
                )
            except Exception as e:
                self.logger.error(f"Emerald ==> Page {page} error: {e}")
                break

            pct = int(5 + (page / total_pages) * 33)
            self._progress(
                pct,
                f"URL collection: page {page}/{total_pages} ({total_saved} URLs)",
                current_url=page_url,
                links_count=total_saved,
            )

        self.logger.info(f"Emerald ==> Total links: {total_saved}")

    def extract_author_info(self):
        work_dir = self.output_dir if self.output_dir else self.directory
        filepath = os.path.join(work_dir, self.url_csv)
        if not os.path.exists(filepath):
            self.logger.error("Emerald ==> URL file not found!")
            return

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                rows = list(csv.reader(f))
            urls = [r[0].strip() for r in rows[1:] if r and r[0].strip()]
        except Exception as e:
            self.logger.error(f"Emerald ==> Cannot read URL file: {e}")
            return

        total = len(urls)
        authors_found = 0

        for idx, article_url in enumerate(urls, 1):
            try:
                self.driver.get(article_url)
                time.sleep(2)

                # Click expand button
                try:
                    btn = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((
                            By.CSS_SELECTOR,
                            "a.js-expand-collapse-metadata.author-expand-collapse-metadata"
                        ))
                    )
                    btn.click()
                    time.sleep(1)
                except Exception:
                    pass

                # Extract from wi-footnotes
                try:
                    footnotes = self.driver.find_element(
                        By.CSS_SELECTOR, "div.wi-footnotes"
                    ).find_elements(By.CSS_SELECTOR, "div.article-footnote")

                    author_info = []
                    for fn in footnotes:
                        fn_text = fn.text.strip()
                        if "can be contacted at" not in fn_text:
                            continue
                        try:
                            email = fn.find_element(
                                By.CSS_SELECTOR, "a[href^='mailto:']"
                            ).get_attribute("href").replace("mailto:", "").strip()
                            author_name = fn_text.split("can be contacted at")[0].strip()
                            for phrase in [
                                "is the corresponding author and",
                                "is the corresponding author",
                                "Corresponding author",
                                "Associate editor:", "and", "E-mail:", ":"
                            ]:
                                author_name = author_name.replace(phrase, "").strip()
                            author_name = " ".join(author_name.split()).rstrip(",")
                            author_info.append([article_url, author_name, email])
                            self.logger.info(f"Emerald ==> {author_name} — {email}")
                        except Exception:
                            continue

                    if author_info:
                        self.save_to_csv(
                            author_info, self.authors_csv,
                            header=["Article URL", "Author Name", "Email"]
                        )
                        authors_found += len(author_info)
                except Exception:
                    pass

            except Exception as e:
                self.logger.error(f"Emerald ==> Error on {article_url}: {e}")

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
        """
        Emerald Insight scraper.

        Navigation:
          1. emerald.com → accept cookie banner (JS click #onetrust-accept-btn-handler)
          2. emerald.com/advanced-search → fill search form:
               - input#advancedSearchQueryTerm  (keyword)
               - input#3  (Exact Phrase radio)
               - input#startDateSemanticSearch  (MM/DD/YYYY)
               - input#endDateSemanticSearch    (MM/DD/YYYY)
               - button#btnAdvancedSearch       (Search button below date range)
          3. Wait for results, bypass Cloudflare if needed
          4. Extract article links, extract author emails
        """
        try:
            self.logger.info("Emerald ==> Initialising Chrome via ChromeDisplayMixin...")
            self._launch_chrome(
                self._build_default_chrome_options(), driver_path=self.driver_path
            )
            self.wait = WebDriverWait(self.driver, 20)

            # Keep raw date strings in MM/DD/YYYY for the form
            # (Emerald date inputs use MM/DD/YYYY format per placeholder)
            start_date_form = self.start_year   # e.g. "01/01/2025"
            end_date_form   = self.end_year     # e.g. "03/20/2025"

            # ── Step 1: Homepage → accept cookie banner ──────────────────────
            self._load_cf_cookies("https://www.emerald.com")
            self.logger.info("Emerald ==> GET https://www.emerald.com")
            self.driver.get("https://www.emerald.com")
            time.sleep(5)
            self._bypass_cloudflare(timeout=120, target_url="https://www.emerald.com")

            # Cookie banner: <button id="onetrust-accept-btn-handler">Accept All Cookies</button>
            try:
                btn = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "#onetrust-accept-btn-handler")
                    )
                )
                self.driver.execute_script("arguments[0].click();", btn)
                self.logger.info("Emerald ==> Cookie consent accepted")
                time.sleep(2)
            except Exception:
                self.logger.info("Emerald ==> No cookie banner found")

            # ── Step 2: Advanced search form ─────────────────────────────────
            self.logger.info("Emerald ==> GET https://www.emerald.com/advanced-search")
            self.driver.get("https://www.emerald.com/advanced-search")
            time.sleep(6)   # wait for form JS to load
            self._bypass_cloudflare(timeout=120, target_url="https://www.emerald.com")

            self._fill_emerald_search_form(start_date_form, end_date_form)

            # ── Step 3: Wait for results ──────────────────────────────────────
            self._progress(5, "Waiting for search results...")
            time.sleep(10)
            self._bypass_cloudflare(timeout=120, target_url="https://www.emerald.com")

            # Accept cookie again if shown on results page
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

            self.logger.info(f"Emerald ==> Results URL: {self.driver.current_url}")

            # ── Step 4: Extract URLs then emails ─────────────────────────────
            self._progress(8, "Getting result count...")
            total_pages = self.get_total_pages()
            if not total_pages:
                self.logger.error("Emerald ==> No results — aborting")
                return

            # Use current URL as base for pagination
            from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
            parsed     = urlparse(self.driver.current_url)
            flat_params = {k: v[0] for k, v in parse_qs(parsed.query, keep_blank_values=True).items()}
            base_url   = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

            self._progress(10, f"Collecting URLs from {total_pages} pages...")
            self.extract_article_links(total_pages, base_url, flat_params)

            self._progress(40, "PHASE 2: Extracting author emails...")
            self.extract_author_info()

            self._progress(100, "Emerald scraping completed.")
            self.logger.info("Emerald ==> Done.")

        except Exception as e:
            self.logger.error(f"Emerald ==> run() error: {e}", exc_info=True)
            raise   # propagate so SeleniumScraperWrapper marks job FAILED
        finally:
            self._quit_chrome()

    def _fill_emerald_search_form(self, start_date: str, end_date: str):
        """
        Fill the Emerald advanced search form at /advanced-search.

        Selectors from live HTML:
          Keyword input : input#advancedSearchQueryTerm
          Exact Phrase  : input#3  (radio, value="Exact Phrase")
          Start date    : input#startDateSemanticSearch  (MM/DD/YYYY)
          End date      : input#endDateSemanticSearch    (MM/DD/YYYY)
          Search button : button#btnAdvancedSearch  (below the date range)
        """
        import random
        from selenium.webdriver.common.keys import Keys

        self.logger.info(
            f"Emerald ==> Filling form: keyword='{self.keyword}' "
            f"{start_date} → {end_date}"
        )

        try:
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located(
                    (By.ID, "advancedSearchQueryTerm")
                )
            )
        except Exception as e:
            self.logger.error(f"Emerald ==> Search form not loaded: {e}")
            return

        try:
            # ── 1. Type keyword ───────────────────────────────────────────────
            time.sleep(random.uniform(0.8, 1.5))
            kw_input = self.driver.find_element(By.ID, "advancedSearchQueryTerm")
            self.driver.execute_script("arguments[0].click();", kw_input)
            time.sleep(random.uniform(0.4, 0.8))
            kw_input.clear()
            for ch in self.keyword:
                kw_input.send_keys(ch)
                time.sleep(random.uniform(0.06, 0.15))
            self.logger.info(f"Emerald ==> Keyword typed: {self.keyword}")
            time.sleep(random.uniform(0.5, 1.0))

            # ── 2. Select "Exact Phrase" radio ────────────────────────────────
            # <input id="3" name="SearchType" type="radio" value="Exact Phrase">
            try:
                exact_radio = self.driver.find_element(
                    By.CSS_SELECTOR, "input#3[value='Exact Phrase']"
                )
                self.driver.execute_script("arguments[0].click();", exact_radio)
                self.logger.info("Emerald ==> Exact Phrase selected")
            except Exception as e:
                self.logger.warning(f"Emerald ==> Could not select Exact Phrase: {e}")
            time.sleep(random.uniform(0.5, 0.9))

            # ── 3. Fill date fields (MM/DD/YYYY) via JS + send_keys ───────────
            for field_id, value, label in [
                ("startDateSemanticSearch", start_date, "Start"),
                ("endDateSemanticSearch",   end_date,   "End"),
            ]:
                try:
                    field = self.driver.find_element(By.ID, field_id)
                    self.driver.execute_script("arguments[0].value = '';", field)
                    self.driver.execute_script("arguments[0].click();", field)
                    time.sleep(0.3)
                    for ch in value:
                        field.send_keys(ch)
                        time.sleep(random.uniform(0.04, 0.10))
                    field.send_keys(Keys.TAB)   # trigger validation
                    self.logger.info(f"Emerald ==> {label} date: {value}")
                    time.sleep(0.4)
                except Exception as e:
                    self.logger.warning(f"Emerald ==> Date field {field_id}: {e}")

            time.sleep(random.uniform(1.0, 1.8))

            # ── 4. Click the Search button (below date range in Filter section) ─
            # <button id="btnAdvancedSearch" class="btn">Search</button>
            search_btn = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.ID, "btnAdvancedSearch"))
            )
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", search_btn
            )
            time.sleep(random.uniform(0.8, 1.5))
            self.driver.execute_script("arguments[0].click();", search_btn)
            self.logger.info("Emerald ==> Search submitted")

        except Exception as e:
            self.logger.error(f"Emerald ==> Form fill error: {e}", exc_info=True)
            try:
                os.makedirs("logs", exist_ok=True)
                self.driver.save_screenshot("logs/emerald_form_error.png")
            except Exception:
                pass
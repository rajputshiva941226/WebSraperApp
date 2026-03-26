import os, sys
import csv
import re
import time
import logging
import tempfile
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from fuzzywuzzy import process, fuzz
import undetected_chromedriver as uc
from utils import sanitize_filename, safe_log_file_path


class CambridgeScraper:
    def __init__(self, keyword, start_year, end_year, driver_path,
                 output_dir=None, progress_callback=None,conference_name=""):

        self.keyword           = keyword
        self.start_year        = start_year
        self.end_year          = end_year
        self.driver_path       = driver_path
        self.output_dir        = output_dir        # injected by SeleniumScraperWrapper
        self.progress_callback = progress_callback
        self.directory         = sanitize_filename(keyword)
        self.driver            = None
        self.conference_name   = conference_name

        # ── FIX: logger MUST be set up before uc.Chrome() is called.
        # Previously _setup_logger() came after uc.Chrome() in __init__,
        # so any Chrome crash (e.g. "daemonic process" error, missing display)
        # propagated before any FileHandler existed → zero log output.
        self._setup_logger()
        self._init_driver()
        # run() is called explicitly by SeleniumScraperWrapper._scraper_subprocess_entry

    # ─────────────────────────────────────────────────────────────────────
    # Logger
    # ─────────────────────────────────────────────────────────────────────

    def _setup_logger(self):
        """Configure logger with file + stdout handlers (UTF-8 safe).
        Called FIRST in __init__ so Chrome crash errors are captured."""
        self.logger = logging.getLogger(self.__class__.__name__)
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

        try:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            self.logger.addHandler(file_handler)
        except Exception as e:
            print(f"[Cambridge] Could not create log file {log_file}: {e}")

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        self.logger.addHandler(stream_handler)
        self.logger.info(f"Cambridge ==> Logger initialised, log file: {log_file}")

    # ─────────────────────────────────────────────────────────────────────
    # Driver init
    # ─────────────────────────────────────────────────────────────────────

    def _init_driver(self):
        """Initialise uc.Chrome AFTER the logger exists so crashes are logged."""
        self.logger.info(f"Cambridge ==> Initialising Chrome (driver={self.driver_path})")
        try:
            options = Options()
            # --headless=new is required on EC2 (no display server)
            options.add_argument('--headless=new')
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--disable-notifications')
            options.add_argument('--disable-background-timer-throttling')
            options.add_argument('--disable-backgrounding-occluded-windows')
            options.add_argument('--disable-renderer-backgrounding')
            # Eager: DOM ready is enough, skip waiting for images/JS
            options.page_load_strategy = 'eager'

            self.uc_temp_dir = tempfile.mkdtemp(prefix="Cambridge_")

            self.driver = uc.Chrome(
                options=options,
                driver_executable_path=self.driver_path,
                version_main=None,
                use_subprocess=False
            )
            self.driver.set_page_load_timeout(45)  # prevents 120s HTTP pool hang
            self.wait = WebDriverWait(self.driver, 30)

            # Verify browser is alive
            time.sleep(2)
            _ = self.driver.current_url
            self.logger.info("Cambridge ==> Chrome initialised successfully")

        except Exception as exc:
            # Log BEFORE re-raising so the file handler captures the full traceback
            self.logger.exception(f"Cambridge ==> Chrome init FAILED: {exc}")
            raise

    # ─────────────────────────────────────────────────────────────────────
    # Progress helper
    # ─────────────────────────────────────────────────────────────────────

    def _progress(self, pct, msg, **kwargs):
        self.logger.info(f"Cambridge ==> [{pct}%] {msg}")
        if self.progress_callback:
            try:
                self.progress_callback(pct, msg, **kwargs)
            except KeyboardInterrupt:
                raise
            except Exception:
                pass

    def _reinit_driver(self):
        """Kill the dead Chrome session and start a fresh one."""
        self.logger.warning("Cambridge ==> Reinitialising Chrome after session failure...")
        try:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
        except Exception:
            pass
        self.driver = None
        time.sleep(3)
        self._init_driver()
        self.logger.info("Cambridge ==> Chrome reinitialised successfully")

    def _is_driver_alive(self):
        """Quick check if ChromeDriver session is still responsive."""
        try:
            _ = self.driver.current_url
            return True
        except Exception:
            return False

    # ─────────────────────────────────────────────────────────────────────
    # Main run
    # ─────────────────────────────────────────────────────────────────────

    def run(self):
        start_year = self.start_year.split("/")[-1]
        end_year   = self.end_year.split("/")[-1]

        self.base_url = (
            f"https://www.cambridge.org/core/search?q={self.keyword}"
            f"&aggs%5BproductTypes%5D%5Bfilters%5D=JOURNAL_ARTICLE"
            f"&filters%5BdateYearRange%5D%5Bfrom%5D={start_year}"
            f"&filters%5BdateYearRange%5D%5Bto%5D={end_year}"
        )

        # Use injected output_dir (Celery path) or fall back to keyword subdir (standalone)
        work_dir = self.output_dir if self.output_dir else self.keyword.replace(" ", "-")
        os.makedirs(work_dir, exist_ok=True)

        safe_kw = self.keyword.replace(' ', '-')
        safe_sd = self.start_year.replace('/', '-')
        safe_ed = self.end_year.replace('/', '-')
        # Add conference name to filename
        conf_suffix = f"_{self.conference_name}" if self.conference_name and self.conference_name != 'default' else ""
        url_file     = f"Cambridge{conf_suffix}_{safe_kw}_{safe_sd}-{safe_ed}_urls.csv"
        authors_file = f"Cambridge{conf_suffix}_{safe_kw}_{safe_sd}-{safe_ed}_authors.csv"
        authors_path = os.path.join(work_dir, authors_file)

        self.initialize_csv(work_dir, url_file,     ["Article_URL"])
        self.initialize_csv(work_dir, authors_file, ["Article URL", "Name", "Email", "Match Score", "Conference Name"])

        phase1_ok = False
        try:
            self._progress(5, "PHASE 1: Extracting article URLs from all pages...")
            self.scrape_article_links_streaming(work_dir, url_file)
            phase1_ok = True
        except Exception as exc:
            self.logger.error(f"Cambridge ==> Phase 1 failed: {exc}")

        # Return early if Phase 1 failed — quit driver first
        if not phase1_ok:
            try:
                if self.driver:
                    self.driver.quit()
            except Exception:
                pass
            return authors_path

        self._progress(40, "PHASE 2: Reading URLs and extracting author information...")
        self.scrape_authors_from_url_file(work_dir, url_file, authors_file)

        self._progress(100, "Scraping completed.")
        self.logger.info("Cambridge ==> Scraping completed.")

        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass

        return authors_path

    # ─────────────────────────────────────────────────────────────────────
    # CSV helpers
    # ─────────────────────────────────────────────────────────────────────

    def initialize_csv(self, directory, filename, header):
        """Initialize CSV file with header."""
        try:
            os.makedirs(directory, exist_ok=True)
            filepath = os.path.join(directory, filename)
            with open(filepath, mode="w", newline="", encoding="utf-8") as file:
                csv.writer(file).writerow(header)
            self.logger.info(f"Cambridge ==> Initialized {filepath} with header.")
        except Exception as e:
            self.logger.error(f"Cambridge ==> Failed to initialize CSV: {e}")

    def write_to_csv(self, directory, filename, row):
        """Write a single row to CSV immediately."""
        try:
            filepath = os.path.join(directory, filename)
            with open(filepath, mode="a", newline="", encoding="utf-8") as file:
                csv.writer(file).writerow(row)
        except Exception as e:
            self.logger.error(f"Cambridge ==> Failed to write to CSV: {e}")

    # ─────────────────────────────────────────────────────────────────────
    # Cookie handling
    # ─────────────────────────────────────────────────────────────────────

    def accept_cookies(self):
        """Accept cookies if the cookie banner is present."""
        try:
            selectors = [
                "button#onetrust-accept-btn-handler",
                "button[id='onetrust-accept-btn-handler']",
                "div#onetrust-button-group button:nth-child(2)",
                ".onetrust-close-btn-handler",
                "button.accept-cookies-button"
            ]
            for selector in selectors:
                try:
                    accept_button = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    accept_button.click()
                    self.logger.info(f"Cambridge ==> Accepted cookies using selector: {selector}")
                    WebDriverWait(self.driver, 3).until(
                        EC.invisibility_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    return
                except Exception:
                    continue
            self.logger.info("Cambridge ==> Could not find cookie accept button with any selector.")
        except Exception as e:
            self.logger.info(f"Cambridge ==> Cookie banner handling failed: {e}")

    # ─────────────────────────────────────────────────────────────────────
    # Phase 1: collect article URLs
    # ─────────────────────────────────────────────────────────────────────

    def scrape_article_links_streaming(self, output_dir, url_file):
        """Scrape article links and write them immediately to CSV."""
        self.logger.info(f"Cambridge ==> Starting scrape for articles: {self.base_url}")
        self.driver.get(self.base_url)
        self.accept_cookies()

        try:
            last_page_element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'li a[aria-label="Last page"]')
                )
            )
            last_page_number = int(last_page_element.get_attribute("data-page-number"))
            self.logger.info(f"Cambridge ==> Found last page number: {last_page_number}")
        except Exception as e:
            self.logger.error(f"Cambridge ==> Error retrieving last page number: {e}")
            return

        total_articles = 0
        for page_num in range(1, last_page_number + 1):
            page_url = (
                f"https://www.cambridge.org/core/search?pageNum={page_num}"
                f"&q={self.keyword}"
                f"&aggs%5BproductTypes%5D%5Bfilters%5D=JOURNAL_ARTICLE"
                f"&filters%5BdateYearRange%5D%5Bfrom%5D={self.start_year.split('/')[-1]}"
                f"&filters%5BdateYearRange%5D%5Bto%5D={self.end_year.split('/')[-1]}"
            )
            self.logger.info(f"Cambridge ==> Processing page {page_num}: {page_url}")
            self.driver.get(page_url)

            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li.title a"))
                )
            except Exception as e:
                self.logger.warning(f"Cambridge ==> No articles found on page {page_num}: {e}")
                continue

            link_elements = self.driver.find_elements(By.CSS_SELECTOR, "li.title a")
            article_urls = [
                elem.get_attribute("href")
                for elem in link_elements
                if elem.get_attribute("href")
            ]

            for article_url in article_urls:
                self.write_to_csv(output_dir, url_file, [article_url])
                total_articles += 1

            pct = int(5 + (page_num / last_page_number) * 35)   # 5 → 40%
            self._progress(pct, f"URL collection: page {page_num}/{last_page_number} ({total_articles} URLs)")

        self.logger.info(f"Cambridge ==> Total articles found: {total_articles}")

    # ─────────────────────────────────────────────────────────────────────
    # Phase 2: extract authors
    # ─────────────────────────────────────────────────────────────────────

    def scrape_authors_from_url_file(self, output_dir, url_file, authors_file):
        """Read article URLs from CSV and scrape author information."""
        filepath = os.path.join(output_dir, url_file)

        if not os.path.exists(filepath):
            self.logger.error(f"Cambridge ==> URL file not found: {filepath}")
            return

        try:
            with open(filepath, mode="r", encoding="utf-8") as file:
                urls = [
                    row.get("Article_URL", "").strip()
                    for row in csv.DictReader(file)
                    if row.get("Article_URL", "").strip()
                ]
        except Exception as e:
            self.logger.error(f"Cambridge ==> Could not read URL file: {e}")
            return

        total = len(urls)
        self.logger.info(f"Cambridge ==> Processing {total} articles")

        consecutive_failures = 0
        MAX_CONSECUTIVE_FAILURES = 3

        for idx, article_url in enumerate(urls, 1):
            self.logger.info(f"Cambridge ==> Processing article {idx}/{total}: {article_url}")

            # Check if driver is still alive before each article
            if not self._is_driver_alive():
                self.logger.warning("Cambridge ==> Driver session dead, reinitialising...")
                try:
                    self._reinit_driver()
                    consecutive_failures = 0
                except Exception as reinit_err:
                    self.logger.error(f"Cambridge ==> Driver reinit failed: {reinit_err}")
                    self.logger.error("Cambridge ==> Cannot continue, saving partial results")
                    break

            try:
                self.scrape_article_streaming(article_url, output_dir, authors_file)
                consecutive_failures = 0  # Reset on success
            except KeyboardInterrupt:
                raise
            except Exception as e:
                from selenium.common.exceptions import WebDriverException
                err_str = str(e)
                # HTTPConnectionPool ReadTimeout = Chrome is stuck but session may be alive
                # WebDriverException with "invalid session" = Chrome is dead, must reinit
                is_session_dead = (
                    isinstance(e, WebDriverException) and
                    any(kw in err_str for kw in [
                        "invalid session", "chrome not reachable",
                        "session deleted", "no such session",
                        "connection refused", "failed to receive"
                    ])
                )
                is_load_timeout = "Read timed out" in err_str or "TimeoutException" in type(e).__name__

                if is_load_timeout:
                    # Page was just slow — Chrome is fine, skip to next article
                    self.logger.warning(
                        f"Cambridge ==> Page load timed out on article {idx}/{total} — skipping"
                    )
                    try:
                        self.driver.execute_script("window.stop();")
                    except Exception:
                        pass
                    consecutive_failures = 0
                    continue

                self.logger.error(f"Cambridge ==> Error on article {idx}/{total}: {e}")
                consecutive_failures += 1

                # Session-dead or repeated failures — reinit driver
                if is_session_dead or consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    self.logger.warning(
                        f"Cambridge ==> Driver appears dead (consecutive={consecutive_failures}), "
                        "reinitialising..."
                    )
                    try:
                        self._reinit_driver()
                        consecutive_failures = 0
                    except Exception as reinit_err:
                        self.logger.error(f"Cambridge ==> Driver reinit failed: {reinit_err}")
                        self.logger.error("Cambridge ==> Stopping article loop, saving partial results")
                        break

                continue  # Skip to next article — never exit the loop on a single failure

            pct = int(40 + (idx / total) * 55)   # 40 → 95%
            self._progress(pct, f"Author extraction: {idx}/{total}",
                           current_url=article_url)

        self.logger.info(f"Cambridge ==> Completed processing {total} articles")

    def scrape_article_streaming(self, article_url, directory, filename):
        """Scrape article and write author data immediately to CSV.

        Raises:
            WebDriverException  — if Chrome session is dead (triggers reinit in caller)
            TimeoutException    — if page load times out (safe to continue, Chrome still alive)
        """
        from selenium.common.exceptions import TimeoutException as SeleniumTimeout
        from selenium.common.exceptions import WebDriverException

        self.logger.info(f"Cambridge ==> Scraping article: {article_url}")

        try:
            self.driver.get(article_url)
        except SeleniumTimeout:
            # Page load hit the 45s timeout — stop loading and continue with DOM we have
            self.logger.warning(f"Cambridge ==> Page load timeout on {article_url} — stopping load and proceeding")
            try:
                self.driver.execute_script("window.stop();")
            except Exception:
                pass
        # WebDriverException (session dead) is NOT caught here — bubbles up to caller

        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "dt.title, div.row.author")
                )
            )
        except Exception as e:
            self.logger.warning(f"Cambridge ==> Page content not loaded for {article_url}: {e}")
            return

        try:
            # Click "Show author details" if present
            try:
                show_author_details_link = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//a[@aria-controls='authors-details']")
                    )
                )
                self.driver.execute_script(
                    "arguments[0].scrollIntoView(true);", show_author_details_link
                )
                WebDriverWait(self.driver, 2).until(
                    EC.visibility_of(show_author_details_link)
                )
                show_author_details_link.click()
                self.logger.info("Cambridge ==> Clicked 'Show author details' link.")
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "div#authors-details")
                    )
                )
            except Exception:
                self.logger.warning("Cambridge ==> Show author details link not found.")

            # Extract authors
            author_elements = self.driver.find_elements(By.CSS_SELECTOR, "dt.title")
            author_names = [el.text.strip() for el in author_elements if el.text.strip()]
            author_names = [
                n for n in author_names
                if n not in ["*", "Type", "Information", "Copyright"]
            ]
            starred_authors     = [n for n in author_names if n.endswith("*")]
            non_starred_authors = [n for n in author_names if not n.endswith("*")]

            # Extract emails from div.corresp
            emails_from_corresp = []
            for container in self.driver.find_elements(By.CSS_SELECTOR, "div.corresp"):
                emails_from_corresp.extend(
                    re.findall(r'[\w\.-]+@[\w\.-]+', container.text.strip())
                )
            emails_from_corresp = list(set(emails_from_corresp))

            # Match starred authors to corresp emails
            for author_name in starred_authors:
                best_email = None
                best_match_score = 0
                if emails_from_corresp:
                    best_match = process.extractOne(
                        author_name.strip("*"), emails_from_corresp,
                        scorer=fuzz.token_sort_ratio
                    )
                    if best_match:
                        best_email, best_match_score = best_match[0], best_match[1]
                if best_email:
                    self.write_to_csv(
                        directory, filename,
                        [article_url, author_name.strip("*"), best_email, best_match_score, self.conference_name]
                    )
                    self.logger.info(
                        f"Cambridge ==> Written: {author_name.strip('*')} - {best_email}"
                    )

            # Fallback for non-starred authors
            try:
                email_spans = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    "span[data-v-2edb8da6] > span[data-v-2edb8da6]"
                )
                fallback_emails = []
                for span in email_spans:
                    span_text = span.text.strip()
                    if "e-mail:" in span_text.lower() or "e-mails:" in span_text.lower():
                        email_part = span_text.split(":")[1]
                        fallback_emails.extend(
                            [e.strip(")") for e in email_part.split(",")]
                        )
                fallback_emails = list(set(fallback_emails))

                for author_name in non_starred_authors:
                    best_email = None
                    best_match_score = 0
                    if fallback_emails:
                        emails_for_matching = {e.split("@")[0]: e for e in fallback_emails}
                        best_match = process.extractOne(
                            author_name, emails_for_matching.keys(),
                            scorer=fuzz.token_sort_ratio
                        )
                        if best_match:
                            best_email_local_part, best_match_score = best_match[0], best_match[1]
                            best_email = emails_for_matching[best_email_local_part]
                    if best_email:
                        self.write_to_csv(
                            directory, filename,
                            [article_url, author_name.strip("*"), best_email, best_match_score, self.conference_name]
                        )
                        self.logger.info(
                            f"Cambridge ==> Written: {author_name.strip('*')} - {best_email}"
                        )
            except Exception as e:
                self.logger.warning(
                    f"Cambridge ==> Fallback email method failed for {article_url}: {e}"
                )

        except Exception as e:
            self.logger.error(f"Cambridge ==> Error processing article {article_url}: {e}")
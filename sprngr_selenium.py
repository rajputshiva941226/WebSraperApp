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

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

import csv, logging, math, sys, time
import os, random, subprocess, tempfile
import undetected_chromedriver as uc


class SpringerAuthorScraper:
    def __init__(self, keyword, start_year, end_year, driver_path,
                 output_dir=None, progress_callback=None, conference_name=""):
        """
        Parameters
        ----------
        keyword           : search keyword
        start_year        : date string e.g. "01/01/2023"
        end_year          : date string e.g. "02/02/2023"
        driver_path       : path to chromedriver binary
        output_dir        : directory to write CSV results (injected by Celery adapter)
        progress_callback : callable(pct, msg, **kwargs) for live progress updates
        """
        self.keyword           = keyword
        self.start_year        = start_year
        self.end_year          = end_year
        self.driver_path       = driver_path
        self.output_dir        = output_dir
        self.progress_callback = progress_callback
        self.conference_name   = conference_name

        # Derive a safe directory/filename prefix from keyword + dates
        safe_kw = keyword.replace(" ", "-")
        safe_sd = start_year.replace("/", "-")
        safe_ed = end_year.replace("/", "-")
        self.directory   = output_dir or safe_kw   # use output_dir if given
        # Add conference name to filename
        conf_suffix = f"_{conference_name}" if conference_name and conference_name != 'default' else ""
        self.url_csv     = f"Springer{conf_suffix}_{safe_kw}-{safe_sd}-{safe_ed}_urls.csv"
        self.authors_csv = f"Springer{conf_suffix}_{safe_kw}-{safe_sd}-{safe_ed}_authors.csv"
        # ── Logger MUST come before uc.Chrome() so init errors are captured ──
        self._setup_logger()
        self._init_driver()
        # NOTE: run() is NOT called here — callers (scraper_adapter) call it explicitly

    # ─────────────────────────────────────────────────────────────────────
    # Logger
    # ─────────────────────────────────────────────────────────────────────

    def _setup_logger(self):
        """Configure logger with file + stdout handlers (UTF-8 safe)."""
        self.logger = logging.getLogger(f"Springer-{id(self)}")
        self.logger.setLevel(logging.INFO)

        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        safe_kw = self.keyword.replace(" ", "-")
        safe_sd = self.start_year.replace("/", "-")
        safe_ed = self.end_year.replace("/", "-")
        log_file = os.path.join(log_dir, f"SpringerAuthorScraper-{safe_kw}-{safe_sd}-{safe_ed}.log")

        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        try:
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setLevel(logging.INFO)
            fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(fh)
        except Exception as e:
            print(f"[Springer] Could not create log file {log_file}: {e}")

        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(logging.INFO)
        sh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(sh)
        self.logger.info(f"Springer ==> Logger initialised, log: {log_file}")

    # ─────────────────────────────────────────────────────────────────────
    # Driver init / recovery
    # ─────────────────────────────────────────────────────────────────────

    def _init_driver(self):
        """Initialise uc.Chrome — called after logger so errors are captured."""
        self.logger.info(f"Springer ==> Initialising Chrome (driver={self.driver_path})")
        options = Options()
        options.add_argument("--headless=new")
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

        self.uc_temp_dir = tempfile.mkdtemp(prefix="Springer_")
        try:
            self.driver = uc.Chrome(
                options=options,
                driver_executable_path=self.driver_path,
                version_main=None,
                use_subprocess=False,
            )
            self.wait = WebDriverWait(self.driver, 30)
            time.sleep(2)
            _ = self.driver.current_url
            self.logger.info("Springer ==> Chrome initialised successfully")
        except Exception as exc:
            self.logger.exception(f"Springer ==> Chrome init FAILED: {exc}")
            raise

    def _is_driver_alive(self):
        try:
            _ = self.driver.current_url
            return True
        except Exception:
            return False

    def _reinit_driver(self):
        """Kill dead session and start a fresh Chrome."""
        self.logger.warning("Springer ==> Reinitialising Chrome after session failure...")
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass
        self.driver = None
        time.sleep(3)
        self._init_driver()

    # ─────────────────────────────────────────────────────────────────────
    # Progress helper
    # ─────────────────────────────────────────────────────────────────────

    def _progress(self, pct, msg, **kwargs):
        self.logger.info(f"Springer ==> [{pct}%] {msg}")
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

    def save_to_csv(self, data, filename, header=None):
        """Append rows to a CSV inside self.directory."""
        try:
            os.makedirs(self.directory, exist_ok=True)
            filepath = os.path.join(self.directory, filename)
            with open(filepath, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if os.path.getsize(filepath) == 0 and header:
                    writer.writerow(header)
                writer.writerows(data)
            self.logger.debug(f"Springer ==> Saved {len(data)} rows to {filepath}")
        except Exception as e:
            self.logger.error(f"Springer ==> Failed to save CSV: {e}")

    def load_links_from_csv(self):
        """Return list of article URLs previously saved during Phase 1."""
        filepath = os.path.join(self.directory, self.url_csv)
        if not os.path.exists(filepath):
            self.logger.error("Springer ==> URL file not found — run Phase 1 first.")
            return []
        links = []
        with open(filepath, mode="r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)   # skip header
            links = ["".join(row) for row in reader if row]
        return links

    # ─────────────────────────────────────────────────────────────────────
    # Cookie / page helpers
    # ─────────────────────────────────────────────────────────────────────

    def dismiss_cookie_banner(self):
        try:
            banner = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "dialog.cc-banner"))
            )
            btn = banner.find_element(By.CSS_SELECTOR, 'button[data-cc-action="accept"]')
            if btn.is_displayed() and btn.is_enabled():
                btn.click()
                self.logger.info("Springer ==> Cookie banner accepted.")
        except Exception:
            pass   # no banner — fine

    def get_total_pages(self):
        try:
            el = self.wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'span[data-test="results-data-total"]')
                )
            )
            total_results = int(el.text.split(" ")[-2].replace(",", "").strip())
            total_pages   = math.ceil(total_results / 20)
            self.logger.info(
                f"Springer ==> Total results: {total_results}, pages: {total_pages}"
            )
            return total_pages
        except Exception as e:
            self.logger.error(f"Springer ==> Failed to get total pages: {e}")
            return 0

    # ─────────────────────────────────────────────────────────────────────
    # Phase 1 — extract article URLs
    # ─────────────────────────────────────────────────────────────────────

    def extract_article_links(self, search_url, total_pages):
        """
        Walk through up to 50 result pages and save all article URLs to CSV.
        Reports per-page progress: 5 → 40%.
        """
        self.driver.get(search_url)
        max_pages = min(total_pages, 50)

        for page in range(max_pages):
            page_links = []
            try:
                self.wait.until(
                    EC.presence_of_all_elements_located(
                        (By.CSS_SELECTOR, "a.app-card-open__link")
                    )
                )
                elements   = self.driver.find_elements(By.CSS_SELECTOR, "a.app-card-open__link")
                page_links = [el.get_attribute("href") for el in elements if el.get_attribute("href")]

                try:
                    next_btn = self.wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'a[rel="next"]'))
                    )
                    if next_btn.is_displayed():
                        next_btn.click()
                        self.wait.until(EC.staleness_of(elements[0]))
                    else:
                        self.logger.info("Springer ==> No next button — last page reached.")
                        self.save_to_csv([[u] for u in page_links], self.url_csv, header=["Article_URL"])
                        break
                except Exception:
                    self.logger.info("Springer ==> Pagination ended.")
                    self.save_to_csv([[u] for u in page_links], self.url_csv, header=["Article_URL"])
                    break

            except Exception as e:
                self.logger.error(f"Springer ==> Error on page {page + 1}: {e}")
                self.driver.refresh()
                time.sleep(2)

            finally:
                if page_links:
                    self.save_to_csv([[u] for u in page_links], self.url_csv, header=["Article_URL"])

            pct = int(5 + ((page + 1) / max_pages) * 35)   # 5 → 40%
            self._progress(
                pct,
                f"URL collection: page {page + 1}/{max_pages} ({(page + 1) * len(page_links)} URLs approx)",
            )

    # ─────────────────────────────────────────────────────────────────────
    # Phase 2 — extract emails from each article
    # ─────────────────────────────────────────────────────────────────────

    def extract_email_and_author(self, article_url):
        """Extract corresponding-author email(s) from one Springer article page."""
        self.driver.get(article_url)
        time.sleep(2)

        try:
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'ul.c-article-author-list'))
            )

            author_list = self.driver.find_element(By.CSS_SELECTOR, 'ul.c-article-author-list')
            self.driver.execute_script(
                "arguments[0].scrollIntoView({behavior:'smooth',block:'center'});", author_list
            )
            time.sleep(0.5)

            # Expand "Show authors" if button exists
            try:
                btn = self.driver.find_element(
                    By.CSS_SELECTOR,
                    'button.c-article-author-list__button[aria-expanded="false"]'
                )
                self.driver.execute_script("arguments[0].click();", btn)
                self.logger.info("Springer ==> Expanded author list")
                time.sleep(1)
            except Exception:
                pass

            all_author_links = self.driver.find_elements(
                By.CSS_SELECTOR, 'a[data-test="author-name"]'
            )
            self.logger.info(f"Springer ==> {len(all_author_links)} authors on page")

            corresponding_authors = [
                lnk for lnk in all_author_links
                if lnk.find_elements(By.CSS_SELECTOR, 'svg[aria-hidden="true"]')
            ]

            if not corresponding_authors:
                self.logger.warning(f"Springer ==> No corresponding authors on {article_url}")
                self.save_to_csv([[article_url, "N/A", "N/A", self.conference_name]], self.authors_csv,
                                 header=["Article_URL", "Author_Name", "Email", "Conference_Name"])
                return

            author_info = []
            seen_emails = set()

            for idx, author_el in enumerate(corresponding_authors, 1):
                try:
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({behavior:'smooth',block:'center'});", author_el
                    )
                    time.sleep(0.5)

                    author_name_raw = author_el.text.strip()
                    author_name = author_name_raw.split('\n')[0].strip()

                    self.logger.info(f"Springer ==> Processing author {idx}: {author_name}")
                    self.driver.execute_script("arguments[0].click();", author_el)
                    time.sleep(2)

                    email            = None
                    popup_author_name = None

                    # Try new popup structure
                    try:
                        WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located(
                                (By.CSS_SELECTOR, 'div.app-researcher-popup__contacts')
                            )
                        )
                        popups = self.driver.find_elements(
                            By.CSS_SELECTOR, 'div.app-researcher-popup'
                        )
                        popup = next(
                            (p for p in popups
                             if p.is_displayed() and 'u-js-hide' not in p.get_attribute('class')),
                            None
                        )
                        if popup:
                            try:
                                popup_author_name = popup.find_element(
                                    By.CSS_SELECTOR, 'h3.app-researcher-popup__subheading'
                                ).text.strip()
                            except Exception:
                                pass
                            try:
                                email_link = popup.find_element(
                                    By.CSS_SELECTOR,
                                    'a[data-track="click_corresponding_email"][href^="mailto:"]'
                                )
                                email = email_link.get_attribute("href").replace("mailto:", "").strip()
                            except Exception:
                                pass
                    except Exception:
                        # Try old popup structure
                        try:
                            WebDriverWait(self.driver, 5).until(
                                EC.presence_of_element_located(
                                    (By.CSS_SELECTOR, 'ul.c-author-popup__author-list')
                                )
                            )
                            popup = self.driver.find_element(By.CSS_SELECTOR, 'div.c-author-popup')
                            try:
                                email_link = popup.find_element(
                                    By.CSS_SELECTOR, 'a.c-author-popup__link[href^="mailto:"]'
                                )
                                email = email_link.get_attribute("href").replace("mailto:", "").strip()
                            except Exception:
                                pass
                        except Exception:
                            pass

                    # Skip if popup name doesn't match
                    if popup_author_name and popup_author_name != author_name:
                        self.logger.warning(
                            f"Springer ==> Mismatch: clicked '{author_name}' "
                            f"but popup shows '{popup_author_name}' — skipping"
                        )
                        email = None

                    if email and email not in seen_emails:
                        seen_emails.add(email)
                        final_name = popup_author_name or author_name
                        author_info.append([article_url, final_name, email])
                        self.logger.info(f"Springer ==> ✅ {final_name}: {email}")
                    elif email:
                        self.logger.info(f"Springer ==> Duplicate email skipped: {email}")
                    else:
                        self.logger.warning(f"Springer ==> No email for {author_name}")

                    # Close popup
                    try:
                        for close_btn in self.driver.find_elements(
                            By.CSS_SELECTOR, "button.c-popup__close"
                        ):
                            if close_btn.is_displayed():
                                self.driver.execute_script("arguments[0].click();", close_btn)
                                time.sleep(0.3)
                                break
                        else:
                            self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                    except Exception:
                        pass

                    # Force-hide any stale popup
                    try:
                        self.driver.execute_script("""
                            document.querySelectorAll(
                                'div.app-researcher-popup, div.c-popup'
                            ).forEach(p => {
                                p.classList.add('u-js-hide');
                                p.style.display = 'none';
                            });
                        """)
                    except Exception:
                        pass

                except Exception as e:
                    self.logger.error(f"Springer ==> Error for author {idx}: {e}")
                    try:
                        self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                    except Exception:
                        pass
                    continue

            if author_info:
                self.save_to_csv(author_info, self.authors_csv,
                                 header=["Article_URL", "Author_Name", "Email", "Conference_Name"])
            else:
                self.save_to_csv([[article_url, "N/A", "N/A", self.conference_name]], self.authors_csv,
                                 header=["Article_URL", "Author_Name", "Email", "Conference_Name"])

        except Exception as e:
            self.logger.error(f"Springer ==> Failed on article {article_url}: {e}")
            self.save_to_csv([[article_url, "N/A", "N/A", self.conference_name]], self.authors_csv,
                                 header=["Article_URL", "Author_Name", "Email", "Conference_Name"])

    # ─────────────────────────────────────────────────────────────────────
    # Main entry point (called by scraper_adapter / SeleniumScraperWrapper)
    # ─────────────────────────────────────────────────────────────────────

    def run(self):
        """
        Execute the full scrape: Phase 1 (URLs) → Phase 2 (emails).
        Returns (output_file_path, summary_string).
        """
        try:
            search_url = (
                f"https://link.springer.com/search?new-search=true&query={self.keyword}"
                f"&content-type=article&content-type=research&content-type=review"
                f"&content-type=conference+paper&content-type=news&date=custom"
                f"&dateFrom={self.start_year.split('/')[-1]}"
                f"&dateTo={self.end_year.split('/')[-1]}&sortBy=relevance"
            )
            self.logger.info(f"Springer ==> Search URL: {search_url}")

            # ── Phase 1: collect article URLs ────────────────────────────
            self._progress(5, "PHASE 1: Extracting article URLs...")
            self.driver.get(search_url)
            self.dismiss_cookie_banner()
            total_pages = self.get_total_pages()

            if total_pages == 0:
                self.logger.warning("Springer ==> No results found — aborting.")
                return (None, "No results found")

            self.extract_article_links(search_url, total_pages)
            article_links = self.load_links_from_csv()

            if not article_links:
                self.logger.warning("Springer ==> No article links extracted.")
                return (None, "No article links extracted")

            self.logger.info(f"Springer ==> Phase 1 complete: {len(article_links)} articles")

            # ── Phase 2: extract emails ──────────────────────────────────
            self._progress(40, f"PHASE 2: Extracting emails from {len(article_links)} articles...")
            total = len(article_links)
            consecutive_failures = 0

            for i, article_url in enumerate(article_links):
                if not self._is_driver_alive():
                    self.logger.warning("Springer ==> Driver dead — reinitialising...")
                    try:
                        self._reinit_driver()
                        consecutive_failures = 0
                    except Exception as e:
                        self.logger.error(f"Springer ==> Driver reinit failed: {e}")
                        self.logger.error("Springer ==> Saving partial results and stopping.")
                        break

                try:
                    self.extract_email_and_author(article_url)
                    consecutive_failures = 0
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    self.logger.error(f"Springer ==> Article {i + 1} failed: {e}")
                    consecutive_failures += 1
                    if consecutive_failures >= 3:
                        self.logger.warning("Springer ==> 3 consecutive failures — reinitialising driver...")
                        try:
                            self._reinit_driver()
                            consecutive_failures = 0
                        except Exception:
                            self.logger.error("Springer ==> Reinit failed — stopping.")
                            break
                    continue

                pct = int(40 + ((i + 1) / total) * 55)   # 40 → 95%
                self._progress(
                    pct,
                    f"Email extraction: {i + 1}/{total} articles",
                    current_url=article_url,
                )

            output_file = os.path.join(self.directory, self.authors_csv)
            self._progress(100, f"Completed: {total} articles processed")
            self.logger.info(f"Springer ==> Scraping complete. Output: {output_file}")
            return (output_file, f"Springer scrape complete: {total} articles")

        finally:
            try:
                self.driver.quit()
            except Exception:
                pass
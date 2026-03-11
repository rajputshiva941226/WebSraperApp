# # Fix for Python 3.12+ distutils compatibility
# try:
#     import setuptools
#     import sys
#     if sys.version_info >= (3, 12):
#         import importlib.util
#         spec = importlib.util.find_spec('setuptools._distutils')
#         if spec:
#             sys.modules['distutils'] = importlib.import_module('setuptools._distutils')
# except ImportError:
#     pass

# import os, argparse, csv, logging, time, math, sys
# from selenium import webdriver
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.common.by import By
# from selenium.webdriver.chrome.service import Service
# from selenium.webdriver.chrome.options import Options
# from selenium.webdriver.support import expected_conditions as EC
# from webdriver_manager.chrome import ChromeDriverManager
# from selenium.webdriver.common.action_chains import ActionChains
# from selenium.webdriver.common.keys import Keys
# from urllib.parse import urlencode
# import undetected_chromedriver as uc
# import tempfile


# class SageScraper:
#     def __init__(self, keyword, start_year, end_year, driver_path):
#         # Configure logging first to ensure root logger is set up
#         logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
#         self.logger = logging.getLogger(__name__)
#         self.keyword = keyword
#         self.start_year = start_year
#         self.end_year = end_year
#         self.options = Options()
        
#         self.options.add_argument("--window-size=1920,1080")
#         #self.options.add_argument("--force-device-scale-factor=1")
#         self.options.add_argument("--disable-notifications")
#         self.options.add_argument("--disable-background-timer-throttling")
#         self.options.add_argument("--disable-backgrounding-occluded-windows")
#         self.options.add_argument("--disable-renderer-backgrounding")
#         self.options.add_argument("--disable-notifications")
        
        
#         self.options.add_argument("--no-sandbox")
        
#         self.options.add_argument("--disable-infobars")
#         self.options.add_argument("--disable-browser-side-navigation")
        
#         self.options.add_argument("--disable-popup-blocking")
#         self.options.add_argument("--disable-crash-reporter")
#         self.options.add_argument("--disable-dev-shm-usage")
#         self.options.add_argument("--disable-logging")
#         self.uc_temp_dir = tempfile.mkdtemp(prefix="Sage_")
#         self.driver = uc.Chrome(
#             options=self.options,
#             driver_executable_path=driver_path,
#             version_main=None,  # Auto-detect Chrome version
#             use_subprocess=False  # Important for multiprocessing
#         )
#         self.wait = WebDriverWait(self.driver, 20)
#         self.directory = keyword.replace(" ","-")

#         self.url_csv = f"Sage_{self.directory}-{start_year.replace('/', '-')}-{end_year.replace('/', '-')}_urls.csv"
#         self.authors_csv = f"Sage_{self.directory}-{start_year.replace('/', '-')}-{end_year.replace('/', '-')}_authors.csv"

#         self._setup_logger()  # Initialize the logger configuration
#         self.driver.maximize_window()
#         self.driver.set_page_load_timeout(180)
#         self.driver.set_script_timeout(180)
#         self.run()

#     def _setup_logger(self):
#         """Configure the logger with both file and stdout handlers (UTF-8 safe)."""
#         self.logger = logging.getLogger(self.__class__.__name__)
#         self.logger.setLevel(logging.INFO)

#         log_dir = "logs"
#         os.makedirs(log_dir, exist_ok=True)
#         log_file = os.path.join(
#             log_dir, 
#             f"{self.__class__.__name__}-{self.directory}-{self.start_year.replace('/', '-')}-{self.end_year.replace('/', '-')}.log"
#         )

#         # Ensure sys.stdout supports UTF-8 for emoji printing
#         sys.stdout.reconfigure(encoding='utf-8')

#         # Remove existing handlers to avoid duplication
#         if self.logger.hasHandlers():
#             self.logger.handlers.clear()

#         # File handler (UTF-8 encoding)
#         file_handler = logging.FileHandler(log_file, encoding="utf-8")
#         file_handler.setLevel(logging.INFO)

#         # Stream handler for logging to stdout
#         stream_handler = logging.StreamHandler(sys.stdout)
#         stream_handler.setLevel(logging.INFO)

#         # Formatter for both handlers
#         formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
#         file_handler.setFormatter(formatter)
#         stream_handler.setFormatter(formatter)

#         self.logger.addHandler(file_handler)
#         self.logger.addHandler(stream_handler)
#     def save_to_csv(self, data, filename, header=None):
#         """Save data to a CSV file."""
#         try:
#             os.makedirs(self.directory, exist_ok=True)
#             filepath = os.path.join(self.directory, filename)
#             with open(filepath, mode="a", newline="", encoding="utf-8") as file:
#                 writer = csv.writer(file)
#                 if os.path.getsize(filepath) == 0 and header:  # Write header only if file is empty
#                     writer.writerow(header)
#                 writer.writerows(data)
#             self.logger.info(f"Sage ==> Saved data to {filepath}.")
#         except Exception as e:
#             self.logger.error(f"Sage ==> Failed to save data to CSV: {e}")

#     def get_total_pages(self):
#         """Retrieve the total number of pages from the search results."""
#         try:
#             stats_element = self.wait.until(
#                 EC.presence_of_element_located((By.CSS_SELECTOR, "span.result__count"))
#             )
#             total_results_text = stats_element.text.split()[-1]
#             total_results = int(total_results_text)
#             total_pages = math.ceil(total_results / 100)
#             self.logger.info(f"Sage ==> Total results: {total_results}, Total pages: {total_pages}")
#             return total_pages
#         except Exception as e:
#             self.logger.error(f"Sage ==> Failed to get total pages: {e}")
#             return 0

#     def extract_article_links(self, total_pages, base_url, query_params):
#         """Extract article links from each page and save them to a CSV file."""
#         #all_links = []

#         for page in range(0, total_pages):
#             query_params["startPage"] = page  # Update page number in query params
#             page_url = f"{base_url}?{urlencode(query_params)}"
#             self.driver.get(page_url)

#             time.sleep(2)  # Allow time for page to load

#             try:
#                 links = self.wait.until(
#                     EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'div.issue-item__title > a[data-id="srp-article-title"]'))
#                 )
#                 page_links = [[link.get_attribute("href")] for link in links if link.get_attribute("href")]
#                 self.save_to_csv(page_links, self.url_csv, header=["Article_URL"])
#                 #all_links.extend(page_links)
#                 self.logger.info(f"Sage ==> Extracted {len(page_links)} links from page {page}.")
#             except Exception as e:
#                 self.logger.error(f"Sage ==> Failed to extract links from page {page}: {e}")


#     def extract_author_info(self):
#         """Read article URLs from the CSV file and extract corresponding author name and email."""
#         filepath = os.path.join(self.directory, self.url_csv)
#         if not os.path.exists(filepath):
#             self.logger.error("Sage ==> URLs file not found! Run extract_article_links() first.")
#             return

#         extracted_data = []
#         with open(filepath, mode="r", encoding="utf-8") as file:
#             reader = csv.reader(file)
#             next(reader)  # Skip header

#             for row in reader:
#                 article_url = row[0]
#                 self.driver.get(article_url)
#                 time.sleep(2)  # Allow time for the page to load

#                 try:
#                     # Open the author section
#                     author_section = self.wait.until(
#                         EC.element_to_be_clickable((By.CSS_SELECTOR, "a.to-authors-affiliations"))
#                     )
#                     author_section.click()

#                     # Wait for the "Show all" button
#                     show_all = self.wait.until(
#                         EC.element_to_be_clickable((By.CSS_SELECTOR, 'div.expand-all-wrapper > button[data-label-expand="Show all"]'))
#                     )

#                     # Scroll into view and click
#                     self.driver.execute_script("arguments[0].scrollIntoView();", show_all)
#                     time.sleep(1)  # Small delay before clicking

#                     try:
#                         show_all.click()
#                         time.sleep(2)
#                     except:
#                         self.driver.execute_script("arguments[0].click();", show_all)

#                     self.logger.info("Sage ==> Show All button clicked.")

#                     # Find all authors
#                     authors = self.driver.find_elements(By.CSS_SELECTOR, "section.core-authors div[property='author']")
                    
#                     for author in authors:
#                         # Extract given name and family name
#                         given_name = author.find_element(By.CSS_SELECTOR, "span[property='givenName']").text
#                         family_name = author.find_element(By.CSS_SELECTOR, "span[property='familyName']").text
#                         full_name = f"{given_name} {family_name}"
                        
#                         # Extract email if available
#                         try:
#                             email = author.find_element(By.CSS_SELECTOR, "div.core-email > a[property='email']")
#                             email = email.get_attribute("href").replace("mailto:", "")
#                         except:
#                             email = None  # If no email found
                        
#                         # Save data immediately to CSV
#                         if email is not None:
#                             self.save_to_csv([[article_url, full_name, email]], self.authors_csv, header=["Article_URL", "Author_Name", "Email"])
#                             self.logger.info(f"Sage ==> Extracted: {full_name} - {email}")
#                         else:
#                             pass

#                 except Exception as e:
#                     self.logger.error(f"Sage ==> Failed to extract author info from {article_url}: {e}")
#                     self.save_to_csv([[article_url, "N/A", "N/A"]], self.authors_csv, header=["Article_URL", "Author_Name", "Email"])
#     def run(self):
#         try:
#             query_params = {
#                 "field1":"AllField",
#                 "text1":self.keyword,
#                 "AfterMonth":self.start_year.split("/")[0],
#                 "AfterYear":self.start_year.split("/")[-1],
#                 "BeforeMonth":self.end_year.split("/")[0],
#                 "BeforeYear":self.end_year.split("/")[-1],
#                 "pageSize":100,
#                 "startPage":0
#             }
#             base_url = "https://journals.sagepub.com/action/doSearch"
#             search_url = f"{base_url}?{urlencode(query_params)}"
#             self.driver.get("https://journals.sagepub.com")
#             time.sleep(30)
#             cookie_section = self.wait.until(
#                     EC.presence_of_element_located((By.ID, "onetrust-accept-btn-handler"))
#                 )
            
#             cookie_section.click()
#             self.driver.get(search_url)
#             time.sleep(20)
#             total_pages = self.get_total_pages()
#             if total_pages > 0:
                    
#                 self.extract_article_links(total_pages, base_url, query_params)
#                 self.extract_author_info()  # Extracts author info after collecting URLs

#         finally:
#             self.driver.quit()


# # if __name__ == "__main__":
# #     parser = argparse.ArgumentParser(description="Scrape article links and author details from Emrald Insights.")
# #     parser.add_argument("--keyword", type=str, required=True, help="Keyword for the search query.")
# #     parser.add_argument("--start_year", type=str, required=True, help="Start date in MM/DD/YYYY format.")
# #     parser.add_argument("--end_year", type=str, required=True, help="End date in MM/DD/YYYY format.")
# #     args = parser.parse_args()
# #     # Set a global cache path for WebDriverManager
# #     os.environ["WDM_CACHE_PATH"] = "C:/shared_drivers"  # Custom shared directory

# # #   Install ChromeDriver once and get its path
# #     driver_path = ChromeDriverManager().install()
# #     scraper = SageScraper(args.keyword, args.start_year, args.end_year, driver_path)
# #     #scraper.run()


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


class SageScraper:
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
        self._start_virtual_display()
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
        Start a Xvfb virtual display so Chrome can run in non-headless mode
        on a headless server (EC2).  Two backends tried in order:
          1. pyvirtualdisplay (preferred — cleaner Python API)
          2. Raw subprocess Xvfb on display :99 (fallback)

        Install: pip install pyvirtualdisplay
                 apt-get install -y xvfb
        """
        # Try pyvirtualdisplay first
        try:
            from pyvirtualdisplay import Display
            self._display = Display(visible=False, size=(1920, 1080), backend='xvfb')
            self._display.start()
            self.logger.info(
                f"Sage ==> Virtual display started via pyvirtualdisplay "
                f"(DISPLAY={os.environ.get('DISPLAY', 'unset')})"
            )
            return
        except ImportError:
            self.logger.warning(
                "Sage ==> pyvirtualdisplay not installed — "
                "falling back to raw Xvfb on :99"
            )
        except Exception as e:
            self.logger.warning(f"Sage ==> pyvirtualdisplay failed: {e} — trying raw Xvfb")

        # Fallback: raw Xvfb subprocess on display :99
        try:
            import subprocess
            # Kill any stale Xvfb on :99
            subprocess.run(["pkill", "-f", "Xvfb :99"], capture_output=True)
            time.sleep(0.5)
            self._xvfb_proc = subprocess.Popen(
                ["Xvfb", ":99", "-screen", "0", "1920x1080x24"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            os.environ["DISPLAY"] = ":99"
            time.sleep(1)   # give Xvfb time to start
            self.logger.info("Sage ==> Raw Xvfb started on display :99")
        except FileNotFoundError:
            self.logger.error(
                "Sage ==> Xvfb not found. Install with: sudo apt-get install -y xvfb\n"
                "Sage ==> Chrome will run WITHOUT a display — may fail on Sage."
            )
        except Exception as e:
            self.logger.error(f"Sage ==> Could not start Xvfb: {e}")

    def _stop_virtual_display(self):
        """Cleanly stop the virtual display."""
        try:
            if self._display is not None:
                self._display.stop()
                self._display = None
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
            self.driver = uc.Chrome(
                options=options,
                driver_executable_path=self.driver_path,
                version_main=None,
                use_subprocess=False,
            )
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

    def get_total_pages(self) -> int:
        try:
            el = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "span.result__count"))
            )
            total_results = int(el.text.split()[-1].replace(",", ""))
            total_pages   = math.ceil(total_results / 100)
            self.logger.info(
                f"Sage ==> Total results: {total_results}, pages: {total_pages}"
            )
            return total_pages
        except Exception as e:
            self.logger.error(f"Sage ==> Failed to get total pages: {e}")
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
            query_params = {
                "field1":      "AllField",
                "text1":       self.keyword,
                "AfterMonth":  self.start_year.split("/")[0],
                "AfterYear":   self.start_year.split("/")[-1],
                "BeforeMonth": self.end_year.split("/")[0],
                "BeforeYear":  self.end_year.split("/")[-1],
                "pageSize":    100,
                "startPage":   0,
            }
            base_url   = "https://journals.sagepub.com/action/doSearch"
            search_url = f"{base_url}?{urlencode(query_params)}"

            # Initialise CSV files
            self._init_csv(self.url_csv,     ["Article_URL"])
            self._init_csv(self.authors_csv, ["Article_URL", "Author_Name", "Email"])

            # ── Navigate to Sage and dismiss cookie banner ────────────────
            self._progress(2, "Opening Sage Journals homepage...")
            self.driver.get("https://journals.sagepub.com")
            time.sleep(15)   # Sage loads slowly — give it time before cookie click
            self._accept_cookies()
            time.sleep(3)

            # ── Phase 1: collect article URLs ─────────────────────────────
            self._progress(5, "PHASE 1: Collecting article URLs...")
            self.driver.get(search_url)
            time.sleep(8)   # let results load fully

            total_pages = self.get_total_pages()
            if total_pages == 0:
                self.logger.warning("Sage ==> No results found — aborting.")
                return authors_path, "No results found"

            self.extract_article_links(total_pages, base_url, query_params)

            # ── Phase 2: extract emails ───────────────────────────────────
            self._progress(40, "PHASE 2: Extracting author emails...")
            self.extract_author_info()

            self._progress(100, "Sage scraping completed.")
            self.logger.info("Sage ==> Scraping complete.")
            return authors_path, f"Sage scrape complete: {total_pages} pages"

        finally:
            # Always quit Chrome and stop the virtual display
            try:
                if self.driver:
                    self.driver.quit()
            except Exception:
                pass
            self._stop_virtual_display()
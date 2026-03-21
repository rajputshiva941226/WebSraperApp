from chrome_display_mixin import ChromeDisplayMixin

try:
    import setuptools
    import sys
    if sys.version_info >= (3, 12):
        import importlib.util
        spec = importlib.util.find_spec('setuptools._distutils')
        if spec:
            sys.modules['distutils'] = importlib.import_module('setuptools._distutils')
except ImportError:
    pass

import os, argparse, csv, logging, time, math, re, sys
import selenium
from selenium import webdriver
from selenium.common.exceptions import WebDriverException, TimeoutException, NoSuchWindowException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains
from urllib.parse import urlencode
import undetected_chromedriver as uc
from datetime import datetime
import tempfile


class BMJJournalScraper(ChromeDisplayMixin):
    def __init__(self, keyword, start_year, end_year, driver_path,
             output_dir=None, progress_callback=None,
             conference_name=""):
        # ── MATCH SAGE PATTERN EXACTLY ────────────────────────────────────────
        # 1. Set all attributes first (raw strings, no conversion yet)
        # 2. Set up logger (_setup_logger uses self.start_year for log filename)
        # 3. Convert dates
        # 4. DO NOT call _initialize_driver() or run() — SeleniumScraperWrapper does it
        self._vdisplay = None
        self.driver = None
        self.wait = None
        self.output_dir = output_dir
        self.progress_callback = progress_callback
        self.driver_path = driver_path
        self.directory = keyword.replace(" ", "-")
        self.keyword         = keyword
        self.conference_name = conference_name

        # Store RAW date strings first — _setup_logger uses them for the log filename
        self.start_year = start_year
        self.end_year = end_year

        # Now logger is safe to set up (self.start_year and self.end_year exist)
        self._setup_logger()

        # Now convert dates for use in URLs and CSV filenames
        self.start_year = self.convert_date_format(start_year)
        self.end_year = self.convert_date_format(end_year)
        conf = f"_{conference_name}" if conference_name else ""
        self.url_csv = f"BMJ_{self.directory}-{self.start_year}-{self.end_year}{conf}_urls.csv"
        self.authors_csv = f"BMJ_{self.directory}-{self.start_year}-{self.end_year}{conf}_authors.csv"

    def _initialize_driver(self):
        """Initialize the Chrome driver"""
        try:
            self._launch_chrome(self._build_default_chrome_options(), driver_path=self.driver_path)
            self.wait = WebDriverWait(self.driver, 20)
            # maximize_window() removed — triggers Runtime.evaluate on Chrome 145+uc 3.5.5
            # Window size is already set via --window-size=1400,900 in the mixin
            self.logger.info("Driver initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize driver: {e}")
            raise

    def _restart_driver(self):
        """Restart the Chrome driver in case of crashes"""
        try:
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
            time.sleep(2)
            self._initialize_driver()
            self.logger.info("Driver restarted successfully")
        except Exception as e:
            self.logger.error(f"Failed to restart driver: {e}")
            raise

    def _report_progress(self, pct, msg, current_url="", authors_count=0, links_count=0):
        """Report progress to Celery job UI — same pattern as Cambridge scraper."""
        self.logger.info(f"BMJ ==> [{pct}%] {msg}")
        if self.progress_callback:
            try:
                self.progress_callback(
                    pct, msg,
                    current_url=current_url,
                    authors_count=authors_count,
                    links_count=links_count,
                )
            except Exception:
                pass

    def _bypass_cloudflare(self, timeout: int = 90) -> bool:
        """
        Bypass Cloudflare Turnstile using ActionChains + JS click.
        Walks all iframes up to 3 levels. ActionChains sends real ChromeDriver
        mouse events; JS dispatchEvent is the fallback.
        """
        import random
        from selenium.webdriver.common.action_chains import ActionChains

        CHALLENGE_PHRASES = [
            "just a moment", "verifying you are human",
            "performing security verification", "checking your browser",
            "cf-browser-verification",
        ]
        tag = "BMJ ==>"
        CF_SELECTORS = [
            "input[type='checkbox']", "div.ctp-checkbox-label",
            ".mark", "span.mark", "label[for='cf-stage']",
            "div[id*='challenge']", "div[class*='checkbox']",
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

        def _click_element(el, label):
            time.sleep(random.uniform(0.4, 0.9))
            try:
                ActionChains(self.driver).move_to_element(el).pause(
                    random.uniform(0.3, 0.7)
                ).click().perform()
                self.logger.info(f"{tag} ActionChains clicked: {label}")
                return True
            except Exception:
                pass
            try:
                self.driver.execute_script("""
                    var el=arguments[0],r=el.getBoundingClientRect();
                    var cx=r.left+r.width/2+(Math.random()-0.5)*3;
                    var cy=r.top+r.height/2+(Math.random()-0.5)*3;
                    ['mousedown','mouseup','click'].forEach(function(t){
                        el.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,
                            clientX:cx,clientY:cy,view:window}));
                    });
                """, el)
                self.logger.info(f"{tag} JS clicked: {label}")
                return True
            except Exception:
                return False

        def _try_in_frame(level=0):
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
            try:
                frames = self.driver.find_elements(By.TAG_NAME, "iframe")
                self.logger.info(f"{tag} {len(frames)} iframes at depth {level}")
                for idx, frame in enumerate(frames):
                    try:
                        self.driver.switch_to.frame(frame)
                        time.sleep(0.6)
                        if _try_in_frame(level + 1):
                            return True
                        self.driver.switch_to.parent_frame()
                        time.sleep(0.3)
                    except Exception:
                        try:
                            self.driver.switch_to.default_content()
                        except Exception:
                            pass
            except Exception:
                pass
            return False

        _wait_ready()
        time.sleep(2)
        if not _on_challenge():
            self.logger.info(f"{tag} No Cloudflare challenge — page ready ✓")
            return True

        self.logger.info(f"{tag} Cloudflare detected — ActionChains+JS bypass...")
        deadline = time.time() + timeout
        last_click = 0
        attempt = 0

        while time.time() < deadline:
            _wait_ready(sec=5)
            if not _on_challenge():
                self.logger.info(f"{tag} Cloudflare cleared ✓")
                return True
            _human_activity()
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
                except Exception:
                    clicked = False
                finally:
                    try:
                        self.driver.switch_to.default_content()
                    except Exception:
                        pass
                if clicked:
                    time.sleep(4)
                    if not _on_challenge():
                        self.logger.info(f"{tag} Cleared after click ✓")
                        return True
            remaining = int(deadline - time.time())
            self.logger.info(f"{tag} Cloudflare active ({remaining}s left)...")
            time.sleep(2)

        self.logger.warning(f"{tag} Bypass timed out after {timeout}s")
        try:
            os.makedirs("logs", exist_ok=True)
            self.driver.save_screenshot("logs/bmj_debug_cloudflare_timeout.png")
        except Exception:
            pass
        return False


    def _setup_logger(self):
        """Configure the logger with both file and stdout handlers (UTF-8 safe)."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)

        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(
            log_dir, 
            f"{self.__class__.__name__}-{self.directory}-{self.start_year.replace('/', '-')}-{self.end_year.replace('/', '-')}.log"
        )

        # Ensure sys.stdout supports UTF-8 for emoji printing
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')

        # Remove existing handlers to avoid duplication
        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        # File handler (UTF-8 encoding)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)

        # Stream handler for logging to stdout
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.INFO)

        # Formatter for both handlers
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        stream_handler.setFormatter(formatter)

        self.logger.addHandler(file_handler)
        self.logger.addHandler(stream_handler)
        
    def convert_date_format(self, date_str):
        """Convert date from MM/DD/YYYY to YYYY-MM-DD format."""
        try:
            input_date = datetime.strptime(date_str, "%m/%d/%Y")
            output_date = input_date.strftime("%Y-%m-%d")
            return output_date
        except ValueError as e:
            self.logger.error(f"Invalid date format: {date_str}. Error: {e}")
            return None

    def save_to_csv(self, data, filename, header=None):
        """Save data to CSV. Uses output_dir if available. Filters out N/A rows."""
        try:
            work_dir = self.output_dir if self.output_dir else self.directory
            os.makedirs(work_dir, exist_ok=True)
            filepath = os.path.join(work_dir, filename)
            file_exists = os.path.exists(filepath) and os.path.getsize(filepath) > 0

            # Only write rows that have a real email address
            if filename == self.authors_csv:
                data = [
                    row for row in data
                    if len(row) >= 3
                    and row[2] not in ("N/A", "ERROR", "", None)
                    and "@" in str(row[2])
                ]
                if not data:
                    return  # Nothing valid to write

            with open(filepath, mode="a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                if not file_exists and header:
                    writer.writerow(header)
                writer.writerows(data)
            self.logger.info(f"BMJ ==> Saved {len(data)} row(s) → {filepath}")
        except Exception as e:
            self.logger.error(f"BMJ ==> CSV save failed: {e}")

    def get_total_pages(self):
        """
        Retrieve total result count from BMJ search results.

        Confirmed HTML structure (from live page inspection):
            <div class="highwire-search-summary" id="search-summary-wrapper">
                228 results
            </div>

        Primary selectors target this element. Fallbacks cover layout changes.
        """
        import re

        # Primary: confirmed selectors from live page — try in order
        PRIMARY_SELECTORS = [
            "div.highwire-search-summary#search-summary-wrapper",  # exact confirmed
            "#search-summary-wrapper",                             # by id
            "div.highwire-search-summary",                        # by class
        ]
        # Fallbacks for future layout changes
        FALLBACK_SELECTORS = [
            "div.search-summary",
            "span.result-count",
            "[data-test='search-summary']",
            "span[class*='result']",
            "h2[class*='result']",
            "p.results-number",
        ]

        # Wait for page body to settle before looking for result count
        time.sleep(3)

        for sel in PRIMARY_SELECTORS + FALLBACK_SELECTORS:
            try:
                el = WebDriverWait(self.driver, 6).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                )
                text = el.text.strip()
                if not text:
                    continue
                self.logger.info(f"BMJ ==> Result element [{sel}]: '{text[:80]}'")
                # e.g. "228 results" → extract leading number
                nums = re.findall(r"[\d,]+", text)
                for n in nums:
                    n_clean = n.replace(",", "")
                    if n_clean.isdigit() and int(n_clean) > 0:
                        total = int(n_clean)
                        pages = math.ceil(total / 100)
                        self.logger.info(f"BMJ ==> {total} results → {pages} pages")
                        return pages
            except Exception:
                continue

        # JS fallback: walk all DOM text nodes for "N results" pattern
        try:
            found = self.driver.execute_script("""
                var all = document.querySelectorAll('*');
                for (var i = 0; i < all.length; i++) {
                    var el = all[i];
                    if (el.children.length > 0) continue;
                    var t = (el.innerText || el.textContent || '').trim();
                    if (/^\\d[\\d,]* results?$/i.test(t)) return t;
                }
                return null;
            """)
            if found:
                nums = re.findall(r"[\d,]+", found)
                for n in nums:
                    n_clean = n.replace(",", "")
                    if n_clean.isdigit() and int(n_clean) > 0:
                        total = int(n_clean)
                        pages = math.ceil(total / 100)
                        self.logger.info(f"BMJ ==> JS text-scan found: '{found}' → {pages} pages")
                        return pages
        except Exception as e:
            self.logger.debug(f"BMJ ==> JS fallback failed: {e}")

        # Debug info when nothing found
        try:
            self.logger.error(f"BMJ ==> No result count found. URL: {self.driver.current_url}")
            os.makedirs("logs", exist_ok=True)
            self.driver.save_screenshot("logs/bmj_debug_no_results.png")
            self.logger.info("BMJ ==> Screenshot saved → logs/bmj_debug_no_results.png")
        except Exception:
            pass
        return 0

    def extract_article_links(self, total_pages, query_params):
        """Extract article links from each page — with live progress updates."""
        all_links = []
        total_saved = 0

        for page in range(0, total_pages):
            page_url = f"{query_params['base_url']}?page={page}"

            try:
                self.driver.get(page_url)
                time.sleep(3)

                links = self.wait.until(
                    EC.presence_of_all_elements_located(
                        (By.CSS_SELECTOR, 'a.highwire-cite-linked-title')
                    )
                )
                page_links = [
                    [lnk.get_attribute("href")]
                    for lnk in links if lnk.get_attribute("href")
                ]
                all_links.extend(page_links)
                total_saved += len(page_links)
                self.logger.info(
                    f"BMJ ==> Page {page+1}/{total_pages}: "
                    f"{len(page_links)} links (total {total_saved})"
                )
            except TimeoutException:
                self.logger.error(f"BMJ ==> Timeout on page {page+1}")
            except NoSuchWindowException:
                self.logger.error(f"BMJ ==> Window closed page {page+1}, restarting")
                self._restart_driver()
            except Exception as e:
                self.logger.error(f"BMJ ==> Error page {page+1}: {e}")

            pct = int(5 + ((page + 1) / total_pages) * 35)   # 5 → 40%
            self._report_progress(
                pct,
                f"URL collection: page {page+1}/{total_pages} ({total_saved} links)",
                current_url=page_url,
                links_count=total_saved,
            )

        self.save_to_csv(all_links, self.url_csv, header=["Article_URL"])

    def extract_author_info(self):
        """Read article URLs and scrape author emails — with live progress updates."""
        work_dir = self.output_dir if self.output_dir else self.directory
        filepath = os.path.join(work_dir, self.url_csv)
        if not os.path.exists(filepath):
            self.logger.error("BMJ ==> URLs file not found!")
            return

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                rows = list(csv.reader(f))
            all_urls = [r[0].strip() for r in rows[1:] if r and r[0].strip()]
        except Exception as e:
            self.logger.error(f"BMJ ==> Cannot read URL file: {e}")
            return

        total = len(all_urls)
        authors_found = 0
        self.logger.info(f"BMJ ==> Processing {total} articles for email extraction")

        for _idx, article_url in enumerate(all_urls, 1):
                if "veterinaryrecord.bmj.com" in article_url:
                    self.logger.info("Skipping veterinaryrecord.bmj.com URL")
                    continue

                max_retries = 3
                retry_count = 0
                
                while retry_count < max_retries:
                    try:
                        # Check if driver is still alive
                        try:
                            _ = self.driver.current_url
                        except (NoSuchWindowException, WebDriverException):
                            self.logger.warning("Driver not responsive, restarting...")
                            self._restart_driver()

                        self.driver.get(article_url + ".info")
                        time.sleep(3)

                        current_url = self.driver.current_url
                        author_info = []

                        if current_url.endswith(".info"):
                            # Old style author extraction
                            author_notes = self.driver.find_elements(By.CSS_SELECTOR, "li#corresp-1")

                            for note in author_notes:
                                corresp_text = note.text.strip()
                                self.logger.info(f"Original Text: {corresp_text}")

                                email_matches = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', corresp_text)
                                if not email_matches:
                                    self.logger.warning(f"No emails found for {article_url}")
                                    continue

                                text_parts = re.split(r'[\w\.-]+@[\w\.-]+\.\w+', corresp_text)
                                for i, email in enumerate(email_matches):
                                    name_part = text_parts[i].strip()
                                    to_remove = ["Correspondence to", "Dr", "Professor", ":", ";", "\n"]
                                    author_name = name_part
                                    for phrase in to_remove:
                                        author_name = author_name.replace(phrase, "").strip()

                                    author_name_final = author_name.split(",")[0].strip()
                                    self.logger.info(f"Extracted: {author_name_final} - {email}")
                                    author_info.append([article_url, author_name_final, email])

                        else:
                            # New style author extraction
                            try:
                                show_all = WebDriverWait(self.driver, 5).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR, '#show-all-button button'))
                                )
                                if show_all.is_displayed():
                                    actions = ActionChains(self.driver)
                                    actions.move_to_element(show_all).perform()
                                    show_all.click()
                                    time.sleep(2)
                            except TimeoutException:
                                self.logger.info(f"Show all button not found for {article_url}")

                            envelopes = self.driver.find_elements(By.CSS_SELECTOR, "#author-list-envelope-icon")

                            for ele in envelopes:
                                try:
                                    actions = ActionChains(self.driver)
                                    actions.move_to_element(ele).perform()
                                    time.sleep(0.5)
                                    ele.click()
                                    time.sleep(1)

                                    div_ele = WebDriverWait(self.driver, 10).until(
                                        EC.presence_of_element_located((By.CSS_SELECTOR, 'div#popover-border'))
                                    )
                                    
                                    email_href = div_ele.find_element(By.CSS_SELECTOR, 'p[data-testid^="author-popover-email"] > a[href^="mailto:"]')
                                    email = email_href.get_attribute("href").replace("mailto:", "").strip()
                                    author_name = div_ele.find_element(By.CSS_SELECTOR, 'p[data-testid="popover-title "]').text.strip()

                                    self.logger.info(f"Extracted: {author_name} - {email}")
                                    author_info.append([article_url, author_name, email])
                                except Exception as inner_e:
                                    self.logger.warning(f"Failed to extract from envelope: {inner_e}")
                                    continue

                        if author_info:
                            self.save_to_csv(author_info, self.authors_csv, header=["Article_URL", "Author_Name", "Email"])
                            authors_found += len(
                                [a for a in author_info if a[2] not in ("N/A", "ERROR")]
                            )
                        else:
                            self.save_to_csv([[article_url, "N/A", "N/A"]], self.authors_csv, header=["Article_URL", "Author_Name", "Email"])

                        pct = int(40 + (_idx / total) * 55)   # 40 → 95%
                        self._report_progress(
                            pct,
                            f"Author extraction: {_idx}/{total} ({authors_found} emails found)",
                            current_url=article_url,
                            authors_count=authors_found,
                            links_count=total,
                        )
                        # If successful, break the retry loop
                        break

                    except (NoSuchWindowException, WebDriverException) as e:
                        retry_count += 1
                        self.logger.error(f"Driver error on {article_url} (attempt {retry_count}/{max_retries}): {e}")
                        if retry_count < max_retries:
                            self._restart_driver()
                            time.sleep(5)
                        else:
                            self.logger.error(f"Max retries reached for {article_url}, skipping...")
                            self.save_to_csv([[article_url, "ERROR", "ERROR"]], self.authors_csv, header=["Article_URL", "Author_Name", "Email"])
                    
                    except Exception as e:
                        self.logger.error(f"Failed to extract author info from {article_url}: {e}")
                        self.save_to_csv([[article_url, "N/A", "N/A"]], self.authors_csv, header=["Article_URL", "Author_Name", "Email"])
                        break

    def run(self):
        """Main execution method — called by SeleniumScraperWrapper."""
        try:
            self._initialize_driver()

            # ── Step 1: Homepage + cookie consent ────────────────────────────
            # <button id="onetrust-accept-btn-handler">I Accept</button>
            self.logger.info("BMJ ==> Loading https://journals.bmj.com")
            self.driver.get("https://journals.bmj.com")
            time.sleep(5)

            try:
                btn = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "#onetrust-accept-btn-handler")
                    )
                )
                self.driver.execute_script("arguments[0].click();", btn)
                self.logger.info("BMJ ==> Cookie consent accepted (JS click)")
            except Exception:
                self.logger.info("BMJ ==> No cookie banner found")
            time.sleep(2)

            # ── Step 2: Navigate to /search form ─────────────────────────────
            self.logger.info("BMJ ==> Navigating to https://journals.bmj.com/search")
            self.driver.get("https://journals.bmj.com/search")
            time.sleep(5)

            # ── Step 3: Fill and submit the search form ───────────────────────
            # Form fields confirmed from live HTML:
            #   Search term : input[name="txtsimple"]     id="edit-txtsimple"
            #   From date   : input[name="limit_from[date]_replacement"]  type="date"
            #   Through date: input[name="limit_to[date]_replacement"]    type="date"
            #   Num results : select[name="numresults"]
            #   Submit      : #edit-button2  (below "Format Results" section)
            submitted = self._fill_and_submit_form()
            if not submitted:
                self.logger.error("BMJ ==> Form submission failed — aborting")
                return

            time.sleep(8)   # wait for results page to load

            # Handle Cloudflare if it appears after form submit
            self._bypass_cloudflare(timeout=60)

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

            total_pages = self.get_total_pages()
            if total_pages > 0:
                # Fix URL path encoding: form submit encodes spaces as "+" in the path
                # but Varnish rejects "+" in URL paths (only valid in query strings).
                # Replace "+" → "%20" in the path segment only.
                raw_url = self.driver.current_url
                from urllib.parse import urlparse, urlunparse
                p = urlparse(raw_url)
                clean_path = p.path.replace('+', '%20')
                clean_url  = urlunparse(p._replace(path=clean_path))
                if clean_url != raw_url:
                    self.logger.info(f"BMJ ==> Fixed URL path encoding: {clean_url[:80]}")
                query_params = {"base_url": clean_url, "page": 0}
                self._report_progress(5, f"Found {total_pages} page(s) — collecting URLs...")
                self.extract_article_links(total_pages, query_params)
                self._report_progress(40, "PHASE 2: Extracting author emails...")
                self.extract_author_info()
                self._report_progress(100, "BMJ scraping completed.")
            else:
                self.logger.error("BMJ ==> No pages found to scrape")

        except Exception as e:
            self.logger.error(f"BMJ ==> Error in run method: {e}", exc_info=True)
        finally:
            self._quit_chrome()

    def _fill_and_submit_form(self) -> bool:
        """
        Fill the BMJ advanced search form and submit it.

        Form fields (from live HTML at journals.bmj.com/search):
          txtsimple                    — Search Term (main keyword field)
          limit_from[date]_replacement — From date  (type="date", YYYY-MM-DD)
          limit_to[date]_replacement   — Through date
          numresults                   — Results per page (select, value="100")
          #edit-button2                — Submit button below Format Results section
        """
        import random
        from selenium.webdriver.common.keys import Keys

        self.logger.info(
            f"BMJ ==> Filling form: keyword='{self.keyword}' "
            f"from={self.start_year} to={self.end_year}"
        )

        try:
            # Wait for the search form to load
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.ID, "edit-txtsimple"))
            )
        except Exception as e:
            self.logger.error(f"BMJ ==> Search form not found: {e}")
            return False

        try:
            # ── 1. Fill keyword ───────────────────────────────────────────────
            kw_input = self.driver.find_element(By.ID, "edit-txtsimple")
            self.driver.execute_script("arguments[0].click();", kw_input)
            time.sleep(0.3)
            kw_input.clear()
            time.sleep(0.2)
            # Type character-by-character (human-like)
            for ch in self.keyword:
                kw_input.send_keys(ch)
                time.sleep(random.uniform(0.04, 0.12))
            self.logger.info(f"BMJ ==> Keyword typed: {self.keyword}")

            # ── 2. Fill date fields via JS (type="date" inputs) ───────────────
            # self.start_year / self.end_year are already in YYYY-MM-DD format
            js_dates = """
                var fromField = document.querySelector(
                    'input[name="limit_from[date]_replacement"]'
                );
                var toField = document.querySelector(
                    'input[name="limit_to[date]_replacement"]'
                );
                if (fromField) {
                    fromField.value = arguments[0];
                    fromField.dispatchEvent(new Event('change', {bubbles: true}));
                }
                if (toField) {
                    toField.value = arguments[1];
                    toField.dispatchEvent(new Event('change', {bubbles: true}));
                }
                return (fromField ? 'from_ok' : 'from_missing') +
                       '|' +
                       (toField ? 'to_ok' : 'to_missing');
            """
            result = self.driver.execute_script(js_dates, self.start_year, self.end_year)
            self.logger.info(f"BMJ ==> Date fields JS result: {result}")

            # ── 3. Set results per page to 100 ───────────────────────────────
            try:
                from selenium.webdriver.support.ui import Select
                numresults_el = self.driver.find_element(By.ID, "edit-numresults")
                Select(numresults_el).select_by_value("100")
                self.logger.info("BMJ ==> Results per page set to 100")
            except Exception as e:
                self.logger.warning(f"BMJ ==> Could not set numresults: {e}")

            # ── 4. Click submit button (#edit-button2 — below Format Results) ─
            time.sleep(0.5)
            submit_btn = self.driver.find_element(By.ID, "edit-button2")
            self.driver.execute_script("arguments[0].click();", submit_btn)
            self.logger.info("BMJ ==> Form submitted (JS click #edit-button2)")
            return True

        except Exception as e:
            self.logger.error(f"BMJ ==> Form fill error: {e}", exc_info=True)
            # Take debug screenshot
            try:
                os.makedirs("logs", exist_ok=True)
                self.driver.save_screenshot("logs/bmj_form_error.png")
            except Exception:
                pass
            return False

# if __name__ == "__main__":
#     parser = argparse.ArgumentParser(description="Scrape article links and author details from BMJ Journal.")
#     parser.add_argument("--keyword", type=str, required=True, help="Keyword for the search query.")
#     parser.add_argument("--start_year", type=str, required=True, help="Start date in MM/DD/YYYY format.")
#     parser.add_argument("--end_year", type=str, required=True, help="End date in MM/DD/YYYY format.")
#     args = parser.parse_args()
    
#     # Set a global cache path for WebDriverManager
#     os.environ["WDM_CACHE_PATH"] = "C:/shared_drivers"

#     # Install ChromeDriver once and get its path
#     driver_path = ChromeDriverManager().install()
    
#     # Create scraper instance and run
#     scraper = BMJJournalScraper(args.keyword, args.start_year, args.end_year, driver_path)
#     scraper.run()  # Only call run() once here, not in __init__
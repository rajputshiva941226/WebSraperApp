"""taylor_selenium.py — Taylor & Francis (tandfonline.com) scraper using ChromeDisplayMixin"""
from chrome_display_mixin import ChromeDisplayMixin

try:
    import setuptools, sys as _sys
    if _sys.version_info >= (3, 12):
        import importlib.util
        spec = importlib.util.find_spec('setuptools._distutils')
        if spec:
            _sys.modules['distutils'] = importlib.import_module('setuptools._distutils')
except ImportError:
    pass

import csv, logging, math, os, re, sys, time
from datetime import datetime
from urllib.parse import quote_plus

from fuzzywuzzy import fuzz, process as fuzz_process
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class TaylorScraper(ChromeDisplayMixin):
    """
    Taylor & Francis (tandfonline.com) scraper.
    Migrated from standalone uc.Chrome subclass to ChromeDisplayMixin.

    Search URL:
        https://www.tandfonline.com/action/doSearch
            ?field1=AllField&text1={keyword}&Ppub=&AfterYear={YYYY}&BeforeYear={YYYY}
            &pageSize=100&startPage={N}

    Article link selector : article.searchResultItem div.art_title span.hlFld-Title a
    Email selector        : span.overlay span.corr-sec span.corr-email a
    Author name selector  : a.author (siblings of the email span)
    """

    def __init__(self, keyword, start_year, end_year, driver_path,
                 output_dir=None, progress_callback=None,
                 conference_name=""):
        self._vdisplay         = None
        self.driver            = None
        self.wait              = None
        self.output_dir        = output_dir
        self.progress_callback = progress_callback
        self.driver_path       = driver_path
        self.directory         = keyword.replace(" ", "-")
        self.keyword           = keyword
        self.conference_name   = conference_name
        self.start_year        = start_year
        self.end_year          = end_year
        self._setup_logger()

        # Extract YYYY from MM/DD/YYYY or plain YYYY
        self.after_year  = start_year.split("/")[-1]
        self.before_year = end_year.split("/")[-1]

        _ts   = datetime.now().strftime("%H-%M-%S")
        _conf = f"_{conference_name}" if conference_name else ""
        _sd   = start_year.replace("/", "-")
        _ed   = end_year.replace("/", "-")
        _base = f"Taylor{_conf}_{self.directory}_{_sd}_{_ed}_{_ts}"
        self.url_csv     = f"{_base}_urls.csv"
        self.authors_csv = f"{_base}_authors.csv"

    # ── Logger (same pattern as BMJ — writes to logs/) ───────────────────────

    def _setup_logger(self):
        self.logger = logging.getLogger(f"TaylorScraper-{id(self)}")
        self.logger.setLevel(logging.INFO)
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(
            log_dir,
            f"TaylorScraper-{self.directory}"
            f"-{self.start_year.replace('/', '-')}"
            f"-{self.end_year.replace('/', '-')}.log"
        )
        if self.logger.hasHandlers():
            self.logger.handlers.clear()
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
        try:
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            ))
            self.logger.addHandler(fh)
        except Exception:
            pass
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
        self.logger.addHandler(sh)
        self.logger.info(f"Taylor ==> Logger initialised → {log_file}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _work_dir(self) -> str:
        d = self.output_dir if self.output_dir else self.directory
        os.makedirs(d, exist_ok=True)
        return d

    def _progress(self, pct, msg, current_url="", authors_count=0, links_count=0):
        self.logger.info(f"Taylor ==> [{pct}%] {msg}")
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

    def save_to_csv(self, data, filename, header=None):
        if filename == self.authors_csv:
            data = [r for r in data
                    if len(r) >= 3 and r[2] not in ("N/A", "ERROR", "", None)
                    and "@" in str(r[2])]
            if not data:
                return
        try:
            fp = os.path.join(self._work_dir(), filename)
            exists = os.path.exists(fp) and os.path.getsize(fp) > 0
            with open(fp, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if not exists and header:
                    w.writerow(header)
                w.writerows(data)
        except Exception as e:
            self.logger.error(f"Taylor ==> CSV save failed: {e}")

    def _init_csv(self, filename, header):
        fp = os.path.join(self._work_dir(), filename)
        with open(fp, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)
        self.logger.info(f"Taylor ==> Initialised {fp}")

    # ── Phase 1: collect article URLs ─────────────────────────────────────────


    def _bypass_cloudflare(self, timeout: int = 120) -> bool:
        """
        Wait for Cloudflare challenge to clear on tandfonline.com.
        Challenge requires human checkbox solve in VNC.
        RAISES RuntimeError on timeout → job marked FAILED.
        """
        CF_PHRASES = [
            "just a moment", "verifying you are human",
            "performing security verification", "checking your browser",
        ]

        def _on_cf() -> bool:
            try:
                t = self.driver.title.lower()
                s = self.driver.page_source.lower()[:800]
                return any(p in t or p in s for p in CF_PHRASES)
            except Exception:
                return False

        time.sleep(3)
        if not _on_cf():
            self.logger.info("Taylor ==> CF bypass: no challenge ✓")
            return True

        self.logger.warning(
            f"Taylor ==> ⚠️ Cloudflare challenge — solve in VNC within {timeout}s. "
            f"URL: {self.driver.current_url}"
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(3)
            if not _on_cf():
                self.logger.info("Taylor ==> CF bypass: challenge cleared ✓")
                return True
            self.logger.info(f"Taylor ==> CF waiting... ({int(deadline - time.time())}s left)")

        try:
            os.makedirs("logs", exist_ok=True)
            self.driver.save_screenshot("logs/TaylorScraper_cf_timeout.png")
        except Exception:
            pass
        raise RuntimeError(
            f"Cloudflare captcha not solved within {timeout}s. "
            "Open VNC at http://3.108.210.45:6080/vnc.html and click the checkbox."
        )

    def _wait_for_page_ready(self, label: str = "page") -> None:
        """Wait for document.readyState == complete."""
        try:
            from selenium.webdriver.support.ui import WebDriverWait
            WebDriverWait(self.driver, 30).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            self.logger.info(f"Taylor ==> {label} ready ✓")
        except Exception as e:
            self.logger.warning(f"Taylor ==> readyState wait failed: {e}")

    def get_total_results(self) -> int:
        """
        Parse total results from Taylor & Francis search page.
        Live page shows: "Showing 1-10 of 4,536 results for search: ..."
        Tries multiple selectors for resilience.
        """
        import re
        SELECTORS = [
            # Primary: the results count paragraph
            "p.results-count",
            "p.result-count",
            "[class*='result'] strong",
            # Fallback: any element with result count text
            "p[data-results]",
        ]
        # Try CSS selectors first
        for sel in SELECTORS:
            try:
                el = WebDriverWait(self.driver, 8).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                )
                text = el.text.strip()
                m = re.search(r'of\s+([\d,]+)', text)
                if m:
                    total = int(m.group(1).replace(",", ""))
                    self.logger.info(f"Taylor ==> [{sel}] {total} results")
                    return total
            except Exception:
                continue

        # XPath fallback: find any element containing "of X results"
        try:
            els = self.driver.find_elements(
                By.XPATH,
                '//*[contains(text(),"results for search") or contains(text(),"of ")]'
            )
            for el in els:
                text = el.text.strip()
                m = re.search(r'of\s+([\d,]+)\s+results', text)
                if m:
                    total = int(m.group(1).replace(",", ""))
                    self.logger.info(f"Taylor ==> [xpath] {total} results")
                    return total
        except Exception:
            pass

        # Page source fallback
        try:
            src = self.driver.page_source
            m = re.search(r'of\s+([\d,]+)\s+results', src)
            if m:
                total = int(m.group(1).replace(",", ""))
                self.logger.info(f"Taylor ==> [pagesrc] {total} results")
                return total
        except Exception:
            pass

        self.logger.error("Taylor ==> get_total_results: no count found")
        self._debug_screenshot("no_results")
        return 0

    def extract_links_from_page(self) -> list:
        """
        Extract article hrefs from the current Taylor & Francis results page.
        Tries multiple selectors in order of specificity.
        """
        import re
        links = []
        SELECTORS = [
            # Primary confirmed selector
            "article.searchResultItem div.art_title span.hlFld-Title a",
            # Alternate layouts
            "h3.art_title a",
            "h2.art_title a",
            ".searchResultItem .art_title a",
            ".resultsItems .art_title a",
            "a.ref.nowrap[href*='/doi/']",
        ]
        for sel in SELECTORS:
            try:
                found = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_all_elements_located(
                        (By.CSS_SELECTOR, sel)
                    )
                )
                if found:
                    for a in found:
                        href = a.get_attribute("href")
                        if href and "/doi/" in href:
                            links.append(href)
                    if links:
                        self.logger.info(
                            f"Taylor ==> [{sel}] {len(links)} links"
                        )
                        return links
            except Exception:
                continue
        self.logger.warning("Taylor ==> extract_links: no links found on page")
        self._debug_screenshot("no_links")
        return links

    # ── Phase 2: extract author emails ────────────────────────────────────────

    def scrape_article(self, article_url: str) -> list:
        """
        Navigate to an article and collect [url, author_name, email] rows.
        Uses:
          show-all-link  — expand collapsed author list
          span.corr-email a — email links
          a.author          — author name elements
        """
        rows = []
        try:
            self.driver.get(article_url)
            time.sleep(2)

            # Expand author list if collapsed
            try:
                show_all = self.wait.until(
                    EC.element_to_be_clickable(
                        (By.CLASS_NAME, "show-all-link")
                    )
                )
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", show_all
                )
                self.driver.execute_script("arguments[0].click();", show_all)
                time.sleep(2)
            except Exception:
                pass  # already fully expanded or no button

            # Collect all email elements
            email_els = self.driver.find_elements(
                By.XPATH,
                '//span[@class="overlay"]/span[@class="corr-sec"]'
                '/span[@class="corr-email"]/a'
            )
            if not email_els:
                return rows

            # Collect author names for fuzzy matching
            name_els = self.driver.find_elements(
                By.XPATH,
                '//span[@class="corr-email"]/a'
                '/following::a[@class="author"]'
            )
            # Fallback: all a.author on the page
            if not name_els:
                name_els = self.driver.find_elements(
                    By.CSS_SELECTOR, "a.author"
                )
            names = [n.text.strip() for n in name_els if n.text.strip()]

            for el in email_els:
                try:
                    href  = el.get_attribute("href") or ""
                    # href may be "mailto:user@domain.com%20" or contain spaces
                    emails = [
                        e.strip()
                        for e in href.replace("mailto:", "").split("%20")
                        if "@" in e
                    ]
                    for email in emails:
                        if names:
                            best, score = fuzz_process.extractOne(
                                email.split("@")[0], names,
                                scorer=fuzz.token_set_ratio
                            )
                        else:
                            best, score = "", 0
                        rows.append([article_url, best, email])
                        self.logger.info(f"Taylor ==> {best} — {email}")
                except Exception as e:
                    self.logger.warning(f"Taylor ==> email extraction error: {e}")
        except Exception as e:
            self.logger.error(f"Taylor ==> Article error {article_url}: {e}")
        return rows

    # ── Main entry point ──────────────────────────────────────────────────────

    def run(self):
        authors_path = os.path.join(self._work_dir(), self.authors_csv)
        try:
            self.logger.info("Taylor ==> Initialising Chrome via ChromeDisplayMixin...")
            self._launch_chrome(
                self._build_default_chrome_options(), driver_path=self.driver_path
            )
            self.wait = WebDriverWait(self.driver, 20)

            self._init_csv(self.url_csv,     ["Article_URL"])
            self._init_csv(self.authors_csv, ["Article_URL", "Author_Name", "Email"])

            kw_enc = quote_plus(self.keyword)
            base   = "https://www.tandfonline.com/action/doSearch"
            # Correct URL format confirmed from live site:
            #   field1=AllField&text1={kw}&Ppub=&AfterYear=YYYY&BeforeYear=YYYY
            search_url = (
                f"{base}?field1=AllField&text1={kw_enc}"
                f"&Ppub=&AfterYear={self.after_year}&BeforeYear={self.before_year}"
                f"&pageSize=100&startPage=0"
            )

            # ── Step 1: Homepage → accept cookies ────────────────────────
            self._progress(2, "Loading Taylor & Francis homepage...")
            self.driver.get("https://www.tandfonline.com")
            time.sleep(5)
            self._wait_for_page_ready("homepage")
            self._bypass_cloudflare(timeout=120)
            try:
                btn = WebDriverWait(self.driver, 8).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "#onetrust-accept-btn-handler")
                    )
                )
                self.driver.execute_script("arguments[0].click();", btn)
                self.logger.info("Taylor ==> Cookies accepted")
                time.sleep(2)
            except Exception:
                self.logger.info("Taylor ==> No cookie banner")

            # ── Step 2: Search results ────────────────────────────────────
            self._progress(4, f"Searching: {self.keyword}...")
            self.driver.get(search_url)
            time.sleep(6)
            self._wait_for_page_ready("search results")
            self._bypass_cloudflare(timeout=120)

            total_results = self.get_total_results()
            if total_results == 0:
                raise RuntimeError("Taylor ==> No results found for this search")

            total_pages = math.ceil(total_results / 100)
            self.logger.info(f"Taylor ==> {total_pages} pages to collect")

            # ── Step 3: Paginate and collect URLs ─────────────────────────
            all_links = []
            for pg in range(total_pages):
                page_url = (
                    f"{base}?field1=AllField&text1={kw_enc}"
                    f"&Ppub=&AfterYear={self.after_year}&BeforeYear={self.before_year}"
                    f"&pageSize=100&startPage={pg}"
                )
                try:
                    self.driver.get(page_url)
                    time.sleep(8)                          # paced navigation
                    self._wait_for_page_ready(f"page {pg+1}")
                    self._bypass_cloudflare(timeout=120)  # catch mid-session CF
                    links = self.extract_links_from_page()
                    all_links.extend(links)
                    self.save_to_csv(
                        [[lnk] for lnk in links], self.url_csv,
                        header=["Article_URL"]
                    )
                    self.logger.info(
                        f"Taylor ==> Page {pg+1}/{total_pages}: "
                        f"{len(links)} links (total {len(all_links)})"
                    )
                except Exception as e:
                    self.logger.error(f"Taylor ==> Page {pg+1} error: {e}")

                pct = int(5 + ((pg + 1) / total_pages) * 33)
                self._progress(
                    pct,
                    f"URL collection: page {pg+1}/{total_pages} ({len(all_links)} URLs)",
                    current_url=page_url,
                    links_count=len(all_links),
                )

            self.logger.info(f"Taylor ==> Phase 1 done: {len(all_links)} URLs")

            # ── Step 4: Extract author emails ─────────────────────────────
            self._progress(40, "PHASE 2: Extracting author emails...")
            total         = len(all_links)
            authors_found = 0

            for idx, article_url in enumerate(all_links, 1):
                rows = self.scrape_article(article_url)
                if rows:
                    self.save_to_csv(
                        rows, self.authors_csv,
                        header=["Article_URL", "Author_Name", "Email"]
                    )
                    authors_found += len(rows)

                pct = int(40 + (idx / total) * 55)
                self._progress(
                    pct,
                    f"Author extraction: {idx}/{total} ({authors_found} found)",
                    current_url=article_url,
                    authors_count=authors_found,
                    links_count=total,
                )
                time.sleep(3)   # polite delay between article requests

            self._progress(100, "Taylor & Francis scraping completed.")
            self.logger.info("Taylor ==> Done.")
            return authors_path, f"Taylor scrape complete: {len(all_links)} articles"

        except Exception:
            raise
        finally:
            self._quit_chrome()
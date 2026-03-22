"""wiley_selenium.py — Wiley Online Library scraper using ChromeDisplayMixin"""
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


class WileyScraper(ChromeDisplayMixin):
    """
    Wiley Online Library (onlinelibrary.wiley.com) scraper.
    Converted from nodriver (async) to Selenium + ChromeDisplayMixin.

    Search URL:
        https://onlinelibrary.wiley.com/action/doSearch
            ?AfterMonth={M}&AfterYear={YYYY}&BeforeMonth={M}&BeforeYear={YYYY}
            &field1=AllField&text1={keyword}&pageSize=100&startPage={N}

    Result count  : div.search__result--space > span.result__count
    Article links : a.publication_title.visitable
    Email links   : a[title="Link to email address"] > span  (span.text = email)
    Author names  : p.author-name
    """

    TITLE_SUFFIXES = [
        " PhD", " RN", " MSc", " BA (Hons)", " PH.D", " BN", " DNP", " MD",
        " MSN", " MPH", " MBBS", " MHA", " Ph.D.", " MBA", " LNHA", " LMSW",
        " MS", " RDH", " CCN",
    ]

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
        self._seen_emails      = set()
        self._title_re         = re.compile(
            r"|".join(map(re.escape, self.TITLE_SUFFIXES))
        )
        self._setup_logger()

        # Parse MM/DD/YYYY
        s = start_year.split("/")
        e = end_year.split("/")
        self.after_month  = s[0].lstrip("0") or "1"
        self.after_year   = s[-1]
        self.before_month = e[0].lstrip("0") or "1"
        self.before_year  = e[-1]

        _ts   = datetime.now().strftime("%H-%M-%S")
        _conf = f"_{conference_name}" if conference_name else ""
        _sd   = start_year.replace("/", "-")
        _ed   = end_year.replace("/", "-")
        _base = f"Wiley{_conf}_{self.directory}_{_sd}_{_ed}_{_ts}"
        self.url_csv     = f"{_base}_urls.csv"
        self.authors_csv = f"{_base}_authors.csv"

    # ── Logger (same pattern as BMJ) ──────────────────────────────────────────

    def _setup_logger(self):
        self.logger = logging.getLogger(f"WileyScraper-{id(self)}")
        self.logger.setLevel(logging.INFO)
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(
            log_dir,
            f"WileyScraper-{self.directory}"
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
        self.logger.info(f"Wiley ==> Logger initialised → {log_file}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _work_dir(self) -> str:
        d = self.output_dir if self.output_dir else self.directory
        os.makedirs(d, exist_ok=True)
        return d

    def _progress(self, pct, msg, current_url="", authors_count=0, links_count=0):
        self.logger.info(f"Wiley ==> [{pct}%] {msg}")
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
            self.logger.error(f"Wiley ==> CSV save failed: {e}")

    def _init_csv(self, filename, header):
        fp = os.path.join(self._work_dir(), filename)
        with open(fp, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)
        self.logger.info(f"Wiley ==> Initialised {fp}")

    def _clean_name(self, name: str) -> str:
        return self._title_re.sub("", name).strip()

    # ── Phase 1: collect article URLs ─────────────────────────────────────────


    def _bypass_cloudflare(self, timeout: int = 120) -> bool:
        """
        Wait for Cloudflare challenge to clear.
        Wiley uses a checkbox challenge — waits for human solve in VNC.
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
            self.logger.info("Wiley ==> CF bypass: no challenge ✓")
            return True

        self.logger.warning(
            f"Wiley ==> ⚠️ Cloudflare challenge — solve in VNC within {timeout}s. "
            f"URL: {self.driver.current_url}"
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(3)
            if not _on_cf():
                self.logger.info("Wiley ==> CF bypass: challenge cleared ✓")
                return True
            self.logger.info(f"Wiley ==> CF waiting... ({int(deadline - time.time())}s left)")

        try:
            os.makedirs("logs", exist_ok=True)
            self.driver.save_screenshot("logs/WileyScraper_cf_timeout.png")
        except Exception:
            pass
        raise RuntimeError(
            f"Cloudflare captcha not solved within {timeout}s. "
            "Open VNC at http://3.108.210.45:6080/vnc.html and click the checkbox."
        )

    def _wait_for_page_ready(self, label: str = "page") -> None:
        """Wait for document.readyState == complete + extra buffer."""
        try:
            from selenium.webdriver.support.ui import WebDriverWait
            WebDriverWait(self.driver, 30).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            self.logger.info(f"Wiley ==> {label} ready ✓")
        except Exception as e:
            self.logger.warning(f"Wiley ==> readyState wait failed: {e}")


    def _click_next_page(self) -> bool:
        """
        Click the Wiley pagination Next button.
        Selector from live page HTML:
          <a aria-label="Next page" class="pagination__btn--next js__ajaxSearchTrigger">
        Returns True if button was found and clicked, False if not found.
        """
        NEXT_SELECTORS = [
            'a[aria-label="Next page"]',
            'a.pagination__btn--next',
            'a[aria-label="Go to next page"]',
        ]
        for sel in NEXT_SELECTORS:
            try:
                btn = self.wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                )
                # Scroll into view before clicking
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", btn
                )
                time.sleep(1.5)
                try:
                    btn.click()
                except Exception:
                    self.driver.execute_script("arguments[0].click();", btn)
                self.logger.info(f"Wiley ==> Next button clicked ({sel})")
                return True
            except Exception:
                continue
        return False

    def get_total_results(self) -> int:
        """
        Get total result count. Wiley uses pageSize=20 (max allowed without login).
        Live selector confirmed: div.search__result--space > span.result__count
        """
        import re, math
        SELECTORS = [
            "div.search__result--space > span.result__count",
            "span.result__count",
            ".search__result span",
            "[class*='result__count']",
        ]
        for sel in SELECTORS:
            try:
                el = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                )
                text = el.text.strip().replace(",", "")
                if text.isdigit():
                    total = int(text)
                    pages = math.ceil(total / 20)   # Wiley shows 20 results/page
                    self.logger.info(
                        f"Wiley ==> [{sel}] {total} results → {pages} pages"
                    )
                    return pages   # return page count, not result count
            except Exception:
                continue

        # Fallback: parse from page text "X results for"
        try:
            src = self.driver.page_source
            m = re.search(r'([\d,]+)\s+results\s+for', src)
            if m:
                total = int(m.group(1).replace(",", ""))
                pages = math.ceil(total / 20)
                self.logger.info(f"Wiley ==> [pagesrc] {total} results → {pages} pages")
                return pages
        except Exception:
            pass

        self.logger.error("Wiley ==> get_total_results: no count found")
        self._debug_screenshot("no_results")
        return 0

    def extract_links_from_page(self) -> list:
        links = []
        try:
            els = WebDriverWait(self.driver, 15).until(
                EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, "a.publication_title.visitable")
                )
            )
            for el in els:
                href = el.get_attribute("href")
                if href:
                    # Wiley hrefs may be relative (/doi/10.xxx/yyy)
                    if href.startswith("/"):
                        href = "https://onlinelibrary.wiley.com" + href
                    links.append(href)
        except Exception as e:
            self.logger.warning(f"Wiley ==> extract_links failed: {e}")
        return links

    # ── Phase 2: extract author emails ────────────────────────────────────────

    def scrape_article(self, article_url: str) -> list:
        """
        Navigate to one Wiley article and collect [url, author_name, email] rows.

        Email selectors (multiple tried in order):
          1. a[title="Link to email address"] > span   — primary (confirmed)
          2. a[href^="mailto:"]                        — fallback
          3. .author-info a[href^="mailto:"]           — author popup

        Author selector: p.author-name, .author-name

        FIX: page_load_timeout=30s prevents 2-minute hangs on slow/blocked pages.
        """
        from selenium.common.exceptions import TimeoutException as SeleniumTimeout

        rows = []
        try:
            # ── Short page-load timeout per article ───────────────────────
            # Default WebDriver timeout can be 300s+ — causes the 120s log errors.
            # 30s is generous; Wiley article pages normally load in <5s.
            self.driver.set_page_load_timeout(30)

            try:
                self.driver.get(article_url)
            except SeleniumTimeout:
                self.logger.warning(
                    f"Wiley ==> Article page timed out (30s), skipping: {article_url}"
                )
                return rows
            finally:
                # Restore a longer timeout for the search/navigation pages
                self.driver.set_page_load_timeout(60)

            time.sleep(2)

            # ── Try email selectors ───────────────────────────────────────
            email_data = []   # list of (email_str, parent_text)

            # Selector 1: primary Wiley email link
            try:
                spans = self.driver.find_elements(
                    By.CSS_SELECTOR, 'a[title="Link to email address"] > span'
                )
                for span in spans:
                    email = span.text.strip()
                    if email and "@" in email:
                        try:
                            parent = span.find_element(
                                By.XPATH, "./ancestor::div[contains(@class,'author')]"
                            ).text
                        except Exception:
                            parent = ""
                        email_data.append((email, parent))
            except Exception:
                pass

            # Selector 2: bare mailto: links (fallback)
            if not email_data:
                try:
                    links = self.driver.find_elements(
                        By.CSS_SELECTOR, 'a[href^="mailto:"]'
                    )
                    for lnk in links:
                        email = lnk.get_attribute("href").replace(
                            "mailto:", ""
                        ).strip()
                        if email and "@" in email:
                            email_data.append((email, lnk.text))
                except Exception:
                    pass

            if not email_data:
                return rows

            # ── Collect author names for fuzzy matching ───────────────────
            names = []
            for sel in ["p.author-name", ".author-name", "li.author-name"]:
                try:
                    els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    names = [
                        self._clean_name(n.text.strip())
                        for n in els if n.text.strip()
                    ]
                    if names:
                        break
                except Exception:
                    pass

            # ── Build rows ────────────────────────────────────────────────
            for email, context in email_data:
                if email in self._seen_emails:
                    continue
                self._seen_emails.add(email)

                if names:
                    best, _score = fuzz_process.extractOne(
                        email.split("@")[0], names,
                        scorer=fuzz.token_set_ratio
                    )
                else:
                    best = context.strip().split("\n")[0][:80] if context else ""

                rows.append([article_url, best, email])
                self.logger.info(f"Wiley ==> ✅ {best} — {email}")

        except Exception as e:
            self.logger.error(f"Wiley ==> Article error {article_url}: {e}")
        return rows

    # ── Main entry point ──────────────────────────────────────────────────────

    def run(self):
        authors_path = os.path.join(self._work_dir(), self.authors_csv)
        try:
            self.logger.info("Wiley ==> Initialising Chrome via ChromeDisplayMixin...")
            self._launch_chrome(
                self._build_default_chrome_options(), driver_path=self.driver_path
            )
            self.wait = WebDriverWait(self.driver, 20)

            self._init_csv(self.url_csv,     ["Article_URL"])
            self._init_csv(self.authors_csv, ["Article_URL", "Author_Name", "Email"])

            kw_enc = quote_plus(self.keyword)
            base   = "https://onlinelibrary.wiley.com/action/doSearch"
            # Correct URL confirmed from live Wiley pagination HTML:
            #   field1=AllField&text1={kw}&publication=&Ppub=
            #   &AfterMonth=M&AfterYear=YYYY&BeforeMonth=M&BeforeYear=YYYY
            search_url = (
                f"{base}?field1=AllField&text1={kw_enc}"
                f"&publication=&Ppub="
                f"&AfterMonth={self.after_month}&AfterYear={self.after_year}"
                f"&BeforeMonth={self.before_month}&BeforeYear={self.before_year}"
                f"&pageSize=20&startPage=0"
            )

            # ── Step 1: Homepage → cookie consent ────────────────────────
            self._progress(2, "Loading Wiley Online Library homepage...")
            self.driver.get("https://onlinelibrary.wiley.com")
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
                self.logger.info("Wiley ==> Cookies accepted")
                time.sleep(2)
            except Exception:
                self.logger.info("Wiley ==> No cookie banner")

            # ── Step 2: Search results ────────────────────────────────────
            self._progress(4, f"Searching: {self.keyword}...")
            self.driver.get(search_url)
            time.sleep(6)
            self._wait_for_page_ready("search results")
            self._bypass_cloudflare(timeout=120)

            total_pages = self.get_total_results()
            if total_pages == 0:
                raise RuntimeError("Wiley ==> No results found for this search")

            self.logger.info(f"Wiley ==> {total_pages} pages to collect")

            # ── Step 3: Paginate using Next button (not URL changes) ─────────
            # Wiley triggers CF at every URL change. Instead we click the
            # pagination Next button so the page updates via AJAX — no new
            # navigation, no new CF challenge.
            all_links = []
            page_num  = 1

            while True:
                current_url = self.driver.current_url
                try:
                    links = self.extract_links_from_page()
                    all_links.extend(links)
                    self.save_to_csv(
                        [[lnk] for lnk in links], self.url_csv,
                        header=["Article_URL"]
                    )
                    self.logger.info(
                        f"Wiley ==> Page {page_num}/{total_pages}: "
                        f"{len(links)} links (total {len(all_links)})"
                    )
                except Exception as e:
                    self.logger.error(f"Wiley ==> Page {page_num} extract error: {e}")

                pct = int(5 + min(page_num / max(total_pages, 1), 1.0) * 33)
                self._progress(
                    pct,
                    f"URL collection: page {page_num}/{total_pages} ({len(all_links)} URLs)",
                    current_url=current_url,
                    links_count=len(all_links),
                )

                if page_num >= total_pages:
                    break

                # Click Next button — keeps session cookies, avoids CF re-challenge
                if not self._click_next_page():
                    self.logger.info("Wiley ==> No Next button found — pagination ended")
                    break

                page_num += 1
                # Generous delay: let AJAX load + avoid rate-limiting
                time.sleep(15)
                self._wait_for_page_ready(f"page {page_num}")
                # Still check for CF (appears occasionally mid-session)
                self._bypass_cloudflare(timeout=120)

            self.logger.info(f"Wiley ==> Phase 1 done: {len(all_links)} URLs")

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
                time.sleep(3)   # be polite between article pages

            self._progress(100, "Wiley Online Library scraping completed.")
            self.logger.info("Wiley ==> Done.")
            return authors_path, f"Wiley scrape complete: {len(all_links)} articles"

        except Exception:
            raise
        finally:
            self._quit_chrome()
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
        conf = f"_{conference_name}" if conference_name else ""
        self.url_csv     = f"Lippincott_{self.directory}-{self.start_year}-{self.end_year}{conf}_urls.csv"
        self.authors_csv = f"Lippincott_{self.directory}-{self.start_year}-{self.end_year}{conf}_authors.csv"
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


    def _bypass_cloudflare(self, timeout: int = 90) -> bool:
        """
        Bypass Cloudflare Turnstile. Walks ALL iframes up to 3 levels.
        Waits up to 8s for Turnstile iframe to inject before walking.
        Uses ActionChains (isTrusted=True) + JS fallback.
        """
        import random
        from selenium.webdriver.common.action_chains import ActionChains

        PHRASES = ["just a moment","verifying you are human",
                   "performing security verification","checking your browser",
                   "cf-browser-verification"]
        CF_SELS = ["input[type='checkbox']","div.ctp-checkbox-label",
                   ".mark","span.mark","label[for='cf-stage']",
                   "div[id*='challenge']","div[class*='checkbox']"]

        def _on_cf():
            try:
                t=self.driver.title.lower(); s=self.driver.page_source.lower()[:600]
                return any(p in t or p in s for p in PHRASES)
            except Exception: return False

        def _wait_ready(sec=10):
            end=time.time()+sec
            while time.time()<end:
                try:
                    if self.driver.execute_script("return document.readyState")=="complete": return
                except Exception: pass
                time.sleep(0.5)

        def _human():
            try:
                self.driver.execute_script("""
                    var x=300+Math.floor(Math.random()*500),y=200+Math.floor(Math.random()*350);
                    document.dispatchEvent(new MouseEvent('mousemove',{bubbles:true,clientX:x,clientY:y}));
                    window.scrollBy(0,Math.floor(Math.random()*40+5));
                    setTimeout(function(){window.scrollBy(0,-20);},300);
                """)
            except Exception: pass

        def _click_el(el, label):
            time.sleep(random.uniform(0.4,0.9))
            try:
                ActionChains(self.driver).move_to_element(el).pause(random.uniform(0.3,0.7)).click().perform()
                self.logger.info(f"CF bypass: ActionChains clicked {label}"); return True
            except Exception: pass
            try:
                self.driver.execute_script("""
                    var el=arguments[0],r=el.getBoundingClientRect();
                    var cx=r.left+r.width/2+(Math.random()-0.5)*3,cy=r.top+r.height/2+(Math.random()-0.5)*3;
                    ['mousedown','mouseup','click'].forEach(function(t){
                        el.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,clientX:cx,clientY:cy,view:window}));});
                """,el); self.logger.info(f"CF bypass: JS clicked {label}"); return True
            except Exception: return False

        def _wait_iframes(sec=8):
            end=time.time()+sec
            while time.time()<end:
                if self.driver.find_elements(By.TAG_NAME,"iframe"): return True
                time.sleep(0.5)
            return False

        def _walk(depth=0):
            if depth==0: _wait_iframes()
            for sel in CF_SELS:
                try:
                    for el in self.driver.find_elements(By.CSS_SELECTOR,sel):
                        if el.is_displayed():
                            if _click_el(el,f"d{depth}:{sel}"): return True
                except Exception: pass
            if depth>=3: return False
            try:
                for fr in self.driver.find_elements(By.TAG_NAME,"iframe"):
                    try:
                        self.driver.switch_to.frame(fr); time.sleep(0.6)
                        if _walk(depth+1): return True
                        self.driver.switch_to.parent_frame(); time.sleep(0.3)
                    except Exception:
                        try: self.driver.switch_to.default_content()
                        except Exception: pass
            except Exception: pass
            return False

        _wait_ready(); time.sleep(2)
        if not _on_cf():
            self.logger.info("CF bypass: page ready (no challenge) ✓"); return True
        self.logger.info("CF bypass: challenge detected — starting bypass...")
        deadline=time.time()+timeout; last_click=0; attempt=0

        while time.time()<deadline:
            _wait_ready(5)
            if not _on_cf(): self.logger.info("CF bypass: cleared ✓"); return True
            _human()
            if time.time()-last_click>5:
                last_click=time.time(); attempt+=1
                self.logger.info(f"CF bypass: attempt #{attempt}")
                try: self.driver.switch_to.default_content()
                except Exception: pass
                try: clicked=_walk()
                except Exception: clicked=False
                finally:
                    try: self.driver.switch_to.default_content()
                    except Exception: pass
                if clicked: time.sleep(4); continue
            self.logger.info(f"CF bypass: active ({int(deadline-time.time())}s left)...")
            time.sleep(2)

        self.logger.warning(f"CF bypass: timed out after {timeout}s")
        try:
            os.makedirs("logs",exist_ok=True)
            self.driver.save_screenshot(f"logs/{self.__class__.__name__}_cf_timeout.png")
        except Exception: pass
        return False

    def run(self):
        try:
            self.logger.info("Lippincott ==> Initialising Chrome via ChromeDisplayMixin...")
            self._launch_chrome(
                self._build_default_chrome_options(), driver_path=self.driver_path
            )
            self.wait = WebDriverWait(self.driver, 60)
            # maximize_window() OMITTED — triggers Runtime.evaluate on Chrome 145

            search_url = (
                f"https://lww.com/pages/results.aspx"
                f"?txtKeywords={self.keyword}"
            )
            self.logger.info(f"Lippincott ==> GET {search_url}")
            self.driver.get(search_url)
            time.sleep(5)
            self._bypass_cloudflare(timeout=60)

            try:
                btn = self.wait.until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "#onetrust-accept-btn-handler")
                    )
                )
                self.driver.execute_script("arguments[0].click();", btn)
                self.logger.info("Lippincott ==> Cookie accepted")
            except Exception:
                self.logger.info("Lippincott ==> No cookie banner")
            time.sleep(2)

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
        finally:
            self._quit_chrome()
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
        conf = f"_{conference_name}" if conference_name else ""
        self.url_csv     = f"Emrald_{self.directory}-{start_year.replace('/', '-')}-{end_year.replace('/', '-')}{conf}_urls.csv"
        self.authors_csv = f"Emrald_{self.directory}-{start_year.replace('/', '-')}-{end_year.replace('/', '-')}{conf}_authors.csv"
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
            self.logger.info("Emerald ==> Initialising Chrome via ChromeDisplayMixin...")
            self._launch_chrome(
                self._build_default_chrome_options(), driver_path=self.driver_path
            )
            self.wait = WebDriverWait(self.driver, 20)
            # maximize_window() OMITTED — triggers Runtime.evaluate on Chrome 145

            start_iso = datetime.strptime(self.start_year, "%m/%d/%Y").strftime("%Y-%m-%d")
            end_iso   = datetime.strptime(self.end_year,   "%m/%d/%Y").strftime("%Y-%m-%d")
            date_range = f"{start_iso}T00:00:00 TO {end_iso}T23:59:59"

            query_params = {
                "q":                self.keyword,
                "fl_SiteID":        "1",
                "access_openaccess":"true",
                "f_ContentType":    "Journal Articles",
                "rg_PublicationDate": date_range,
            }
            base_url   = "https://www.emerald.com/search-results/"
            search_url = f"{base_url}?{urlencode(query_params)}"

            self.logger.info(f"Emerald ==> GET {search_url}")
            self.driver.get(search_url)
            time.sleep(5)
            self._bypass_cloudflare(timeout=60)

            self._progress(5, "Getting result count...")
            total_pages = self.get_total_pages()
            if not total_pages:
                self.logger.error("Emerald ==> No results — aborting")
                return

            self._progress(8, f"Collecting URLs from {total_pages} pages...")
            self.extract_article_links(total_pages, base_url, query_params)

            self._progress(40, "PHASE 2: Extracting author emails...")
            self.extract_author_info()

            self._progress(100, "Emerald scraping completed.")
            self.logger.info("Emerald ==> Done.")

        except Exception as e:
            self.logger.error(f"Emerald ==> run() error: {e}", exc_info=True)
        finally:
            self._quit_chrome()
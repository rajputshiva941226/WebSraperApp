"""
Nature.com Article Scraper
- Non-headless Chrome (Xvfb virtual display on EC2/Linux servers)
- Xvfb fallback when GNOME3/DISPLAY:0 is not accessible via SSH
- Screenshots saved for debugging
- Graceful Chrome + Xvfb cleanup
- Compatible with SeleniumScraperWrapper: __init__ does NOT call run()
  run() launches Chrome, scrapes, cleans up; returns (csv_path, summary)
- Cooperative stop: checks self._stop_requested() injected by wrapper
"""

try:
    import setuptools, sys
    if sys.version_info >= (3, 12):
        import importlib.util
        spec = importlib.util.find_spec('setuptools._distutils')
        if spec:
            sys.modules['distutils'] = importlib.import_module('setuptools._distutils')
except ImportError:
    pass

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, ElementClickInterceptedException)

import csv, time, os, sys, re, platform, subprocess, logging, datetime
from webdriver_manager.chrome import ChromeDriverManager


class NatureScraper:

    def __init__(self, keyword=None, start_year=None, end_year=None,
                 driver_path=None, output_dir=None, progress_callback=None):
        self.keyword     = keyword or 'bioinformatics'
        self.start_year  = str(start_year) if start_year else str(datetime.datetime.now().year)
        self.end_year    = str(end_year)   if end_year   else str(datetime.datetime.now().year)
        self.driver_path = driver_path
        self.output_dir  = output_dir or os.getcwd()
        self._cb         = progress_callback

        self.driver           = None
        self._vdisplay        = None
        self.cookies_accepted = False
        self.logger           = self._setup_logger()

        self.article_types = [
            'research', 'reviews', 'protocols', 'comments-and-opinion',
            'amendments-and-corrections', 'research-highlights', 'correspondence',
        ]
        self.subjects = [
            'biochemistry', 'molecular-biology', 'cell-biology',
            'biological-techniques', 'biophysics', 'biomarkers', 'biotechnology',
            'drug-discovery', 'diseases', 'developing-world',
            'computational-biology-and-bioinformatics', 'neuroscience',
            'structural-biology', 'systems-biology', 'cancer', 'genetics',
            'immunology', 'medical-research', 'scientific-community', 'social-sciences',
        ]
        # NOTE: __init__ does NOT call run() — SeleniumScraperWrapper calls run() directly

    # ── Stop check ────────────────────────────────────────────────────────────

    def _check_stop(self):
        """Call at the top of every loop iteration. Raises KeyboardInterrupt if stop requested."""
        if getattr(self, '_stop_requested', lambda: False)():
            raise KeyboardInterrupt('Stop requested')

    # ── Logging ───────────────────────────────────────────────────────────────

    def _setup_logger(self):
        logger = logging.getLogger(f"Nature.{self.keyword[:20]}")
        logger.setLevel(logging.INFO)
        if logger.hasHandlers():
            logger.handlers.clear()
        fmt = logging.Formatter('%(asctime)s  %(levelname)-8s %(message)s',
                                datefmt='%H:%M:%S')
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            fh = logging.FileHandler(
                os.path.join(self.output_dir, 'nature_debug.log'), encoding='utf-8')
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except Exception:
            pass
        return logger

    def _save_screenshot(self, label: str):
        if self.driver is None:
            return
        try:
            ss_dir = os.path.join(self.output_dir, 'screenshots')
            os.makedirs(ss_dir, exist_ok=True)
            ts   = datetime.datetime.now().strftime('%H%M%S')
            path = os.path.join(ss_dir, f'{ts}_{label}.png')
            self.driver.save_screenshot(path)
            self.logger.info("[Nature] Screenshot -> %s", path)
        except Exception as e:
            self.logger.debug("[Nature] Screenshot failed: %s", e)

    def _progress(self, pct, msg, url=''):
        if self._cb:
            try:
                self._cb(progress=pct, status=msg, current_url=url)
            except Exception:
                pass
        self.logger.info("[Nature] [%d%%] %s", pct, msg)

    # ── Virtual display (Xvfb) ────────────────────────────────────────────────

    def _start_virtual_display(self):
        try:
            from pyvirtualdisplay import Display
            self._vdisplay = Display(visible=False, size=(1920, 1080), backend='xvfb')
            self._vdisplay.start()
            disp = f":{self._vdisplay.display}"
            self.logger.info("[Nature] pyvirtualdisplay on %s", disp)
            return disp
        except ImportError:
            self.logger.info("[Nature] pyvirtualdisplay not installed — using raw Xvfb")
            subprocess.run(['pkill', '-f', 'Xvfb :99'], capture_output=True)
            time.sleep(0.5)
            proc = subprocess.Popen(
                ['Xvfb', ':99', '-screen', '0', '1920x1080x24', '-ac'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._vdisplay = proc
            time.sleep(1.5)
            self.logger.info("[Nature] Xvfb PID=%d on :99", proc.pid)
            return ':99'

    def _stop_virtual_display(self):
        if self._vdisplay is None:
            return
        try:
            if hasattr(self._vdisplay, 'stop'):
                self._vdisplay.stop()
            elif hasattr(self._vdisplay, 'terminate'):
                self._vdisplay.terminate()
        except Exception:
            pass
        finally:
            self._vdisplay = None
        self.logger.info("[Nature] Virtual display stopped")

    # ── Chrome setup / teardown ───────────────────────────────────────────────

    def _build_chrome_options(self):
        opts = Options()
        # NO --headless: Nature popup/email extraction needs real or virtual display
        for arg in [
            '--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu',
            '--window-size=1920,1080',
            '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            '--disable-blink-features=AutomationControlled',
        ]:
            opts.add_argument(arg)
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option('useAutomationExtension', False)
        return opts

    def _try_launch_chrome(self):
        opts = self._build_chrome_options()
        self.logger.info("[Nature] Launching Chrome DISPLAY=%s", os.environ.get('DISPLAY'))
        if self.driver_path:
            service = Service(self.driver_path)
        else:
            service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=opts)
        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.logger.info("[Nature] Chrome launched OK")

    def setup_driver(self):
        if platform.system() == 'Windows':
            self._try_launch_chrome()
            return

        if not os.environ.get('DISPLAY'):
            os.environ['DISPLAY'] = ':0'
        uid_str = str(os.getuid()) if hasattr(os, 'getuid') else '1000'
        xauth = os.environ.get('XAUTHORITY', '')
        if not xauth or not os.path.exists(xauth):
            for c in [f"/run/user/{uid_str}/gdm/Xauthority",
                      os.path.expanduser("~/.Xauthority"),
                      "/home/ubuntu/.Xauthority", "/root/.Xauthority"]:
                if os.path.exists(c) and os.access(c, os.R_OK):
                    os.environ['XAUTHORITY'] = c
                    self.logger.info("[Nature] XAUTHORITY -> %s", c)
                    break

        try:
            self._try_launch_chrome()
            return
        except Exception as e1:
            self.logger.warning("[Nature] Chrome failed on :0 (%s) -> trying Xvfb",
                                type(e1).__name__)

        xvfb = self._start_virtual_display()
        os.environ['DISPLAY'] = xvfb
        os.environ.pop('XAUTHORITY', None)
        self._try_launch_chrome()
        self.logger.info("[Nature] Chrome on Xvfb %s OK", xvfb)

    def cleanup(self):
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("[Nature] Chrome closed")
            except Exception:
                pass
            finally:
                self.driver = None
        self._stop_virtual_display()

    # ── Page helpers ──────────────────────────────────────────────────────────

    def accept_cookies(self):
        if self.cookies_accepted:
            return
        try:
            btn = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, 'button[data-cc-action="accept"]')))
            btn.click()
            self.logger.info("[Nature] Cookies accepted")
            time.sleep(1)
        except Exception:
            pass
        self.cookies_accepted = True

    # ── Link scraping ─────────────────────────────────────────────────────────

    def get_total_results(self, url):
        try:
            self.driver.get(url)
            self.accept_cookies()
            time.sleep(2)
            el = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, '[data-test="results-data"] span:last-child')))
            return int(el.text.strip().split()[0].replace(',', ''))
        except Exception:
            return 0

    def scrape_links_from_url(self, base_url, links_file):
        self._check_stop()
        total = self.get_total_results(base_url + "&page=1")
        if total == 0:
            return []
        total_pages = min((total // 50) + 1, 20)
        links = []
        with open(links_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            for page in range(1, total_pages + 1):
                self._check_stop()
                try:
                    self.driver.get(base_url + f"&page={page}")
                    time.sleep(1.5)
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, '.app-article-list-row__item')))
                    for article in self.driver.find_elements(
                            By.CSS_SELECTOR, '.app-article-list-row__item article'):
                        try:
                            lnk = article.find_element(
                                By.CSS_SELECTOR, '.c-card__title a').get_attribute('href')
                            if lnk:
                                writer.writerow([lnk])
                                f.flush()
                                links.append(lnk)
                        except Exception:
                            pass
                    time.sleep(1)
                except Exception:
                    continue
        return links

    # ── Email extraction ──────────────────────────────────────────────────────

    def extract_author_emails(self, article_url):
        self._check_stop()
        try:
            self.driver.get(article_url)
            time.sleep(2)
            self.accept_cookies()
            authors_data = []

            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, '[data-test="authors-list"]')))
            except TimeoutException:
                return []

            # Expand full author list if collapsed
            try:
                show_btn = WebDriverWait(self.driver, 3).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, 'button.c-article-author-list__button')))
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", show_btn)
                time.sleep(0.5)
                try:
                    WebDriverWait(self.driver, 2).until(
                        EC.element_to_be_clickable(
                            (By.CSS_SELECTOR, 'button.c-article-author-list__button')))
                    show_btn.click()
                except Exception:
                    self.driver.execute_script("arguments[0].click();", show_btn)
                time.sleep(1.5)
            except TimeoutException:
                pass

            author_links = self.driver.find_elements(
                By.CSS_SELECTOR,
                '[data-test="authors-list"] a[data-test="author-name"]')

            for idx in range(len(author_links)):
                self._check_stop()
                try:
                    # Re-fetch to avoid stale element refs
                    author_links = self.driver.find_elements(
                        By.CSS_SELECTOR,
                        '[data-test="authors-list"] a[data-test="author-name"]')
                    if idx >= len(author_links):
                        break
                    author_link = author_links[idx]
                    author_name = author_link.text.strip().replace('✉', '').strip()
                    safe_name   = re.sub(r'[^a-zA-Z0-9]', '-', author_name)

                    # Only process authors with email icon
                    try:
                        author_link.find_element(
                            By.CSS_SELECTOR,
                            'svg use[href*="mail"], svg use[*|href*="mail"]')
                    except NoSuchElementException:
                        continue

                    email = ''
                    try:
                        self.driver.execute_script(
                            "arguments[0].scrollIntoView({block: 'center'});", author_link)
                        time.sleep(0.3)
                        author_link.click()
                        time.sleep(1)

                        popup_sel = f"div[id*='popup-auth-{safe_name[:5]}']"
                        try:
                            WebDriverWait(self.driver, 5).until(
                                EC.visibility_of_element_located(
                                    (By.CSS_SELECTOR, popup_sel)))
                        except TimeoutException:
                            try:
                                WebDriverWait(self.driver, 3).until(
                                    EC.visibility_of_element_located(
                                        (By.CSS_SELECTOR, '.app-researcher-popup')))
                            except TimeoutException:
                                self._save_screenshot(f'popup_timeout_{idx}')

                        try:
                            el = WebDriverWait(self.driver, 3).until(
                                EC.visibility_of_element_located(
                                    (By.CSS_SELECTOR,
                                     f"{popup_sel} a[href^='mailto:']")))
                            email = el.get_attribute('href').replace('mailto:', '').strip()
                        except TimeoutException:
                            pass

                        if email:
                            authors_data.append({'name': author_name, 'email': email})

                    except Exception:
                        pass

                    # Close popup
                    try:
                        close = WebDriverWait(self.driver, 2).until(
                            EC.element_to_be_clickable(
                                (By.CSS_SELECTOR, 'button.c-popup__close')))
                        close.click()
                        WebDriverWait(self.driver, 3).until(
                            EC.invisibility_of_element_located(
                                (By.CSS_SELECTOR, 'button.c-popup__close')))
                    except Exception:
                        self.driver.execute_script("document.body.click();")
                        time.sleep(0.5)

                except KeyboardInterrupt:
                    raise   # propagate stop signal
                except Exception:
                    continue

            return authors_data

        except KeyboardInterrupt:
            raise   # propagate stop signal
        except Exception as e:
            self.logger.warning("[Nature] Page error %s: %s", article_url, str(e)[:80])
            self._save_screenshot('article_error')
            return []

    def extract_emails_for_links(self, links, emails_file):
        if not links:
            return
        with open(emails_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            for idx, url in enumerate(links, 1):
                self._check_stop()
                authors = self.extract_author_emails(url)
                for author in authors:
                    writer.writerow([url, author['name'], author['email']])
                f.flush()
                time.sleep(1.5)

    # ── Main run — called by SeleniumScraperWrapper ───────────────────────────

    def run(self):
        """
        Entry point called by SeleniumScraperWrapper.
        Launches Chrome, scrapes all years, cleans up in finally.
        Returns (csv_path, summary_dict).
        """
        authors_seen = set()
        emails_seen  = set()
        csv_path     = None

        try:
            self._progress(1, 'Launching Chrome...')
            self.setup_driver()
            self._progress(5, 'Chrome ready')
            self._save_screenshot('chrome_started')

            keyword    = self.keyword
            start_year = self.start_year
            end_year   = self.end_year

            out_dir = os.path.join(
                self.output_dir,
                f"{keyword.replace(' ', '_')}_{start_year}-{end_year}")
            os.makedirs(out_dir, exist_ok=True)

            years       = list(range(int(start_year), int(end_year) + 1))
            total_years = len(years)

            for yr_idx, year in enumerate(years):
                self._check_stop()
                yr_pct_base = 5 + int(90 * yr_idx / max(total_years, 1))
                self._progress(yr_pct_base, f'Scraping year {year}...')

                links_file  = os.path.join(
                    out_dir, f"{keyword.replace(' ', '_')}-{year}-links.csv")
                emails_file = os.path.join(
                    out_dir, f"{keyword.replace(' ', '_')}-{year}-emails.csv")

                # Write CSV headers
                with open(links_file, 'w', newline='', encoding='utf-8') as f:
                    csv.writer(f).writerow(['article_link'])
                with open(emails_file, 'w', newline='', encoding='utf-8') as f:
                    csv.writer(f).writerow(['article_link', 'author_name', 'email'])

                # Broad search (no article_type/subject filter)
                base_url = (f"https://www.nature.com/search?q={keyword}"
                            f"&date_range={year}-&order=relevance")
                links = self.scrape_links_from_url(base_url, links_file)
                if links:
                    self.extract_emails_for_links(links, emails_file)

                # Filtered combos
                total_combos = len(self.article_types) * len(self.subjects)
                for combo_idx, (atype, subject) in enumerate(
                        [(a, s) for a in self.article_types for s in self.subjects]):
                    self._check_stop()
                    combo_pct = yr_pct_base + int(
                        (90 / max(total_years, 1)) * combo_idx / max(total_combos, 1))
                    self._progress(
                        combo_pct,
                        f'Year {year}: {atype}/{subject[:20]}')
                    base_url = (f"https://www.nature.com/search?q={keyword}"
                                f"&article_type={atype}&subject={subject}"
                                f"&date_range={year}-&order=relevance")
                    links = self.scrape_links_from_url(base_url, links_file)
                    if links:
                        self.extract_emails_for_links(links, emails_file)
                    time.sleep(0.5)

                # Accumulate counts from this year's file
                csv_path = emails_file
                try:
                    with open(emails_file, encoding='utf-8') as f:
                        for row in csv.DictReader(f):
                            if row.get('author_name'):
                                authors_seen.add(row['author_name'])
                            if row.get('email'):
                                emails_seen.add(row['email'])
                except Exception:
                    pass

            self._progress(100,
                f'Done — {len(authors_seen)} authors, {len(emails_seen)} emails')

        except KeyboardInterrupt:
            # Stop was requested — return whatever we collected so far
            self.logger.info(
                "[Nature] Stop requested — partial results: %d authors, %d emails",
                len(authors_seen), len(emails_seen))

        except Exception as e:
            self.logger.error("[Nature] Fatal error: %s", e)
            self._save_screenshot('fatal_error')
            raise

        finally:
            self.cleanup()   # Always runs — closes Chrome and Xvfb

        summary = {
            'unique_authors': len(authors_seen),
            'unique_emails':  len(emails_seen),
            'message': (f'Found {len(authors_seen)} unique authors, '
                        f'{len(emails_seen)} unique emails'),
        }
        return csv_path, summary
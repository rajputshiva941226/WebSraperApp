"""
Nature.com Article Scraper
- Non-headless Chrome (Xvfb virtual display on EC2/Linux servers)
- Xvfb fallback when GNOME3/DISPLAY:0 is not accessible via SSH
- Graceful Chrome + virtual display cleanup on completion or error
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

import csv, time, os, sys, re, glob, platform, subprocess, logging
from datetime import datetime
from webdriver_manager.chrome import ChromeDriverManager


class NatureScraper:
    def __init__(self):
        self.driver           = None
        self.output_dir       = None
        self.cookies_accepted = False
        self._vdisplay        = None
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

    # ── Logging ──────────────────────────────────────────────────────────────

    def _setup_logger(self):
        logger = logging.getLogger("NatureScraper")
        logger.setLevel(logging.INFO)
        if not logger.hasHandlers():
            fmt = logging.Formatter('%(asctime)s  %(levelname)-8s %(message)s',
                                    datefmt='%H:%M:%S')
            sh = logging.StreamHandler(sys.stdout)
            sh.setFormatter(fmt)
            logger.addHandler(sh)
        return logger

    # ── Virtual display (Xvfb) ───────────────────────────────────────────────

    def _start_virtual_display(self):
        """Start Xvfb. Returns new DISPLAY string."""
        try:
            from pyvirtualdisplay import Display
            self._vdisplay = Display(visible=False, size=(1920, 1080), backend='xvfb')
            self._vdisplay.start()
            disp = f":{self._vdisplay.display}"
            self.logger.info("[Nature] pyvirtualdisplay on %s", disp)
            return disp
        except ImportError:
            self.logger.info("[Nature] pyvirtualdisplay not installed — using Xvfb directly")
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

    # ── Chrome setup ─────────────────────────────────────────────────────────

    def _build_chrome_options(self):
        opts = Options()
        # NO --headless: Nature popup/email extraction needs a real (or virtual) display
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
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=opts)
        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.logger.info("[Nature] Chrome launched OK")

    def setup_driver(self):
        """
        Launch Chrome with Xvfb fallback.
        Called once at the start of a scraping session.
        """
        if platform.system() == 'Windows':
            self._try_launch_chrome()
            return

        # ── Attempt 1: real GNOME3 display ───────────────────────────────────
        if not os.environ.get('DISPLAY'):
            os.environ['DISPLAY'] = ':0'
        uid_str = str(os.getuid()) if hasattr(os, 'getuid') else '1000'
        xauth   = os.environ.get('XAUTHORITY', '')
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

        # ── Attempt 2: Xvfb ──────────────────────────────────────────────────
        xvfb = self._start_virtual_display()
        os.environ['DISPLAY'] = xvfb
        os.environ.pop('XAUTHORITY', None)
        try:
            self._try_launch_chrome()
            self.logger.info("[Nature] Chrome on Xvfb %s OK", xvfb)
        except Exception as e2:
            self.logger.error("[Nature] Chrome also failed on Xvfb: %s\n"
                              "  Install: sudo apt install xvfb && pip install pyvirtualdisplay",
                              e2)
            raise

    def cleanup(self):
        """Close Chrome and stop Xvfb. Always call this when done."""
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("[Nature] Chrome session closed")
            except Exception:
                pass
            finally:
                self.driver = None
        self._stop_virtual_display()

    # ── Cookie / navigation helpers ───────────────────────────────────────────

    def accept_cookies(self):
        if self.cookies_accepted:
            return
        try:
            btn = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, 'button[data-cc-action="accept"]')))
            btn.click()
            self.logger.info("[Nature] Cookies accepted")
            self.cookies_accepted = True
            time.sleep(2)
        except TimeoutException:
            self.cookies_accepted = True
        except Exception:
            self.cookies_accepted = True

    def create_output_directory(self, keyword, start_year, end_year):
        dir_name = f"{keyword.replace(' ', '_')}_{start_year}-{end_year}"
        os.makedirs(dir_name, exist_ok=True)
        self.output_dir = dir_name
        self.logger.info("[Nature] Output dir: %s", os.path.abspath(dir_name))
        return dir_name

    def get_total_results(self, url):
        try:
            self.driver.get(url)
            if not self.cookies_accepted:
                self.accept_cookies()
            time.sleep(2)
            el = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, '[data-test="results-data"] span:last-child')))
            return int(el.text.strip().split()[0].replace(',', ''))
        except Exception:
            return 0

    # ── Link scraping ─────────────────────────────────────────────────────────

    def scrape_links_from_url(self, base_url, links_file):
        total = self.get_total_results(base_url + "&page=1")
        if total == 0:
            return []
        total_pages = min((total // 50) + 1, 20)
        self.logger.info("[Nature] %d results, %d pages", total, total_pages)
        links = []
        with open(links_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            for page in range(1, total_pages + 1):
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
                    print(f"\r  Page {page}/{total_pages} — {len(links)} articles", end='')
                    time.sleep(1)
                except Exception:
                    continue
        print()
        return links

    # ── Email extraction ──────────────────────────────────────────────────────

    def extract_author_emails(self, article_url):
        try:
            self.driver.get(article_url)
            time.sleep(2)
            if not self.cookies_accepted:
                self.accept_cookies()
            time.sleep(0.5)
            authors_data = []

            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, '[data-test="authors-list"]')))
            except TimeoutException:
                return []

            # Click "Show authors" if present
            try:
                show_btn = WebDriverWait(self.driver, 3).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, 'button.c-article-author-list__button')))
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", show_btn)
                time.sleep(1)
                for _ in range(3):
                    try:
                        WebDriverWait(self.driver, 2).until(
                            EC.element_to_be_clickable(
                                (By.CSS_SELECTOR,
                                 'button.c-article-author-list__button')))
                        show_btn.click()
                        break
                    except (ElementClickInterceptedException, TimeoutException):
                        try:
                            self.driver.execute_script(
                                "arguments[0].click();", show_btn)
                            break
                        except Exception:
                            time.sleep(1)
                time.sleep(2)
            except TimeoutException:
                pass

            author_links = self.driver.find_elements(
                By.CSS_SELECTOR,
                '[data-test="authors-list"] a[data-test="author-name"]')

            for idx in range(len(author_links)):
                try:
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
                            "arguments[0].scrollIntoView({block: 'center'});",
                            author_link)
                        time.sleep(0.5)
                        author_link.click()
                        time.sleep(1)

                        popup_sel = f"div[id*='popup-auth-{safe_name[:5]}']"
                        try:
                            WebDriverWait(self.driver, 5).until(
                                EC.visibility_of_element_located(
                                    (By.CSS_SELECTOR, popup_sel)))
                        except TimeoutException:
                            WebDriverWait(self.driver, 3).until(
                                EC.visibility_of_element_located(
                                    (By.CSS_SELECTOR, ".app-researcher-popup")))

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

                except Exception:
                    continue

            return authors_data

        except Exception as e:
            self.logger.warning("[Nature] Page error on %s: %s", article_url, str(e)[:60])
            return []

    def extract_emails_for_links(self, links, emails_file):
        if not links:
            return
        with open(emails_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            for idx, url in enumerate(links, 1):
                print(f"  [{idx}/{len(links)}] {url}")
                authors = self.extract_author_emails(url)
                for author in authors:
                    writer.writerow([url, author['name'], author['email']])
                f.flush()
                time.sleep(2)

    # ── Year / all-years scraping ─────────────────────────────────────────────

    def scrape_year_data(self, keyword, year, extract_emails=True):
        links_file  = os.path.join(self.output_dir,
                                   f"{keyword.replace(' ', '_')}-{year}-links.csv")
        emails_file = os.path.join(self.output_dir,
                                   f"{keyword.replace(' ', '_')}-{year}-emails.csv")

        with open(links_file, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(['article_link'])
        if extract_emails:
            with open(emails_file, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow(['article_link', 'author_name', 'email'])

        year_total = 0

        # 1. Search without filters
        base_url = (f"https://www.nature.com/search?q={keyword}"
                    f"&date_range={year}-&order=relevance")
        links     = self.scrape_links_from_url(base_url, links_file)
        year_total += len(links)
        if links and extract_emails:
            self.extract_emails_for_links(links, emails_file)

        # 2. All article_type × subject combos
        for atype in self.article_types:
            for subject in self.subjects:
                base_url = (f"https://www.nature.com/search?q={keyword}"
                            f"&article_type={atype}&subject={subject}"
                            f"&date_range={year}-&order=relevance")
                links = self.scrape_links_from_url(base_url, links_file)
                year_total += len(links)
                if links and extract_emails:
                    self.extract_emails_for_links(links, emails_file)
                time.sleep(0.5)

        self.logger.info("[Nature] Year %s: %d links", year, year_total)
        return year_total

    def scrape_all_years(self, keyword, start_year, end_year, extract_emails=True):
        self.setup_driver()
        self.create_output_directory(keyword, start_year, end_year)
        grand_total = 0
        for year in range(int(start_year), int(end_year) + 1):
            grand_total += self.scrape_year_data(keyword, year, extract_emails)
        self.logger.info("[Nature] Grand total: %d articles", grand_total)
        return True

    def extract_emails_from_existing_links(self, keyword, start_year, end_year):
        if not self.output_dir or not os.path.exists(self.output_dir):
            self.logger.error("[Nature] Output dir not found: %s", self.output_dir)
            return False
        link_files = glob.glob(
            os.path.join(self.output_dir,
                         f"{keyword.replace(' ', '_')}-*-links.csv"))
        if not link_files:
            self.logger.error("[Nature] No link files in %s", self.output_dir)
            return False
        if not self.driver:
            self.setup_driver()
        self.cookies_accepted = False
        for lf in sorted(link_files):
            year        = lf.split('-')[-2]
            emails_file = lf.replace('-links.csv', '-emails.csv')
            with open(lf, 'r', encoding='utf-8') as f:
                links = list(set([row['article_link'] for row in csv.DictReader(f)]))
            with open(emails_file, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow(['article_link', 'author_name', 'email'])
            self.logger.info("[Nature] Processing year %s (%d articles)", year, len(links))
            self.extract_emails_for_links(links, emails_file)
        return True


def main():
    keyword     = input("Search keyword (default: Bioinformatics): ").strip() or "Bioinformatics"
    start_year  = input("Start year (default: 2020): ").strip() or "2020"
    end_year    = input("End year (default: current): ").strip() or str(datetime.now().year)
    new_links   = (input("Extract NEW article links? (y/n, default: y): ").strip().lower()
                   or 'y') in ('y', 'yes')
    ext_emails  = False
    if new_links:
        ext_emails = (input("Extract emails immediately? (y/n, default: y): ").strip().lower()
                      or 'y') in ('y', 'yes')

    scraper = NatureScraper()
    scraper.output_dir = f"{keyword.replace(' ', '_')}_{start_year}-{end_year}"

    try:
        if new_links:
            scraper.scrape_all_years(keyword, start_year, end_year, ext_emails)
        else:
            if not os.path.exists(scraper.output_dir):
                print(f"Directory not found: {scraper.output_dir}")
                return
            scraper.extract_emails_from_existing_links(keyword, start_year, end_year)
        print("\nDone!")
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        scraper.cleanup()   # Always close Chrome + Xvfb


if __name__ == "__main__":
    main()
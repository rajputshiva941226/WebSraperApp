# from chrome_display_mixin import ChromeDisplayMixin
# """
# Oxford Academic Scraper
# - Non-headless Chrome (Xvfb virtual display on EC2/Linux servers)
# - Xvfb fallback when GNOME3/DISPLAY:0 is not accessible via SSH
# - Cookie-based captcha bypass for academic.oup.com
# - Graceful Chrome session cleanup on finish or error
# - Compatible with SeleniumScraperWrapper: __init__ does NOT call run()
#   run() launches Chrome, scrapes, and cleans up; returns (csv_path, summary)
# """

# try:
#     import setuptools, sys
#     if sys.version_info >= (3, 12):
#         import importlib.util
#         spec = importlib.util.find_spec('setuptools._distutils')
#         if spec:
#             sys.modules['distutils'] = importlib.import_module('setuptools._distutils')
# except ImportError:
#     pass

# from selenium.webdriver.common.by import By
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC

# import os, time, sys, platform, json, subprocess, csv, math, logging, datetime
# from urllib.parse import urlencode, urljoin
# from fuzzywuzzy import fuzz, process
# import undetected_chromedriver as uc

# _OXFORD_COOKIE_FILE = os.path.expanduser("~/.oxford_scraper_cookies.json")


# class OxfordScraper(ChromeDisplayMixin):
#     def __init__(self, keyword, start_year, end_year, driver_path=None,
#                  output_dir=None, progress_callback=None):
#         self.keyword     = keyword
#         self.start_year  = start_year
#         self.end_year    = end_year
#         self.driver_path = driver_path
#         self.output_dir  = output_dir or os.getcwd()
#         self._cb         = progress_callback
#         self._vdisplay   = None
#         self.driver      = None
#         self.directory   = keyword.replace(" ", "-")
#         self._setup_logger()
#         # NOTE: __init__ does NOT call run() — SeleniumScraperWrapper calls run() directly

#     # ── Logging ──────────────────────────────────────────────────────────────

#     def _setup_logger(self):
#         self.logger = logging.getLogger(f"Oxford.{self.keyword[:20]}")
#         self.logger.setLevel(logging.DEBUG)
#         if self.logger.hasHandlers():
#             self.logger.handlers.clear()
#         fmt = logging.Formatter('%(asctime)s  %(levelname)-8s %(message)s',
#                                 datefmt='%Y-%m-%d %H:%M:%S')
#         sh = logging.StreamHandler(sys.stdout)
#         sh.setFormatter(fmt)
#         self.logger.addHandler(sh)

#         # Fixed path — always writable on the server:
#         #   tail -f /tmp/oxford_scraper_debug.log
#         fixed_log = '/tmp/oxford_scraper_debug.log'
#         try:
#             fh_fixed = logging.FileHandler(fixed_log, encoding='utf-8')
#             fh_fixed.setFormatter(fmt)
#             self.logger.addHandler(fh_fixed)
#         except Exception as e:
#             print(f"[Oxford] WARNING: could not open fixed log {fixed_log}: {e}", flush=True)

#         # Output-dir log alongside results
#         try:
#             os.makedirs(self.output_dir, exist_ok=True)
#             fh = logging.FileHandler(
#                 os.path.join(self.output_dir, 'oxford_debug.log'), encoding='utf-8')
#             fh.setFormatter(fmt)
#             self.logger.addHandler(fh)
#         except Exception:
#             pass

#     def _save_screenshot(self, label: str):
#         """Save a debug screenshot to output_dir/screenshots/"""
#         if self.driver is None:
#             return
#         try:
#             ss_dir = os.path.join(self.output_dir, 'screenshots')
#             os.makedirs(ss_dir, exist_ok=True)
#             ts   = datetime.datetime.now().strftime('%H%M%S')
#             path = os.path.join(ss_dir, f'{ts}_{label}.png')
#             self.driver.save_screenshot(path)
#             self.logger.info("[Oxford] Screenshot -> %s", path)
#         except Exception as e:
#             self.logger.debug("[Oxford] Screenshot failed: %s", e)

#     def _progress(self, pct, msg, url=''):
#         if self._cb:
#             try:
#                 self._cb(progress=pct, status=msg, current_url=url)
#             except Exception:
#                 pass
#         self.logger.info("[Oxford] [%d%%] %s", pct, msg)

#     # ── Virtual display (Xvfb) ───────────────────────────────────────────────

#     def _start_virtual_display(self):
#         try:
#             from pyvirtualdisplay import Display
#             self._vdisplay = Display(visible=False, size=(1400, 900), backend='xvfb')
#             self._vdisplay.start()
#             disp = f":{self._vdisplay.display}"
#             self.logger.info("[Oxford] pyvirtualdisplay on %s", disp)
#             return disp
#         except ImportError:
#             self.logger.info("[Oxford] pyvirtualdisplay not installed — using Xvfb directly")
#             subprocess.run(['pkill', '-f', 'Xvfb :99'], capture_output=True)
#             time.sleep(0.5)
#             proc = subprocess.Popen(
#                 ['Xvfb', ':99', '-screen', '0', '1400x900x24', '-ac'],
#                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
#             self._vdisplay = proc
#             time.sleep(1.5)
#             self.logger.info("[Oxford] Xvfb PID=%d on :99", proc.pid)
#             return ':99'

#     def _stop_virtual_display(self):
#         if self._vdisplay is None:
#             return
#         try:
#             if hasattr(self._vdisplay, 'stop'):
#                 self._vdisplay.stop()
#             elif hasattr(self._vdisplay, 'terminate'):
#                 self._vdisplay.terminate()
#         except Exception:
#             pass
#         finally:
#             self._vdisplay = None
#         self.logger.info("[Oxford] Virtual display stopped")

#     # ── Chrome launch ─────────────────────────────────────────────────────────

#     def _build_chrome_options(self):
#         opts = uc.ChromeOptions()
#         # NO --headless: Oxford captcha blocks headless TLS fingerprint
#         for arg in [
#             "--disable-gpu", "--no-sandbox", "--window-size=1400,900",
#             "--disable-notifications", "--disable-background-timer-throttling",
#             "--disable-backgrounding-occluded-windows",
#             "--disable-renderer-backgrounding", "--disable-dev-shm-usage",
#             "--disable-blink-features=AutomationControlled", "--start-maximized",
#         ]:
#             opts.add_argument(arg)
#         return opts

#     def _try_launch_chrome(self):
#         opts   = self._build_chrome_options()
#         kwargs = dict(options=opts, use_subprocess=False)
#         if self.driver_path:
#             kwargs['driver_executable_path'] = self.driver_path
#         self.logger.info("[Oxford] uc.Chrome() DISPLAY=%s", os.environ.get('DISPLAY'))
#         # [REMOVED uc.Chrome INIT — replaced by mixin]
#         # Wait for window handle
#         deadline = time.time() + 15
#         while time.time() < deadline:
#             try:
#                 if self.driver.window_handles:
#                     self.driver.switch_to.window(self.driver.window_handles[0])
#                     break
#             except Exception:
#                 pass
#             time.sleep(0.5)
#         self.logger.info("[Oxford] Chrome launched OK")

#     def _launch_chrome(self):
#         if platform.system() == 'Windows':
#             self._try_launch_chrome()
#             return

#         if not os.environ.get('DISPLAY'):
#             os.environ['DISPLAY'] = ':0'
#         uid_str = str(os.getuid()) if hasattr(os, 'getuid') else '1000'
#         xauth   = os.environ.get('XAUTHORITY', '')
#         if not xauth or not os.path.exists(xauth):
#             for c in [f"/run/user/{uid_str}/gdm/Xauthority",
#                       os.path.expanduser("~/.Xauthority"),
#                       "/home/ubuntu/.Xauthority", "/root/.Xauthority"]:
#                 if os.path.exists(c) and os.access(c, os.R_OK):
#                     os.environ['XAUTHORITY'] = c
#                     self.logger.info("[Oxford] XAUTHORITY -> %s", c)
#                     break

#         try:
#             self._try_launch_chrome()
#             return
#         except Exception as e1:
#             self.logger.warning("[Oxford] Chrome failed on :0 (%s) -> trying Xvfb",
#                                 type(e1).__name__)

#         xvfb = self._start_virtual_display()
#         os.environ['DISPLAY'] = xvfb
#         os.environ.pop('XAUTHORITY', None)
#         try:
#             self._try_launch_chrome()
#             self.logger.info("[Oxford] Chrome on Xvfb %s OK", xvfb)
#         except Exception as e2:
#             self.logger.error("[Oxford] Chrome also failed on Xvfb: %s\n"
#                               "  Install: sudo apt install xvfb && pip install pyvirtualdisplay", e2)
#             raise

#     def _quit(self):
#         """Always call this in finally — closes Chrome and stops Xvfb."""
#         if self.driver:
#             try:
#                 self.driver.quit()
#                 self.logger.info("[Oxford] Chrome session closed")
#             except Exception:
#                 pass
#             finally:
#                 self.driver = None
#         self._stop_virtual_display()

#     # ── Cookie handling ───────────────────────────────────────────────────────

#     def _save_cookies(self):
#         try:
#             cookies = self.driver.get_cookies()
#             with open(_OXFORD_COOKIE_FILE, 'w') as f:
#                 json.dump(cookies, f)
#             self.logger.info("[Oxford] Cookies saved -> %s", _OXFORD_COOKIE_FILE)
#         except Exception as e:
#             self.logger.warning("[Oxford] Could not save cookies: %s", e)

#     def _load_cookies(self):
#         if not os.path.exists(_OXFORD_COOKIE_FILE):
#             return False
#         try:
#             with open(_OXFORD_COOKIE_FILE) as f:
#                 cookies = json.load(f)
#             self.driver.get("https://academic.oup.com/")   # raw get — avoids recursion via _navigate→detect→_load_cookies
#             time.sleep(2)
#             for cookie in cookies:
#                 cookie.pop('sameSite', None)
#                 try:
#                     self.driver.add_cookie(cookie)
#                 except Exception:
#                     pass
#             self.driver.refresh()
#             time.sleep(2)
#             self.logger.info("[Oxford] Cookies loaded")
#             return True
#         except Exception as e:
#             self.logger.warning("[Oxford] Could not load cookies: %s", e)
#             return False

#     # ── Captcha handling ──────────────────────────────────────────────────────

#     def detect_and_handle_captcha(self):
#         """
#         Oxford 'crawlprevention/governor' soft-block handler.
#         Waits up to 60s for auto-resolution, saves cookies after passing.
#         """
#         if 'crawlprevention' not in self.driver.current_url.lower():
#             return
#         self.logger.warning("[Oxford] Crawler-prevention page: %s", self.driver.current_url)
#         self._save_screenshot('captcha_detected')
#         self._progress(0, 'Oxford captcha detected — waiting up to 60s...')

#         for i in range(60):
#             time.sleep(1)
#             if 'crawlprevention' not in self.driver.current_url.lower():
#                 self.logger.info("[Oxford] Block cleared after %ds", i + 1)
#                 self._save_screenshot('captcha_cleared')
#                 self._save_cookies()
#                 return

#         self.logger.warning("[Oxford] Still blocked after 60s — reloading cookies")
#         self._save_screenshot('captcha_still_blocked')
#         self._load_cookies()
#         time.sleep(3)

#         if 'crawlprevention' in self.driver.current_url.lower():
#             self.logger.error(
#                 "[Oxford] Captcha persists. Scraper continues but results may be limited.")

#     def _try_click_captcha_checkbox(self):
#         """
#         Attempt to click the Cloudflare / Oxford human-verification checkbox.
#         Oxford uses a Cloudflare Turnstile widget inside an iframe.
#         Returns True if the click was attempted.
#         """
#         # Iframe selectors for Cloudflare challenge iframes
#         iframe_selectors = [
#             "iframe[src*='challenges.cloudflare.com']",
#             "iframe[src*='challenge']",
#             "iframe[title*='challenge']",
#             "iframe[title*='verify']",
#             "#challenge-stage iframe",
#             "iframe[src*='turnstile']",
#             "iframe",  # last resort — any iframe
#         ]

#         for iframe_sel in iframe_selectors:
#             try:
#                 iframes = self.driver.find_elements(By.CSS_SELECTOR, iframe_sel)
#                 if not iframes:
#                     continue
#                 for iframe in iframes:
#                     try:
#                         self.driver.switch_to.frame(iframe)
#                         # Checkbox selectors inside Cloudflare challenge iframe
#                         checkbox_selectors = [
#                             "input[type='checkbox']",
#                             ".ctp-checkbox-label",
#                             "label.ctp-checkbox-label",
#                             "#cf-stage input",
#                             "span.mark",
#                             "[id*='checkbox']",
#                             "[class*='checkbox']",
#                         ]
#                         for cb_sel in checkbox_selectors:
#                             try:
#                                 cb = WebDriverWait(self.driver, 2).until(
#                                     EC.presence_of_element_located((By.CSS_SELECTOR, cb_sel)))
#                                 # Use JS click — more reliable than ActionChains for iframe elements
#                                 self.driver.execute_script("arguments[0].click();", cb)
#                                 self.logger.info(
#                                     "[Oxford] Clicked captcha checkbox sel=%r in iframe=%r",
#                                     cb_sel, iframe_sel)
#                                 self.driver.switch_to.default_content()
#                                 return True
#                             except Exception:
#                                 continue
#                         self.driver.switch_to.default_content()
#                     except Exception:
#                         self.driver.switch_to.default_content()
#                         continue
#             except Exception:
#                 try:
#                     self.driver.switch_to.default_content()
#                 except Exception:
#                     pass
#                 continue

#         self.logger.info("[Oxford] No captcha checkbox found to click")
#         return False

#     def _navigate(self, url):
#         """
#         Navigate to url.  If Oxford shows a human-verification page:
#           1. Save a screenshot
#           2. Try to click the Cloudflare checkbox (Turnstile)
#           3. Wait up to 30s for the page to auto-forward
#           4. If still blocked after 30s → proceed anyway (partial results)
#         """
#         self.driver.get(url)   # raw Selenium — do NOT call _navigate here

#         verify_signals = [
#             'verify', 'human', 'cloudflare', 'challenge', 'crawlprevention',
#             'checking your browser', 'just a moment',
#         ]

#         def _is_blocked():
#             cur = self.driver.current_url.lower()
#             ttl = self.driver.title.lower()
#             return (any(s in cur for s in verify_signals) or
#                     any(s in ttl for s in verify_signals))

#         time.sleep(2)

#         if not _is_blocked():
#             return  # clean load — no verification needed

#         self.logger.warning(
#             "[Oxford] Verification page detected — url=%s  title=%r",
#             self.driver.current_url, self.driver.title)
#         self._save_screenshot('verification_page')
#         self._progress(0, 'Oxford human-verification: trying to click checkbox...')

#         # Attempt to click the checkbox
#         clicked = self._try_click_captcha_checkbox()
#         if clicked:
#             self._save_screenshot('verification_after_click')
#             self._progress(0, 'Oxford checkbox clicked — waiting up to 30s for redirect...')
#         else:
#             self._progress(0, 'Oxford verification — no checkbox found, waiting 30s...')

#         # Wait up to 30s for the page to redirect away from the block
#         for i in range(30):
#             time.sleep(1)
#             if not _is_blocked():
#                 self.logger.info("[Oxford] Verification cleared after %ds (clicked=%s)", i+1, clicked)
#                 self._save_screenshot('verification_cleared')
#                 self._save_cookies()
#                 return
#             # Retry click every 5 seconds in case the widget reloaded
#             if i > 0 and i % 5 == 0 and not clicked:
#                 self.logger.info("[Oxford] Retrying checkbox click at %ds...", i)
#                 clicked = self._try_click_captcha_checkbox()

#         self.logger.warning("[Oxford] Still blocked after 30s — proceeding (results may be empty)")
#         self._save_screenshot('verification_timeout')

#         # Also handle crawlprevention URL redirect
#         self.detect_and_handle_captcha()

#     def accept_cookies(self):
#         for selector in [
#             "button#onetrust-accept-btn-handler",
#             "button[id='onetrust-accept-btn-handler']",
#             "div#onetrust-button-group button:nth-child(2)",
#         ]:
#             try:
#                 btn = WebDriverWait(self.driver, 5).until(
#                     EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
#                 btn.click()
#                 self.logger.info("[Oxford] Cookie banner accepted")
#                 time.sleep(1)
#                 self._save_cookies()
#                 return
#             except Exception:
#                 continue

#     # ── Scraping helpers ──────────────────────────────────────────────────────

#     def _get_wait(self):
#         return WebDriverWait(self.driver, 20)

#     def get_total_pages(self):
#         """
#         Oxford stats div text is like: "81-100 of 737"
#         Selector confirmed from live HTML: div.sr-statistics.at-sr-statistics
#         """
#         try:
#             el   = WebDriverWait(self.driver, 15).until(
#                 EC.presence_of_element_located(
#                     (By.CSS_SELECTOR, "div.sr-statistics.at-sr-statistics")))
#             text = el.text.strip()
#             self.logger.info("[Oxford] sr-statistics text: %r", text)
#             # Parse "81-100 of 737" — grab the number after "of"
#             m = re.search(r'of\s+([\d,]+)', text)
#             if m:
#                 total = int(m.group(1).replace(",", ""))
#                 pages = math.ceil(total / 20)
#                 self.logger.info("[Oxford] %d results -> %d pages", total, pages)
#                 return pages
#             # Fallback: grab any standalone integer (handles "737 results" style)
#             nums = re.findall(r'\b(\d[\d,]*)\b', text)
#             if nums:
#                 total = int(max(nums, key=lambda x: int(x.replace(",", ""))).replace(",", ""))
#                 pages = math.ceil(total / 20)
#                 self.logger.info("[Oxford] fallback parse: %d results -> %d pages", total, pages)
#                 return pages
#         except Exception as e:
#             self.logger.error("[Oxford] get_total_pages error: %s", e)
#             self._save_screenshot('get_total_pages_error')
#         return 0

#     def extract_links(self):
#         links = []
#         # Also try updated selectors for article cards
#         card_selectors = [
#             "div.sr-list.al-article-box.al-normal.clearfix",  # old
#             "div.sr-list.al-article-box",                     # without al-normal
#             "article.search-result-item",                     # new
#             "[data-test='article-item']",                     # data-test
#             ".search-result-item",                            # generic
#         ]
#         try:
#             articles = []
#             for sel in card_selectors:
#                 try:
#                     articles = self._get_wait().until(
#                         EC.presence_of_all_elements_located((By.CSS_SELECTOR, sel)))
#                     if articles:
#                         self.logger.info("[Oxford] extract_links using selector: %r", sel)
#                         break
#                 except Exception:
#                     continue

#             link_selectors = [
#                 "a.article-link.at-sr-article-title-link",   # old
#                 "a.article-link",                             # without at- class
#                 "h3.sr-list-title a",                         # h3 title link
#                 ".search-result-title a",                     # generic title
#                 "a[data-test='article-title']",               # data-test
#                 "h3 a",                                       # any h3 link
#             ]
#             for article in articles:
#                 for lsel in link_selectors:
#                     try:
#                         el = article.find_element(By.CSS_SELECTOR, lsel)
#                         href = el.get_attribute("href")
#                         if href:
#                             links.append(href)
#                             break
#                     except Exception:
#                         continue
#             self.logger.info("[Oxford] Extracted %d links", len(links))
#         except Exception as e:
#             self.logger.error("[Oxford] extract_links error: %s", e)
#             self._save_screenshot('extract_links_error')
#         return links

#     def get_next_url(self):
#         """Try multiple selectors for Oxford's 'next page' button."""
#         next_selectors = [
#             "a.sr-nav-next.al-nav-next",    # old
#             "a.sr-nav-next",                # without al- class
#             "a[data-test='next-page']",     # data-test variant
#             ".pagination-next a",           # generic pagination
#             "a[aria-label='Next page']",    # aria-label variant
#             "a[rel='next']",                # rel=next
#         ]
#         for sel in next_selectors:
#             try:
#                 nxt    = self.driver.find_element(By.CSS_SELECTOR, sel)
#                 # Try data-url first, then href
#                 params = nxt.get_attribute("data-url")
#                 if params:
#                     base = self.driver.current_url.split("?")[0]
#                     return urljoin(base, "?" + params)
#                 href = nxt.get_attribute("href")
#                 if href and href != "#":
#                     return href
#             except Exception:
#                 continue
#         return None

#     def save_to_csv(self, data, directory, filename, header=None):
#         try:
#             os.makedirs(directory, exist_ok=True)
#             filepath = os.path.join(directory, filename)
#             with open(filepath, mode="a", newline="", encoding="utf-8") as f:
#                 writer = csv.writer(f)
#                 if os.path.getsize(filepath) == 0 and header:
#                     writer.writerow(header)
#                 writer.writerows(data)
#             return filepath
#         except Exception as e:
#             self.logger.error("[Oxford] save_to_csv error: %s", e)
#             return None

#     def scrape_author_emails(self, input_csv, output_csv):
#         try:
#             with open(input_csv, "r", encoding="utf-8") as f:
#                 reader = csv.reader(f)
#                 next(reader)
#                 urls = [row[0] for row in reader if row]
#         except Exception as e:
#             self.logger.error("[Oxford] Cannot read input CSV: %s", e)
#             return

#         total = len(urls)
#         for i, url in enumerate(urls):
#             if getattr(self, '_stop_requested', lambda: False)():
#                 raise KeyboardInterrupt('Stop requested')
#             self._progress(
#                 50 + int(50 * i / max(total, 1)),
#                 f"Extracting emails {i+1}/{total}",
#                 url)
#             self._navigate(url)
#             self.detect_and_handle_captcha()
#             if not self.driver.current_url.startswith("https://academic.oup.com/"):
#                 continue
#             try:
#                 self.accept_cookies()
#             except Exception:
#                 pass

#             author_names = []
#             try:
#                 try:
#                     show_more = WebDriverWait(self.driver, 5).until(
#                         EC.presence_of_element_located((By.CSS_SELECTOR, "a#show-meta-authors")))
#                     show_more.click()
#                 except Exception:
#                     pass

#                 for link in self.driver.find_elements(
#                         By.CSS_SELECTOR,
#                         "span.al-author-name-more a.js-linked-name-trigger"):
#                     if getattr(self, '_stop_requested', lambda: False)():
#                         raise KeyboardInterrupt('Stop requested')
#                     try:
#                         author_name = link.text.strip()
#                         author_names.append(author_name)
#                         link.click()
#                         popup = self._get_wait().until(EC.presence_of_element_located(
#                             (By.CSS_SELECTOR, "span.al-author-info-wrap.open")))
#                         for el in popup.find_elements(By.CSS_SELECTOR, "a[href^='mailto']"):
#                             email       = el.get_attribute("href").replace("mailto:", "")
#                             best, score = process.extractOne(
#                                 email.split("@")[0], author_names, scorer=fuzz.ratio)
#                             self.save_to_csv(
#                                 [[url, author_name, email, best, score]],
#                                 os.path.dirname(output_csv),
#                                 os.path.basename(output_csv),
#                                 header=["url", "author", "email", "best_match", "match_score"])
#                     except Exception as e:
#                         self.logger.warning("[Oxford] Author link error: %s", e)

#                 # Fallback: Author Notes footnotes
#                 try:
#                     self.driver.find_element(
#                         By.CSS_SELECTOR, "a.js-linked-footnotes").click()
#                     for popup in WebDriverWait(self.driver, 5).until(
#                             EC.presence_of_all_elements_located(
#                                 (By.CSS_SELECTOR, "p.footnote-compatibility"))):
#                         for el in popup.find_elements(By.CSS_SELECTOR, "a[href^='mailto']"):
#                             email       = el.get_attribute("href").replace("mailto:", "")
#                             best, score = process.extractOne(
#                                 email.split("@")[0], author_names or ["unknown"],
#                                 scorer=fuzz.ratio)
#                             self.save_to_csv(
#                                 [[url, None, email, best, score]],
#                                 os.path.dirname(output_csv),
#                                 os.path.basename(output_csv),
#                                 header=["url", "author", "email", "best_match", "match_score"])
#                 except Exception:
#                     pass

#             except Exception as e:
#                 self.logger.error("[Oxford] Error on %s: %s", url, e)
#                 self._save_screenshot(f'article_error_{i}')

#     # ── Main run — called by SeleniumScraperWrapper ───────────────────────────

#     def run(self):
#         """
#         Entry point called by SeleniumScraperWrapper.
#         Launches Chrome, scrapes, cleans up in finally.
#         Returns (csv_path, summary_dict).
#         """
#         csv_path     = None
#         authors_seen = set()
#         emails_seen  = set()

#         try:
#             self._progress(1, 'Launching Chrome...')
#             self._launch_chrome()
#             self._progress(5, 'Chrome ready')

#             qp = {
#                 "q":                          self.keyword,
#                 "f_ContentType":              "Journal Article",
#                 "f_ContentSubTypeDisplayName":
#                     "Research ArticleANDReview ArticleANDOtherANDAbstract",
#                 "fl_SiteID":                  "191",
#                 "rg_ArticleDate":             f"{self.start_year} TO {self.end_year}",
#                 "rg_AllPublicationDates":     f"{self.start_year} TO {self.end_year}",
#                 "rg_VersionDate":             f"{self.start_year} TO {self.end_year}",
#                 "dateFilterType":             "range",
#                 "noDateTypes":                "true",
#             }
#             base_url   = "https://academic.oup.com/search-results"
#             search_url = f"{base_url}?{urlencode(qp)}"
#             out_dir    = self.output_dir
#             slug       = self.directory
#             s          = self.start_year.replace('/', '-')
#             e          = self.end_year.replace('/', '-')

#             self._progress(8, 'Loading Oxford...')
#             self._load_cookies()
#             self._navigate(base_url)
#             time.sleep(3)
#             self._save_screenshot('homepage')
#             self.accept_cookies()
#             self.detect_and_handle_captcha()

#             self._progress(12, 'Running search...')
#             self._navigate(search_url)
#             time.sleep(3)
#             self._save_screenshot('search_results')
#             self.detect_and_handle_captcha()

#             total_pages = self.get_total_pages()
#             all_links   = []

#             for page_num in range(total_pages):
#                 if getattr(self, '_stop_requested', lambda: False)():
#                     raise KeyboardInterrupt('Stop requested')
#                 pct = 12 + int(38 * page_num / max(total_pages, 1))
#                 self._progress(pct, f'Collecting links page {page_num+1}/{total_pages}',
#                                self.driver.current_url)
#                 self.detect_and_handle_captcha()
#                 links    = self.extract_links()
#                 all_links.extend(links)
#                 next_url = self.get_next_url()
#                 if next_url:
#                     self._navigate(next_url)
#                     time.sleep(2)
#                 else:
#                     break

#             url_file   = f"Oxford_{slug}_{s}_to_{e}_urls.csv"
#             email_file = f"Oxford_{slug}_{s}_to_{e}_authors_emails.csv"
#             self.save_to_csv([[lnk] for lnk in all_links],
#                              out_dir, url_file, header=["Article_URL"])

#             self._progress(50, f'Collected {len(all_links)} links — extracting emails...')

#             email_csv_path = os.path.join(out_dir, email_file)
#             self.scrape_author_emails(
#                 os.path.join(out_dir, url_file),
#                 email_csv_path)

#             # Count results
#             if os.path.exists(email_csv_path):
#                 csv_path = email_csv_path
#                 try:
#                     with open(email_csv_path, encoding='utf-8') as f:
#                         for row in csv.DictReader(f):
#                             if row.get('author'):
#                                 authors_seen.add(row['author'])
#                             if row.get('email'):
#                                 emails_seen.add(row['email'])
#         finally:
#             self._quit_chrome()

#                 except Exception:
#                     pass

#             self._save_cookies()
#             self._progress(100, f'Done — {len(authors_seen)} authors, {len(emails_seen)} emails')

#         except KeyboardInterrupt:
#             self.logger.info("[Oxford] Stop requested — returning partial results "
#                              "(%d authors, %d emails)", len(authors_seen), len(emails_seen))
#         except Exception as e:
#             self.logger.error("[Oxford] Fatal error: %s", e)
#             self._save_screenshot('fatal_error')
#             raise
#         finally:
#             self._quit()

#         summary = {
#             'unique_authors': len(authors_seen),
#             'unique_emails':  len(emails_seen),
#             'message':        (f'Found {len(authors_seen)} unique authors, '
#                                f'{len(emails_seen)} unique emails'),
#         }
#         return csv_path, summary


"""oxford_selenium.py — Oxford Academic scraper using ChromeDisplayMixin"""
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

import csv, logging, math, os, random, sys, time
from datetime import datetime
from urllib.parse import urlencode, urljoin

from fuzzywuzzy import fuzz, process
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
import undetected_chromedriver as uc

from utils import safe_log_file_path


class OxfordScraper(ChromeDisplayMixin):

    def __init__(self, keyword, start_year, end_year, driver_path,
                 output_dir=None, progress_callback=None,
                 conference_name=""):
        # ── Required by ChromeDisplayMixin ───────────────────────────────────
        self._vdisplay         = None
        self.driver            = None
        self.wait              = None
        # ── Scraper attrs ─────────────────────────────────────────────────────
        self.output_dir        = output_dir
        self.progress_callback = progress_callback
        self.driver_path       = driver_path
        self.directory         = keyword.replace(" ", "-")
        self.keyword           = keyword
        self.conference_name   = conference_name
        # Raw dates — logger uses them before conversion
        self.start_year        = start_year
        self.end_year          = end_year

        self._setup_logger()

        # Convert MM/DD/YYYY → YYYY-MM-DD for Oxford URLs
        self.start_year_fmt = self._to_oxford_date(start_year)
        self.end_year_fmt   = self._to_oxford_date(end_year)

        # Timestamped CSV names
        from datetime import datetime as _dt
        _ts   = _dt.now().strftime("%H-%M-%S")
        _conf = f"_{conference_name}" if conference_name else ""
        _sd   = start_year.replace("/", "-")
        _ed   = end_year.replace("/", "-")
        _base = f"Oxford{_conf}_{self.directory}_{_sd}_{_ed}_{_ts}"
        self.url_csv     = f"{_base}_urls.csv"
        self.authors_csv = f"{_base}_authors.csv"

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _to_oxford_date(self, date_str: str) -> str:
        """Convert MM/DD/YYYY → YYYY-MM-DD for Oxford date range params."""
        try:
            parts = date_str.split("/")
            return f"{parts[2]}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"
        except Exception:
            return date_str

    def _setup_logger(self):
        self.logger = logging.getLogger(f"OxfordScraper-{id(self)}")
        self.logger.setLevel(logging.INFO)
        log_file = safe_log_file_path(
            "OxfordScraper", self.directory, self.start_year, self.end_year
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
        self.logger.info(f"Oxford ==> Logger initialised → {log_file}")

    def _work_dir(self) -> str:
        d = self.output_dir if self.output_dir else self.directory
        os.makedirs(d, exist_ok=True)
        return d

    def _progress(self, pct, msg, current_url="", authors_count=0, links_count=0):
        self.logger.info(f"Oxford ==> [{pct}%] {msg}")
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
        """Save rows to CSV inside work dir. Filters rows without valid email."""
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
            self.logger.error(f"Oxford ==> CSV save failed: {e}")

    def _init_csv(self, filename, header):
        fp = os.path.join(self._work_dir(), filename)
        with open(fp, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)
        self.logger.info(f"Oxford ==> Initialised {fp}")

    # ── Page helpers ──────────────────────────────────────────────────────────


    def _bypass_cloudflare(self, timeout: int = 120) -> bool:
        """
        Oxford uses Cloudflare managed challenge (auto-verifies in ~5s on most runs).
        Waits for it to clear. RAISES RuntimeError on timeout.
        """
        CF_PHRASES = [
            "just a moment", "verifying you are human",
            "performing security verification", "checking your browser",
        ]

        def _on_cf() -> bool:
            try:
                t = self.driver.title.lower()
                s = self.driver.page_source.lower()[:600]
                return any(p in t or p in s for p in CF_PHRASES)
            except Exception:
                return False

        time.sleep(3)
        if not _on_cf():
            self.logger.info("Oxford ==> CF bypass: no challenge ✓")
            return True

        self.logger.warning(
            f"Oxford ==> ⚠️ Cloudflare challenge — waiting up to {timeout}s "
            f"(managed challenge usually auto-clears). URL: {self.driver.current_url}"
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(3)
            if not _on_cf():
                self.logger.info("Oxford ==> CF bypass: challenge cleared ✓")
                return True
            self.logger.info(
                f"Oxford ==> CF bypass: waiting... ({int(deadline - time.time())}s left)"
            )

        try:
            os.makedirs("logs", exist_ok=True)
            self.driver.save_screenshot("logs/OxfordScraper_cf_timeout.png")
        except Exception:
            pass
        raise RuntimeError(
            f"Oxford Cloudflare challenge not cleared within {timeout}s. "
            "Open VNC at http://3.108.210.45:6080/vnc.html and solve the captcha."
        )

    def accept_cookies(self):
        for sel in [
            "#onetrust-accept-btn-handler",
            "button[id='onetrust-accept-btn-handler']",
        ]:
            try:
                btn = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                )
                self.driver.execute_script("arguments[0].click();", btn)
                self.logger.info("Oxford ==> Cookie consent accepted")
                time.sleep(1)
                return
            except Exception:
                continue

    def _detect_captcha(self):
        """Return True if Oxford governor/captcha page is showing."""
        try:
            url = self.driver.current_url
            return "crawlprevention" in url or "governor" in url
        except Exception:
            return False

    # ── Phase 1: collect article URLs ─────────────────────────────────────────

    def get_total_pages(self) -> int:
        try:
            el = self.wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.sr-statistics.at-sr-statistics")
                )
            )
            total = int(el.text.split()[2].replace(",", ""))
            pages = math.ceil(total / 20)
            self.logger.info(f"Oxford ==> {total} results → {pages} pages")
            return pages
        except Exception as e:
            self.logger.error(f"Oxford ==> get_total_pages failed: {e}")
            return 0

    def extract_links(self) -> list:
        links = []
        try:
            articles = self.wait.until(
                EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR,
                     "div.sr-list.al-article-box.al-normal.clearfix")
                )
            )
            for art in articles:
                try:
                    href = art.find_element(
                        By.CSS_SELECTOR,
                        "a.article-link.at-sr-article-title-link"
                    ).get_attribute("href")
                    if href:
                        links.append(href)
                except Exception:
                    pass
        except Exception as e:
            self.logger.error(f"Oxford ==> extract_links failed: {e}")
        self.logger.info(f"Oxford ==> Extracted {len(links)} links from page")
        return links

    def get_next_url(self):
        try:
            btn = self.driver.find_element(
                By.CSS_SELECTOR, "a.sr-nav-next.al-nav-next"
            )
            params   = btn.get_attribute("data-url")
            base_url = self.driver.current_url.split("?")[0]
            return urljoin(base_url, "?" + params)
        except Exception:
            return None

    # ── Phase 2: extract author emails ────────────────────────────────────────

    def scrape_author_emails(self, article_url: str) -> list:
        """
        Scrape authors + emails from one Oxford article page.
        Returns list of [url, author_name, email] rows.
        """
        results = []
        try:
            self.driver.get(article_url)
            time.sleep(2)

            if self._detect_captcha():
                self.logger.warning(f"Oxford ==> Captcha on {article_url} — skipping")
                return results

            if not article_url.startswith("https://academic.oup.com/"):
                self.logger.info(f"Oxford ==> Skipping non-OUP URL: {article_url}")
                return results

            self.accept_cookies()

            # Expand author list
            try:
                btn = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "a#show-meta-authors")
                    )
                )
                btn.click()
                time.sleep(1)
            except Exception:
                pass

            author_names = []

            # ── Method A: author name popups ──────────────────────────────
            author_links = self.driver.find_elements(
                By.CSS_SELECTOR,
                "span.al-author-name-more a.js-linked-name-trigger"
            )
            for link in author_links:
                try:
                    name = link.text.strip()
                    author_names.append(name)
                    link.click()
                    time.sleep(0.8)

                    popup = self.wait.until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "span.al-author-info-wrap.open")
                        )
                    )
                    email_els = popup.find_elements(
                        By.CSS_SELECTOR, "a[href^='mailto']"
                    )
                    for el in email_els:
                        email = el.get_attribute("href").replace("mailto:", "").strip()
                        if email and "@" in email:
                            best, score = process.extractOne(
                                email.split("@")[0], author_names, scorer=fuzz.ratio
                            )
                            results.append([article_url, name, email])
                            self.logger.info(f"Oxford ==> {name} — {email}")
                except Exception as e:
                    self.logger.warning(f"Oxford ==> Author popup failed: {e}")

            # ── Method B: Author Notes fallback ──────────────────────────
            try:
                notes_btn = self.driver.find_element(
                    By.CSS_SELECTOR, "a.js-linked-footnotes"
                )
                notes_btn.click()
                popups = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_all_elements_located(
                        (By.CSS_SELECTOR, "p.footnote-compatibility")
                    )
                )
                for popup in popups:
                    for el in popup.find_elements(
                        By.CSS_SELECTOR, "a[href^='mailto']"
                    ):
                        email = el.get_attribute("href").replace("mailto:", "").strip()
                        if email and "@" in email:
                            name = ""
                            if author_names:
                                name, _ = process.extractOne(
                                    email.split("@")[0], author_names,
                                    scorer=fuzz.ratio
                                )
                            results.append([article_url, name, email])
                            self.logger.info(f"Oxford ==> Notes fallback: {email}")
            except Exception:
                pass

        except Exception as e:
            self.logger.error(f"Oxford ==> Error on {article_url}: {e}")
        return results

    # ── Main entry point ──────────────────────────────────────────────────────

    def run(self):
        authors_path = os.path.join(self._work_dir(), self.authors_csv)
        try:
            self._launch_chrome(
                self._build_default_chrome_options(), driver_path=self.driver_path
            )
            self.wait = WebDriverWait(self.driver, 20)

            self._init_csv(self.url_csv,     ["Article_URL"])
            self._init_csv(self.authors_csv, ["Article_URL", "Author_Name", "Email"])

            # ── Build search URL ──────────────────────────────────────────
            query_params = {
                "q":                              self.keyword,
                "f_ContentType":                  "Journal Article",
                "dateFilterType":                 "range",
                "rg_ArticleDate":                 f"{self.start_year_fmt} TO {self.end_year_fmt}",
                "rg_AllPublicationDates":         f"{self.start_year_fmt} TO {self.end_year_fmt}",
            }
            base_url   = "https://academic.oup.com/search-results"
            search_url = f"{base_url}?{urlencode(query_params)}"

            # ── Step 1: Homepage → cookie consent ────────────────────────
            self._progress(2, "Loading Oxford Academic homepage...")
            self.driver.get(base_url)
            time.sleep(5)
            self._bypass_cloudflare(timeout=60)
            self.accept_cookies()

            # ── Step 2: Search results ────────────────────────────────────
            self._progress(4, f"Searching: {self.keyword}...")
            self.driver.get(search_url)
            time.sleep(5)
            self._bypass_cloudflare(timeout=120)

            if self._detect_captcha():
                raise RuntimeError(
                    "Oxford governor/captcha detected. "
                    "Open VNC and reload the page manually, then re-run the job."
                )

            # ── Step 3: Paginate and collect URLs ─────────────────────────
            total_pages = self.get_total_pages()
            if total_pages == 0:
                raise RuntimeError("Oxford ==> No results found")

            all_links  = []
            current_url = search_url

            for pg in range(total_pages):
                links = self.extract_links()
                all_links.extend(links)
                self.save_to_csv(
                    [[lnk] for lnk in links], self.url_csv,
                    header=["Article_URL"]
                )
                pct = int(5 + ((pg + 1) / total_pages) * 35)
                self._progress(
                    pct,
                    f"URL collection: page {pg+1}/{total_pages} ({len(all_links)} URLs)",
                    current_url=current_url,
                    links_count=len(all_links),
                )

                next_url = self.get_next_url()
                if not next_url:
                    break
                self.driver.get(next_url)
                current_url = next_url
                time.sleep(2)

            self.logger.info(f"Oxford ==> Phase 1 done: {len(all_links)} URLs")

            # ── Step 4: Extract author emails ─────────────────────────────
            self._progress(40, "PHASE 2: Extracting author emails...")
            total      = len(all_links)
            authors_found = 0

            for idx, article_url in enumerate(all_links, 1):
                rows = self.scrape_author_emails(article_url)
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

            self._progress(100, "Oxford scraping completed.")
            self.logger.info("Oxford ==> Done.")
            return authors_path, f"Oxford scrape complete: {len(all_links)} articles"

        except Exception:
            raise
        finally:
            self._quit_chrome()
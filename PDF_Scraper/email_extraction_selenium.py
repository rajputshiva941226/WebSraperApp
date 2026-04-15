import pandas as pd
import csv
import time
import re
import os
import logging
import sys
from typing import List, Dict, Optional
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

from selenium.common.exceptions import WebDriverException, TimeoutException, NoSuchElementException
from urllib.parse import urlparse

class AuthorInfoExtractor:
    def __init__(self, headless: bool = False, timeout: int = 30000, output_dir: str = "results"):
        """
        Initialize the extractor with Selenium/undetected-chromedriver
        
        Args:
            headless: Run browser in headless mode
            timeout: Page load timeout in milliseconds
            output_dir: Directory to save results
        """
        self.headless = headless
        self.timeout = timeout / 1000  # Convert to seconds for Selenium
        self.output_dir = output_dir
        self.results = []
        # Track cookie acceptance per domain
        self.cookies_accepted = set()

        
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f"Created output directory: {output_dir}")
        
        # Setup logging
        self._setup_logger()
        
        # Initialize browser
        self.driver = None
        self.wait = None
        self._initialize_driver()
    
    

    def _setup_logger(self):
        """Configure the logger"""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)
        
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "author_extractor.log")
        
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        
        if self.logger.hasHandlers():
            self.logger.handlers.clear()
        
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        stream_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(stream_handler)
    
    # In email_extraction_selenium.py, update _initialize_driver method:

    def _initialize_driver(self):
        """Initialize the Chrome driver"""
        try:
            options = Options()
            # Remove headless option completely since you don't want it
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--disable-notifications")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-blink-features=AutomationControlled")
            
            # For PyInstaller compatibility
            import sys
            if getattr(sys, 'frozen', False):
                # Running in PyInstaller bundle
                self.driver = uc.Chrome(options=options, use_subprocess=True, version_main=144)
            else:
                # Running in normal Python
                self.driver = uc.Chrome(options=options, use_subprocess=False, version_main=144)
            
            self.wait = WebDriverWait(self.driver, self.timeout)
            self.driver.maximize_window()
            self.logger.info("Browser initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize browser: {e}")
            raise
        
    def _restart_driver(self):
        """Fully restart Chrome safely"""
        try:
            if self.driver:
                self.driver.quit()
        except:
            pass

        time.sleep(2)

        # IMPORTANT: cookies are gone after restart
        self.cookies_accepted.clear()

        self._initialize_driver()


    def ensure_valid_window(self):
        """
        Ensure Selenium is attached to a live browser window.
        Recover if a site closed the active tab.
        """
        try:
            handles = self.driver.window_handles

            if not handles:
                raise WebDriverException("No browser windows left")

            # Always switch to the newest window
            self.driver.switch_to.window(handles[-1])
            return True

        except Exception as e:
            self.logger.error(f"Window lost, restarting browser: {e}")
            self._restart_driver()
            return False

    def accept_sciencedirect_cookies(self):
        """Accept ScienceDirect OneTrust cookies"""
        try:
            self.ensure_valid_window()

            accept_btn = WebDriverWait(self.driver, 6).until(
                EC.element_to_be_clickable((
                    By.ID, "onetrust-accept-btn-handler"
                ))
            )

            self.driver.execute_script("arguments[0].click();", accept_btn)
            self.logger.info("Accepted cookies for ScienceDirect")
            return True

        except TimeoutException:
            self.logger.info("No ScienceDirect cookie banner found")
            return False

        except Exception as e:
            self.logger.warning(f"ScienceDirect cookie accept failed: {e}")
            return False


    def accept_springer_cookies(self):
        """Accept Springer cookie banner (cc-banner)"""
        try:
            self.ensure_valid_window()

            # Wait for banner container
            WebDriverWait(self.driver, 6).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.cc-banner__content")
                )
            )

            # Click accept button
            accept_btn = WebDriverWait(self.driver, 6).until(
                EC.element_to_be_clickable((
                    By.CSS_SELECTOR,
                    "button[data-cc-action='accept']"
                ))
            )

            self.driver.execute_script("arguments[0].click();", accept_btn)
            self.logger.info("Accepted cookies for Springer")
            return True

        except TimeoutException:
            self.logger.info("No Springer cookie banner found")
            return False

        except Exception as e:
            self.logger.warning(f"Springer cookie accept failed: {e}")
            return False

    def accept_emerald_cookies(self):
        """Accept Emerald Insight OneTrust cookies"""
        try:
            self.ensure_valid_window()

            # Wait for OneTrust container
            WebDriverWait(self.driver, 6).until(
                EC.presence_of_element_located(
                    (By.ID, "onetrust-policy-text")
                )
            )

            accept_btn = WebDriverWait(self.driver, 6).until(
                EC.element_to_be_clickable((
                    By.ID, "onetrust-accept-btn-handler"
                ))
            )

            self.driver.execute_script("arguments[0].click();", accept_btn)
            self.logger.info("Accepted cookies for Emerald")
            return True

        except TimeoutException:
            self.logger.info("No Emerald cookie banner found")
            return False

        except Exception as e:
            self.logger.warning(f"Emerald cookie accept failed: {e}")
            return False

    def accept_oxford_cookies(self):
        """Accept Oxford Academic OneTrust cookies"""
        try:
            self.ensure_valid_window()

            # Wait for OneTrust banner
            WebDriverWait(self.driver, 6).until(
                EC.presence_of_element_located(
                    (By.ID, "onetrust-button-group")
                )
            )

            # Click "Accept all cookies" button
            accept_btn = WebDriverWait(self.driver, 6).until(
                EC.element_to_be_clickable((
                    By.ID, "onetrust-accept-btn-handler"
                ))
            )

            self.driver.execute_script("arguments[0].click();", accept_btn)
            self.logger.info("Accepted cookies for Oxford")
            return True

        except TimeoutException:
            self.logger.info("No Oxford cookie banner found")
            return False

        except Exception as e:
            self.logger.warning(f"Oxford cookie accept failed: {e}")
            return False
        
        
    def accept_cookies(self, domain: str):
        try:
            self.ensure_valid_window()
        except:
            return False

        if domain in self.cookies_accepted:
            return False

        # ScienceDirect
        if domain == "sciencedirect":
            self.accept_sciencedirect_cookies()
            self.cookies_accepted.add(domain)
            return True

        # Springer
        if domain == "springer":
            self.accept_springer_cookies()
            self.cookies_accepted.add(domain)
            return True

        # Emerald
        if domain == "emerald":
            self.accept_emerald_cookies()
            self.cookies_accepted.add(domain)
            return True

        # Oxford
        if domain == "oxford":
            self.accept_oxford_cookies()
            self.cookies_accepted.add(domain)
            return True

        # MDPI (Usercentrics v3)
        if domain == "mdpi":
            try:
                accepted = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, 'button#accept.uc-accept-button')
                    )
                )

                # Scroll + JS click (required)
                self.driver.execute_script("arguments[0].scrollIntoView(true);", accepted)
                self.driver.execute_script("arguments[0].click();", accepted)

                self.logger.info("✅ MDPI cookies accepted (Usercentrics v3)")
                self.cookies_accepted.add(domain)
                return True

            except Exception as e:
                self.logger.warning(f"MDPI cookie accept failed: {e}")

        # Fallback: generic OneTrust
        selectors = [
            "#onetrust-accept-btn-handler",
            "button[data-cc-action='accept']"
        ]

        for selector in selectors:
            try:
                btn = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                )
                self.driver.execute_script("arguments[0].click();", btn)
                self.cookies_accepted.add(domain)
                self.logger.info(f"Accepted cookies for domain: {domain}")
                return True
            except:
                continue

        self.cookies_accepted.add(domain)
        return False


    def extract_nature_authors(self, url: str) -> Dict:
        """Extract author info from Nature articles"""
        result = {
            'url': url,
            'title': '',
            'authors': [],
            'emails': [],
            'extraction_method': 'Nature',
            'status': 'success'
        }
        
        try:
            self.driver.get(url)
            time.sleep(3)
            result['title'] = self.driver.title
            
            # Wait for author list to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'ul.c-article-author-list'))
            )
            
            # Click "Show authors" button if present
            try:
                show_authors_btn = self.driver.find_element(
                    By.CSS_SELECTOR, 
                    'button.c-article-author-list__button[aria-expanded="false"]'
                )
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", show_authors_btn)
                time.sleep(0.5)
                self.driver.execute_script("arguments[0].click();", show_authors_btn)
                time.sleep(1)
                self.logger.info("Nature: Clicked 'Show authors' button")
            except:
                self.logger.info("Nature: 'Show authors' button not found or already expanded")
            
            # Find all author links with envelope icons (corresponding authors)
            author_links = self.driver.find_elements(
                By.CSS_SELECTOR, 
                'a[data-test="author-name"]'
            )
            
            corresponding_authors = []
            for link in author_links:
                try:
                    # Check if this author has an envelope icon
                    envelope_icon = link.find_elements(
                        By.CSS_SELECTOR, 
                        'svg.u-icon use[*|href="#icon-eds-i-mail-medium"]'
                    )
                    if envelope_icon:
                        corresponding_authors.append(link)
                except:
                    continue
            
            self.logger.info(f"Nature: Found {len(corresponding_authors)} corresponding authors")
            
            seen_emails = set()
            
            for author_elem in corresponding_authors:
                try:
                    # Get author name from the link text (remove envelope icon text)
                    author_name = author_elem.text.strip()
                    
                    # Scroll to author link and click
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});", 
                        author_elem
                    )
                    time.sleep(0.5)
                    self.driver.execute_script("arguments[0].click();", author_elem)
                    time.sleep(2)
                    
                    # Wait for popup to appear
                    try:
                        popup = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((
                                By.CSS_SELECTOR, 
                                'div.app-researcher-popup:not(.u-js-hide)'
                            ))
                        )
                        
                        # Extract email from popup
                        email_link = popup.find_element(
                            By.CSS_SELECTOR, 
                            'a[data-track="click_corresponding_email"][href^="mailto:"]'
                        )
                        email = email_link.get_attribute("href").replace("mailto:", "").strip()
                        
                        # Verify author name from popup if needed
                        try:
                            popup_name = popup.find_element(
                                By.CSS_SELECTOR, 
                                'h3.app-researcher-popup__subheading'
                            ).text.strip()
                            if popup_name:
                                author_name = popup_name
                        except:
                            pass
                        
                        # Add to results if email not already seen
                        if email and email not in seen_emails:
                            seen_emails.add(email)
                            result['authors'].append(author_name)
                            result['emails'].append(email)
                            self.logger.info(f"Nature: Matched {author_name} -> {email}")
                        
                        # Close popup
                        try:
                            close_button = self.driver.find_element(
                                By.CSS_SELECTOR, 
                                "button.c-popup__close"
                            )
                            self.driver.execute_script("arguments[0].click();", close_button)
                            time.sleep(0.5)
                        except:
                            # Fallback: press ESC key
                            from selenium.webdriver.common.keys import Keys
                            self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                            time.sleep(0.5)
                    
                    except TimeoutException:
                        self.logger.warning(f"Nature: Popup did not appear for {author_name}")
                        continue
                    
                except Exception as e:
                    self.logger.debug(f"Nature: Error processing author: {e}")
                    continue
            
            self.logger.info(
                f"Nature: Found {len(result['authors'])} authors, {len(result['emails'])} emails"
            )
            
        except Exception as e:
            result['status'] = 'error'
            result['extraction_method'] = f'Nature Error: {str(e)}'
            self.logger.error(f"Nature extraction error: {e}")
        
        return result

    def extract_sciencedirect_authors(self, url: str) -> Dict:
        result = {
            "url": url,
            "title": "",
            "authors": [],
            "emails": [],
            "extraction_method": "ScienceDirect",
            "status": "success"
        }

        try:
            self.driver.get(url)
            time.sleep(3)
            self.accept_cookies("sciencedirect")

            result["title"] = self.driver.title

            # --------------------------------------------------
            # STEP 1: Click "Show all authors" if present
            # --------------------------------------------------
            try:
                show_all = self.driver.find_element(By.ID, "show-more-btn")
                self.driver.execute_script("arguments[0].click();", show_all)
                time.sleep(1)
            except:
                pass

            # --------------------------------------------------
            # STEP 2: Find author buttons with envelope icons
            # --------------------------------------------------
            # Look for buttons that have the envelope icon (indicating email available)
            author_buttons = self.driver.find_elements(
                By.CSS_SELECTOR,
                'button[data-sd-ui-side-panel-opener="true"][data-xocs-content-type="author"] svg.icon-envelope.react-xocs-author-icon'
            )

            # Get parent buttons of the envelope icons
            envelope_buttons = []
            for svg in author_buttons:
                try:
                    # Navigate up to the button element
                    button = svg.find_element(By.XPATH, './ancestor::button[@data-sd-ui-side-panel-opener="true"]')
                    if button not in envelope_buttons:
                        envelope_buttons.append(button)
                except:
                    continue

            self.logger.info(
                f"ScienceDirect: Found {len(envelope_buttons)} author buttons with email"
            )

            seen = set()

            for button in envelope_buttons:
                try:
                    # Scroll + click button
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", button
                    )
                    time.sleep(0.5)
                    self.driver.execute_script("arguments[0].click();", button)
                    time.sleep(1.5)

                    # --------------------------------------------------
                    # STEP 3: Wait for side panel
                    # --------------------------------------------------
                    panel = WebDriverWait(self.driver, 8).until(
                        EC.presence_of_element_located(
                            (By.ID, "side-panel-author")
                        )
                    )

                    # --------------------------------------------------
                    # STEP 4: Extract name
                    # --------------------------------------------------
                    given = panel.find_element(
                        By.CSS_SELECTOR, ".author .given-name"
                    ).text.strip()

                    surname = panel.find_element(
                        By.CSS_SELECTOR, ".author .surname"
                    ).text.strip()

                    author_name = f"{given} {surname}".strip()

                    # --------------------------------------------------
                    # STEP 5: Extract email
                    # --------------------------------------------------
                    email_el = panel.find_element(
                        By.CSS_SELECTOR,
                        ".e-address a[href^='mailto:']"
                    )

                    email = email_el.get_attribute(
                        "href"
                    ).replace("mailto:", "").strip()

                    key = (author_name, email)
                    if key in seen:
                        # Close panel and continue
                        try:
                            close_btn = panel.find_element(
                                By.CSS_SELECTOR,
                                'button[aria-label="Close"]'
                            )
                            self.driver.execute_script(
                                "arguments[0].click();", close_btn
                            )
                        except:
                            self.driver.find_element(
                                By.TAG_NAME, "body"
                            ).send_keys(Keys.ESCAPE)
                        time.sleep(0.5)
                        continue
                    
                    seen.add(key)

                    result["authors"].append(author_name)
                    result["emails"].append(email)

                    self.logger.info(
                        f"ScienceDirect: {author_name} → {email}"
                    )

                    # --------------------------------------------------
                    # STEP 6: Close side panel
                    # --------------------------------------------------
                    try:
                        close_btn = panel.find_element(
                            By.CSS_SELECTOR,
                            'button[aria-label="Close"]'
                        )
                        self.driver.execute_script(
                            "arguments[0].click();", close_btn
                        )
                    except:
                        self.driver.find_element(
                            By.TAG_NAME, "body"
                        ).send_keys(Keys.ESCAPE)

                    time.sleep(0.5)

                except Exception as e:
                    self.logger.debug(
                        f"ScienceDirect author extraction skipped: {e}"
                    )
                    # Try to close any open panel before continuing
                    try:
                        self.driver.find_element(
                            By.TAG_NAME, "body"
                        ).send_keys(Keys.ESCAPE)
                        time.sleep(0.3)
                    except:
                        pass
                    continue

            self.logger.info(
                f"ScienceDirect: Found {len(result['emails'])} emails total"
            )

        except Exception as e:
            result["status"] = "error"
            result["extraction_method"] = f"ScienceDirect Error: {e}"
            self.logger.error(f"ScienceDirect extraction error: {e}")

        return result

    def extract_emails_from_text(self, text: str) -> List[str]:
        """Extract email addresses from text using regex"""
        if not text:
            return []
        
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, text)
        
        # Clean and deduplicate
        emails = list(set([email.lower().strip() for email in emails]))
        return emails
    
    from urllib.parse import urlparse

    def detect_domain_from_browser(self) -> str:
        """
        Detect publisher domain using the currently loaded browser URL
        (handles DOI redirects correctly)
        """
        try:
            current_url = self.driver.current_url.lower()
            parsed = urlparse(current_url)
            domain = parsed.netloc

            # BMJ
            if "bmj.com" in domain:
                return "bmj"

            # Cambridge
            if "cambridge.org" in domain:
                return "cambridge"

            # Emerald
            if "emerald.com" in domain:
                return "emerald"

            # Lippincott / Wolters Kluwer
            if "lww.com" in domain:
                return "lippincott"

            # Oxford Academic
            if "oup.com" in domain or "oxfordacademic.com" in domain:
                return "oxford"

            # Sage
            if "sagepub.com" in domain:
                return "sage"
            # Nature (before Springer check since nature.com is part of Springer Nature)
            if "nature.com" in domain:
                return "nature"
            # Springer
            if "springer.com" in domain or "link.springer.com" in domain:
                return "springer"
            # ScienceDirect
            if "sciencedirect.com" in domain:
                return "sciencedirect"
            
            if "mdpi.com" in domain:
                return "mdpi"


            return "generic"

        except Exception as e:
            self.logger.warning(f"Domain detection failed: {e}")
            return "generic"

    
    def extract_bmj_authors(self, url: str) -> Dict:
        """Extract author info from BMJ articles"""
        result = {
            'url': url,
            'title': '',
            'authors': [],
            'emails': [],
            'extraction_method': 'BMJ',
            'status': 'success'
        }
        
        try:
            # Try .info URL first
            info_url = url + ".info" if not url.endswith(".info") else url
            self.driver.get(info_url)
            time.sleep(5)
            
            result['title'] = self.driver.title
            
            current_url = self.driver.current_url
            if current_url.endswith(".info"):
                # Old style extraction
                author_notes = self.driver.find_elements(By.CSS_SELECTOR, "li#corresp-1")
                for note in author_notes:
                    corresp_text = note.text.strip()
                    email_matches = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', corresp_text)
                    
                    if email_matches:
                        text_parts = re.split(r'[\w\.-]+@[\w\.-]+\.\w+', corresp_text)
                        for i, email in enumerate(email_matches):
                            name_part = text_parts[i].strip()
                            to_remove = ["Correspondence to", "Dr", "Professor", ":", ";", "\n"]
                            author_name = name_part
                            for phrase in to_remove:
                                author_name = author_name.replace(phrase, "").strip()
                            
                            author_name_final = author_name.split(",")[0].strip()
                            if author_name_final:
                                result['authors'].append(author_name_final)
                                result['emails'].append(email)
            else:
                # New style extraction
                try:
                    show_all = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, '#show-all-button button'))
                    )
                    show_all.click()
                    time.sleep(1)
                except:
                    pass
                
                envelopes = self.driver.find_elements(By.CSS_SELECTOR, "#author-list-envelope-icon")
                for ele in envelopes:
                    try:
                        actions = ActionChains(self.driver)
                        actions.move_to_element(ele).perform()
                        ele.click()
                        time.sleep(1)
                        
                        div_ele = WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, 'div#popover-border'))
                        )
                        
                        email_href = div_ele.find_element(By.CSS_SELECTOR, 
                            'p[data-testid^="author-popover-email"] > a[href^="mailto:"]')
                        email = email_href.get_attribute("href").replace("mailto:", "").strip()
                        
                        author_name = div_ele.find_element(By.CSS_SELECTOR, 
                            'p[data-testid="popover-title "]').text.strip()
                        
                        result['authors'].append(author_name)
                        result['emails'].append(email)
                    except:
                        continue
            
            self.logger.info(f"BMJ: Found {len(result['authors'])} authors, {len(result['emails'])} emails")
            
        except Exception as e:
            result['status'] = 'error'
            result['extraction_method'] = f'BMJ Error: {str(e)}'
            self.logger.error(f"BMJ extraction error: {e}")
        
        return result
    
    def extract_cambridge_authors(self, url: str) -> Dict:
        """Extract author info from Cambridge articles"""
        result = {
            'url': url,
            'title': '',
            'authors': [],
            'emails': [],
            'extraction_method': 'Cambridge',
            'status': 'success'
        }
        
        try:
            self.driver.get(url)
            time.sleep(3)
            result['title'] = self.driver.title
            
            # Click "Show author details" if available
            try:
                show_details = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//a[@aria-controls='authors-details']"))
                )
                self.driver.execute_script("arguments[0].scrollIntoView(true);", show_details)
                time.sleep(1)
                show_details.click()
                time.sleep(2)
                
                # Wait for author details to expand
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div#authors-details"))
                )
            except:
                self.logger.warning("Cambridge: Show author details link not found or not clickable")
            
            # Extract author names
            author_elements = self.driver.find_elements(By.CSS_SELECTOR, "dt.title")
            author_names = [elem.text.strip() for elem in author_elements if elem.text.strip()]
            author_names = [name for name in author_names if name not in ["*", "Type", "Information", "Copyright"]]
            
            # Separate starred and non-starred authors
            starred_authors = [name for name in author_names if name.endswith("*")]
            non_starred_authors = [name for name in author_names if not name.endswith("*")]
            
            # Extract emails from div.corresp (for starred authors)
            email_containers = self.driver.find_elements(By.CSS_SELECTOR, "div.corresp")
            emails_from_corresp = []
            for container in email_containers:
                email_text = container.text.strip()
                found_emails = re.findall(r'[\w\.-]+@[\w\.-]+', email_text)
                emails_from_corresp.extend(found_emails)
            
            emails_from_corresp = list(set(emails_from_corresp))
            
            # Match starred authors with emails using fuzzy matching
            from fuzzywuzzy import process, fuzz
            
            for author_name in starred_authors:
                best_email = None
                if emails_from_corresp:
                    best_match = process.extractOne(
                        author_name.strip("*"), 
                        emails_from_corresp, 
                        scorer=fuzz.token_sort_ratio
                    )
                    if best_match and best_match[1] > 50:  # 50% threshold
                        best_email = best_match[0]
                
                if best_email:
                    result['authors'].append(author_name.strip("*"))
                    result['emails'].append(best_email)
                    self.logger.info(f"Cambridge: Matched starred author {author_name.strip('*')} -> {best_email}")
            
            # Fallback method for non-starred authors
            try:
                email_spans = self.driver.find_elements(By.CSS_SELECTOR, "span[data-v-2edb8da6] > span[data-v-2edb8da6]")
                fallback_emails = []
                
                for span in email_spans:
                    span_text = span.text.strip()
                    if "e-mail:" in span_text.lower() or "e-mails:" in span_text.lower():
                        # Extract email part after the colon
                        email_part = span_text.split(":", 1)[1] if ":" in span_text else span_text
                        # Split by comma and clean each email
                        emails = [email.strip().strip(")").strip() for email in email_part.split(",")]
                        fallback_emails.extend([e for e in emails if "@" in e])
                
                fallback_emails = list(set(fallback_emails))
                
                if fallback_emails:
                    # Create mapping of email local part to full email for better matching
                    emails_for_matching = {email.split("@")[0]: email for email in fallback_emails}
                    
                    for author_name in non_starred_authors:
                        best_email = None
                        best_match = process.extractOne(
                            author_name, 
                            emails_for_matching.keys(), 
                            scorer=fuzz.token_sort_ratio
                        )
                        
                        if best_match and best_match[1] > 50:  # 50% threshold
                            best_email_local_part = best_match[0]
                            best_email = emails_for_matching[best_email_local_part]
                        
                        if best_email:
                            result['authors'].append(author_name.strip("*"))
                            result['emails'].append(best_email)
                            self.logger.info(f"Cambridge: Matched non-starred author {author_name} -> {best_email}")
            
            except Exception as e:
                self.logger.warning(f"Cambridge: Fallback method failed for {url}: {e}")
            
            self.logger.info(f"Cambridge: Found {len(result['authors'])} authors, {len(result['emails'])} emails")
            
        except Exception as e:
            result['status'] = 'error'
            result['extraction_method'] = f'Cambridge Error: {str(e)}'
            self.logger.error(f"Cambridge extraction error for {url}: {e}")
        
        return result
    # def extract_emerald_authors(self, url: str) -> Dict:
    #     """Extract author info from Emerald articles (old + new UI)"""
    #     result = {
    #         'url': url,
    #         'title': '',
    #         'authors': [],
    #         'emails': [],
    #         'extraction_method': 'Emerald',
    #         'status': 'success'
    #     }

    #     try:
    #         self.driver.get(url)
    #         time.sleep(3)

    #         self.ensure_valid_window()

    #         result['title'] = self.driver.title

    #         seen_emails = set()

    #         # ============================
    #         # ✅ NEW EMERALD UI (icon click)
    #         # ============================
    #         author_links = self.driver.find_elements(
    #             By.CSS_SELECTOR,
    #             "a.stats-author-info-trigger"
    #         )

    #         for link in author_links:
    #             try:
    #                 self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link)
    #                 time.sleep(0.5)
    #                 self.driver.execute_script("arguments[0].click();", link)
    #                 time.sleep(1)

    #                 # Wait for open info card
    #                 info_card = WebDriverWait(self.driver, 5).until(
    #                     EC.presence_of_element_located(
    #                         (By.CSS_SELECTOR, "div.al-author-info-wrap.open")
    #                     )
    #                 )

    #                 # Author name
    #                 try:
    #                     author_name = info_card.find_element(
    #                         By.CSS_SELECTOR, "div.info-card-name"
    #                     ).text.strip()
    #                 except:
    #                     author_name = link.text.strip()

    #                 # Email
    #                 email_links = info_card.find_elements(
    #                     By.CSS_SELECTOR,
    #                     "div.info-author-correspondence a[href^='mailto:']"
    #                 )

    #                 for email_el in email_links:
    #                     email = email_el.get_attribute("href").replace("mailto:", "").strip()
    #                     if email and email not in seen_emails:
    #                         seen_emails.add(email)
    #                         result['authors'].append(author_name)
    #                         result['emails'].append(email)

    #                 # Close popup by clicking body
    #                 self.driver.execute_script("document.body.click();")
    #                 time.sleep(0.5)

    #             except Exception:
    #                 continue

    #         # ============================
    #         # 🔁 FALLBACK: old footnotes UI
    #         # ============================
    #         if not result['emails']:
    #             try:
    #                 footnotes = self.driver.find_elements(
    #                     By.CSS_SELECTOR, "div.article-footnote"
    #                 )

    #                 for fn in footnotes:
    #                     text = fn.text.strip()
    #                     if "can be contacted at" in text:
    #                         email_el = fn.find_element(By.CSS_SELECTOR, "a[href^='mailto:']")
    #                         email = email_el.get_attribute("href").replace("mailto:", "").strip()

    #                         author_name = text.split("can be contacted at")[0].strip()
    #                         author_name = re.sub(
    #                             r"(Corresponding author|is the corresponding author|E-mail:|:)",
    #                             "",
    #                             author_name,
    #                             flags=re.I
    #                         ).strip()

    #                         if email and email not in seen_emails:
    #                             seen_emails.add(email)
    #                             result['authors'].append(author_name)
    #                             result['emails'].append(email)
    #             except:
    #                 pass

    #         self.logger.info(
    #             f"Emerald: Found {len(result['authors'])} authors, {len(result['emails'])} emails"
    #         )

    #     except Exception as e:
    #         result['status'] = 'error'
    #         result['extraction_method'] = f'Emerald Error: {str(e)}'
    #         self.logger.error(f"Emerald extraction error: {e}")

    #     return result

    def extract_emerald_authors(self, url: str) -> Dict:
        """Extract author info from Emerald articles (improved for both UIs)"""
        result = {
            'url': url,
            'title': '',
            'authors': [],
            'emails': [],
            'extraction_method': 'Emerald',
            'status': 'success'
        }

        try:
            self.driver.get(url)
            time.sleep(3)

            self.ensure_valid_window()
            self.accept_cookies("emerald")

            result['title'] = self.driver.title

            seen_emails = set()

            # ============================
            # ✅ NEW EMERALD UI (click author names with icon)
            # ============================
            try:
                # Find all clickable author links
                author_links = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    "a.linked-name.js-linked-name.stats-author-info-trigger"
                )

                self.logger.info(f"Emerald: Found {len(author_links)} author links")

                for link in author_links:
                    try:
                        # Get author name from link text (before clicking)
                        author_name = link.text.strip()
                        
                        # Remove the corresponding author icon text if present
                        author_name = author_name.replace("Corresponding Author", "").strip()
                        
                        if not author_name:
                            continue

                        # Scroll and click
                        self.driver.execute_script(
                            "arguments[0].scrollIntoView({block:'center'});", 
                            link
                        )
                        time.sleep(0.5)
                        self.driver.execute_script("arguments[0].click();", link)
                        time.sleep(1.5)

                        # Wait for info card to open
                        try:
                            info_card = WebDriverWait(self.driver, 5).until(
                                EC.presence_of_element_located(
                                    (By.CSS_SELECTOR, "div.al-author-info-wrap.open div.info-card-author")
                                )
                            )

                            # Extract author name from info card (more reliable)
                            try:
                                name_elem = info_card.find_element(
                                    By.CSS_SELECTOR, "div.info-card-name"
                                )
                                # Get clean name without footnotes
                                card_name = self.driver.execute_script("""
                                    var elem = arguments[0].cloneNode(true);
                                    var footnotes = elem.querySelectorAll('.info-card-footnote');
                                    footnotes.forEach(function(fn) { fn.remove(); });
                                    return elem.textContent.trim();
                                """, name_elem)
                                if card_name:
                                    author_name = card_name
                            except:
                                pass

                            # Extract email from correspondence section
                            try:
                                corresp_div = info_card.find_element(
                                    By.CSS_SELECTOR, "div.info-author-correspondence"
                                )
                                
                                # Look for email in text first
                                corresp_text = corresp_div.text.strip()
                                
                                # Pattern: "Name can be contacted at: email"
                                if "can be contacted at" in corresp_text:
                                    email_part = corresp_text.split("can be contacted at")[-1].strip()
                                    # Extract email using regex
                                    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', email_part)
                                    if email_match:
                                        email = email_match.group(0).strip()
                                        if email and email not in seen_emails:
                                            seen_emails.add(email)
                                            result['authors'].append(author_name)
                                            result['emails'].append(email)
                                            self.logger.info(f"Emerald: {author_name} -> {email}")
                                else:
                                    # Try mailto links
                                    email_links = corresp_div.find_elements(
                                        By.CSS_SELECTOR, "a[href^='mailto:']"
                                    )
                                    for email_el in email_links:
                                        email = email_el.get_attribute("href").replace("mailto:", "").strip()
                                        if email and email not in seen_emails:
                                            seen_emails.add(email)
                                            result['authors'].append(author_name)
                                            result['emails'].append(email)
                                            self.logger.info(f"Emerald: {author_name} -> {email}")
                            except:
                                pass

                            # Close popup by clicking elsewhere
                            try:
                                self.driver.execute_script("document.body.click();")
                                time.sleep(0.5)
                            except:
                                pass

                        except TimeoutException:
                            self.logger.debug(f"Emerald: No info card appeared for {author_name}")
                            continue

                    except Exception as e:
                        self.logger.debug(f"Emerald: Error processing author link: {e}")
                        continue

            except Exception as e:
                self.logger.warning(f"Emerald: New UI extraction failed: {e}")

            # ============================
            # 🔁 FALLBACK: Old footnotes UI
            # ============================
            if not result['emails']:
                try:
                    self.logger.info("Emerald: Trying fallback footnotes extraction")
                    
                    footnotes = self.driver.find_elements(
                        By.CSS_SELECTOR, "div.article-footnote"
                    )

                    for fn in footnotes:
                        text = fn.text.strip()
                        if "can be contacted at" in text:
                            # Extract email
                            email_links = fn.find_elements(By.CSS_SELECTOR, "a[href^='mailto:']")
                            if email_links:
                                email = email_links[0].get_attribute("href").replace("mailto:", "").strip()
                            else:
                                # Try regex
                                email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
                                email = email_match.group(0) if email_match else None

                            if email:
                                # Extract author name
                                author_name = text.split("can be contacted at")[0].strip()
                                author_name = re.sub(
                                    r"(Corresponding author|is the corresponding author|E-mail:|:)",
                                    "",
                                    author_name,
                                    flags=re.I
                                ).strip()

                                if email and email not in seen_emails:
                                    seen_emails.add(email)
                                    result['authors'].append(author_name)
                                    result['emails'].append(email)
                                    self.logger.info(f"Emerald (Fallback): {author_name} -> {email}")
                except Exception as e:
                    self.logger.warning(f"Emerald: Fallback extraction failed: {e}")

            self.logger.info(
                f"Emerald: Found {len(result['authors'])} authors, {len(result['emails'])} emails"
            )

        except Exception as e:
            result['status'] = 'error'
            result['extraction_method'] = f'Emerald Error: {str(e)}'
            self.logger.error(f"Emerald extraction error: {e}")

        return result

    def extract_lippincott_authors(self, url: str) -> Dict:
        """Extract author info from Lippincott articles (updated for new HTML structure)"""
        result = {
            'url': url,
            'title': '',
            'authors': [],
            'emails': [],
            'extraction_method': 'Lippincott',
            'status': 'success'
        }
        
        try:
            self.driver.get(url)
            time.sleep(5)
            result['title'] = self.driver.title
            
            seen_pairs = set()
            
            # ==========================================
            # STEP 1: Click "Author Information" link
            # ==========================================
            try:
                author_info_link = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR, 
                        "#ejp-article-authors-link, a#ejp-article-authors-link"
                    ))
                )
                
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", 
                    author_info_link
                )
                time.sleep(0.5)
                
                # Click using JavaScript to avoid interception issues
                self.driver.execute_script("arguments[0].click();", author_info_link)
                time.sleep(2)
                
                self.logger.info("Lippincott: Clicked 'Author Information' link")
                
            except Exception as e:
                self.logger.warning(f"Lippincott: Could not find/click Author Information link: {e}")
                result['status'] = 'error'
                result['extraction_method'] = f'Lippincott Error: Could not find Author Information section'
                return result
            
            # ==========================================
            # STEP 2: Wait for author info section to appear
            # ==========================================
            try:
                author_info_section = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR, 
                        "#ejp-article-authors-info, section#ejp-article-authors-info"
                    ))
                )
                
                self.logger.info("Lippincott: Author information section loaded")
                
            except Exception as e:
                self.logger.warning(f"Lippincott: Author info section did not appear: {e}")
                result['status'] = 'error'
                result['extraction_method'] = f'Lippincott Error: Author info section not found'
                return result
            
            # ==========================================
            # STEP 3: Extract correspondence information
            # ==========================================
            try:
                # Find all paragraphs in the author info section
                info_paragraphs = author_info_section.find_elements(
                    By.CSS_SELECTOR, 
                    "p"
                )
                
                for paragraph in info_paragraphs:
                    try:
                        # Get the paragraph text and HTML
                        para_text = paragraph.text.strip()
                        para_html = paragraph.get_attribute('innerHTML')
                        
                        # Check if this is a correspondence paragraph
                        if ('correspondence' in para_text.lower() or 
                            'corresponding author' in para_text.lower() or
                            paragraph.get_attribute('id').startswith('cor')):
                            
                            # Extract email
                            email_links = paragraph.find_elements(
                                By.CSS_SELECTOR, 
                                'a[href^="mailto:"]'
                            )
                            
                            if email_links:
                                for email_link in email_links:
                                    email_href = email_link.get_attribute("href")
                                    # Handle double mailto: prefix
                                    email = email_href.replace("mailto:mailto:", "").replace("mailto:", "").strip()
                                    
                                    if email:
                                        # Extract author name from the paragraph
                                        author_name = self._extract_author_name_from_correspondence(para_text, email)
                                        
                                        pair = (author_name, email)
                                        if pair not in seen_pairs:
                                            seen_pairs.add(pair)
                                            result['authors'].append(author_name)
                                            result['emails'].append(email)
                                            self.logger.info(f"Lippincott: Matched {author_name} -> {email}")
                    
                    except Exception as e:
                        self.logger.debug(f"Lippincott: Error processing paragraph: {e}")
                        continue
                
            except Exception as e:
                self.logger.warning(f"Lippincott: Error extracting correspondence info: {e}")
            
            # ==========================================
            # STEP 4: Fallback - Try to extract from main author section
            # ==========================================
            if not result['emails']:
                try:
                    self.logger.info("Lippincott: Trying fallback extraction from main author section")
                    
                    # Get the main author section
                    main_author_section = self.driver.find_element(
                        By.CSS_SELECTOR,
                        "#ejp-article-authors"
                    )
                    
                    # Look for authors with asterisk (corresponding author marker)
                    author_text = main_author_section.text
                    
                    # Find all emails in the expanded section
                    all_emails = self.extract_emails_from_text(author_info_section.text)
                    
                    # Try to match authors with asterisks to emails
                    if all_emails:
                        # Look for names followed by asterisk in superscript
                        author_name_pattern = r'([A-Z][a-z]+(?:,\s*[A-Z][a-z]+)+)\s*\*'
                        matches = re.finditer(author_name_pattern, author_text)
                        
                        for match in matches:
                            # Name might be in "Last, First" format
                            raw_name = match.group(1).strip()
                            # Convert "Last, First" to "First Last"
                            if ',' in raw_name:
                                parts = [p.strip() for p in raw_name.split(',')]
                                author_name = ' '.join(reversed(parts))
                            else:
                                author_name = raw_name
                            
                            # Match with available emails
                            if all_emails:
                                email = all_emails[0]  # Use first available email
                                pair = (author_name, email)
                                if pair not in seen_pairs:
                                    seen_pairs.add(pair)
                                    result['authors'].append(author_name)
                                    result['emails'].append(email)
                                    self.logger.info(f"Lippincott (Fallback): Matched {author_name} -> {email}")
                                    all_emails.pop(0)  # Remove used email
                
                except Exception as e:
                    self.logger.warning(f"Lippincott: Fallback extraction failed: {e}")
            
            self.logger.info(
                f"Lippincott: Found {len(result['authors'])} authors, {len(result['emails'])} emails"
            )
            
        except Exception as e:
            result['status'] = 'error'
            result['extraction_method'] = f'Lippincott Error: {str(e)}'
            self.logger.error(f"Lippincott extraction error: {e}")
        
        return result


    def _extract_author_name_from_correspondence(self, correspondence_text: str, email: str) -> str:
        """
        Helper method to extract author name from correspondence paragraph text.
        
        Args:
            correspondence_text: The text from the correspondence paragraph
            email: The extracted email address
            
        Returns:
            Extracted author name or empty string
        """
        author_name = ""
        
        try:
            # Remove common prefixes and suffixes
            text = correspondence_text
            
            # Remove phrases before the actual name
            prefixes_to_remove = [
                "Correspondence to:",
                "Corresponding author:",
                "Address correspondence to:",
                "Correspondence:",
                "*",
                "**",
                "†",
                "‡"
            ]
            
            for prefix in prefixes_to_remove:
                text = text.replace(prefix, "")
            
            # Split by email to get the part before it
            if email in text:
                text = text.split(email)[0]
            
            # Split by comma to get name part (usually "Name, Title" format)
            parts = text.split(',')
            
            if parts:
                potential_name = parts[0].strip()
                
                # Remove academic titles
                titles_to_remove = ["Dr.", "Dr", "Prof.", "Prof", "Professor", "MD", "PhD", "MS", "MSc"]
                for title in titles_to_remove:
                    potential_name = potential_name.replace(title, "")
                
                # Clean up extra whitespace and special characters
                potential_name = re.sub(r'\s+', ' ', potential_name).strip()
                potential_name = re.sub(r'[*†‡§¶#]+', '', potential_name).strip()
                
                # Check if we have a valid name (at least 2 characters, contains letters)
                if len(potential_name) > 2 and re.search(r'[A-Za-z]', potential_name):
                    author_name = potential_name
            
            # If we couldn't extract a good name, try another approach
            if not author_name:
                # Look for pattern: "Name, Title, email"
                # Extract everything between "Correspondence to:" and the email/comma
                match = re.search(
                    r'(?:correspondence|corresponding author)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
                    text,
                    re.IGNORECASE
                )
                if match:
                    author_name = match.group(1).strip()
        
        except Exception as e:
            pass
        
        return author_name
    
    def extract_oxford_authors(self, url: str) -> Dict:
        """Extract author info from Oxford articles (updated for new HTML structure)"""
        result = {
            'url': url,
            'title': '',
            'authors': [],
            'emails': [],
            'extraction_method': 'Oxford',
            'status': 'success'
        }
        
        try:
            self.driver.get(url)
            time.sleep(3)
            
            # Check if URL is valid Oxford Academic URL
            current_url = self.driver.current_url
            if not current_url.startswith("https://academic.oup.com/"):
                self.logger.warning(f"Oxford: URL {current_url} does not match expected Oxford Academic pattern")
                result['status'] = 'skipped'
                result['extraction_method'] = 'Oxford (Invalid URL)'
                return result
            
            result['title'] = self.driver.title
            
            seen_pairs = set()
            
            # ==========================================
            # STEP 1: Click "Show More" if available
            # ==========================================
            try:
                show_more = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a#show-meta-authors"))
                )
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", show_more)
                time.sleep(0.5)
                show_more.click()
                time.sleep(2)
                self.logger.info("Oxford: Clicked 'Show More' button")
            except:
                self.logger.info("Oxford: No 'Show More' button found, proceeding with visible authors")
            
            # ==========================================
            # STEP 2: Find author links with envelope icons
            # ==========================================
            try:
                # Find all author links that contain an envelope icon
                author_links_with_email = self.driver.find_elements(
                    By.CSS_SELECTOR, 
                    'a.linked-name.js-linked-name-trigger i.icon-general-mail'
                )
                
                # Get the parent <a> elements
                author_links = []
                for icon in author_links_with_email:
                    try:
                        link = icon.find_element(By.XPATH, './parent::a')
                        if link not in author_links:
                            author_links.append(link)
                    except:
                        continue
                
                self.logger.info(f"Oxford: Found {len(author_links)} author links with email icons")
                
                # ==========================================
                # STEP 3: Click each author link and extract info
                # ==========================================
                for link in author_links:
                    try:
                        # Scroll to link
                        self.driver.execute_script(
                            "arguments[0].scrollIntoView({block: 'center'});", 
                            link
                        )
                        time.sleep(0.5)
                        
                        # Click to open info card
                        self.driver.execute_script("arguments[0].click();", link)
                        time.sleep(1.5)
                        
                        self.logger.info(f"Oxford: Clicked author link")
                        
                        # Wait for info card to appear
                        info_card = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((
                                By.CSS_SELECTOR, 
                                'span.al-author-info-wrap.arrow-up'
                            ))
                        )
                        
                        # ==========================================
                        # STEP 4: Extract author name from info card
                        # ==========================================
                        author_name = ""
                        try:
                            name_elem = info_card.find_element(
                                By.CSS_SELECTOR, 
                                'div.info-card-name'
                            )
                            # Get text content, excluding footnote spans
                            author_name = self.driver.execute_script("""
                                var elem = arguments[0];
                                var clone = elem.cloneNode(true);
                                var footnotes = clone.querySelectorAll('.info-card-footnote');
                                footnotes.forEach(function(fn) { fn.remove(); });
                                return clone.textContent.trim();
                            """, name_elem)
                            
                            if not author_name:
                                author_name = name_elem.text.strip()
                        except:
                            self.logger.warning("Oxford: Could not extract author name from info card")
                        
                        # ==========================================
                        # STEP 5: Extract email from correspondence section
                        # ==========================================
                        emails = []
                        try:
                            correspondence_div = info_card.find_element(
                                By.CSS_SELECTOR, 
                                'div.info-author-correspondence'
                            )
                            
                            email_links = correspondence_div.find_elements(
                                By.CSS_SELECTOR, 
                                'a[href^="mailto:"]'
                            )
                            
                            for email_elem in email_links:
                                email = email_elem.get_attribute("href").replace("mailto:", "").strip()
                                if email:
                                    emails.append(email)
                        except:
                            self.logger.warning(f"Oxford: Could not extract email for {author_name}")
                        
                        # ==========================================
                        # STEP 6: Add to results if we have both name and email
                        # ==========================================
                        if author_name and emails:
                            for email in emails:
                                pair = (author_name, email)
                                if pair not in seen_pairs:
                                    seen_pairs.add(pair)
                                    result['authors'].append(author_name)
                                    result['emails'].append(email)
                                    self.logger.info(f"Oxford: Matched {author_name} -> {email}")
                        elif author_name:
                            # Add author without email if not already added
                            if author_name not in result['authors']:
                                result['authors'].append(author_name)
                                self.logger.info(f"Oxford: Added {author_name} (no email found)")
                        
                        # ==========================================
                        # STEP 7: Close info card
                        # ==========================================
                        try:
                            # Click elsewhere to close the popup
                            from selenium.webdriver.common.keys import Keys
                            self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                            time.sleep(0.5)
                        except:
                            pass
                        
                    except Exception as e:
                        self.logger.warning(f"Oxford: Failed to process author link: {e}")
                        # Try to close any open popup before continuing
                        try:
                            from selenium.webdriver.common.keys import Keys
                            self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                            time.sleep(0.3)
                        except:
                            pass
                        continue
            
            except Exception as e:
                self.logger.warning(f"Oxford: Error processing author links: {e}")
            
            # ==========================================
            # STEP 8: Fallback - Check "Author Notes" section
            # ==========================================
            if not result['emails']:
                try:
                    self.logger.info("Oxford: Trying Author Notes fallback")
                    
                    # Look for the author notes link
                    author_notes_link = self.driver.find_element(
                        By.CSS_SELECTOR, 
                        "a.js-linked-footnotes"
                    )
                    
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});", 
                        author_notes_link
                    )
                    time.sleep(0.5)
                    author_notes_link.click()
                    time.sleep(2)
                    
                    self.logger.info("Oxford: Clicked 'Author Notes'")
                    
                    # Wait for popup contents
                    popup_contents = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_all_elements_located((
                            By.CSS_SELECTOR, 
                            "p.footnote-compatibility"
                        ))
                    )
                    
                    # Extract all author names for fuzzy matching
                    all_author_names = []
                    try:
                        author_name_elems = self.driver.find_elements(
                            By.CSS_SELECTOR,
                            'div.info-card-name'
                        )
                        for elem in author_name_elems:
                            name = elem.text.strip()
                            if name:
                                all_author_names.append(name)
                    except:
                        pass
                    
                    for popup in popup_contents:
                        try:
                            # Extract emails from this footnote
                            email_elements = popup.find_elements(
                                By.CSS_SELECTOR, 
                                "a[href^='mailto:']"
                            )
                            
                            for email_elem in email_elements:
                                email = email_elem.get_attribute("href").replace("mailto:", "").strip()
                                
                                if email and email not in result['emails']:
                                    # Try to match with author names
                                    matched_author = ""
                                    
                                    if all_author_names:
                                        from fuzzywuzzy import process, fuzz
                                        best_match = process.extractOne(
                                            email.split("@")[0],
                                            all_author_names,
                                            scorer=fuzz.ratio
                                        )
                                        
                                        if best_match and best_match[1] > 50:
                                            matched_author = best_match[0]
                                    
                                    pair = (matched_author, email)
                                    if pair not in seen_pairs:
                                        seen_pairs.add(pair)
                                        result['authors'].append(matched_author)
                                        result['emails'].append(email)
                                        self.logger.info(
                                            f"Oxford (Fallback): Matched {matched_author} -> {email}"
                                        )
                        
                        except Exception as e:
                            self.logger.debug(f"Oxford: Error processing footnote: {e}")
                            continue
                    
                except Exception as e:
                    self.logger.info(f"Oxford: No emails found in Author Notes fallback: {e}")
            
            self.logger.info(
                f"Oxford: Found {len(result['authors'])} authors, {len(result['emails'])} emails"
            )
            
        except Exception as e:
            result['status'] = 'error'
            result['extraction_method'] = f'Oxford Error: {str(e)}'
            self.logger.error(f"Oxford extraction error: {e}")
        
        return result
    def extract_sage_authors(self, url: str) -> Dict:
        """Extract author info from new Sage inline author HTML"""
        result = {
            'url': url,
            'title': '',
            'authors': [],
            'emails': [],
            'extraction_method': 'Sage',
            'status': 'success'
        }

        try:
            self.driver.get(url)
            time.sleep(30)
            self.ensure_valid_window()

            result['title'] = self.driver.title

            # --------------------------------------------------
            # STEP 1: Click "View all authors and affiliations"
            # --------------------------------------------------
            try:
                reveal_buttons = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    'span[data-action="reveal"]'
                )
                for btn in reveal_buttons:
                    try:
                        self.driver.execute_script(
                            "arguments[0].scrollIntoView({block:'center'});", btn
                        )
                        self.driver.execute_script("arguments[0].click();", btn)
                        time.sleep(1)
                    except:
                        continue
            except:
                pass

            # --------------------------------------------------
            # STEP 2: Parse author blocks
            # --------------------------------------------------
            author_blocks = self.driver.find_elements(
                By.CSS_SELECTOR,
                'span[property="author"][typeof="Person"]'
            )

            seen = set()

            for author in author_blocks:
                try:
                    # Full name
                    given = author.find_elements(By.CSS_SELECTOR, 'span[property="givenName"]')
                    family = author.find_elements(By.CSS_SELECTOR, 'span[property="familyName"]')

                    full_name = " ".join(
                        [g.text.strip() for g in given] +
                        [f.text.strip() for f in family]
                    ).strip()

                    if not full_name:
                        continue

                    # Email (optional)
                    email = ""
                    email_links = author.find_elements(
                        By.CSS_SELECTOR,
                        'a[href^="mailto:"]'
                    )
                    if email_links:
                        email = email_links[0].get_attribute("href").replace("mailto:", "").strip()

                    key = (full_name, email)
                    if key in seen:
                        continue
                    seen.add(key)

                    result['authors'].append(full_name)
                    if email:
                        result['emails'].append(email)

                except:
                    continue

            self.logger.info(
                f"Sage: Found {len(result['authors'])} authors, {len(result['emails'])} emails"
            )

        except Exception as e:
            result['status'] = 'error'
            result['extraction_method'] = f'Sage Error: {str(e)}'
            self.logger.error(f"Sage extraction error: {e}")

        return result

    def extract_springer_authors(self, url: str) -> Dict:
        """Extract author info from Springer articles"""
        result = {
            'url': url,
            'title': '',
            'authors': [],
            'emails': [],
            'extraction_method': 'Springer',
            'status': 'success'
        }
        
        try:
            self.driver.get(url)
            time.sleep(3)
            result['title'] = self.driver.title
            
            # Wait for author list
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'ul.c-article-author-list'))
            )
            
            # Click "Show authors" if present
            try:
                show_authors = self.driver.find_element(By.CSS_SELECTOR, 
                    'button.c-article-author-list__button[aria-expanded="false"]')
                self.driver.execute_script("arguments[0].click();", show_authors)
                time.sleep(1)
            except:
                pass
            
            # Find author links with email icon
            author_links = self.driver.find_elements(By.CSS_SELECTOR, 'a[data-test="author-name"]')
            corresponding_authors = []
            
            for link in author_links:
                try:
                    svg_icon = link.find_elements(By.CSS_SELECTOR, 'svg[aria-hidden="true"]')
                    if svg_icon:
                        corresponding_authors.append(link)
                except:
                    continue
            
            seen_emails = set()
            for author_elem in corresponding_authors:
                try:
                    author_name = author_elem.text.strip().split('\n')[0].strip()
                    
                    self.driver.execute_script("arguments[0].click();", author_elem)
                    time.sleep(2)
                    
                    # Try new popup structure
                    try:
                        popup = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, 
                                'div.app-researcher-popup:not(.u-js-hide)'))
                        )
                        
                        email_link = popup.find_element(By.CSS_SELECTOR, 
                            'a[data-track="click_corresponding_email"][href^="mailto:"]')
                        email = email_link.get_attribute("href").replace("mailto:", "").strip()
                        
                        if email not in seen_emails:
                            seen_emails.add(email)
                            result['authors'].append(author_name)
                            result['emails'].append(email)
                    except:
                        pass
                    
                    # Close popup
                    try:
                        close_button = self.driver.find_element(By.CSS_SELECTOR, "button.c-popup__close")
                        self.driver.execute_script("arguments[0].click();", close_button)
                        time.sleep(0.5)
                    except:
                        from selenium.webdriver.common.keys import Keys
                        self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                        time.sleep(0.5)
                except:
                    continue
            
            self.logger.info(f"Springer: Found {len(result['authors'])} authors, {len(result['emails'])} emails")
            
        except Exception as e:
            result['status'] = 'error'
            result['extraction_method'] = f'Springer Error: {str(e)}'
            self.logger.error(f"Springer extraction error: {e}")
        
        return result
    
    # def extract_mdpi_authors(self, url: str) -> Dict:
    #     result = {
    #         "url": url,
    #         "title": "",
    #         "authors": [],
    #         "emails": [],
    #         "extraction_method": "MDPI",
    #         "status": "success"
    #     }

    #     try:
    #         self.driver.get(url)
    #         time.sleep(3)
    #         self.accept_cookies()

    #         result["title"] = self.driver.title

    #         author_blocks = self.driver.find_elements(
    #             By.CSS_SELECTOR, "div.affiliation-email"
    #         )

    #         for block in author_blocks:
    #             try:
    #                 email_el = block.find_element(By.CSS_SELECTOR, "a[href^='mailto']")
    #                 email = email_el.get_attribute("href").replace("mailto:", "").strip()

    #                 name = block.find_element(
    #                     By.XPATH, "./preceding::span[@class='author-name'][1]"
    #                 ).text.strip()

    #                 result["authors"].append(name)
    #                 result["emails"].append(email)

    #             except:
    #                 continue

    #         self.logger.info(
    #             f"MDPI: {len(result['emails'])} emails extracted"
    #         )

    #     except Exception as e:
    #         result["status"] = "error"
    #         result["extraction_method"] = f"MDPI Error: {e}"
    #         self.logger.error(e)

    #     return result

    def extract_mdpi_authors(self, url: str) -> Dict:
        result = {
            "url": url,
            "title": "",
            "authors": [],
            "emails": [],
            "extraction_method": "MDPI",
            "status": "success"
        }

        try:
            self.driver.get(url)
            time.sleep(3)

            # Accept cookies once per domain
            self.accept_cookies("mdpi")

            result["title"] = self.driver.title

            # Container holding all authors
            author_container = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.art-authors")
                )
            )

            # Each author is inside a span.inlineblock
            author_blocks = author_container.find_elements(
                By.CSS_SELECTOR, "span.inlineblock"
            )

            seen = set()

            for block in author_blocks:
                try:
                    # -------- Author name --------
                    name_el = block.find_element(
                        By.CSS_SELECTOR, "div.profile-card-drop"
                    )
                    author_name = name_el.text.strip()

                    if not author_name:
                        continue

                    # -------- Email (try multiple methods) --------
                    email = ""
                    
                    # Method 1: Direct mailto link with email in href
                    try:
                        email_link = block.find_element(
                            By.CSS_SELECTOR, "a.emailCaptcha[href^='mailto:']"
                        )
                        email_href = email_link.get_attribute("href")
                        email = email_href.replace("mailto:", "").strip()
                        
                        if email:
                            self.logger.info(f"MDPI: Found email in href for {author_name}: {email}")
                    except:
                        pass

                    # Method 2: If no email found, try data attributes or onclick
                    if not email:
                        try:
                            email_link = block.find_element(
                                By.CSS_SELECTOR, "a.emailCaptcha"
                            )
                            
                            # Check data attributes
                            for attr in ['data-email', 'data-mailto', 'data-address']:
                                email_val = email_link.get_attribute(attr)
                                if email_val and '@' in email_val:
                                    email = email_val.strip()
                                    break
                        except:
                            pass

                    # Method 3: Try to find email in surrounding text
                    if not email:
                        try:
                            block_text = block.text
                            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', block_text)
                            if email_match:
                                email = email_match.group(0)
                        except:
                            pass

                    key = (author_name, email)
                    if key in seen:
                        continue
                    seen.add(key)

                    result["authors"].append(author_name)
                    if email:
                        result["emails"].append(email)
                        self.logger.info(f"MDPI: Matched {author_name} -> {email}")
                    else:
                        self.logger.info(f"MDPI: Added {author_name} (no email found)")

                except Exception as e:
                    self.logger.debug(f"MDPI: Error processing author block: {e}")
                    continue

            self.logger.info(
                f"MDPI: Found {len(result['authors'])} authors, "
                f"{len(result['emails'])} emails"
            )

        except Exception as e:
            result["status"] = "error"
            result["extraction_method"] = f"MDPI Error: {e}"
            self.logger.error(f"MDPI extraction error: {e}")

        return result


    def extract_generic_authors(self, url: str) -> Dict:
        """
        Generic extraction method for unknown domains.
        Improved logic to better match authors with emails.
        """
        result = {
            'url': url,
            'title': '',
            'authors': [],
            'emails': [],
            'extraction_method': 'Generic',
            'status': 'success'
        }
        
        try:
            self.driver.get(url)
            time.sleep(2)
            result['title'] = self.driver.title
            
            # ==========================================
            # STRATEGY 1: Look for structured author sections
            # ==========================================
            author_email_pairs = []
            
            # Try to find author sections with emails nearby
            try:
                # Look for common author section patterns
                author_sections = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    'div[class*="author"], section[class*="author"], '
                    'div[class*="contributor"], li[class*="author"]'
                )
                
                for section in author_sections:
                    section_text = section.text.strip()
                    section_html = section.get_attribute('innerHTML')
                    
                    # Extract emails from this section
                    section_emails = self.extract_emails_from_text(section_html)
                    
                    # Try to find author name in this section
                    # Look for meta tags or name elements
                    name_elements = section.find_elements(
                        By.CSS_SELECTOR,
                        '[class*="name"], [property*="name"], '
                        '[itemprop*="name"], h3, h4, strong, b'
                    )
                    
                    for name_elem in name_elements:
                        name = name_elem.text.strip()
                        # Clean author name
                        name = re.sub(r'[0-9,*†‡§¶#]+', '', name).strip()
                        
                        if name and len(name) > 2 and len(name) < 100:
                            # If we found emails in this section, pair them
                            if section_emails:
                                for email in section_emails:
                                    author_email_pairs.append((name, email))
                            else:
                                # Author without email
                                author_email_pairs.append((name, ''))
                            break  # Only take first valid name per section
            except Exception as e:
                self.logger.debug(f"Author section extraction failed: {e}")
            
            # ==========================================
            # STRATEGY 2: Meta tags extraction
            # ==========================================
            try:
                meta_authors = self.driver.find_elements(
                    By.CSS_SELECTOR, 
                    'meta[name="citation_author"], meta[property="author"]'
                )
                
                meta_author_names = []
                for meta in meta_authors:
                    author_name = meta.get_attribute('content')
                    if author_name:
                        meta_author_names.append(author_name.strip())
                
                # If we have meta authors but no pairs yet, add them
                if meta_author_names and not author_email_pairs:
                    for name in meta_author_names:
                        author_email_pairs.append((name, ''))
            except Exception as e:
                self.logger.debug(f"Meta tag extraction failed: {e}")
            
            # ==========================================
            # STRATEGY 3: Look for correspondence/contact sections
            # ==========================================
            try:
                correspondence_sections = self.driver.find_elements(
                    By.XPATH,
                    "//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'correspondence') or "
                    "contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'corresponding author') or "
                    "contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'contact')]"
                )
                
                for section in correspondence_sections:
                    section_text = section.text
                    emails = self.extract_emails_from_text(section_text)
                    
                    if emails:
                        # Try to find author name near this email
                        # Look for patterns like "Correspondence to: Name (email@)"
                        # or "Contact: Name, email@"
                        name_pattern = r'(?:correspondence|contact|author)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)'
                        name_match = re.search(name_pattern, section_text, re.IGNORECASE)
                        
                        if name_match:
                            name = name_match.group(1).strip()
                            for email in emails:
                                author_email_pairs.append((name, email))
            except Exception as e:
                self.logger.debug(f"Correspondence section extraction failed: {e}")
            
            # ==========================================
            # STRATEGY 4: Fallback - get all emails from page
            # ==========================================
            if not author_email_pairs:
                page_content = self.driver.page_source
                all_emails = self.extract_emails_from_text(page_content)
                
                # Filter out common false positives
                filtered_emails = [
                    e for e in all_emails 
                    if not any(x in e.lower() for x in [
                        'example.com', 'test.com', 'placeholder',
                        'scielo.org', 'springernature.com', 
                        'permissions@', 'support@', 'admin@',
                        'info@', 'contact@', 'webmaster@'
                    ])
                ]
                
                # Limit to reasonable number
                filtered_emails = filtered_emails[:5]
                
                # Try to get author names from meta tags
                try:
                    meta_authors = self.driver.find_elements(
                        By.CSS_SELECTOR, 
                        'meta[name="citation_author"]'
                    )
                    if meta_authors and filtered_emails:
                        # Only create pairs if we have similar counts
                        # Otherwise, list them separately
                        if len(meta_authors) == len(filtered_emails):
                            for i, meta in enumerate(meta_authors):
                                name = meta.get_attribute('content')
                                author_email_pairs.append((name, filtered_emails[i]))
                        else:
                            # List authors without specific email pairing
                            for meta in meta_authors:
                                name = meta.get_attribute('content')
                                author_email_pairs.append((name, ''))
                            # Add emails as separate entries if needed
                            for email in filtered_emails:
                                author_email_pairs.append(('', email))
                    elif meta_authors:
                        for meta in meta_authors:
                            name = meta.get_attribute('content')
                            author_email_pairs.append((name, ''))
                    elif filtered_emails:
                        for email in filtered_emails:
                            author_email_pairs.append(('', email))
                except:
                    # Just add emails if we can't find names
                    for email in filtered_emails:
                        author_email_pairs.append(('', email))
            
            # ==========================================
            # Remove duplicates and populate result
            # ==========================================
            seen = set()
            for name, email in author_email_pairs:
                key = (name.strip() if name else '', email.strip() if email else '')
                if key not in seen and (key[0] or key[1]):  # At least one should be non-empty
                    seen.add(key)
                    if name:
                        result['authors'].append(name.strip())
                    if email:
                        result['emails'].append(email.strip())
            
            # If no authors/emails found, mark as such
            if not result['authors'] and not result['emails']:
                result['extraction_method'] = 'Generic (No data found)'
            
            self.logger.info(
                f"Generic: Found {len(result['authors'])} authors, "
                f"{len(result['emails'])} emails"
            )
            
        except Exception as e:
            result['status'] = 'error'
            result['extraction_method'] = f'Generic Error: {str(e)}'
            self.logger.error(f"Generic extraction error: {e}")
        
        return result


    def append_result_to_csv(self, result: Dict, output_file: str):
        """
        Append a single result to CSV file immediately.
        Improved to avoid Cartesian product in output.
        """
        authors = result['authors'] if result['authors'] else ['']
        emails = result['emails'] if result['emails'] else ['']
        
        rows = []
        
        # Strategy 1: If counts match, pair them 1-to-1
        if authors and emails and len(authors) == len(emails):
            for author, email in zip(authors, emails):
                rows.append({
                    'url': result['url'],
                    'title': result['title'],
                    'author_name': author,
                    'email': email,
                    'all_authors': '; '.join(result['authors']),
                    'all_emails': '; '.join(result['emails']),
                    'extraction_method': result['extraction_method'],
                    'status': result['status']
                })
        
        # Strategy 2: More authors than emails - pair available emails, rest without
        elif authors and emails and len(authors) > len(emails):
            for i, author in enumerate(authors):
                email = emails[i] if i < len(emails) else ''
                rows.append({
                    'url': result['url'],
                    'title': result['title'],
                    'author_name': author,
                    'email': email,
                    'all_authors': '; '.join(result['authors']),
                    'all_emails': '; '.join(result['emails']),
                    'extraction_method': result['extraction_method'],
                    'status': result['status']
                })
        
        # Strategy 3: More emails than authors - pair available authors, rest without
        elif authors and emails and len(emails) > len(authors):
            for i, email in enumerate(emails):
                author = authors[i] if i < len(authors) else ''
                rows.append({
                    'url': result['url'],
                    'title': result['title'],
                    'author_name': author,
                    'email': email,
                    'all_authors': '; '.join(result['authors']),
                    'all_emails': '; '.join(result['emails']),
                    'extraction_method': result['extraction_method'],
                    'status': result['status']
                })
        
        # Strategy 4: Only authors, no emails
        elif authors and not emails:
            for author in authors:
                rows.append({
                    'url': result['url'],
                    'title': result['title'],
                    'author_name': author,
                    'email': '',
                    'all_authors': '; '.join(result['authors']),
                    'all_emails': '',
                    'extraction_method': result['extraction_method'],
                    'status': result['status']
                })
        
        # Strategy 5: Only emails, no authors
        elif emails and not authors:
            for email in emails:
                rows.append({
                    'url': result['url'],
                    'title': result['title'],
                    'author_name': '',
                    'email': email,
                    'all_authors': '',
                    'all_emails': '; '.join(result['emails']),
                    'extraction_method': result['extraction_method'],
                    'status': result['status']
                })
        
        # Strategy 6: No data at all
        else:
            rows.append({
                'url': result['url'],
                'title': result['title'],
                'author_name': '',
                'email': '',
                'all_authors': '',
                'all_emails': '',
                'extraction_method': result['extraction_method'],
                'status': result['status']
            })
        
        # Write to CSV
        if rows:
            fieldnames = ['url', 'title', 'author_name', 'email', 'all_authors', 
                        'all_emails', 'extraction_method', 'status']
            
            filepath = os.path.join(self.output_dir, output_file)
            file_exists = os.path.isfile(filepath)
            
            with open(filepath, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerows(rows)
                
    # def extract_author_info_from_page(self, url: str) -> Dict:
    #     self.logger.info(f"Processing: {url}")

    #     try:
    #                     # Navigate
    #         self.driver.get(url)
    #         time.sleep(2)
    #         self.ensure_valid_window()

    #         # Detect domain FIRST
    #         domain = self.detect_domain_from_browser()
    #         self.logger.info(f"Detected domain (browser): {domain}")

    #         # Accept cookies ONCE per domain
    #         self.accept_cookies(domain)

    #         current_url = self.driver.current_url

    #         if domain == 'bmj':
    #             return self.extract_bmj_authors(current_url)
    #         elif domain == 'cambridge':
    #             return self.extract_cambridge_authors(current_url)
    #         elif domain == 'emerald':
    #             return self.extract_emerald_authors(current_url)
    #         elif domain == 'lippincott':
    #             return self.extract_lippincott_authors(current_url)
    #         elif domain == 'oxford':
    #             return self.extract_oxford_authors(current_url)
    #         elif domain == 'sage':
    #             return self.extract_sage_authors(current_url)
            
    #         elif domain == 'nature':
    #             return self.extract_nature_authors(current_url)
            
    #         elif domain == 'springer':
    #             return self.extract_springer_authors(current_url)
    #         elif domain == "sciencedirect":
    #             return self.extract_sciencedirect_authors(current_url)
    #         elif domain == "mdpi":
    #             return self.extract_mdpi_authors(current_url)

        
    #         else:
    #             return self.extract_generic_authors(current_url)

    #     except Exception as e:
    #         self.logger.error(f"Error processing {url}: {e}")
    #         return {
    #             'url': url,
    #             'title': '',
    #             'authors': [],
    #             'emails': [],
    #             'extraction_method': f'Error: {str(e)}',
    #             'status': 'failed'
    #         }
 
    def extract_author_info_from_page(self, url: str) -> Dict:
        self.logger.info(f"Processing: {url}")

        try:
            # Navigate
            self.driver.get(url)
            time.sleep(2)
            self.ensure_valid_window()

            # Detect domain FIRST
            domain = self.detect_domain_from_browser()
            self.logger.info(f"Detected domain (browser): {domain}")

            # Skip generic domains
            if domain == 'generic':
                self.logger.info(f"Skipping generic domain: {self.driver.current_url}")
                return {
                    'url': url,
                    'title': self.driver.title if self.driver.title else '',
                    'authors': [],
                    'emails': [],
                    'extraction_method': 'Generic (Skipped)',
                    'status': 'skipped'
                }

            # Accept cookies ONCE per domain
            self.accept_cookies(domain)

            current_url = self.driver.current_url

            if domain == 'bmj':
                return self.extract_bmj_authors(current_url)
            elif domain == 'cambridge':
                return self.extract_cambridge_authors(current_url)
            elif domain == 'emerald':
                return self.extract_emerald_authors(current_url)
            elif domain == 'lippincott':
                return self.extract_lippincott_authors(current_url)
            elif domain == 'oxford':
                return self.extract_oxford_authors(current_url)
            elif domain == 'sage':
                return self.extract_sage_authors(current_url)
            elif domain == 'nature':
                return self.extract_nature_authors(current_url)
            elif domain == 'springer':
                return self.extract_springer_authors(current_url)
            elif domain == "sciencedirect":
                return self.extract_sciencedirect_authors(current_url)
            elif domain == "mdpi":
                return self.extract_mdpi_authors(current_url)
            else:
                # This should not be reached since generic is handled above
                self.logger.warning(f"Unknown domain type: {domain}")
                return {
                    'url': url,
                    'title': self.driver.title if self.driver.title else '',
                    'authors': [],
                    'emails': [],
                    'extraction_method': f'Unknown domain: {domain}',
                    'status': 'skipped'
                }

        except Exception as e:
            self.logger.error(f"Error processing {url}: {e}")
            return {
                'url': url,
                'title': '',
                'authors': [],
                'emails': [],
                'extraction_method': f'Error: {str(e)}',
                'status': 'failed'
            }

    def process_urls(self, urls: List[str], output_file: str = "author_info.csv") -> List[Dict]:
        """Process a list of URLs and extract author information"""
        print(f"Starting extraction for {len(urls)} URLs...")
        print("="*60)
        
        for idx, url in enumerate(urls):
            print(f"\n[{idx+1}/{len(urls)}] Processing: {url}")
            
            try:
                # Extract information
                result = self.extract_author_info_from_page(url)
                self.results.append(result)
                
                # Write immediately to CSV
                self.append_result_to_csv(result, output_file)
                
            except Exception as e:
                print(f"    ✗ Failed to process URL: {str(e)}")
                failed_result = {
                    'url': url,
                    'title': '',
                    'authors': [],
                    'emails': [],
                    'extraction_method': f'Processing error: {str(e)}',
                    'status': 'failed'
                }
                self.results.append(failed_result)
                self.append_result_to_csv(failed_result, output_file)
            
            # Be polite - wait between requests
            time.sleep(2)
        
        print("\n" + "="*60)
        print("Extraction complete!")
        print(f"Results saved to: {os.path.join(self.output_dir, output_file)}")
        print("="*60)
        
        return self.results
    
    def save_to_csv(self, output_file: str):
        """Print summary statistics"""
        print(f"✓ Results were written incrementally to {os.path.join(self.output_dir, output_file)}")
        print(f"  Total URLs processed: {len(self.results)}")
        print(f"  Successful: {sum(1 for r in self.results if r['status'] == 'success')}")
        print(f"  Failed: {sum(1 for r in self.results if r['status'] != 'success')}")
    
    def process_csv_file(self, input_csv: str, url_column: str = 'url', output_csv: str = None):
        """
        Process URLs from a CSV file
        
        Args:
            input_csv: Path to input CSV file
            url_column: Name of column containing URLs
            output_csv: Path to output CSV file (auto-generated if None)
        """
        print(f"Reading URLs from: {input_csv}")
        
        try:
            # Read CSV
            df = pd.read_csv(input_csv)
            
            if url_column not in df.columns:
                raise ValueError(f"Column '{url_column}' not found in CSV. Available columns: {', '.join(df.columns)}")
            
            # Get URLs
            urls = df[url_column].dropna().unique().tolist()
            print(f"Found {len(urls)} unique URLs to process")
            
            # Generate output filename if not provided
            if output_csv is None:
                base_name = os.path.splitext(os.path.basename(input_csv))[0]
                output_csv = f"{base_name}_author_info.csv"
            else:
                if os.path.dirname(output_csv) == '':
                    output_csv = os.path.basename(output_csv)
            
            print(f"Results will be saved to: {os.path.join(self.output_dir, output_csv)}")
            
            # Process URLs
            self.process_urls(urls, output_file=output_csv)
            
            # Print final summary
            self.save_to_csv(output_csv)
            
        except FileNotFoundError:
            print(f"Error: File '{input_csv}' not found!")
        except Exception as e:
            print(f"Error processing CSV: {str(e)}")
    
    def close(self):
        """Close the browser"""
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("Browser closed successfully")
            except Exception as e:
                self.logger.error(f"Error closing browser: {e}")


# Example usage
# if __name__ == "__main__":
#     print("="*60)
#     print("Author Information Extractor from Paper URLs")
#     print("Supports: BMJ, Cambridge, Emerald, Lippincott, Oxford, Sage, Springer")
#     print("="*60)
    
#     # Get input file
#     input_file = input("\nEnter path to CSV file with URLs (e.g., results/combined_unique.csv): ")
    
#     # Get URL column name
#     url_column = input("Enter the name of the URL column (default: 'url'): ").strip()
#     if not url_column:
#         url_column = 'url'
    
#     # Ask about headless mode
#     headless_input = input("Run browser in headless mode? (y/n, default: n): ").strip().lower()
#     headless = headless_input == 'y'
    
#     # Create extractor
#     extractor = AuthorInfoExtractor(headless=headless, timeout=30000, output_dir="results")
    
#     try:
#         # Process file
#         extractor.process_csv_file(input_file, url_column=url_column)
#     finally:
#         # Always close browser
#         extractor.close()
    
#     print("\n" + "="*60)
#     print("Script complete!")
#     print("="*60)
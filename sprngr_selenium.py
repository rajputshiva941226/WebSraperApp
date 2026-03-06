# Fix for Python 3.12+ distutils compatibility
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

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

import csv, logging, math, sys, time
import os, random, subprocess
from selenium import webdriver






from webdriver_manager.chrome import ChromeDriverManager
import undetected_chromedriver as uc
import tempfile

class SpringerAuthorScraper:
    def __init__(self, keyword, start_year, end_year,driver_path):
        # Initialize Selenium WebDriver
        self.options = Options()
        self.options.add_argument("--headless")
        self.options.add_argument("--window-size=1920,1080")
        #self.options.add_argument("--force-device-scale-factor=1")
        self.options.add_argument("--disable-notifications")
        self.options.add_argument("--disable-background-timer-throttling")
        self.options.add_argument("--disable-backgrounding-occluded-windows")
        self.options.add_argument("--disable-renderer-backgrounding")
        self.options.add_argument("--disable-notifications")
        self.options.add_argument("--disable-lazy-loading")
        self.options.add_argument("--disable-print-preview")
        self.options.add_argument("--disable-stack-profiler")
        self.options.add_argument("--disable-background-networking")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("excludeSwitches=enable-automation")
        self.options.add_argument("--disable-infobars")
        self.options.add_argument("--disable-browser-side-navigation")
        
        self.options.add_argument("--disable-blink-features=AutomationControlled")
        self.options.add_argument("--disable-popup-blocking")
        self.options.add_argument("--disable-crash-reporter")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--disable-logging")

        # Use WebDriverManager to automatically download and manage ChromeDriver
        self.uc_temp_dir = tempfile.mkdtemp(prefix="Springer_")
        self.driver = uc.Chrome(
                options=self.options,
                driver_executable_path=driver_path,
                version_main=None,  # Auto-detect Chrome version
                use_subprocess=False  # Critical for multiprocessing
            )
        self.wait = WebDriverWait(self.driver, 30)
        
        # Verify window is still open after initialization
        time.sleep(2)
        try:
            _ = self.driver.current_url
        except:
            self.logger.warning("Window closed during init, reinitializing...")
            self.driver = uc.Chrome(
                options=self.options,
                driver_executable_path=driver_path,
                version_main=None,
                use_subprocess=False
            )
            self.wait = WebDriverWait(self.driver, 30)
        
        self.directory = keyword.replace(" ","-")
        self.keyword = keyword
        self.start_year = start_year
        self.end_year = end_year
        filename = keyword.replace(" ","-")
        self.url_csv = f"Springer_{filename}-{start_year.replace('/', '-')}-{end_year.replace('/', '-')}_urls.csv"
        self.authors_csv = f"Springer_{filename}-{start_year.replace('/', '-')}-{end_year.replace('/', '-')}_authors.csv"

        self.output_csv = "article_links.csv"

        
        self._setup_logger()  # Initialize logger for the subclass
        self.driver.maximize_window()
        self.run()

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

    def dismiss_cookie_banner(self):
        """Dismiss the cookie consent banner if present."""
        try:
            cookie_banner = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "dialog.cc-banner")))
            accept_button = cookie_banner.find_element(By.CSS_SELECTOR, 'button[data-cc-action="accept"]')
            if accept_button.is_displayed() and accept_button.is_enabled():
                accept_button.click()
                self.logger.info("Springer ==> Cookie banner accepted.")
        except Exception as e:
            self.logger.error(f"Springer ==> Error dismissing cookie banner: {e}")

    def save_to_csv(self, data, filename, header=None):
        """Save data to a CSV file."""
        try:
            os.makedirs(self.directory, exist_ok=True)
            filepath = os.path.join(self.directory, filename)
            with open(filepath, mode="a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                if os.path.getsize(filepath) == 0 and header:  # Write header only if file is empty
                    writer.writerow(header)
                writer.writerows(data)
            self.logger.info(f"Springer ==> Saved data to {filepath}.")
        except Exception as e:
            self.logger.error(f"Springer ==> Failed to save data to CSV: {e}")

    def get_total_pages(self):
        """Retrieve the total number of pages from the search results."""
        try:
            stats_element = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'span[data-test="results-data-total"]'))
            )
            total_results_text = stats_element.text.split(" ")[-2].replace(",","").strip()
            total_results = int(total_results_text)
            total_pages = math.ceil(total_results / 20)
            self.logger.info(f"Springer ==> Total results: {total_results}, Total pages: {total_pages}")
            return total_pages
        except Exception as e:
            self.logger.error(f"Springer ==> Failed to get total pages: {e}")
            return 0
    def load_links_from_csv(self):
        """Load article links from a CSV file."""
        filepath = os.path.join(self.directory, self.url_csv)
        if not os.path.exists(filepath):
            self.logger.error("Springer ==> URLs file not found! Run extract_article_links() first.")
            return

        links = []
        with open(filepath, mode="r", encoding="utf-8") as file:
            reader = csv.reader(file)
            next(reader)  # Skip header
        
            links = ["".join(row) for row in reader]
        return links

    def extract_article_links(self, search_url, csv_urls, total_pages):
        """Extract article links from multiple pages of the search results."""
        self.driver.get(search_url)


        #loop_until = (total_pages if total_pages < 11 else 11)
        for page in range(0, 50):
            all_links = []
            try:
                # Wait for article links to load
                self.wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.app-card-open__link")))
                article_links = self.driver.find_elements(By.CSS_SELECTOR, "a.app-card-open__link")
                
                # Extract links from the current page

                page_links = [link.get_attribute("href") for link in article_links]
                self.logger.info(f"Springer ==> Found {len(page_links)} article links on the current page.")
                #all_links.append(page_links)

                # Check for the presence of a "next" button
                try:
                    next_button = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'a[rel="next"]')))
                    if next_button.is_displayed():
                        # Click the "next" button
                        next_button.click()
                        self.logger.info("Springer ==> Navigating to the next page...")
                        
                        # Wait for the next page to load
                        self.wait.until(EC.staleness_of(article_links[0]))  # Ensure the old page elements are stale
                    else:
                        self.logger.error("Springer ==> Next button is not displayed. Stopping pagination.")
                        
                except Exception as e:
                    self.logger.error(f"Springer ==> No 'next' button found or unable to navigate to the next page: {e}")
                    break
            except Exception as e:
                self.logger.error(f"Springer ==> Error extracting links: {e}")
                self.driver.refresh()

            finally:
                self.logger.info(f"Springer ==> Total links extracted: {len(page_links)} from page: {page}")
                self.save_to_csv(page_links, self.url_csv, header=["Article_URL"])  # Save all collected links to CSV


    def extract_email_and_author(self, article_url, csv_output):
        """Extract unique email and author name from an article page - only for corresponding authors with email icon."""
        self.driver.get(article_url)
        time.sleep(3)  # Give page time to fully load
        
        try:
            # Wait for author list to be present
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'ul.c-article-author-list')))
            
            # Scroll to the author list first
            author_list = self.driver.find_element(By.CSS_SELECTOR, 'ul.c-article-author-list')
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", author_list)
            time.sleep(1)
            
            # Check if "Show authors" button exists and click it
            try:
                show_authors_button = self.driver.find_element(By.CSS_SELECTOR, 'button.c-article-author-list__button[aria-expanded="false"]')
                self.logger.info(f"Springer ==> Found 'Show authors' button, clicking it...")
                
                # Scroll to button and click
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", show_authors_button)
                time.sleep(0.5)
                
                # Try clicking with JavaScript first
                try:
                    self.driver.execute_script("arguments[0].click();", show_authors_button)
                    self.logger.info(f"Springer ==> ✅ Clicked 'Show authors' button using JavaScript")
                except:
                    # Fallback to regular click
                    show_authors_button.click()
                    self.logger.info(f"Springer ==> ✅ Clicked 'Show authors' button using regular click")
                
                time.sleep(1)  # Wait for all authors to be displayed
                
            except Exception as e:
                self.logger.info(f"Springer ==> No 'Show authors' button found (all authors already visible)")
            
            # Find ALL author links after expanding
            all_author_links = self.driver.find_elements(By.CSS_SELECTOR, 'a[data-test="author-name"]')
            self.logger.info(f"Springer ==> Found {len(all_author_links)} total authors on page")
            
            # Filter only those with SVG email icon
            corresponding_authors = []
            for link in all_author_links:
                try:
                    # Check if this link contains an SVG element
                    svg_icon = link.find_elements(By.CSS_SELECTOR, 'svg[aria-hidden="true"]')
                    if svg_icon:
                        corresponding_authors.append(link)
                        self.logger.info(f"Springer ==> Found corresponding author link: {link.text.strip()}")
                except Exception:
                    continue
            
            if not corresponding_authors:
                self.logger.warning(f"Springer ==> No corresponding authors found on {article_url}")
                self.save_to_csv([[article_url, "N/A", "N/A"]], self.authors_csv, header=["Article_URL", "Author_Name", "Email"])
                return
            
            self.logger.info(f"Springer ==> Found {len(corresponding_authors)} corresponding author(s) with email icon on {article_url}")
            
            author_info = []
            seen_emails = set()  # Track unique emails only
            
            for idx, author_element in enumerate(corresponding_authors, 1):
                try:
                    # Scroll to author element
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", author_element)
                    time.sleep(1)
                    
                    # Get author name before clicking (extract only text, excluding SVG)
                    author_name_raw = author_element.text.strip()
                    # Remove any trailing/leading whitespace and newlines
                    author_name = author_name_raw.split('\n')[0].strip() if '\n' in author_name_raw else author_name_raw
                    
                    self.logger.info(f"Springer ==> Processing corresponding author {idx}/{len(corresponding_authors)}: {author_name}")
                    
                    # Re-find the element to avoid stale element reference
                    data_author_popup = author_element.get_attribute("data-author-popup")
                    self.logger.info(f"Springer ==> Author popup ID: {data_author_popup}")
                    
                    # Click using different methods
                    clicked = False
                    
                    # Method 1: JavaScript click
                    try:
                        self.driver.execute_script("arguments[0].click();", author_element)
                        self.logger.info(f"Springer ==> Clicked using JavaScript")
                        clicked = True
                        time.sleep(2)
                    except Exception as e:
                        self.logger.warning(f"Springer ==> JS click failed: {e}")
                    
                    # Method 2: ActionChains click
                    if not clicked:
                        try:
                            
                            actions = ActionChains(self.driver)
                            actions.move_to_element(author_element).click().perform()
                            self.logger.info(f"Springer ==> Clicked using ActionChains")
                            clicked = True
                            time.sleep(2)
                        except Exception as e:
                            self.logger.warning(f"Springer ==> ActionChains click failed: {e}")
                    
                    # Method 3: Regular click
                    if not clicked:
                        try:
                            author_element.click()
                            self.logger.info(f"Springer ==> Clicked using regular click")
                            clicked = True
                            time.sleep(2)
                        except Exception as e:
                            self.logger.error(f"Springer ==> All click methods failed: {e}")
                            continue
                    
                    if not clicked:
                        self.logger.error(f"Springer ==> Could not click on {author_name}")
                        continue
                    
                    # Extract email from popup
                    email = None
                    popup_author_name = None  # Track the actual author name from popup
                    
                    # Try new popup structure first (app-researcher-popup)
                    try:
                        popup_wait = WebDriverWait(self.driver, 5)
                        popup_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div.app-researcher-popup__contacts')))
                        
                        # Find the VISIBLE popup (not hidden)
                        popups = self.driver.find_elements(By.CSS_SELECTOR, 'div.app-researcher-popup')
                        popup = None
                        for p in popups:
                            # Check if popup is visible (not hidden)
                            if p.is_displayed() and 'u-js-hide' not in p.get_attribute('class'):
                                popup = p
                                break
                        
                        if not popup:
                            raise Exception("No visible popup found")
                        
                        self.logger.info(f"Springer ==> Found new popup structure")
                        
                        # Get the author name from the popup to verify it matches
                        try:
                            popup_author_element = popup.find_element(By.CSS_SELECTOR, 'h3.app-researcher-popup__subheading')
                            popup_author_name = popup_author_element.text.strip()
                            self.logger.info(f"Springer ==> Popup is for author: {popup_author_name}")
                        except:
                            self.logger.warning(f"Springer ==> Could not extract author name from popup")
                        
                        self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", popup)
                        time.sleep(0.5)
                        
                        # Look for email link in new structure
                        try:
                            email_link = popup.find_element(By.CSS_SELECTOR, 'a[data-track="click_corresponding_email"][href^="mailto:"]')
                            mailto_href = email_link.get_attribute("href")
                            email = mailto_href.replace("mailto:", "").strip()
                            self.logger.info(f"Springer ==> Found email in popup: {email}")
                                
                        except Exception as e:
                            self.logger.warning(f"Springer ==> No email in new popup: {e}")
                            
                    except Exception as e2:
                        self.logger.warning(f"Springer ==> New popup not found: {e2}")
                        # Try old popup structure (c-author-popup)
                        try:
                            popup_wait = WebDriverWait(self.driver, 5)
                            popup_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'ul.c-author-popup__author-list')))
                            popup = self.driver.find_element(By.CSS_SELECTOR, 'div.c-author-popup')
                            self.logger.info(f"Springer ==> Found old popup structure")
                            
                            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", popup)
                            time.sleep(0.5)
                            
                            # Find email link in old structure
                            try:
                                email_link = popup.find_element(By.CSS_SELECTOR, 'a.c-author-popup__link[href^="mailto:"]')
                                mailto_href = email_link.get_attribute("href")
                                email = mailto_href.replace("mailto:", "").strip()
                                self.logger.info(f"Springer ==> Found email in popup: {email}")
                            except Exception as e:
                                self.logger.warning(f"Springer ==> No email in old popup: {e}")
                                    
                        except Exception as e:
                            self.logger.error(f"Springer ==> Could not find any popup: {e}")
                    
                    # Verify the popup author name matches the clicked author (if we got it)
                    if popup_author_name and popup_author_name != author_name:
                        self.logger.error(f"Springer ==> ❌ MISMATCH: Clicked '{author_name}' but popup shows '{popup_author_name}'. Skipping.")
                        email = None  # Discard the email as it's from wrong author
                    
                    # Save the author info only if email was found AND is unique
                    if email:
                        if email not in seen_emails:
                            seen_emails.add(email)
                            # Use the popup author name if available, otherwise use clicked author name
                            final_author_name = popup_author_name if popup_author_name else author_name
                            self.logger.info(f"Springer ==> ✅ Extracted - Author: {final_author_name}, Email: {email}")
                            author_info.append([article_url, final_author_name, email])
                        else:
                            self.logger.info(f"Springer ==> ⏭️ Skipped duplicate email for {author_name}: {email}")
                    else:
                        self.logger.warning(f"Springer ==> ❌ No email found for corresponding author {author_name}")
                    
                    # CRITICAL: Close the popup completely before moving to next author
                    popup_closed = False
                    try:
                        # Try new popup close button
                        close_buttons = self.driver.find_elements(By.CSS_SELECTOR, "button.c-popup__close")
                        
                        for close_button in close_buttons:
                            try:
                                if close_button.is_displayed():
                                    self.driver.execute_script("arguments[0].click();", close_button)
                                    time.sleep(0.5)
                                    self.logger.info(f"Springer ==> Closed popup for {author_name}")
                                    popup_closed = True
                                    break
                            except:
                                continue
                        
                        if not popup_closed:
                            # Try ESC key as fallback
                            
                            self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                            time.sleep(0.5)
                            self.logger.info(f"Springer ==> Closed popup using ESC key")
                            popup_closed = True
                            
                    except Exception as e:
                        self.logger.warning(f"Springer ==> Could not close popup for {author_name}: {e}")
                    
                    # Double-check popup is closed by waiting for it to be hidden
                    try:
                        WebDriverWait(self.driver, 3).until(
                            EC.invisibility_of_element_located((By.CSS_SELECTOR, 'div.app-researcher-popup:not(.u-js-hide)'))
                        )
                        self.logger.info(f"Springer ==> ✓ Confirmed popup is closed")
                    except:
                        # Force close with JavaScript
                        self.driver.execute_script("""
                            var popups = document.querySelectorAll('div.app-researcher-popup, div.c-popup');
                            popups.forEach(function(popup) {
                                popup.classList.add('u-js-hide');
                                popup.setAttribute('hidden', 'true');
                                popup.style.display = 'none';
                            });
                        """)
                        time.sleep(0.3)
                        self.logger.info(f"Springer ==> Force-closed popup with JavaScript")
                    
                except Exception as e:
                    self.logger.error(f"Springer ==> Error processing corresponding author {author_name}: {e}")
                    # Try to close any open popup before continuing
                    try:
                        
                        self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                    except:
                        pass
                    continue
            
            # Save all collected author info to CSV
            if author_info:
                self.save_to_csv(author_info, self.authors_csv, header=["Article_URL", "Author_Name", "Email"])
                self.logger.info(f"Springer ==> ✅ Saved {len(author_info)} unique corresponding author(s) for article {article_url}")
            else:
                self.logger.warning(f"Springer ==> No unique emails extracted for corresponding authors on {article_url}")
                self.save_to_csv([[article_url, "N/A", "N/A"]], self.authors_csv, header=["Article_URL", "Author_Name", "Email"])
                
        except Exception as e:
            self.logger.error(f"Springer ==> Error processing article {article_url}: {e}")
            # Save article with N/A if completely failed
            self.save_to_csv([[article_url, "N/A", "N/A"]], self.authors_csv, header=["Article_URL", "Author_Name", "Email"])
            

    def ChangeVPN(self):
        countries = ["Georgia","Serbia","Moldova","'North Macedonia'","Jersey","Monaco","Slovakia",
                     "Slovenia","Croatia","Albania","Cyprus","Liechtenstein","Malta","Ukraine",
                     "Belarus","Bulgaria","Hungary","Luxembourg","Montenegro","Andorra",
                     "'Czech Republic'","Estonia","Latvia","Lithuania","Poland","Armenia","Austria",
                     "Portugal","Greece","Finland","Belgium","Denmark","Norway","Iceland","Ireland",
                     "Spain","Romania","Italy","Sweden","Turkey","Singapore","Japan",
                     "Australia","'South Korea - 2'","Malaysia","Pakistan","'Sri Lanka'","Kazakhstan",
                     "Thailand","Indonesia","'New Zealand'","Taiwan - 3","Cambodia","Vietnam","Macau",
                     "Mongolia","Laos","Bangladesh","Uzbekistan","Myanmar","Nepal","Brunei","Bhutan",
                     "'United Kingdom'", "'United States'","Japan", "Germay", "'Hong Kong'", "Netherlands",
                     "Switzerland","Algeria","France","Egypt"] 
        choice = random.choice(countries)
        print(f"Selected Country is {choice}")
        #os.environ["ExpressVPN"] = os.pathsep + r"C:\Program Files (x86)\ExpressVPN\services"
        
        process = subprocess.Popen(["powershell","ExpressVPN.CLI.exe", "disconnect"], shell=True)
        result = process.communicate()[0]
        print(result)
        process = subprocess.Popen(["powershell","ExpressVPN.CLI.exe", "connect",
                            f"{str(choice)}"],shell=True)
        result = process.communicate()[0]
        print(result) 


    def run(self):
        """Run the scraper with dynamic keyword and date range."""
        try:
            
            search_url = (
            f"https://link.springer.com/search?new-search=true&query={self.keyword}"
            f"&content-type=article&content-type=research&content-type=review"
            f"&content-type=conference+paper&content-type=news&date=custom"
            f"&dateFrom={self.start_year.split('/')[-1]}"  # Use SINGLE quotes in split('/')
            f"&dateTo={self.end_year.split('/')[-1]}&sortBy=relevance"
        )
        
            self.logger.info(f"Springer ==> Starting scraper with URL: {search_url}")

            # Fix 2: Navigate to URL FIRST before cookie handling
            self.driver.get(search_url)  # Explicit page load
            self.dismiss_cookie_banner()  # Now handles cookies on the actual page

            # Step 1: Extract and save links to CSV
            total_pages = self.get_total_pages()

            self.extract_article_links(search_url, self.url_csv, total_pages)
            #ChangeVPN()
            # Step 2: Read links from CSV and process each
            article_links = self.load_links_from_csv()
            
            for i, article_url in enumerate(article_links):
                #if i == 100:
                    #self.ChangeVPN()
                self.extract_email_and_author(article_url, self.authors_csv)

        finally:
            self.driver.quit()


# if __name__ == "__main__":
#     import argparse

#     # Parse command-line arguments
#     parser = argparse.ArgumentParser(description="Springer Author Scraper")
#     parser.add_argument("--keyword", required=True, help="Keyword to search for")
#     parser.add_argument("--start_year", required=True, type=str, help="Start year for the search")
#     parser.add_argument("--end_year", required=True, type=str, help="End year for the search")

#     args = parser.parse_args()
#     # Set a global cache path for WebDriverManager
#     os.environ["WDM_CACHE_PATH"] = "C:/shared_drivers"  # Custom shared directory

# #   Install ChromeDriver once and get its path
#     driver_path = ChromeDriverManager().install()

#     # Initialize and run the scraper with arguments
#     scraper = SpringerAuthorScraper(keyword=args.keyword, start_year=args.start_year, end_year=args.end_year, driver_path=driver_path)
#     #scraper.run()

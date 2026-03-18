from chrome_display_mixin import ChromeDisplayMixin
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

import os, argparse, csv, logging, time, math, re, sys
from selenium import webdriver





from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import urlencode, quote
from datetime import datetime
import undetected_chromedriver as uc
import tempfile
from utils import sanitize_filename, safe_log_file_path
class EmeraldInsights(ChromeDisplayMixin):
    def __init__(self, keyword, start_year, end_year, driver_path,
             output_dir=None, progress_callback=None):
        self._vdisplay = None
        self.driver = None
        # Configure logging
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
        self.logger = logging.getLogger(__name__)

        self.options = Options()
        #self.options.add_argument("--headless")
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

        self.uc_temp_dir = tempfile.mkdtemp(prefix="Emerald_")
         
        self._launch_chrome(self._build_default_chrome_options(), driver_path=driver_path)
        self.wait = WebDriverWait(self.driver, 20)
        self.directory = sanitize_filename(keyword)
        self.output_dir = output_dir
        self.progress_callback = progress_callback
        self.keyword = keyword
        self.start_year = start_year
        self.end_year = end_year
        self.url_csv = f"Emrald_{self.directory}-{start_year.replace('/', '-')}-{end_year.replace('/', '-')}_urls.csv"
        self.authors_csv = f"Emrald_{self.directory}-{start_year.replace('/', '-')}-{end_year.replace('/', '-')}_authors.csv"

        self._setup_logger()  # Initialize logger for the subclass
        self.driver.maximize_window()
        self.run()

    def _setup_logger(self):
        """Configure the logger with both file and stdout handlers (UTF-8 safe)."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)

        log_file = safe_log_file_path(self.__class__.__name__, self.directory, self.start_year, self.end_year)

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
            self.logger.info(f"Emerald ==> Saved data to {filepath}.")
        except Exception as e:
            self.logger.error(f"Emerald ==> Failed to save data to CSV: {e}")

    # def accept_cookies(self):
    #     """Accept cookies if the cookie banner is present."""
    #     try:
    #         # Try multiple possible selectors
    #         selectors = [
    #             "button#onetrust-accept-btn-handler",
    #             "button[id='onetrust-accept-btn-handler']",
    #             "div#onetrust-button-group button:nth-child(2)"
    #         ]
            
    #         for selector in selectors:
    #             try:
    #                 accept_button = WebDriverWait(self.driver, 5).until(
    #                     EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
    #                 )
    #                 accept_button.click()
    #                 self.logger.info(f"Emerald ==> Accepted cookies using selector: {selector}")
    #                 time.sleep(1)  # Brief pause to ensure action completes
    #                 return
    #             except Exception:
    #                 continue
            
    #         self.logger.info("Emerald ==> Could not find cookie accept button with any selector.")
            
    #     except Exception as e:
    #         self.logger.info(f"Emerald ==> Cookie banner handling failed: {e}")
    

    # def get_total_pages(self):
    #     """Retrieve the total number of pages from the search results."""
    #     try:
    #         stats_element = self.wait.until(
    #             EC.presence_of_element_located((By.CSS_SELECTOR, "span.intent_searchresultscount:nth-child(2)"))
    #         )
    #         total_results_text = stats_element.text.split()[-1]
    #         total_results = int(total_results_text)
    #         total_pages = math.ceil(total_results / 50)
    #         self.logger.info(f"Emerald ==> Total results: {total_results}, Total pages: {total_pages}")
    #         return total_pages
    #     except Exception as e:
    #         self.logger.error(f"Emerald ==> Failed to get total pages: {e}")
    #         return 0

    def accept_cookies(self):
        """Accept cookies if the cookie banner is present."""
        try:
            # Wait a bit for the cookie banner to appear
            time.sleep(2)
            
            # Try multiple possible selectors for Emerald Insights cookie banner
            selectors = [
                "button#onetrust-accept-btn-handler",
                "button[id='onetrust-accept-btn-handler']",
                "div#onetrust-button-group button:nth-child(2)",
                ".onetrust-close-btn-handler",
                "button.accept-cookies-button"
            ]
            
            for selector in selectors:
                try:
                    accept_button = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    accept_button.click()
                    self.logger.info(f"Emerald ==> Accepted cookies using selector: {selector}")
                    time.sleep(2)  # Brief pause to ensure action completes
                    return
                except Exception:
                    continue
            
            self.logger.info("Emerald ==> Could not find cookie accept button with any selector.")
            
        except Exception as e:
            self.logger.info(f"Emerald ==> Cookie banner handling failed: {e}")


    def get_total_pages(self):
        """Retrieve the total number of pages from the search results using the HTML structure."""
        try:
            # First, accept cookies before extracting data
            self.accept_cookies()
            
            # Wait for the statistics element to be present
            # Using the structure from document: div.sr-statistics with data-total-item-count attribute
            stats_element = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.sr-statistics.at-sr-statistics"))
            )
            
            # Get the total count from the data attribute
            total_results = int(stats_element.get_attribute("data-total-item-count"))
            
            self.logger.info(f"Emerald ==> Total results found: {total_results}")
            
            # Calculate total pages (assuming 20 results per page based on "1-20 of 19881")
            results_per_page = 20
            total_pages = math.ceil(total_results / results_per_page)
            
            self.logger.info(f"Emerald ==> Total pages: {total_pages}")
            return total_pages
            
        except Exception as e:
            self.logger.error(f"Emerald ==> Failed to get total pages: {e}")
            
            # Fallback method: try to extract from the text content
            try:
                stats_text = self.wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.sr-statistics"))
                ).text
                
                self.logger.info(f"Emerald ==> Statistics text: {stats_text}")
                
                # Extract numbers from text like "1-20 of 19881"
                import re
                match = re.search(r'of\s+([\d,]+)', stats_text)
                if match:
                    total_results = int(match.group(1).replace(',', ''))
                    results_per_page = 20
                    total_pages = math.ceil(total_results / results_per_page)
                    self.logger.info(f"Emerald ==> Total results (fallback): {total_results}, Total pages: {total_pages}")
                    return total_pages
            except Exception as fallback_error:
                self.logger.error(f"Emerald ==> Fallback method also failed: {fallback_error}")
            
            return 0

    def extract_article_links(self, total_pages, base_url, query_params):
        """Extract article links from Emerald search results."""
        all_links = []

        for page in range(1, total_pages + 1):
            query_params["page"] = page
            page_url = f"{base_url}?{urlencode(query_params)}"
            self.logger.info(f"Emerald ==> Loading Page {page}/{total_pages}: {page_url}")

            self.driver.get(page_url)
            time.sleep(3)

            try:
                # Check if we're on a valid page with results
                # Look for "No results found" message
                try:
                    no_results = self.driver.find_element(By.XPATH, "//*[contains(text(), 'No results found')]")
                    if no_results:
                        self.logger.warning(f"Emerald ==> Page {page} shows 'No results found'. Stopping pagination.")
                        break
                except:
                    pass  # No "no results" message, continue
                
                # Find all article boxes of type Journal Articles
                articles = self.wait.until(
                    EC.presence_of_all_elements_located(
                        (By.CSS_SELECTOR, "div.content-type-journal-articles")
                    )
                )

                if not articles:
                    self.logger.warning(f"Emerald ==> No articles found on page {page}. Stopping pagination.")
                    break

                page_links = []
                for article in articles:
                    try:
                        link_tag = article.find_element(By.CSS_SELECTOR, ".sri-title h4 a")
                        href = link_tag.get_attribute("href")

                        # Convert relative URLs to absolute
                        if href.startswith("/"):
                            href = "https://www.emerald.com" + href

                        page_links.append([href])

                    except Exception as e:
                        self.logger.error(f"Emerald ==> Failed to extract link inside article block: {e}")

                if not page_links:
                    self.logger.warning(f"Emerald ==> No links extracted from page {page}. Stopping pagination.")
                    break

                all_links.extend(page_links)
                self.logger.info(f"Emerald ==> Extracted {len(page_links)} links from page {page}.")

            except Exception as e:
                self.logger.error(f"Emerald ==> No articles found on page {page}: {e}")
                # If we can't find articles, stop trying more pages
                break

        # Save to CSV
        if all_links:
            self.save_to_csv(all_links, self.url_csv, header=["Article URL"])
            self.logger.info(f"Emerald ==> Total links extracted: {len(all_links)}")
        else:
            self.logger.warning(f"Emerald ==> No links were extracted from any page.")

    # def extract_author_info(self):
    #     """Read article URLs from the CSV file and extract corresponding author name and email."""
    #     filepath = os.path.join(self.directory, self.url_csv)
    #     if not os.path.exists(filepath):
    #         self.logger.error("URLs file not found! Run extract_article_links() first.")
    #         return

    #     extracted_data = []
    #     with open(filepath, mode="r", encoding="utf-8") as file:
    #         reader = csv.reader(file)
    #         next(reader)  # Skip header

    #         for row in reader:
    #             article_url = row[0]
    #             self.driver.get(article_url)
    #             time.sleep(2)  # Allow time for the page to load

    #             try:
                    
    #                 # Check if AuthorNotes section exists
    #                 author_section = self.wait.until(
    #                     EC.presence_of_element_located((By.CSS_SELECTOR, "section.AuthorNotes"))
    #                 )
    #                 author_name_element = author_section.find_element(By.CSS_SELECTOR, "span.corresp")

    #                 if not author_name_element:
    #                     self.logger.info(f"No author information found for {article_url}. Skipping...")
    #                     self.save_to_csv([[article_url, "N/A", "N/A"]], self.authors_csv, header=["Article URL", "Author Name", "Email"])
    #                     continue  # Move to the next article link
                    
    #                 author_text = author_name_element.text.strip()

    #                 # Remove unwanted phrases
    #                 clean_text = author_text.replace("is the corresponding author and can be contacted at:", "").replace(
    #                     "can be contacted at:", "").replace("can be contacted at", "").strip()

    #                 # Try extracting email
    #                 email_element = author_name_element.find_elements(By.CSS_SELECTOR, "a[href^='mailto:']")
    #                 email = email_element[0].get_attribute("href").replace("mailto:", "").strip() if email_element else "N/A"

    #                 # Extract Name **without appending extra 'N/A'**
    #                 if email != "N/A":
    #                     author_name = clean_text.replace(email, "").strip().rstrip(",")
    #                 else:
    #                     author_name = clean_text  # Keep as is if email is missing

    #                 # Save data immediately to CSV
    #                 self.save_to_csv([[article_url, author_name, email]], self.authors_csv, header=["Article URL", "Author Name", "Email"])
    #                 self.logger.info(f"Extracted: {author_name} - {email}")

    #             except Exception as e:
    #                 self.logger.error(f"Failed to extract author info from {article_url}: {e}")
    #                 self.save_to_csv([[article_url, "N/A", "N/A"]], self.authors_csv, header=["Article URL", "Author Name", "Email"])
    def extract_author_info(self):
        """Read article URLs from the CSV file and extract corresponding author name and email."""
        filepath = os.path.join(self.directory, self.url_csv)
        if not os.path.exists(filepath):
            self.logger.error("Emerald ==> URLs file not found! Run extract_article_links() first.")
            return
        
        with open(filepath, mode="r", encoding="utf-8") as file:
            reader = csv.reader(file)
            next(reader)  # Skip header
            
            for row in reader:
                article_url = row[0]
                self.logger.info(f"Emerald ==> Processing: {article_url}")
                
                try:
                    self.driver.get(article_url)
                    time.sleep(2)  # Allow time for the page to load
                    
                    # Step 1: Click the "Author & Article Information" expand button
                    try:
                        expand_button = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "a.js-expand-collapse-metadata.author-expand-collapse-metadata"))
                        )
                        expand_button.click()
                        time.sleep(1)  # Wait for content to expand
                        self.logger.info(f"Emerald ==> Clicked expand button for {article_url}")
                    except Exception as e:
                        self.logger.warning(f"Emerald ==> Could not find/click expand button for {article_url}: {e}")
                    
                    # Step 2: Extract author information from wi-footnotes
                    try:
                        footnotes_div = self.driver.find_element(By.CSS_SELECTOR, "div.wi-footnotes")
                        article_footnotes = footnotes_div.find_elements(By.CSS_SELECTOR, "div.article-footnote")
                        
                        author_info = []
                        
                        for footnote in article_footnotes:
                            footnote_text = footnote.text.strip()
                            
                            # Check if this footnote contains contact information
                            if "can be contacted at" in footnote_text:
                                # Extract email from the <a> tag
                                try:
                                    email_link = footnote.find_element(By.CSS_SELECTOR, "a[href^='mailto:']")
                                    email = email_link.get_attribute("href").replace("mailto:", "").strip()
                                    
                                    # Extract author name by removing the contact phrase and email
                                    author_name = footnote_text.split("can be contacted at")[0].strip()
                                    
                                    # Remove additional unwanted phrases
                                    phrases_to_remove = [
                                        "is the corresponding author and",
                                        "is the corresponding author",
                                        "Corresponding author",
                                        "Associate editor:",
                                        "and",
                                        "E-mail:",
                                        ":"
                                    ]
                                    
                                    for phrase in phrases_to_remove:
                                        author_name = author_name.replace(phrase, "").strip()
                                    
                                    # Clean up author name (remove any extra whitespace and trailing commas)
                                    author_name = " ".join(author_name.split())
                                    author_name = author_name.rstrip(",").strip()
                                    
                                    self.logger.info(f"Emerald ==> Extracted: {author_name} - {email}")
                                    author_info.append([article_url, author_name, email])
                                    
                                except Exception as e:
                                    self.logger.warning(f"Emerald ==> Could not extract email from footnote: {e}")
                                    continue
                        
                        # Save extracted author info if any found
                        if author_info:
                            self.save_to_csv(author_info, self.authors_csv, header=["Article URL", "Author Name", "Email"])
                        else:
                            self.logger.warning(f"Emerald ==> No author email found for {article_url}")
                            # Continue to next URL without saving
                            continue
                            
                    except Exception as e:
                        self.logger.warning(f"Emerald ==> Could not find wi-footnotes section for {article_url}: {e}")
                        # Continue to next URL without saving
                        continue
                        
                except Exception as e:
                    self.logger.error(f"Emerald ==> Failed to process {article_url}: {e}")
                    # Continue to next URL without saving
                    continue


    def run(self):
        try:
            # Convert MM/DD/YYYY → YYYY-MM-DD
            start_iso = datetime.strptime(self.start_year, "%m/%d/%Y").strftime("%Y-%m-%d")
            end_iso = datetime.strptime(self.end_year, "%m/%d/%Y").strftime("%Y-%m-%d")

            # Construct publication date range:
            # Example: 2025-01-01T00:00:00 TO 2025-01-31T23:59:59
            date_range = f"{start_iso}T00:00:00 TO {end_iso}T23:59:59"

            # Important: date range must be URL-encoded using quote()
            encoded_date_range = quote(date_range, safe="")

            query_params = {
                "q": self.keyword,
                "fl_SiteID": "1",
                "access_openaccess": "true",
                "f_ContentType": "Journal Articles",
                "rg_PublicationDate": date_range,
            }

            base_url = "https://www.emerald.com/search-results/"
            search_url = f"{base_url}?{urlencode(query_params)}"

            print("Final Search URL:", search_url)
            self.driver.get(search_url)

            total_pages = self.get_total_pages()
            if not total_pages or total_pages == 0:
                self.logger.error("Emerald ==> No results found or failed to retrieve total pages.")
                return

            self.extract_article_links(total_pages, base_url, query_params)
            self.extract_author_info()

        except Exception as e:
            self.logger.error(f"Emerald ==> Error in run(): {e}")
        finally:
            # Safely quit the driver
            try:
                if self.driver:
                    self.driver.quit()
                    self.logger.info("Emerald ==> Browser closed successfully.")
            except Exception as quit_error:
                self.logger.warning(f"Emerald ==> Error while closing browser: {quit_error}")

# if __name__ == "__main__":
#     parser = argparse.ArgumentParser(description="Scrape article links and author details from Emrald Insights.")
#     parser.add_argument("--keyword", type=str, required=True, help="Keyword for the search query.")
#     parser.add_argument("--start_year", type=str, required=True, help="Start date in MM/DD/YYYY format.")
#     parser.add_argument("--end_year", type=str, required=True, help="End date in MM/DD/YYYY format.")
#     args = parser.parse_args()
#     # Set a global cache path for WebDriverManager
#     os.environ["WDM_CACHE_PATH"] = "C:/shared_drivers"  # Custom shared directory

# #   Install ChromeDriver once and get its path
#     driver_path = ChromeDriverManager().install()
#     scraper = EmraldInsights(args.keyword, args.start_year, args.end_year, driver_path)
#     scraper.run()

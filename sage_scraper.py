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

import os, argparse, csv, logging, time, math, sys
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from urllib.parse import urlencode
import undetected_chromedriver as uc
import tempfile


class SageScraper:
    def __init__(self, keyword, start_year, end_year, driver_path):
        # Configure logging first to ensure root logger is set up
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
        self.logger = logging.getLogger(__name__)
        self.keyword = keyword
        self.start_year = start_year
        self.end_year = end_year
        self.options = Options()
        
        self.options.add_argument("--window-size=1920,1080")
        #self.options.add_argument("--force-device-scale-factor=1")
        self.options.add_argument("--disable-notifications")
        self.options.add_argument("--disable-background-timer-throttling")
        self.options.add_argument("--disable-backgrounding-occluded-windows")
        self.options.add_argument("--disable-renderer-backgrounding")
        self.options.add_argument("--disable-notifications")
        
        
        self.options.add_argument("--no-sandbox")
        
        self.options.add_argument("--disable-infobars")
        self.options.add_argument("--disable-browser-side-navigation")
        
        self.options.add_argument("--disable-popup-blocking")
        self.options.add_argument("--disable-crash-reporter")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--disable-logging")
        self.uc_temp_dir = tempfile.mkdtemp(prefix="Sage_")
        self.driver = uc.Chrome(
            options=self.options,
            driver_executable_path=driver_path,
            version_main=None,  # Auto-detect Chrome version
            use_subprocess=False  # Important for multiprocessing
        )
        self.wait = WebDriverWait(self.driver, 20)
        self.directory = keyword.replace(" ","-")

        self.url_csv = f"Sage_{self.directory}-{start_year.replace('/', '-')}-{end_year.replace('/', '-')}_urls.csv"
        self.authors_csv = f"Sage_{self.directory}-{start_year.replace('/', '-')}-{end_year.replace('/', '-')}_authors.csv"

        self._setup_logger()  # Initialize the logger configuration
        self.driver.maximize_window()
        self.driver.set_page_load_timeout(180)
        self.driver.set_script_timeout(180)
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
            self.logger.info(f"Sage ==> Saved data to {filepath}.")
        except Exception as e:
            self.logger.error(f"Sage ==> Failed to save data to CSV: {e}")

    def get_total_pages(self):
        """Retrieve the total number of pages from the search results."""
        try:
            stats_element = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "span.result__count"))
            )
            total_results_text = stats_element.text.split()[-1]
            total_results = int(total_results_text)
            total_pages = math.ceil(total_results / 100)
            self.logger.info(f"Sage ==> Total results: {total_results}, Total pages: {total_pages}")
            return total_pages
        except Exception as e:
            self.logger.error(f"Sage ==> Failed to get total pages: {e}")
            return 0

    def extract_article_links(self, total_pages, base_url, query_params):
        """Extract article links from each page and save them to a CSV file."""
        #all_links = []

        for page in range(0, total_pages):
            query_params["startPage"] = page  # Update page number in query params
            page_url = f"{base_url}?{urlencode(query_params)}"
            self.driver.get(page_url)

            time.sleep(2)  # Allow time for page to load

            try:
                links = self.wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'div.issue-item__title > a[data-id="srp-article-title"]'))
                )
                page_links = [[link.get_attribute("href")] for link in links if link.get_attribute("href")]
                self.save_to_csv(page_links, self.url_csv, header=["Article_URL"])
                #all_links.extend(page_links)
                self.logger.info(f"Sage ==> Extracted {len(page_links)} links from page {page}.")
            except Exception as e:
                self.logger.error(f"Sage ==> Failed to extract links from page {page}: {e}")


    def extract_author_info(self):
        """Read article URLs from the CSV file and extract corresponding author name and email."""
        filepath = os.path.join(self.directory, self.url_csv)
        if not os.path.exists(filepath):
            self.logger.error("Sage ==> URLs file not found! Run extract_article_links() first.")
            return

        extracted_data = []
        with open(filepath, mode="r", encoding="utf-8") as file:
            reader = csv.reader(file)
            next(reader)  # Skip header

            for row in reader:
                article_url = row[0]
                self.driver.get(article_url)
                time.sleep(2)  # Allow time for the page to load

                try:
                    # Open the author section
                    author_section = self.wait.until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "a.to-authors-affiliations"))
                    )
                    author_section.click()

                    # Wait for the "Show all" button
                    show_all = self.wait.until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, 'div.expand-all-wrapper > button[data-label-expand="Show all"]'))
                    )

                    # Scroll into view and click
                    self.driver.execute_script("arguments[0].scrollIntoView();", show_all)
                    time.sleep(1)  # Small delay before clicking

                    try:
                        show_all.click()
                        time.sleep(2)
                    except:
                        self.driver.execute_script("arguments[0].click();", show_all)

                    self.logger.info("Sage ==> Show All button clicked.")

                    # Find all authors
                    authors = self.driver.find_elements(By.CSS_SELECTOR, "section.core-authors div[property='author']")
                    
                    for author in authors:
                        # Extract given name and family name
                        given_name = author.find_element(By.CSS_SELECTOR, "span[property='givenName']").text
                        family_name = author.find_element(By.CSS_SELECTOR, "span[property='familyName']").text
                        full_name = f"{given_name} {family_name}"
                        
                        # Extract email if available
                        try:
                            email = author.find_element(By.CSS_SELECTOR, "div.core-email > a[property='email']")
                            email = email.get_attribute("href").replace("mailto:", "")
                        except:
                            email = None  # If no email found
                        
                        # Save data immediately to CSV
                        if email is not None:
                            self.save_to_csv([[article_url, full_name, email]], self.authors_csv, header=["Article_URL", "Author_Name", "Email"])
                            self.logger.info(f"Sage ==> Extracted: {full_name} - {email}")
                        else:
                            pass

                except Exception as e:
                    self.logger.error(f"Sage ==> Failed to extract author info from {article_url}: {e}")
                    self.save_to_csv([[article_url, "N/A", "N/A"]], self.authors_csv, header=["Article_URL", "Author_Name", "Email"])
    def run(self):
        try:
            query_params = {
                "field1":"AllField",
                "text1":self.keyword,
                "AfterMonth":self.start_year.split("/")[0],
                "AfterYear":self.start_year.split("/")[-1],
                "BeforeMonth":self.end_year.split("/")[0],
                "BeforeYear":self.end_year.split("/")[-1],
                "pageSize":100,
                "startPage":0
            }
            base_url = "https://journals.sagepub.com/action/doSearch"
            search_url = f"{base_url}?{urlencode(query_params)}"
            self.driver.get("https://journals.sagepub.com")
            time.sleep(30)
            cookie_section = self.wait.until(
                    EC.presence_of_element_located((By.ID, "onetrust-accept-btn-handler"))
                )
            
            cookie_section.click()
            self.driver.get(search_url)
            time.sleep(20)
            total_pages = self.get_total_pages()
            if total_pages > 0:
                    
                self.extract_article_links(total_pages, base_url, query_params)
                self.extract_author_info()  # Extracts author info after collecting URLs

        finally:
            self.driver.quit()


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
#     scraper = SageScraper(args.keyword, args.start_year, args.end_year, driver_path)
#     #scraper.run()

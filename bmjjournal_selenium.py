from chrome_display_mixin import ChromeDisplayMixin

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

import os, argparse, csv, logging, time, math, re, sys
import selenium
from selenium import webdriver
from selenium.common.exceptions import WebDriverException, TimeoutException, NoSuchWindowException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains
from urllib.parse import urlencode
import undetected_chromedriver as uc
from datetime import datetime
import tempfile


class BMJJournalScraper(ChromeDisplayMixin):
    def __init__(self, keyword, start_year, end_year, driver_path,
             output_dir=None, progress_callback=None):
        self._vdisplay = None
        self.driver = None
        self.output_dir = output_dir
        self.progress_callback = progress_callback
        # Configure logging
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
        self.logger = logging.getLogger(__name__)

        self.options = Options()
        #self.options.add_argument("--headless")
        self.options.add_argument("--window-size=1920,1080")
        self.options.add_argument("--disable-notifications")
        self.options.add_argument("--disable-background-timer-throttling")
        self.options.add_argument("--disable-backgrounding-occluded-windows")
        self.options.add_argument("--disable-renderer-backgrounding")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("excludeSwitches=enable-automation")
        self.options.add_argument("--disable-logging")
        self.options.add_argument("--disable-blink-features=AutomationControlled")

        self.uc_temp_dir = tempfile.mkdtemp(prefix="BMJ_")
        self.driver = None
        self.wait = None
        self.driver_path = driver_path
        
        self.directory = keyword.replace(" ","-")
        self.keyword = keyword
        self.start_year = self.convert_date_format(start_year)
        self.end_year = self.convert_date_format(end_year)
        self.url_csv = f"BMJ_{self.directory}-{self.start_year}-{self.end_year}_urls.csv"
        self.authors_csv = f"BMJ_{self.directory}-{self.start_year}-{self.end_year}_authors.csv"

        self._setup_logger()  # Initialize logger for the subclass
        self._initialize_driver()
        self.run()

    def _initialize_driver(self):
        """Initialize the Chrome driver"""
        try:
            self._launch_chrome(self._build_default_chrome_options(), driver_path=self.driver_path)
            self.wait = WebDriverWait(self.driver, 20)
            self.driver.maximize_window()
            self.logger.info("Driver initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize driver: {e}")
            raise

    def _restart_driver(self):
        """Restart the Chrome driver in case of crashes"""
        try:
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
            time.sleep(2)
            self._initialize_driver()
            self.logger.info("Driver restarted successfully")
        except Exception as e:
            self.logger.error(f"Failed to restart driver: {e}")
            raise

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
        if hasattr(sys.stdout, 'reconfigure'):
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
        
    def convert_date_format(self, date_str):
        """Convert date from MM/DD/YYYY to YYYY-MM-DD format."""
        try:
            input_date = datetime.strptime(date_str, "%m/%d/%Y")
            output_date = input_date.strftime("%Y-%m-%d")
            return output_date
        except ValueError as e:
            self.logger.error(f"Invalid date format: {date_str}. Error: {e}")
            return None

    def save_to_csv(self, data, filename, header=None):
        """Save data to a CSV file."""
        try:
            os.makedirs(self.directory, exist_ok=True)
            filepath = os.path.join(self.directory, filename)
            file_exists = os.path.exists(filepath) and os.path.getsize(filepath) > 0
            
            with open(filepath, mode="a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                if not file_exists and header:
                    writer.writerow(header)
                writer.writerows(data)
            self.logger.info(f"Saved data to {filepath}.")
        except Exception as e:
            self.logger.error(f"Failed to save data to CSV: {e}")

    def get_total_pages(self):
        """Retrieve the total number of pages from the search results."""
        try:
            stats_element = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#search-summary-wrapper"))
            )
            stats_text = stats_element.text.strip()
            
            # Check for "No results" case
            if "No results" in stats_text or "0 results" in stats_text:
                self.logger.info("No results found for this search")
                return 0
            
            total_results_text = stats_text.split()[0].replace(",","").strip()
            
            # Validate it's a digit before parsing
            if not total_results_text.isdigit():
                self.logger.warning(f"Could not parse total results from: {stats_text}")
                return 0
            
            total_results = int(total_results_text)
            total_pages = math.ceil(total_results / 100)
            self.logger.info(f"Total results: {total_results}, Total pages: {total_pages}")
            return total_pages
        except Exception as e:
            self.logger.error(f"Failed to get total pages: {e}")
            return 0

    def extract_article_links(self, total_pages, query_params):
        """Extract article links from each page and save them to a CSV file."""
        all_links = []

        for page in range(0, total_pages):
            page_url = f"{query_params['base_url']}?page={page}"
            
            try:
                self.driver.get(page_url)
                time.sleep(3)  # Increased wait time

                links = self.wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'a.highwire-cite-linked-title'))
                )
                page_links = [[link.get_attribute("href")] for link in links if link.get_attribute("href")]
                all_links.extend(page_links)
                self.logger.info(f"Extracted {len(page_links)} links from page {page}.")
            except TimeoutException:
                self.logger.error(f"Timeout while extracting links from page {page}")
            except NoSuchWindowException:
                self.logger.error(f"Window closed on page {page}, restarting driver")
                self._restart_driver()
            except Exception as e:
                self.logger.error(f"Failed to extract links from page {page}: {e}")

        self.save_to_csv(all_links, self.url_csv, header=["Article_URL"])

    def extract_author_info(self):
        """Read article URLs from the CSV file and extract corresponding author name and email."""
        filepath = os.path.join(self.directory, self.url_csv)
        if not os.path.exists(filepath):
            self.logger.error("URLs file not found! Run extract_article_links() first.")
            return

        with open(filepath, mode="r", encoding="utf-8") as file:
            reader = csv.reader(file)
            next(reader)  # Skip header

            for row in reader:
                article_url = row[0]
                if "veterinaryrecord.bmj.com" in article_url:
                    self.logger.info("Skipping veterinaryrecord.bmj.com URL")
                    continue

                max_retries = 3
                retry_count = 0
                
                while retry_count < max_retries:
                    try:
                        # Check if driver is still alive
                        try:
                            _ = self.driver.current_url
                        except (NoSuchWindowException, WebDriverException):
                            self.logger.warning("Driver not responsive, restarting...")
                            self._restart_driver()

                        self.driver.get(article_url + ".info")
                        time.sleep(3)

                        current_url = self.driver.current_url
                        author_info = []

                        if current_url.endswith(".info"):
                            # Old style author extraction
                            author_notes = self.driver.find_elements(By.CSS_SELECTOR, "li#corresp-1")

                            for note in author_notes:
                                corresp_text = note.text.strip()
                                self.logger.info(f"Original Text: {corresp_text}")

                                email_matches = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', corresp_text)
                                if not email_matches:
                                    self.logger.warning(f"No emails found for {article_url}")
                                    continue

                                text_parts = re.split(r'[\w\.-]+@[\w\.-]+\.\w+', corresp_text)
                                for i, email in enumerate(email_matches):
                                    name_part = text_parts[i].strip()
                                    to_remove = ["Correspondence to", "Dr", "Professor", ":", ";", "\n"]
                                    author_name = name_part
                                    for phrase in to_remove:
                                        author_name = author_name.replace(phrase, "").strip()

                                    author_name_final = author_name.split(",")[0].strip()
                                    self.logger.info(f"Extracted: {author_name_final} - {email}")
                                    author_info.append([article_url, author_name_final, email])

                        else:
                            # New style author extraction
                            try:
                                show_all = WebDriverWait(self.driver, 5).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR, '#show-all-button button'))
                                )
                                if show_all.is_displayed():
                                    actions = ActionChains(self.driver)
                                    actions.move_to_element(show_all).perform()
                                    show_all.click()
                                    time.sleep(2)
                            except TimeoutException:
                                self.logger.info(f"Show all button not found for {article_url}")

                            envelopes = self.driver.find_elements(By.CSS_SELECTOR, "#author-list-envelope-icon")

                            for ele in envelopes:
                                try:
                                    actions = ActionChains(self.driver)
                                    actions.move_to_element(ele).perform()
                                    time.sleep(0.5)
                                    ele.click()
                                    time.sleep(1)

                                    div_ele = WebDriverWait(self.driver, 10).until(
                                        EC.presence_of_element_located((By.CSS_SELECTOR, 'div#popover-border'))
                                    )
                                    
                                    email_href = div_ele.find_element(By.CSS_SELECTOR, 'p[data-testid^="author-popover-email"] > a[href^="mailto:"]')
                                    email = email_href.get_attribute("href").replace("mailto:", "").strip()
                                    author_name = div_ele.find_element(By.CSS_SELECTOR, 'p[data-testid="popover-title "]').text.strip()

                                    self.logger.info(f"Extracted: {author_name} - {email}")
                                    author_info.append([article_url, author_name, email])
                                except Exception as inner_e:
                                    self.logger.warning(f"Failed to extract from envelope: {inner_e}")
                                    continue

                        if author_info:
                            self.save_to_csv(author_info, self.authors_csv, header=["Article_URL", "Author_Name", "Email"])
                        else:
                            self.save_to_csv([[article_url, "N/A", "N/A"]], self.authors_csv, header=["Article_URL", "Author_Name", "Email"])
                        
                        # If successful, break the retry loop
                        break

                    except (NoSuchWindowException, WebDriverException) as e:
                        retry_count += 1
                        self.logger.error(f"Driver error on {article_url} (attempt {retry_count}/{max_retries}): {e}")
                        if retry_count < max_retries:
                            self._restart_driver()
                            time.sleep(5)
                        else:
                            self.logger.error(f"Max retries reached for {article_url}, skipping...")
                            self.save_to_csv([[article_url, "ERROR", "ERROR"]], self.authors_csv, header=["Article_URL", "Author_Name", "Email"])
                    
                    except Exception as e:
                        self.logger.error(f"Failed to extract author info from {article_url}: {e}")
                        self.save_to_csv([[article_url, "N/A", "N/A"]], self.authors_csv, header=["Article_URL", "Author_Name", "Email"])
                        break

    def run(self):
        """Main execution method"""
        try:
            query_params = {
                "base_url": f"https://journals.bmj.com/search/{self.keyword}%20limit_from%3A{self.start_year}%20limit_to%3A{self.end_year}%20exclude_meeting_abstracts%3A1%20numresults%3A100%20sort%3Arelevance-rank%20format_result%3Astandard%20button%3ASubmit",
                "page": 0
            }
            
            search_url = query_params["base_url"]
            self.driver.get(search_url)
            time.sleep(3)
            
            try:
                cookie_section = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
                )
                cookie_section.click()
                time.sleep(2)
            except TimeoutException:
                self.logger.info("Cookie banner not found, continuing...")

            total_pages = self.get_total_pages()
            if total_pages > 0:
                self.extract_article_links(total_pages, query_params)
                self.extract_author_info()
            else:
                self.logger.error("No pages found to scrape")

        except Exception as e:
            self.logger.error(f"Error in run method: {e}")
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                    self.logger.info("Driver closed successfully")
                except Exception as e:
                    self.logger.error(f"Error closing driver: {e}")


# if __name__ == "__main__":
#     parser = argparse.ArgumentParser(description="Scrape article links and author details from BMJ Journal.")
#     parser.add_argument("--keyword", type=str, required=True, help="Keyword for the search query.")
#     parser.add_argument("--start_year", type=str, required=True, help="Start date in MM/DD/YYYY format.")
#     parser.add_argument("--end_year", type=str, required=True, help="End date in MM/DD/YYYY format.")
#     args = parser.parse_args()
    
#     # Set a global cache path for WebDriverManager
#     os.environ["WDM_CACHE_PATH"] = "C:/shared_drivers"

#     # Install ChromeDriver once and get its path
#     driver_path = ChromeDriverManager().install()
    
#     # Create scraper instance and run
#     scraper = BMJJournalScraper(args.keyword, args.start_year, args.end_year, driver_path)
#     scraper.run()  # Only call run() once here, not in __init__
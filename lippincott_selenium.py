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
import selenium
from selenium import webdriver
from selenium.common.exceptions import WebDriverException





from webdriver_manager.chrome import ChromeDriverManager

from urllib.parse import urlencode
import undetected_chromedriver as uc
from datetime import datetime
import tempfile


class LippincottScraper(ChromeDisplayMixin):
    def __init__(self, keyword, start_year, end_year,driver_path):
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
        self.options.add_argument("excludeSwitches=enable-automation")
        
        
        self.options.add_argument("--disable-logging")
        self.options.add_argument("--disable-blink-features=AutomationControlled")
        self.uc_temp_dir = tempfile.mkdtemp(prefix="Lippincott_")
        # [REMOVED uc.Chrome INIT — replaced by mixin]
        self.wait = WebDriverWait(self.driver, 60)
        self.directory = keyword.replace(" ","-")
        self.keyword = keyword
        self.start_year = self.convert_date_format(start_year)
        self.end_year = self.convert_date_format(end_year)
        self.url_csv = f"Lippincott_{self.directory}-{self.start_year}-{self.end_year}_urls.csv"
        self.authors_csv = f"Lippincott_{self.directory}-{self.start_year}-{self.end_year}_authors.csv"

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
        
    def convert_date_format(self, date_str):
        """Convert date from MM/DD/YYYY to YYYY-MM-DD format."""
        try:
            # Parse the input date string
            input_date = datetime.strptime(date_str, "%m/%d/%Y")
            # Format the date in the desired output format
            output_date = input_date.strftime("%Y-%m-%d")
            return output_date
        except ValueError as e:
            self.logger.error(f"Lippincott ==> Invalid date format: {date_str}. Error: {e}")
            return None
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
            self.logger.info(f"Lippincott ==> Saved data to {filepath}.")
        except Exception as e:
            self.logger.error(f"Lippincott ==> Failed to save data to CSV: {e}")

    def get_total_pages(self):
        """Retrieve the total number of pages from the search results."""
        try:
            stats_element = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "span.primary-search-results-text"))
            )
            total_results_text = stats_element.text.split(" ")[1].replace(",","").strip()
            total_results = int(total_results_text)
            total_pages = math.ceil(total_results / 100)
            self.logger.info(f"Lippincott ==> Total results: {total_results}, Total pages: {total_pages}")
            return total_pages
        except Exception as e:
            self.logger.error(f"Lippincott ==> Failed to get total pages: {e}")
            return 0

    def extract_article_links(self, total_pages, query_params):
        """Extract article links from each page and save them to a CSV file."""
        loop_until = (total_pages if total_pages < 11 else 11)
        
        for page in range(0, loop_until):
            time.sleep(5)  # Wait for page to load
            
            try:
                # Wait for content to load
                div_ele = self.wait.until(EC.presence_of_all_elements_located((By.ID, "checkBoxListContainer")))
                article_links = self.wait.until(EC.presence_of_all_elements_located((By.XPATH, "//header//a[@href]")))
                
                # Extract href attributes
                hrefs = [link.get_attribute("href").strip() for link in article_links]
                
                # Filter unique links
                unique_links = []
                for href in hrefs:
                    if href.startswith("https://journals.lww.com"):
                        unique_links.append(href)
                
                self.logger.info(f"Lippincott ==> Extracted {len(unique_links)} links from page {page + 1}/{loop_until}.")
                self.save_to_csv([[link] for link in unique_links], self.url_csv, header=["Article_URL"])
                
                # Break if this is the last page
                if page >= loop_until - 1:
                    self.logger.info("Lippincott ==> Reached last page to scrape.")
                    break
                
                # Navigate to next page using multiple methods
                next_clicked = False
                
                # Method 1: Try clicking the next button directly
                try:
                    next_button = self.wait.until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "a.element__nav--next"))
                    )
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
                    time.sleep(1)
                    
                    # Try JavaScript click first (more reliable for ASP.NET postbacks)
                    self.driver.execute_script("arguments[0].click();", next_button)
                    self.logger.info(f"Lippincott ==> ✅ Navigated to page {page + 2} using JS click.")
                    next_clicked = True
                    time.sleep(3)  # Wait for page load
                    
                except Exception as e:
                    self.logger.warning(f"Lippincott ==> Method 1 (JS click) failed: {e}")
                
                # Method 2: If JS click didn't work, try executing the WebForm postback directly
                if not next_clicked:
                    try:
                        next_page_num = page + 2  # Next page number (1-indexed)
                        
                        # Execute ASP.NET postback for the specific page number
                        postback_script = f"""
                        __doPostBack('ctl00$ctl30$g_3e59ddb2_821c_45f2_8a16_6a9672a5d882$ctl00$listItemActionToolbarControlBottom$pagingControl$pagingControl$pageno{next_page_num}', '');
                        """
                        
                        self.driver.execute_script(postback_script)
                        self.logger.info(f"Lippincott ==> ✅ Navigated to page {next_page_num} using postback.")
                        next_clicked = True
                        time.sleep(3)
                        
                    except Exception as e:
                        self.logger.warning(f"Lippincott ==> Method 2 (postback) failed: {e}")
                
                # Method 3: Try clicking the numbered page link
                if not next_clicked:
                    try:
                        next_page_num = page + 2
                        page_link = self.wait.until(
                            EC.element_to_be_clickable((By.XPATH, f"//a[@aria-label='Goto Page {next_page_num}']"))
                        )
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", page_link)
                        time.sleep(1)
                        self.driver.execute_script("arguments[0].click();", page_link)
                        self.logger.info(f"Lippincott ==> ✅ Navigated to page {next_page_num} using page link.")
                        next_clicked = True
                        time.sleep(3)
                        
                    except Exception as e:
                        self.logger.warning(f"Lippincott ==> Method 3 (page link) failed: {e}")
                
                # If all methods failed, break the loop
                if not next_clicked:
                    self.logger.error("Lippincott ==> 🚀 Could not navigate to next page. All methods failed.")
                    break
                
                # Verify we're on a new page by checking page indicator
                try:
                    current_page_indicator = self.driver.find_element(
                        By.CSS_SELECTOR, "a.element__link[aria-current='true']"
                    )
                    current_page_text = current_page_indicator.text
                    self.logger.info(f"Lippincott ==> Current page indicator: {current_page_text}")
                    
                    if int(current_page_text) != page + 2:
                        self.logger.warning(f"Lippincott ==> Page indicator mismatch. Expected {page + 2}, got {current_page_text}")
                        
                except Exception as e:
                    self.logger.warning(f"Lippincott ==> Could not verify page number: {e}")
            
            except Exception as e:
                self.logger.error(f"Lippincott ==> Failed to extract links from page {page + 1}: {e}")
                break

    
    def extract_author_info(self):
        """Read article URLs from the CSV file and extract corresponding author name and email."""
        filepath = os.path.join(self.directory, self.url_csv)
        if not os.path.exists(filepath):
            self.logger.error("Lippincott ==> URLs file not found! Run extract_article_links() first.")
            return

        with open(filepath, mode="r", encoding="utf-8") as file:
            reader = csv.reader(file)
            next(reader)  # Skip header

            for row in reader:
                article_url = "".join(row)
                author_info = []
                try:
                    self.driver.get(article_url)
                    time.sleep(2)  # Allow time for the page to load

                    # Get and print the current URL
                    author_details = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#ejp-article-authors-link")))
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", author_details)
                    
                    #author_details = self.driver.find_element(By.CSS_SELECTOR, "#ejp-article-authors-link")
                    author_details.click()
                    
                    
                    #if current_url.endswith(".info"):

                    author_notes = self.driver.find_element(By.CSS_SELECTOR, "#ejp-article-authors-info")
                    try:
                        # Wait for the email link to be present
                        span_elements = WebDriverWait(author_notes, 10).until(
                            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "span a[href^='mailto:']"))
                        )

                        # Extract email address from href
                        emails = []
                        text_parts = []
                        
                        for span in span_elements:
                            email_href = span.get_attribute("href")
                            email = email_href.replace("mailto:mailto:", "").replace("mailto:", "").strip()
                            print(f"Lippincot ==> 📧 Extracted Email: {email}")
                            emails.append(email)


                            # Find the parent <p> element
                            parent_p_element = span.find_element(By.XPATH, "./ancestor::p")
                            print(f"Lippincot ==> DEBUG: Parent <p> outer HTML: {parent_p_element.get_attribute('outerHTML')}")
                            parent_text = self.driver.execute_script("return arguments[0].textContent;", parent_p_element).strip()
                            print(f"Lippincot ==> DEBUG (JS Extracted): {parent_text}")
                            text_parts = re.split(r'[\w\.-]+@[\w\.-]+\.\w+', parent_text)
                        

                        for i, email in enumerate(emails):
                            
                            # The name should be in the part of the text before the email
                            name_part = text_parts[i].strip()
                            if text_parts[i + 1].startswith("("):
                                author_name = text_parts[i+1].strip().replace(").","").removeprefix("(")
                                self.logger.info(f"Lippincott ==> Extracted: {author_name} - {email}")
                                author_info.append([article_url, author_name, email])
                            
                                continue       
                            elif "is corresponding author." in name_part:
                                split_names = name_part.split(",")
                                for name in split_names:
                                    if "is corresponding author." in name:

                                        nametext = name.split(".")
                                        for n in nametext:
                                            if "is corresponding author" in n:
                                                author_name = n.replace("is corresponding author","").strip()
                                                self.logger.info(f"Lippincott ==> Extracted: {author_name} - {email}")
                                                author_info.append([article_url, author_name, email])
                                continue
                            else:        
                                # Remove unnecessary parts from the author text to get the name
                                part = name_part.split(",")[0].replace("Correspondence to","").strip()
                                to_remove = ["Corresponding Author. Address","Corresponding author", "Corresponding author.","Corresponding Author","Address correspondence to",
                                            "Address for correspondence","Correspondence","E-mail","Send reprint requests to","Reprint requests:","Please send correspondence to",
                                            "reprint requests to", "For correspondence","✉","To whom correspondance may be addressed","Email for correspondence",
                                            "Assoc.", "Reprints:","P. O. Box","Dr.", "Prof.","Professor","Co-correspondence",":", ";", "*", "and","\n"]
                                author_name = part
                                for phrase in to_remove:
                                    author_name = author_name.replace(phrase, "",1).strip(".").strip()
                                self.logger.info(f"Lippincott ==> Extracted: {author_name} - {email}")
                                author_info.append([article_url, author_name, email])

                        # Save all extracted author info to CSV
                        self.save_to_csv(author_info, self.authors_csv, header=["Article_URL", "Author_Name", "Email"])


                    except Exception as e:
                        self.logger.error(f"❌ Error: {e}")
                        continue

                except WebDriverException as e:
                    self.logger.error(f"Lippincot ==> Failed to navigate to {article_url}.info: {e}")
                    self.driver.quit()
                    # [REMOVED uc.Chrome INIT — replaced by mixin]
                    self.wait = WebDriverWait(self.driver, 10)
                    self.driver.get("https://journals.lww.com/environepidem/fulltext/2022/06000/exposomic_determinants_of_immune_mediated.6.aspx")
                    time.sleep(5)
                    cookie_section = self.wait.until(EC.presence_of_element_located((By.ID, "onetrust-reject-all-handler")))
                    cookie_section.click()
                    continue
                except Exception as e:
                    self.logger.error(f"Lippincott ==> Failed to extract author info from {article_url}: {e}")
                    self.save_to_csv([[article_url, "N/A", "N/A"]], self.authors_csv, header=["Article_URL", "Author_Name", "Email"])
            
    def run(self):
        opts = self._build_default_chrome_options(download_dir=getattr(self, 'output_dir', None))
        self._launch_chrome(opts, driver_path=getattr(self, 'driver_path', None))
        try:
            query_params = {
                "base_url": f"https://lww.com/pages/results.aspx?txtKeywords={self.keyword}",
                
            }
            
            search_url = f"{query_params["base_url"]}" #?{urlencode(str(query_params["page"]))}"
            self.driver.get(search_url)
            #self.driver.save_screenshot("homepage.png")
            time.sleep(5)
            # **Step 1: Reject Cookies**
            try:
                reject_cookies = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#onetrust-accept-btn-handler")))
                reject_cookies.click()
                #self.driver.save_screenshot("cookies.png")
                self.logger.info("Lippincott ==> ✅ Rejected cookies.")
        finally:
            self._quit_chrome()

            except:
                self.logger.warning("Lippincott ==> ℹ️ No cookie popup found.")
            self.driver.implicitly_wait(5)
            total_pages = self.get_total_pages()
            if total_pages > 0:
                # **Step 2: Scroll to the dropdown element before interaction**
                dropdown_container = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.wp-items-on-page")))
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", dropdown_container)
                time.sleep(2)

                # **Step 3: Use JavaScript to change dropdown value to "100"**
                dropdown_id = "ctl00_ctl30_g_3e59ddb2_821c_45f2_8a16_6a9672a5d882_ctl00_listItemActionToolbarControlBottom_pagingControl_itemsOnPageControl_ddOptionsMobile"

                self.driver.execute_script(f"""
                    var dropdown = document.getElementById('{dropdown_id}');
                    dropdown.value = '100';
                    dropdown.dispatchEvent(new Event('change'));
                """)
                self.logger.info("Lippincott ==> ✅ JavaScript: Changed dropdown value to 100.")
                # **Step 4: Wait for the page to update after selecting 100**
                self.driver.implicitly_wait(5)
                self.extract_article_links(total_pages, query_params)
                self.extract_author_info()  # Extracts author info after collecting URLs

        finally:
            self.driver.close()
            self.driver.quit()


# if __name__ == "__main__":
#     parser = argparse.ArgumentParser(description="Scrape article links and author details from BJM Journal.")
#     parser.add_argument("--keyword", type=str, required=True, help="Keyword for the search query.")
#     parser.add_argument("--start_year", type=str, required=True, help="Start date in MM/DD/YYYY format.")
#     parser.add_argument("--end_year", type=str, required=True, help="End date in MM/DD/YYYY format.")
#     args = parser.parse_args()
# #    Set a global cache path for WebDriverManager
#     os.environ["WDM_CACHE_PATH"] = "C:/shared_drivers"  # Custom shared directory

# #   Install ChromeDriver once and get its path
#     driver_path = ChromeDriverManager().install()
#     scraper = LippincottScraper(args.keyword, args.start_year, args.end_year, driver_path)
#     #scraper.run()


#################################################################################################
######## Changed pagination logic for Next page click
##################################################################################################


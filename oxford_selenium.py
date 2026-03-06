# import os
# import csv
# import math
# import logging
# import argparse
# 
# 
# 
# 
# from urllib.parse import urlencode, urljoin
# import undetected_chromedriver as uc  # Import undetected_chromedriver

# # Configure logging to file and console
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s - %(levelname)s - %(message)s",
#     handlers=[
#         logging.FileHandler("scraper.log"),
#         logging.StreamHandler()  # Adds console output
#     ]
# )

# class ArticleScraper:
#     def __init__(self):
#         options = Options()
#         options.add_argument("--start-maximized")
#         options.add_argument("--disable-notifications")
#         # options.add_argument("--headless")  # Optional: Use headless mode for speed
#         self.driver = uc.Chrome(options=options)  # Use undetected_chromedriver
#         self.wait = WebDriverWait(self.driver, 20)

#     def detect_and_handle_captcha(self):
#         """Detect and dismiss CAPTCHA if present."""
#         try:
#             captcha_element = self.wait.until(
#                 EC.presence_of_element_located((By.CSS_SELECTOR, ".g-recaptcha, img[src*='captcha']"))
#             )
#             if captcha_element:
#                 logging.warning("CAPTCHA detected!")
#                 try:
#                     verify_button = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Verify')]")
#                     verify_button.click()
#                     logging.info("Clicked 'Verify' button on CAPTCHA.")
#                 except Exception:
#                     logging.warning("No 'Verify' button found. Manual intervention may be required.")
#         except Exception:
#             logging.info("No CAPTCHA detected. Continuing...")

#     def accept_cookies(self):
#         """Accept cookies if the cookie banner is present."""
#         try:
#             accept_button = self.wait.until(
#                 EC.presence_of_element_located((By.CSS_SELECTOR, "button#accept-button.banner-filled-button"))
#             )
#             accept_button.click()
#             logging.info("Accepted cookies.")
#         except Exception:
#             logging.info("Cookie banner not found or already dismissed.")

#     def get_total_pages(self):
#         """Retrieve the total number of pages from the search results."""
#         try:
#             stats_element = self.wait.until(
#                 EC.presence_of_element_located((By.CSS_SELECTOR, "div.sr-statistics.at-sr-statistics"))
#             )
#             total_results_text = stats_element.text.split()[2].replace(",", "")
#             total_results = int(total_results_text)
#             total_pages = math.ceil(total_results / 20)
#             logging.info(f"Total results: {total_results}, Total pages: {total_pages}")
#             return total_pages
#         except Exception as e:
#             logging.error(f"Failed to get total pages: {e}")
#             return 0

#     def extract_links(self):
#         """Extract all article links from the current page."""
#         links = []
#         try:
#             articles = self.wait.until(
#                 EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.sr-list.al-article-box.al-normal.clearfix"))
#             )
#             for article in articles:
#                 try:
#                     link_element = article.find_element(By.CSS_SELECTOR, "a.article-link.at-sr-article-title-link")
#                     link = link_element.get_attribute("href")
#                     links.append(link)
#                 except Exception as e:
#                     logging.warning(f"Failed to extract a link: {e}")
#             logging.info(f"Extracted {len(links)} links from the current page.")
#         except Exception as e:
#             logging.error(f"Error extracting links: {e}")
#         return links

#     def save_to_csv(self, data, directory, filename, header=None):
#         """Save data to a CSV file."""
#         try:
#             os.makedirs(directory, exist_ok=True)
#             filepath = os.path.join(directory, filename)
#             with open(filepath, mode="a", newline="", encoding="utf-8") as file:
#                 writer = csv.writer(file)
#                 if os.path.getsize(filepath) == 0 and header:  # Write header only if file is empty
#                     writer.writerow(header)
#                 writer.writerows(data)
#             logging.info(f"Saved data to {filepath}.")
#         except Exception as e:
#             logging.error(f"Failed to save data to CSV: {e}")

#     def get_next_url(self):
#         """Get the URL for the next page if available."""
#         try:
#             next_button = self.driver.find_element(By.CSS_SELECTOR, "a.sr-nav-next.al-nav-next")
#             next_url_params = next_button.get_attribute("data-url")
#             current_url = self.driver.current_url
#             base_url = current_url.split("?")[0]
#             next_url = urljoin(base_url, "?" + next_url_params)
#             logging.info(f"Next page URL: {next_url}")
#             return next_url
#         except Exception:
#             logging.info("No 'Next' button found. Pagination ended.")
#             return None

#     def scrape_author_emails(self, input_csv, output_csv):
#         """Extract authors and emails from article pages."""
#         try:
#             with open(input_csv, "r", encoding="utf-8") as file:
#                 reader = csv.reader(file)
#                 next(reader)  # Skip header row
#                 urls = [row[0] for row in reader]

#             with open(output_csv, "w", encoding="utf-8", newline="") as csvfile:
#                 writer = csv.writer(csvfile)
#                 writer.writerow(["url", "author", "email"])  # Write header

#                 for url in urls:
#                     self.driver.get(url)
#                     try:
#                         # Click "Show More" if the button is available
#                         try:
#                             show_more_button = self.wait.until(
#                                 EC.presence_of_element_located((By.CSS_SELECTOR, "a#show-meta-authors"))
#                             )
#                             show_more_button.click()
#                             self.driver.implicitly_wait(2)
#                             logging.info(f"'Show More' clicked on {url}")
#                         except Exception:
#                             logging.info(f"No 'Show More' button found on {url}. Proceeding with author link search.")

#                         # Iterate through author links and extract emails from each popup
#                         author_links = self.driver.find_elements(By.CSS_SELECTOR, "span.al-author-name-more button.js-linked-name-trigger")
#                         if author_links:
#                             for link in author_links:
#                                 try:
#                                     author_name = link.text.strip()
#                                     link.click()
#                                     logging.info(f"Author link clicked for {author_name} on {url}")

#                                     # Wait for the popup to load and fetch the dynamically updated content
#                                     popup_content = self.wait.until(
#                                         EC.presence_of_element_located(
#                                             (By.CSS_SELECTOR, "span.al-author-info-wrap.open")
#                                         )
#                                     )
#                                     self.driver.implicitly_wait(2)
#                                     # Extract emails from the current popup
#                                     email_elements = popup_content.find_elements(By.CSS_SELECTOR, "a[href^='mailto:']")
#                                     emails = [email.get_attribute("href").replace("mailto:", "") for email in email_elements]

#                                     if emails:
#                                         for email in emails:
#                                             writer.writerow([url, author_name, email])
#                                             logging.info(f"Extracted: {author_name} - {email}")
#                                     else:
#                                         logging.info(f"No emails found for {author_name} on {url}")

#                                     # Close the popup if necessary (depends on website behavior)
#                                     try:
#                                         close_button = popup_content.find_element(By.CSS_SELECTOR, ".close-button")
#                                         close_button.click()
#                                     except Exception:
#                                         pass

#                                 except Exception as e:
#                                     logging.warning(f"Failed to extract data from author link for {url}: {e}")
#                                     continue
#                         else:
#                             logging.info(f"No author links found on {url}. Proceeding with Author Notes fallback.")

#                         # If no emails are found from author links, check for Author Notes link
#                         try:
#                             author_notes_link = self.driver.find_element(By.CSS_SELECTOR, "a.js-linked-footnotes")
#                             author_notes_link.click()
#                             logging.info(f"Author Notes clicked on {url}")

#                             # Extract author name and emails from the Author Notes popup
#                             popup_content = self.wait.until(
#                                 EC.presence_of_element_located(
#                                     (By.CSS_SELECTOR, "span.al-author-info-wrap")
#                                 )
#                             )
#                             self.driver.implicitly_wait(2)
#                             name_element = popup_content.find_element(By.CSS_SELECTOR, "div.info-card-name")
#                             author_name = name_element.text.strip()
#                             email_elements = popup_content.find_elements(By.CSS_SELECTOR, "a[href^='mailto:']")
#                             emails = [email.get_attribute("href").replace("mailto:", "") for email in email_elements]

#                             for email in emails:
#                                 writer.writerow([url, author_name, email])
#                                 logging.info(f"Extracted from Author Notes: {author_name} - {email}")

#                         except Exception as e:
#                             logging.warning(f"No Author Notes found or failed to extract from Author Notes for {url}: {e}")

#                     except Exception as e:
#                         logging.error(f"Error while processing {url}: {e}")

#         except Exception as e:
#             logging.error(f"Failed to scrape author emails: {e}")


#     def run(self, search_url, keyword, start_year, end_year):
#         """Run the scraper for the given search URL."""
#         try:
#             self.driver.get(search_url)
#             self.detect_and_handle_captcha()
#             self.accept_cookies()

#             directory = keyword
#             url_filename = f"{keyword}_{start_year.replace('/', '-')}_to_{end_year.replace('/', '-')}_urls.csv"
#             email_filename = f"{keyword}_{start_year.replace('/', '-')}_to_{end_year.replace('/', '-')}_authors_emails.csv"

#             total_pages = self.get_total_pages()

#             for page_number in range(total_pages):
#                 links = self.extract_links()
#                 self.save_to_csv([[link] for link in links], directory, url_filename, header=["article_url"])

#                 next_url = self.get_next_url()
#                 if not next_url:
#                     logging.info("Pagination ended. Starting to scrape author emails.")
#                     self.scrape_author_emails(os.path.join(directory, url_filename), os.path.join(directory, email_filename))
#                     break

#                 self.driver.get(next_url)
#         finally:
#             self.driver.quit()


# if __name__ == "__main__":
#     parser = argparse.ArgumentParser(description="Scrape article links and author details.")
#     parser.add_argument("keyword", type=str, help="Keyword for the search query.")
#     parser.add_argument("start_year", type=str, help="Start date in MM/DD/YYYY format.")
#     parser.add_argument("end_year", type=str, help="End date in MM/DD/YYYY format.")
#     args = parser.parse_args()

#     query_params = {
#         "q": args.keyword,
#         "f_ContentType": "Journal Article",
#         "f_ContentSubTypeDisplayName": "Research ArticleANDReview ArticleANDOtherANDAbstract",
#         "fl_SiteID": "191",
#         "rg_ArticleDate": f"{args.start_year} TO {args.end_year}",
#         "rg_AllPublicationDates": f"{args.start_year} TO {args.end_year}",
#         "rg_VersionDate": f"{args.start_year} TO {args.end_year}",
#         "dateFilterType": "range",
#         "noDateTypes": "true"
#     }
#     base_url = "https://academic.oup.com/search-results"
#     search_url = f"{base_url}?{urlencode(query_params)}"

#     scraper = ArticleScraper()
#     scraper.run(search_url, args.keyword, args.start_year, args.end_year)

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

import os, time, sys
import csv
import math
import logging
import argparse



from webdriver_manager.chrome import ChromeDriverManager

from urllib.parse import urlencode, urljoin
from fuzzywuzzy import fuzz, process
import undetected_chromedriver as uc
import tempfile
import subprocess, random


class OxfordScraper:
    def __init__(self,keyword, start_year, end_year, driver_path):
        self.options = Options()
        
        self.options.add_argument("--disable-gpu")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--window-size=1920,1080")
        #self.options.add_argument("--force-device-scale-factor=1")
        self.options.add_argument("--disable-notifications")
        self.options.add_argument("--disable-background-timer-throttling")
        self.options.add_argument("--disable-backgrounding-occluded-windows")
        self.options.add_argument("--disable-renderer-backgrounding")
        self.uc_temp_dir = tempfile.mkdtemp(prefix="Cambridge_")
        self.driver = uc.Chrome(
                options=self.options,
                driver_executable_path=driver_path,
                version_main=None,  # Auto-detect Chrome version
                use_subprocess=False  # Critical for multiprocessing
            )
        self.wait = WebDriverWait(self.driver, 20)
        self.directory = keyword.replace(" ","-")
        self.keyword = keyword
        self.start_year = start_year
        self.end_year = end_year
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

    def detect_and_handle_captcha(self):
        """Detect and dismiss CAPTCHA if present."""
        if self.driver.current_url.startswith('https://academic.oup.com/crawlprevention/governor'):
            self.logger.warning("Oxford ==> CAPTCHA detected!")
            try:
                
                self.ChangeVPN()

                # captcha_element = self.wait.until(
                #     EC.presence_of_element_located((By.CSS_SELECTOR, 'iframe[title="reCAPTCHA"]'))
                # )
                # if captcha_element:
                #     self.logger.warning("Oxford ==> CAPTCHA detected!")
                #     try:
                #         #verify_button = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Verify')]")
                #         # Locate the reCAPTCHA checkbox using its ID

                #         captcha_element.click()
                #         # Add a new class using JavaScript
                #         #self.driver.execute_script("arguments[0].classList.add('recaptcha-checkbox-checked')", captcha_element)
                        
                #         print("Class added successfully!")
                #         time.sleep(5)
                #         self.driver.implicitly_wait(5)
                #         form_button = self.driver.find_element(By.CSS_SELECTOR, 'form#captchaForm div button#btnSubmit')
                #         form_button.click()
                #         self.logger.info("Oxford ==> Clicked 'Verify' button on CAPTCHA.")
                #         time.sleep(5)
                #     except Exception:
                #         self.logger.warning("Oxford ==> No 'Verify' button found. Manual intervention may be required.")
            except Exception:
                self.logger.info("Oxford ==> Unable to change location, trying again ...")
                self.ChangeVPN()

        else:
            pass
    
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

    def accept_cookies(self):
        """Accept cookies if the cookie banner is present."""
        try:
            # Try multiple possible selectors
            selectors = [
                "button#onetrust-accept-btn-handler",
                "button[id='onetrust-accept-btn-handler']",
                "div#onetrust-button-group button:nth-child(2)"
            ]
            
            for selector in selectors:
                try:
                    accept_button = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    accept_button.click()
                    self.logger.info(f"Oxford ==> Accepted cookies using selector: {selector}")
                    time.sleep(1)  # Brief pause to ensure action completes
                    return
                except Exception:
                    continue
            
            self.logger.info("Oxford ==> Could not find cookie accept button with any selector.")
            
        except Exception as e:
            self.logger.info(f"Oxford ==> Cookie banner handling failed: {e}")
            
    def get_total_pages(self):
        """Retrieve the total number of pages from the search results."""
        try:
            stats_element = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.sr-statistics.at-sr-statistics"))
            )
            total_results_text = stats_element.text.split()[2].replace(",", "")
            total_results = int(total_results_text)
            total_pages = math.ceil(total_results / 20)
            self.logger.info(f"Oxford ==> Total results: {total_results}, Total pages: {total_pages}")
            return total_pages
        except Exception as e:
            self.logger.error(f"Oxford ==> Failed to get total pages: {e}")
            return 0

    def extract_links(self):
        """Extract all article links from the current page."""
        links = []
        try:
            articles = self.wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.sr-list.al-article-box.al-normal.clearfix"))
            )
            for article in articles:
                try:
                    link_element = article.find_element(By.CSS_SELECTOR, "a.article-link.at-sr-article-title-link")
                    link = link_element.get_attribute("href")
                    links.append(link)
                except Exception as e:
                    self.logger.warning(f"Oxford ==> Failed to extract a link: {e}")
            self.logger.info(f"Oxford ==> Extracted {len(links)} links from the current page.")
        except Exception as e:
            self.logger.error(f"Oxford ==> Error extracting links: {e}")
        return links

    def get_next_url(self):
        """Get the URL for the next page if available."""
        try:
            next_button = self.driver.find_element(By.CSS_SELECTOR, "a.sr-nav-next.al-nav-next")
            next_url_params = next_button.get_attribute("data-url")
            current_url = self.driver.current_url
            base_url = current_url.split("?")[0]
            next_url = urljoin(base_url, "?" + next_url_params)
            self.logger.info(f"Oxford ==> Next page URL: {next_url}")
            return next_url
        except Exception:
            self.logger.info("Oxford ==> No 'Next' button found. Pagination ended.")
            return None

    def save_to_csv(self, data, directory, filename, header=None):
        """Save data to a CSV file."""
        try:
            os.makedirs(directory, exist_ok=True)
            filepath = os.path.join(directory, filename)
            with open(filepath, mode="a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                if os.path.getsize(filepath) == 0 and header:  # Write header only if file is empty
                    writer.writerow(header)
                writer.writerows(data)
            self.logger.info(f"Oxford ==> Saved data to {filepath}.")
        except Exception as e:
            self.logger.error(f"Oxford ==> Failed to save data to CSV: {e}")

    def scrape_author_emails(self, input_csv, output_csv):
        """Extract authors and emails from article pages."""
        try:
            with open(input_csv, "r", encoding="utf-8") as file:
                reader = csv.reader(file)
                next(reader)  # Skip header row
                urls = [row[0] for row in reader]

            for url in urls:
                self.driver.get(url)

                #Check if the current URL starts with the required prefix
                current_url = self.driver.current_url
                if not current_url.startswith("https://academic.oup.com/"):
                    self.logger.info(f"Oxford ==> Skipping URL {current_url} as it does not start with the required prefix.")
                    continue
                try:
                    self.accept_cookies()
                except Exception as e:
                    self.logger.info(f"Oxford ==> Cookie acceptance failed on {url}: {e}")
                author_names = []
                emails = []

                try:
                    # cookie_element = self.driver.find_element(By.ID, "cookie-consent-banner")
                    # if cookie_element:
                    #     cookie_element.click()
                    #     time.sleep()
                    # else:
                    #     self.accept_cookies()
                    # Click "Show More" if the button is available
                    try:
                        show_more_button = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "a#show-meta-authors"))
                        )
                        show_more_button.click()
                        self.logger.info(f"'Oxford ==> Show More' clicked on {url}")
                                            
                    except Exception:
                        self.logger.info(f"Oxford ==> No 'Show More' button found on {url}. Proceeding with author link search.")

                    # Iterate through author links and extract emails
                    author_links = self.driver.find_elements(By.CSS_SELECTOR, "span.al-author-name-more a.js-linked-name-trigger")
                    for link in author_links:
                        try:
                            author_name = link.text.strip()
                            author_names.append(author_name)  # Collect author names
                            link.click()
                            #self.driver.implicitly_wait(2)
                            self.logger.info(f"Oxford ==> Author link clicked for {author_name} on {url}")

                            # Extract emails from the popup
                            popup_content = self.wait.until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "span.al-author-info-wrap.open"))
                            )

                            email_elements = popup_content.find_elements(By.CSS_SELECTOR, "a[href^='mailto']")
                            popup_emails = [email.get_attribute("href").replace("mailto:", "") for email in email_elements]
                            emails.extend(popup_emails)

                            # Match emails with author names if multiple emails are found
                            for email in popup_emails:
                                best_match, score = process.extractOne(email.split("@")[0], author_names, scorer=fuzz.ratio)
                                self.save_to_csv(
                                    [[url, author_name, email, best_match, score]],
                                    os.path.dirname(output_csv),
                                    os.path.basename(output_csv),
                                    header=["url", "author", "email", "best_match", "match_score"]
                                )
                                self.logger.info(f"Oxford ==> Matched {email} with {best_match} (score: {score}).")
                        except Exception as e:
                            self.logger.warning(f"Oxford ==> Failed to process author link: {e}")

                    # Fallback: Check "Author Notes"
                    try:
                        author_notes = self.driver.find_element(By.CSS_SELECTOR, "a.js-linked-footnotes")
                        author_notes.click()

                        self.logger.info(f"Oxford ==> Author Notes clicked on {url}")

                        # Extract author name and emails from the Author Notes popup
                        popup_contents = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_all_elements_located(
                                (By.CSS_SELECTOR, "p.footnote-compatibility")
                            )
                        )
                        if popup_contents:
                            for popup in popup_contents:

                                    email_elements = popup.find_elements(By.CSS_SELECTOR, "a[href^='mailto']")
                                    note_emails = [email.get_attribute("href").replace("mailto:", "") for email in email_elements]
                                    for email in note_emails:
                                        best_match, score = process.extractOne(email.split("@")[0], author_names, scorer=fuzz.ratio)
                                        self.save_to_csv(
                                            [[url, None, email, best_match, score]],
                                            os.path.dirname(output_csv),
                                            os.path.basename(output_csv),
                                            header=["url", "author", "email", "best_match", "match_score"]
                                        )
                                        self.logger.info(f"Oxford ==> Fallback: Matched {email} with {best_match} (score: {score}).")
                    except Exception:
                        self.logger.info(f"Oxford ==> No emails found in Author Notes for {url}.")

                except Exception as e:
                    self.logger.error(f"Oxford ==> Error while processing {url}: {e}")

        except Exception as e:
            self.logger.error(f"Oxford ==> Failed to scrape author emails: {e}")

    def run(self):
        """Run the scraper for the given search URL."""
        
        try:
            query_params = {
                "q": self.keyword,
                "f_ContentType": "Journal Article",
                "f_ContentSubTypeDisplayName": "Research ArticleANDReview ArticleANDOtherANDAbstract",
                "fl_SiteID": "191",
                "rg_ArticleDate": f"{self.start_year} TO {self.end_year}",
                "rg_AllPublicationDates": f"{self.start_year} TO {self.end_year}",
                "rg_VersionDate": f"{self.start_year} TO {self.end_year}",
                "dateFilterType": "range",
                "noDateTypes": "true"
            }
            base_url = f"https://academic.oup.com/search-results"
            search_url = f"{base_url}?{urlencode(query_params)}"

            self.driver.get(base_url)
            #self.detect_and_handle_captcha()
            time.sleep(60)
            self.accept_cookies()
            self.driver.get(search_url)

            url_filename = f"Oxford_{self.directory}_{self.start_year.replace('/', '-')}_to_{self.end_year.replace('/', '-')}_urls.csv"
            email_filename = f"Oxford_{self.directory}_{self.start_year.replace('/', '-')}_to_{self.end_year.replace('/', '-')}_authors_emails.csv"

            total_pages = self.get_total_pages()

            all_links = []  # Store links instead of saving per page

            for page_number in range(total_pages):
                links = self.extract_links()
                all_links.extend(links)  # Append to list instead of saving each time

                next_url = self.get_next_url()
                if next_url:
                    self.driver.get(next_url)
                else:
                    print("Oxford ==> No more pages to navigate.")

            # 🔹 Save all extracted links at once
            self.save_to_csv([[link] for link in all_links], self.directory, url_filename, header=["Article_URL"])

            # 🔹 Extract author emails AFTER all links are processed
            self.scrape_author_emails(
                os.path.join(self.directory, url_filename),
                os.path.join(self.directory, email_filename)
            )

        except Exception as e:
            print(f"Error encountered: {e}")

        finally:
            self.driver.quit()


# if __name__ == "__main__":
#     parser = argparse.ArgumentParser(description="Scrape article links and author details.")
#     parser.add_argument("--keyword", type=str, help="Keyword for the search query.")
#     parser.add_argument("--start_year", type=str, help="Start date in MM/DD/YYYY format.")
#     parser.add_argument("--end_year", type=str, help="End date in MM/DD/YYYY format.")
#     args = parser.parse_args()
#     # Set a global cache path for WebDriverManager
#     os.environ["WDM_CACHE_PATH"] = "C:/shared_drivers"  # Custom shared directory

# #   Install ChromeDriver once and get its path
#     driver_path = ChromeDriverManager().install()
    
#     scraper = OxfordScraper(args.keyword, args.start_year, args.end_year, driver_path)
#     # scraper.run()

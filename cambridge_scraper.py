# # import csv
# # import re
# # import time
# # import logging
# # from selenium import webdriver
# # 
# # 
# # 
# # from webdriver_manager.chrome import ChromeDriverManager
# # from fuzzywuzzy import process, fuzz
# # import argparse
# # 

# # class CambridgeScraper:
# #     def __init__(self, keyword, start_year, end_year):
# #         # Initialize parameters
# #         self.keyword = keyword
# #         self.start_year = start_year
# #         self.end_year = end_year
# #         self.base_url = (
# #             f"https://www.cambridge.org/core/search?q={keyword}"
# #             f"&aggs%5BproductTypes%5D%5Bfilters%5D=JOURNAL_ARTICLE"
# #             f"&filters%5BdateYearRange%5D%5Bfrom%5D={start_year}"
# #             f"&filters%5BdateYearRange%5D%5Bto%5D={end_year}"
# #         )

# #         # Configure logging
# #         logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
# #         self.logger = logging.getLogger(__name__)

# #         # Set up Selenium WebDriver
# #         self.options = Options()
# #         self.options.add_argument("--disable-gpu")
# #         self.options.add_argument("--no-sandbox")
# #         self.options.add_argument("--start-maximized")  # Start browser in maximized state
# #         self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=self.options)

# #     def scrape(self):
# #         url_file = f"{self.keyword}_{self.start_year}-{self.end_year}_urls.csv"
# #         authors_file = f"{self.keyword}_{self.start_year}-{self.end_year}_authors.csv"

# #         # Extract article links
# #         article_links = self.scrape_article_links()
# #         self.save_to_csv(url_file, [["URL"]] + [[url] for url in article_links])

# #         # Extract authors and emails
# #         author_data = []
# #         for article_url in article_links:
# #             authors = self.scrape_article(article_url, authors_file)
# #             author_data.extend(authors)

# #         # Save extracted authors data to CSV
# #         self.save_to_csv(authors_file, [["Name", "Email", "Article URL", "Match Score"]] + author_data)

# #         self.driver.quit()
# #         self.logger.info("Scraping completed.")

# #     def scrape_article_links(self):
# #         self.logger.info(f"Starting scrape for articles: {self.base_url}")
# #         self.driver.get(self.base_url)
# #         time.sleep(5)

# #         try:
# #             last_page_element = self.driver.find_element(By.CSS_SELECTOR, 'li a[aria-label="Last page"]')
# #             last_page_number = int(last_page_element.get_attribute("data-page-number"))
# #             self.logger.info(f"Found last page number: {last_page_number}")
# #         except Exception as e:
# #             self.logger.error(f"Error retrieving last page number: {e}")
# #             return []

# #         article_links = []
# #         for page_num in range(1, last_page_number + 1):
# #             page_url = (
# #                 f"https://www.cambridge.org/core/search?pageNum={page_num}"
# #                 f"&q={self.keyword}"
# #                 f"&aggs%5BproductTypes%5D%5Bfilters%5D=JOURNAL_ARTICLE"
# #                 f"&filters%5BdateYearRange%5D%5Bfrom%5D={self.start_year}"
# #                 f"&filters%5BdateYearRange%5D%5Bto%5D={self.end_year}"
# #             )
# #             self.logger.info(f"Processing page {page_num}: {page_url}")
# #             self.driver.get(page_url)
# #             time.sleep(5)

# #             links = [a.get_attribute("href") for a in self.driver.find_elements(By.CSS_SELECTOR, "li.title a")]
# #             article_links.extend(links)

# #         self.logger.info(f"Total articles found: {len(article_links)}")
# #         return article_links

# #     def scrape_article(self, article_url, csv_file):
# #         self.logger.info(f"Scraping article: {article_url}")
# #         self.driver.get(article_url)
# #         time.sleep(5)

# #         authors = []
# #         emails = []
# #         match_scores = []
# #         extracted_data = []

# #         try:
# #             # Locate and click the "Show author details" button
# #             try:
# #                 show_author_details_link = self.driver.find_element(By.XPATH, "//a[@aria-controls='authors-details']")
# #                 actions = ActionChains(self.driver)
# #                 actions.move_to_element(show_author_details_link).perform()
# #                 time.sleep(2)
# #                 show_author_details_link.click()
# #                 self.logger.info("Clicked 'Show author details' link.")
# #                 time.sleep(2)
# #             except Exception:
# #                 self.logger.warning("Show author details link not found. Attempting alternative scraping methods.")

# #             # Extract all author elements
# #             author_elements = self.driver.find_elements(By.CSS_SELECTOR, "dt.title")
# #             email_container = self.driver.find_elements(By.CSS_SELECTOR, "div.corresp")

# #             # Extract emails from `div.corresp`
# #             all_emails = []
# #             if email_container:
# #                 for container in email_container:
# #                     email_text = container.text.strip()
# #                     emails_found = re.findall(r'[\w\.-]+@[\w\.-]+', email_text)
# #                     all_emails.extend(emails_found)

# #             # Process each author element
# #             for author_element in author_elements:
# #                 author_name = author_element.text.strip()

# #                 # Skip standalone "*" author names
# #                 if author_name == "*":
# #                     continue

# #                 # Handle authors ending with "*"
# #                 if author_name.endswith("*"):
# #                     best_email = None
# #                     best_match_score = 0

# #                     # Use fuzzy matching to find the best email for the author
# #                     if all_emails:
# #                         best_match = process.extractOne(author_name, all_emails, scorer=fuzz.token_sort_ratio)
# #                         if best_match:
# #                             best_email, best_match_score = best_match

# #                     # Append the result if email is found
# #                     if best_email:
# #                         authors.append(author_name)
# #                         emails.append(best_email)
# #                         match_scores.append(best_match_score)
# #                         extracted_data.append([author_name, best_email, article_url, best_match_score])

# #                 # Handle authors without "*"
# #                 else:
# #                     try:
# #                         # Look for email in the sibling `dd` element's text
# #                         dd_element = author_element.find_element(By.XPATH, "following-sibling::dd")
# #                         dd_text = dd_element.text
# #                         email_match = re.search(r"(?:Email|email):\s*([\w\.-]+@[\w\.-]+)", dd_text)
# #                         if email_match:
# #                             email = email_match.group(1)
# #                             authors.append(author_name)
# #                             emails.append(email)
# #                             match_scores.append("N/A")  # No match score for direct extraction
# #                             extracted_data.append([author_name, email, article_url, "N/A"])
# #                     except Exception:
# #                         self.logger.warning(f"Could not find email for author: {author_name}")

# #             # Fallback extraction for alternative HTML structure
# #             author_rows = self.driver.find_elements(By.CSS_SELECTOR, "div.row.author")
# #             for row in author_rows:
# #                 try:
# #                     # Extract author name
# #                     author_name = row.find_element(By.CSS_SELECTOR, "dt.title").text.strip()
# #                     if author_name == "*" or not author_name:
# #                         continue

# #                     # Extract email from the `dd` text
# #                     dd_text = row.find_element(By.CSS_SELECTOR, "dd.col.content").text.strip()
# #                     email_match = re.search(r"(?:Email|E-mail):\s*([\w\.-]+@[\w\.-]+)", dd_text, re.IGNORECASE)
# #                     if email_match:
# #                         email = email_match.group(1)
# #                         authors.append(author_name)
# #                         emails.append(email)
# #                         match_scores.append("N/A")  # No match score for direct extraction
# #                         extracted_data.append([author_name, email, article_url, "N/A"])

# #                     # Attempt to extract multiple emails from the text using regex and fuzzy matching
# #                     email_match = re.findall(r"[\w\.-]+@[\w\.-]+", dd_text)
# #                     if email_match:
# #                         for email in email_match:
# #                             best_match = process.extractOne(author_name, email_match, scorer=fuzz.token_sort_ratio)
# #                             if best_match:
# #                                 authors.append(author_name)
# #                                 emails.append(best_match[0])
# #                                 match_scores.append(best_match[1])
# #                                 extracted_data.append([author_name, best_match[0], article_url, best_match[1]])

# #                 except Exception as e:
# #                     self.logger.warning(f"Error processing row structure for author. Error: {e}")

# #             # Save extracted data to CSV row by row
# #             self.save_to_csv(csv_file, extracted_data)

# #         except Exception as e:
# #             self.logger.error(f"Error processing article {article_url}: {e}")

# #         # Log extracted data
# #         for author, email, match_score in zip(authors, emails, match_scores):
# #             self.logger.info(f"Extracted Author: {author}, Email: {email}, Match Score: {match_score}")

# #         return extracted_data

# #     def save_to_csv(self, filename, data):
# #         try:
# #             # Append data to CSV file, don't overwrite
# #             with open(filename, mode="a", newline="", encoding="utf-8") as file:
# #                 writer = csv.writer(file)
# #                 writer.writerows(data)
# #             self.logger.info(f"Saved data to {filename}")
# #         except Exception as e:
# #             self.logger.error(f"Failed to save data to CSV: {e}")


# # if __name__ == "__main__":
# #     # Parse command-line arguments
# #     parser = argparse.ArgumentParser(description="Cambridge Author Scraper")
# #     parser.add_argument("--keyword", required=True, help="Keyword to search for")
# #     parser.add_argument("--start_year", required=True, type=int, help="Start year for the search")
# #     parser.add_argument("--end_year", required=True, type=int, help="End year for the search")

# #     args = parser.parse_args()

# #     # Instantiate and start the scraper
# #     scraper = CambridgeScraper(args.keyword, args.start_year, args.end_year)
# #     scraper.scrape()


# import os, sys
# import csv
# import re
# import time
# import logging
# from selenium import webdriver
# 
# 
# 
# from webdriver_manager.chrome import ChromeDriverManager
# from fuzzywuzzy import process, fuzz
# import argparse
# 
# import undetected_chromedriver as uc
# import tempfile
# 

# class CambridgeScraper:
#     def __init__(self, keyword, start_year, end_year,driver_path):
#         # Initialize parameters
        

#         # Configure logging
#         logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
#         self.logger = logging.getLogger(__name__)

#         # Set up Selenium WebDriver
#         self.options = Options()
#         self.options.add_argument('--headless')
#         self.options.add_argument("--disable-gpu")
#         self.options.add_argument("--no-sandbox")
#         self.options.add_argument("--window-size=1920,1080")
#         #options.add_argument("--force-device-scale-factor=1")
#         self.options.add_argument("--disable-notifications")
#         self.options.add_argument("--disable-background-timer-throttling")
#         self.options.add_argument("--disable-backgrounding-occluded-windows")
#         self.options.add_argument("--disable-renderer-backgrounding")  
#         self.uc_temp_dir = tempfile.mkdtemp(prefix="Cambridge_")
#         self.driver = uc.Chrome(
#                 options=self.options,
#                 driver_executable_path=driver_path,  # Shared driver path
#                 use_subprocess=False  # Critical for multiprocessing
#             )
#         self.wait = WebDriverWait(self.driver, 60)
#         self.directory = keyword.replace(" ","-")
#         self.keyword = keyword
#         self.start_year = start_year
#         self.end_year = end_year
#         self._setup_logger()  # Initialize logger for the subclass
#         self.driver.maximize_window()
#         self.run()

#     def _setup_logger(self):
#         """Configure the logger with both file and stdout handlers (UTF-8 safe)."""
#         self.logger = logging.getLogger(self.__class__.__name__)
#         self.logger.setLevel(logging.INFO)

#         log_dir = "logs"
#         os.makedirs(log_dir, exist_ok=True)
#         log_file = os.path.join(
#             log_dir, 
#             f"{self.__class__.__name__}-{self.directory}-{self.start_year.replace('/', '-')}-{self.end_year.replace('/', '-')}.log"
#         )

#         # Ensure sys.stdout supports UTF-8 for emoji printing
#         sys.stdout.reconfigure(encoding='utf-8')

#         # Remove existing handlers to avoid duplication
#         if self.logger.hasHandlers():
#             self.logger.handlers.clear()

#         # File handler (UTF-8 encoding)
#         file_handler = logging.FileHandler(log_file, encoding="utf-8")
#         file_handler.setLevel(logging.INFO)

#         # Stream handler for logging to stdout
#         stream_handler = logging.StreamHandler(sys.stdout)
#         stream_handler.setLevel(logging.INFO)

#         # Formatter for both handlers
#         formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
#         file_handler.setFormatter(formatter)
#         stream_handler.setFormatter(formatter)

#         self.logger.addHandler(file_handler)
#         self.logger.addHandler(stream_handler)

#     def run(self):
#         start_year = self.start_year.split("/")[-1]
#         end_year = self.end_year.split("/")[-1]
        
#         self.base_url = (
#             f"https://www.cambridge.org/core/search?q={self.keyword}"
#             f"&aggs%5BproductTypes%5D%5Bfilters%5D=JOURNAL_ARTICLE"
#             f"&filters%5BdateYearRange%5D%5Bfrom%5D={start_year}"
#             f"&filters%5BdateYearRange%5D%5Bto%5D={end_year}"
#         )
#         output_dir = self.keyword.replace(" ","-")
#         os.makedirs(output_dir, exist_ok=True)
        
#         url_file = f"Cambridge_{output_dir}_{self.start_year.replace("/","-")}-{self.end_year.replace("/","-")}_urls.csv"
#         authors_file = f"Cambridge_{output_dir}_{self.start_year.replace("/","-")}-{self.end_year.replace("/","-")}_authors.csv"

#         # Extract article links
#         article_links = self.scrape_article_links()

#         self.save_to_csv(data=[[url] for url in article_links], directory=output_dir, filename=url_file, header=["Article_URL"])

#         # Extract authors and emails
#         for article_url in article_links:
#             self.scrape_article(article_url, output_dir, authors_file)

#         self.driver.quit()
#         self.logger.info("Cambridge ==> Scraping completed.")

#     def scrape_article_links(self):
#         self.logger.info(f"Cambridge ==> Starting scrape for articles: {self.base_url}")
#         self.driver.get(self.base_url)
#         time.sleep(5)

#         try:
#             last_page_element = self.driver.find_element(By.CSS_SELECTOR, 'li a[aria-label="Last page"]')
#             last_page_number = int(last_page_element.get_attribute("data-page-number"))
#             self.logger.info(f"Cambridge ==> Found last page number: {last_page_number}")
#         except Exception as e:
#             self.logger.error(f"Cambridge ==> Error retrieving last page number: {e}")
#             return []

#         article_links = []
#         for page_num in range(1, last_page_number + 1):
#             page_url = (
#                 f"https://www.cambridge.org/core/search?pageNum={page_num}"
#                 f"&q={self.keyword}"
#                 f"&aggs%5BproductTypes%5D%5Bfilters%5D=JOURNAL_ARTICLE"
#                 f"&filters%5BdateYearRange%5D%5Bfrom%5D={self.start_year.split("/")[-1]}"
#                 f"&filters%5BdateYearRange%5D%5Bto%5D={self.end_year.split("/")[-1]}"
#             )
#             self.logger.info(f"Cambridge ==> Processing page {page_num}: {page_url}")
#             self.driver.get(page_url)
#             time.sleep(5)

#             links = [a.get_attribute("href") for a in self.driver.find_elements(By.CSS_SELECTOR, "li.title a")]
#             article_links.extend(links)
#             self.logger.info(f"Cambridge ==> Total articles extracted {len(article_links)} from page {page_num}.")
#         self.logger.info(f"Cambridge ==> Total articles found: {len(article_links)}")
#         return article_links

#     def scrape_article(self, article_url, directory, filename):
#         self.logger.info(f"Cambridge ==> Scraping article: {article_url}")
#         self.driver.get(article_url)
#         time.sleep(5)

#         extracted_data = []

#         try:
#             # Locate and click the "Show author details" button
#             try:
#                 show_author_details_link = self.driver.find_element(By.XPATH, "//a[@aria-controls='authors-details']")
#                 actions = ActionChains(self.driver)
#                 actions.move_to_element(show_author_details_link).perform()
#                 time.sleep(2)
#                 show_author_details_link.click()
#                 self.logger.info("Cambridge ==> Clicked 'Show author details' link.")
#                 time.sleep(2)
#             except Exception:
#                 self.logger.warning("Cambridge ==> Show author details link not found. Attempting alternative scraping methods.")

#             # Extract authors
#             author_elements = self.driver.find_elements(By.CSS_SELECTOR, "dt.title")
#             author_names = [element.text.strip() for element in author_elements if element.text.strip()]
#             author_names = [name for name in author_names if name not in ["*", "Type", "Information", "Copyright"]]

#             # Separate authors ending with "*"
#             starred_authors = [name for name in author_names if name.endswith("*")]
#             non_starred_authors = [name for name in author_names if not name.endswith("*")]

#             # Extract emails from `div.corresp`
#             email_container = self.driver.find_elements(By.CSS_SELECTOR, "div.corresp")
#             emails_from_corresp = []
#             if email_container:
#                 for container in email_container:
#                     email_text = container.text.strip()
#                     emails_found = re.findall(r'[\w\.-]+@[\w\.-]+', email_text)
#                     emails_from_corresp.extend(emails_found)
#             emails_from_corresp = list(set(emails_from_corresp))  # Deduplicate

#             # Match emails to starred authors
#             for author_name in starred_authors:
#                 best_email = None
#                 best_match_score = 0
#                 if emails_from_corresp:
#                     best_match = process.extractOne(author_name.strip("*"), emails_from_corresp, scorer=fuzz.token_sort_ratio)
#                     if best_match:
#                         best_email, best_match_score = best_match
#                 if best_email:
#                     extracted_data.append([article_url, author_name.strip("*"), best_email, best_match_score])

#             # Fallback method for non-starred authors
#             try:
#                 email_spans = self.driver.find_elements(By.CSS_SELECTOR, "span[data-v-2edb8da6] > span[data-v-2edb8da6]")
#                 fallback_emails = []
#                 for span in email_spans:
#                     span_text = span.text.strip()
#                     if "e-mail:" in span_text.lower() or "e-mails:" in span_text.lower():
#                         email_part = span_text.split(":")[1]  # Get text after 'e-mail:'
#                         emails = [email.strip(")") for email in email_part.split(",")]
#                         fallback_emails.extend(emails)
#                 fallback_emails = list(set(fallback_emails))  # Deduplicate

#                 for author_name in non_starred_authors:
#                     best_email = None
#                     best_match_score = 0
#                     if fallback_emails:
#                         # Extract the text before "@" for comparison
#                         emails_for_matching = {email.split("@")[0]: email for email in fallback_emails}
        
#                         best_match = process.extractOne(author_name, emails_for_matching.keys(), scorer=fuzz.token_sort_ratio)
#                         if best_match:
#                             best_email_local_part, best_match_score = best_match
#                             best_email = emails_for_matching[best_email_local_part]
#                     if best_email:
#                         extracted_data.append([article_url, author_name.strip("*"), best_email, best_match_score])
#             except Exception as e:
#                 self.logger.warning(f"Cambridge ==> No emails found in fallback method for {article_url}: {e}")

#             # Save extracted data to CSV
#             self.save_to_csv(data=extracted_data, directory=directory, filename=filename, header=["Article URL", "Name", "Email", "Match Score"])
#             self.logger.info(f"Cambridge ==> Extracted data: {extracted_data}")

#         except Exception as e:
#             self.logger.error(f"Cambridge ==> Error processing article {article_url}: {e}")


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
#             self.logger.info(f"Cambridge ==> Saved data to {filepath}.")
#         except Exception as e:
#             self.logger.error(f"Cambridge ==> Failed to save data to CSV: {e}")


# # if __name__ == "__main__":
# #     # Parse command-line arguments
# #     parser = argparse.ArgumentParser(description="Cambridge Author Scraper")
# #     parser.add_argument("--keyword", required=True, help="Keyword to search for")
# #     parser.add_argument("--start_year", required=True, type=str, help="Start year for the search")
# #     parser.add_argument("--end_year", required=True, type=str, help="End year for the search")

# #     args = parser.parse_args()
# #     # Set a global cache path for WebDriverManager
# #     os.environ["WDM_CACHE_PATH"] = "C:/shared_drivers"  # Custom shared directory

# # #   Install ChromeDriver once and get its path
# #     driver_path = ChromeDriverManager().install()


import os, sys
import csv
import re
import time
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from webdriver_manager.chrome import ChromeDriverManager
from fuzzywuzzy import process, fuzz
import argparse

import undetected_chromedriver as uc
import tempfile
from utils import sanitize_filename, safe_log_file_path


class CambridgeScraper:
    def __init__(self, keyword, start_year, end_year, driver_path):
        # Configure logging
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
        self.logger = logging.getLogger(__name__)

        # Set up Selenium WebDriver
        self.options = Options()
        self.options.add_argument("--disable-gpu")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--window-size=1920,1080")
        self.options.add_argument("--disable-notifications")
        self.options.add_argument("--disable-background-timer-throttling")
        self.options.add_argument("--disable-backgrounding-occluded-windows")
        self.options.add_argument("--disable-renderer-backgrounding")  
        self.uc_temp_dir = tempfile.mkdtemp(prefix="Cambridge_")
        self.driver = uc.Chrome(
            options=self.options,
            driver_executable_path=driver_path,
            version_main=None,  # Auto-detect Chrome version
            use_subprocess=False
        )
        self.wait = WebDriverWait(self.driver, 60)
        
        # Verify window is still open after initialization
        time.sleep(2)
        try:
            _ = self.driver.current_url
        except:
            print("Window closed during init, reinitializing...")
            self.driver = uc.Chrome(
                options=self.options,
                driver_executable_path=driver_path,
                version_main=None,
                use_subprocess=False
            )
            self.wait = WebDriverWait(self.driver, 60)
        
        self.directory = sanitize_filename(keyword)
        self.keyword = keyword
        self.start_year = start_year
        self.end_year = end_year
        self._setup_logger()
        self.driver.maximize_window()
        self.run()

    def _setup_logger(self):
        """Configure the logger with both file and stdout handlers (UTF-8 safe)."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)

        log_file = safe_log_file_path(self.__class__.__name__, self.directory, self.start_year, self.end_year)

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

    def run(self):
        start_year = self.start_year.split("/")[-1]
        end_year = self.end_year.split("/")[-1]
        
        self.base_url = (
            f"https://www.cambridge.org/core/search?q={self.keyword}"
            f"&aggs%5BproductTypes%5D%5Bfilters%5D=JOURNAL_ARTICLE"
            f"&filters%5BdateYearRange%5D%5Bfrom%5D={start_year}"
            f"&filters%5BdateYearRange%5D%5Bto%5D={end_year}"
        )
        output_dir = self.keyword.replace(" ", "-")
        os.makedirs(output_dir, exist_ok=True)
        
        url_file = f"Cambridge_{output_dir}_{self.start_year.replace('/', '-')}-{self.end_year.replace('/', '-')}_urls.csv"
        authors_file = f"Cambridge_{output_dir}_{self.start_year.replace('/', '-')}-{self.end_year.replace('/', '-')}_authors.csv"

        # Initialize CSV files with headers
        self.initialize_csv(output_dir, url_file, ["Article_URL"])
        self.initialize_csv(output_dir, authors_file, ["Article URL", "Name", "Email", "Match Score"])

        # Step 1: Extract all article links first
        self.logger.info("Cambridge ==> PHASE 1: Extracting article URLs from all pages...")
        self.scrape_article_links_streaming(output_dir, url_file)
        
        # Step 2: Read URLs from CSV and scrape authors
        self.logger.info("Cambridge ==> PHASE 2: Reading URLs and extracting author information...")
        self.scrape_authors_from_url_file(output_dir, url_file, authors_file)

        self.driver.quit()
        self.logger.info("Cambridge ==> Scraping completed.")

    def initialize_csv(self, directory, filename, header):
        """Initialize CSV file with header."""
        try:
            os.makedirs(directory, exist_ok=True)
            filepath = os.path.join(directory, filename)
            with open(filepath, mode="w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(header)
            self.logger.info(f"Cambridge ==> Initialized {filepath} with header.")
        except Exception as e:
            self.logger.error(f"Cambridge ==> Failed to initialize CSV: {e}")

    def write_to_csv(self, directory, filename, row):
        """Write a single row to CSV immediately."""
        try:
            filepath = os.path.join(directory, filename)
            with open(filepath, mode="a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(row)
        except Exception as e:
            self.logger.error(f"Cambridge ==> Failed to write to CSV: {e}")

    def accept_cookies(self):
        """Accept cookies if the cookie banner is present."""
        try:
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
                    self.logger.info(f"Cambridge ==> Accepted cookies using selector: {selector}")
                    # Brief wait for cookie acceptance to complete
                    WebDriverWait(self.driver, 3).until(
                        EC.invisibility_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    return
                except Exception:
                    continue
            
            self.logger.info("Cambridge ==> Could not find cookie accept button with any selector.")
            
        except Exception as e:
            self.logger.info(f"Cambridge ==> Cookie banner handling failed: {e}")

    def scrape_article_links_streaming(self, output_dir, url_file):
        """Scrape article links and write them immediately to CSV."""
        self.logger.info(f"Cambridge ==> Starting scrape for articles: {self.base_url}")
        self.driver.get(self.base_url)
        self.accept_cookies()
        
        try:
            last_page_element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'li a[aria-label="Last page"]'))
            )
            last_page_number = int(last_page_element.get_attribute("data-page-number"))
            self.logger.info(f"Cambridge ==> Found last page number: {last_page_number}")
        except Exception as e:
            self.logger.error(f"Cambridge ==> Error retrieving last page number: {e}")
            return

        total_articles = 0
        for page_num in range(1, last_page_number + 1):
            page_url = (
                f"https://www.cambridge.org/core/search?pageNum={page_num}"
                f"&q={self.keyword}"
                f"&aggs%5BproductTypes%5D%5Bfilters%5D=JOURNAL_ARTICLE"
                f"&filters%5BdateYearRange%5D%5Bfrom%5D={self.start_year.split('/')[-1]}"
                f"&filters%5BdateYearRange%5D%5Bto%5D={self.end_year.split('/')[-1]}"
            )
            self.logger.info(f"Cambridge ==> Processing page {page_num}: {page_url}")
            self.driver.get(page_url)
            
            # Wait for article links to be present
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li.title a"))
                )
            except Exception as e:
                self.logger.warning(f"Cambridge ==> No articles found on page {page_num}: {e}")
                continue
            
            # Extract hrefs immediately to avoid stale element reference
            link_elements = self.driver.find_elements(By.CSS_SELECTOR, "li.title a")
            article_urls = [elem.get_attribute("href") for elem in link_elements if elem.get_attribute("href")]
            
            # Write each URL immediately
            for article_url in article_urls:
                self.write_to_csv(output_dir, url_file, [article_url])
                total_articles += 1
                #self.logger.info(f"Cambridge ==> Written article URL #{total_articles}: {article_url}")
            
            self.logger.info(f"Cambridge ==> Completed page {page_num}, total articles so far: {total_articles}")
        
        self.logger.info(f"Cambridge ==> Total articles found: {total_articles}")

    def scrape_authors_from_url_file(self, output_dir, url_file, authors_file):
        """Read article URLs from CSV and scrape author information."""
        filepath = os.path.join(output_dir, url_file)
        
        if not os.path.exists(filepath):
            self.logger.error(f"Cambridge ==> URL file not found: {filepath}")
            return
        
        try:
            with open(filepath, mode="r", encoding="utf-8") as file:
                reader = csv.DictReader(file)
                article_count = 0
                for row in reader:
                    article_url = row.get("Article_URL", "").strip()
                    if article_url:
                        article_count += 1
                        self.logger.info(f"Cambridge ==> Processing article {article_count}: {article_url}")
                        self.scrape_article_streaming(article_url, output_dir, authors_file)
                
                self.logger.info(f"Cambridge ==> Completed processing {article_count} articles")
        except Exception as e:
            self.logger.error(f"Cambridge ==> Error reading URL file: {e}")


    def scrape_article_streaming(self, article_url, directory, filename):
        """Scrape article and write author data immediately to CSV."""
        self.logger.info(f"Cambridge ==> Scraping article: {article_url}")
        self.driver.get(article_url)

        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "dt.title, div.row.author"))
            )
        except Exception as e:
            self.logger.warning(f"Cambridge ==> Page content not loaded for {article_url}: {e}")
            return

        try:
            # Click "Show author details" if present
            try:
                show_author_details_link = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//a[@aria-controls='authors-details']"))
                )
                self.driver.execute_script("arguments[0].scrollIntoView(true);", show_author_details_link)
                WebDriverWait(self.driver, 2).until(EC.visibility_of(show_author_details_link))
                show_author_details_link.click()
                self.logger.info("Cambridge ==> Clicked 'Show author details' link.")
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div#authors-details"))
                )
            except Exception:
                self.logger.warning("Cambridge ==> Show author details link not found.")

            # Extract authors
            author_elements = self.driver.find_elements(By.CSS_SELECTOR, "dt.title")
            author_names = [el.text.strip() for el in author_elements if el.text.strip()]
            author_names = [n for n in author_names if n not in ["*", "Type", "Information", "Copyright"]]
            starred_authors = [n for n in author_names if n.endswith("*")]
            non_starred_authors = [n for n in author_names if not n.endswith("*")]

            # Extract emails from div.corresp
            emails_from_corresp = []
            for container in self.driver.find_elements(By.CSS_SELECTOR, "div.corresp"):
                emails_from_corresp.extend(re.findall(r'[\w\.-]+@[\w\.-]+', container.text.strip()))
            emails_from_corresp = list(set(emails_from_corresp))

            # Match starred authors to corresp emails
            for author_name in starred_authors:
                best_email = None
                best_match_score = 0
                if emails_from_corresp:
                    best_match = process.extractOne(author_name.strip("*"), emails_from_corresp, scorer=fuzz.token_sort_ratio)
                    if best_match:
                        best_email, best_match_score = best_match[0], best_match[1]
                if best_email:
                    self.write_to_csv(directory, filename, [article_url, author_name.strip("*"), best_email, best_match_score])
                    self.logger.info(f"Cambridge ==> Written: {author_name.strip('*')} - {best_email}")

            # Fallback for non-starred authors
            try:
                email_spans = self.driver.find_elements(By.CSS_SELECTOR, "span[data-v-2edb8da6] > span[data-v-2edb8da6]")
                fallback_emails = []
                for span in email_spans:
                    span_text = span.text.strip()
                    if "e-mail:" in span_text.lower() or "e-mails:" in span_text.lower():
                        email_part = span_text.split(":")[1]
                        fallback_emails.extend([e.strip(")") for e in email_part.split(",")])
                fallback_emails = list(set(fallback_emails))

                for author_name in non_starred_authors:
                    best_email = None
                    best_match_score = 0
                    if fallback_emails:
                        emails_for_matching = {e.split("@")[0]: e for e in fallback_emails}
                        best_match = process.extractOne(author_name, emails_for_matching.keys(), scorer=fuzz.token_sort_ratio)
                        if best_match:
                            best_email_local_part, best_match_score = best_match[0], best_match[1]
                            best_email = emails_for_matching[best_email_local_part]
                    if best_email:
                        self.write_to_csv(directory, filename, [article_url, author_name.strip("*"), best_email, best_match_score])
                        self.logger.info(f"Cambridge ==> Written: {author_name.strip('*')} - {best_email}")
            except Exception as e:
                self.logger.warning(f"Cambridge ==> Fallback email method failed for {article_url}: {e}")

        except Exception as e:
            self.logger.error(f"Cambridge ==> Error processing article {article_url}: {e}")


# if __name__ == "__main__":
#     parser = argparse.ArgumentParser(description="Cambridge Author Scraper")
#     parser.add_argument("--keyword", required=True, help="Keyword to search for")
#     parser.add_argument("--start_year", required=True, type=str, help="Start year for the search")
#     parser.add_argument("--end_year", required=True, type=str, help="End year for the search")

#     args = parser.parse_args()
#     os.environ["WDM_CACHE_PATH"] = "C:/shared_drivers"
#     driver_path = ChromeDriverManager().install()

#     scraper = CambridgeScraper(args.keyword, args.start_year, args.end_year, driver_path)
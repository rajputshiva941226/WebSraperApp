from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
#from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
import undetected_chromedriver as uc

import logging
import csv
from datetime import datetime, timedelta
import os, time, glob

class NCBIPMC(uc.Chrome):
    def __init__(self, options: Options=None, service:Service=None):
        self.options = Options()
        
        self.options.add_argument("--disable-lazy-loading")
        self.options.add_argument("--disable-print-preview")
        self.options.add_argument("--disable-stack-profiler")
        self.options.add_argument("--disable-background-networking")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("excludeSwitches=enable-automation")
        self.options.add_argument("--disable-infobars")
        self.options.add_argument("--disable-browser-side-navigation")
        self.options.add_argument("--disable-notifications")
        self.options.add_argument("--disable-blink-features=AutomationControlled")
        self.options.add_argument("--disable-popup-blocking")
        self.options.add_argument("--disable-crash-reporter")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--disable-logging")
        # self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

        super(NCBIPMC, self).__init__(options=self.options, service=service)
        self.maximize_window()
        self.wait = WebDriverWait(self, 10)
        # ✅ Force downloads into current working dir
        download_dir = os.path.abspath(os.getcwd())
        print("Download directory:", download_dir)

        # Use execute_cdp_cmd *after* Chrome is initialized
        self.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": download_dir,
            "eventsEnabled": True
        })
        
        logging.basicConfig(filename='ncbi_pmc.log', filemode='w', level=logging.DEBUG)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.quit()
        #return super().__exit__(exc_type, exc_val, exc_tb)
    
    def search_articles(self, query, s_year, s_month, s_day, e_year, e_month, e_day):
        # Prepare output file (query name with underscores)
        #filename = f"{query.replace(' ', '_')}.txt"
        #seen_links = set()

        self.get(f"https://pmc.ncbi.nlm.nih.gov/search/?term={query}")

        # Open date picker
        custom_date_range_button = self.wait.until(EC.element_to_be_clickable((By.ID, "datepicker-trigger")))
        custom_date_range_button.click()
        time.sleep(1)

        # Fill in start date
        start_year_input = self.wait.until(EC.presence_of_element_located((By.ID, "start-year")))
        start_year_input.clear()
        start_year_input.send_keys(str(s_year))

        start_month_input = Select(self.find_element(By.ID, "start-month"))
        start_month_input.select_by_value(str(s_month))

        start_day_input = self.find_element(By.ID, "start-day")
        start_day_input.clear()
        start_day_input.send_keys(str(s_day))

        # Fill in end date
        end_year_input = self.find_element(By.ID, "end-year")
        end_year_input.clear()
        end_year_input.send_keys(str(e_year))

        end_month_input = Select(self.find_element(By.ID, "end-month"))
        end_month_input.select_by_value(str(e_month))

        end_day_input = self.find_element(By.ID, "end-day")
        end_day_input.clear()
        end_day_input.send_keys(str(e_day))

        # Apply date range
        apply_button = self.find_element(By.CLASS_NAME, "custom-date-range-apply")
        apply_button.click()
        time.sleep(2)

        # Select "all results" per page
        save_button = self.find_element(By.XPATH, "//button[@aria-controls='export-save-modal']")
        save_button.click()
        time.sleep(2)

        results_per_page_select = Select(self.wait.until(EC.presence_of_element_located((By.ID, "results-selection"))))
        results_per_page_select.select_by_value("all-results")
        time.sleep(2)

        results_type_select = Select(self.wait.until(EC.presence_of_element_located((By.ID, "file-format"))))
        results_type_select.select_by_value("pmcid")
        time.sleep(1)

        download_button = self.find_element(By.XPATH, "//button[text()='Create file']")
        download_button.click()
        time.sleep(10)
        
        # Function to scrape & save links
        # def scrape_and_save():
        #     articles = self.find_elements_recursive(By.XPATH, "//a[@data-ga-category='result_click']")
        #     new_links = []
        #     for article in articles:
        #         href = article.get_attribute("href")
        #         if href and href not in seen_links:
        #             seen_links.add(href)
        #             new_links.append(href)
        #             print(article.text, href)

        #     # Append new links immediately to file
        #     if new_links:
        #         with open(filename, "a", encoding="utf-8") as f:
        #             for link in new_links:
        #                 f.write(link + "\n")

        # # Scrape first page
        # scrape_and_save()

        # # Paginate
        # try:
        #     pagination_next = self.wait.until(EC.presence_of_element_located(
        #         (By.XPATH, "//button[@data-ga-category='pagination' and @data-ga-label='show_more_results']")
        #     ))
        # except TimeoutException:
        #     pagination_next = None

        # while pagination_next and pagination_next.is_enabled():
        #     pagination_next.click()
        #     time.sleep(2)
        #     scrape_and_save()

        #     try:
        #         pagination_next = self.wait.until(EC.presence_of_element_located(
        #             (By.XPATH, "//button[@data-ga-category='pagination' and @data-ga-label='show_more_results']")
        #         ))
        #     except TimeoutException:
        #         break

        #print(f"✅ Saved {len(seen_links)} unique article links to {filename}")

    
# if __name__=="__main__":
    
#     keyword = input("Enter search keyword: ")

#     # Take user input
#     start_date_str = input("Enter start date (dd/mm/yyyy): ")
#     end_date_str = input("Enter end date (dd/mm/yyyy): ")

#     # Convert to datetime objects
#     start_date = datetime.strptime(start_date_str, "%d/%m/%Y")
#     end_date = datetime.strptime(end_date_str, "%d/%m/%Y")

#     # Generate weekly ranges
#     current = start_date
#     ranges = []
#     query = keyword.replace(" ", "_")
#     #download_dir = os.path.mkdir(os.path.join(os.getcwd(), query), exist_ok=True)
#     download_dir = os.path.join(os.getcwd(), query)
#     os.makedirs(download_dir, exist_ok=True)
#     # Wait for file to finish downloading
#     #time.sleep(10)  # or poll until no .crdownload exists

#     while current <= end_date:
#         week_end = current + timedelta(days=6)  # 7-day window
#         if week_end > end_date:
#             week_end = end_date
        
#         # Extract components as integers, then convert to str (no leading zeros)
#         start_year, start_month, start_day = str(current.year), str(current.month), str(current.day)
#         end_year, end_month, end_day = str(week_end.year), str(week_end.month), str(week_end.day)

#         ranges.append({
#             "start_year": start_year,
#             "start_month": start_month,
#             "start_day": start_day,
#             "end_year": end_year,
#             "end_month": end_month,
#             "end_day": end_day
#         })

#         current = week_end + timedelta(days=1)

#     # Print result
#     with NCBIPMC() as pmc:
#         for r in ranges:
#             print(r)
#             #desired_name = query.replace(" ", "_") + f'{r["start_year"]}-{r["start_month"]}-{r["start_day"]}-{r["end_year"]}-{r["end_month"]}-{r["end_day"]}.txt'
#             desired_name = query.replace(" ", "_") + ".txt"
#             pmc.search_articles(keyword, r["start_year"], r["start_month"], r["start_day"], r["end_year"], r["end_month"], r["end_day"])
#             latest_file = max(glob.glob(os.path.join(os.getcwd(),"*")), key=os.path.getctime)
#             new_path = os.path.join(download_dir, desired_name)
#             os.rename(latest_file, new_path)
            


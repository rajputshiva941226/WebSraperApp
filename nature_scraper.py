"""
Nature.com Article Scraper - Improved Email Extraction
With "Show authors" button handling and better popup detection
"""

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

import csv
import time
import os
import sys
import glob
from datetime import datetime
from selenium import webdriver



from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager



from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException


class NatureScraper:
    def __init__(self):
        self.driver = None
        self.output_dir = None
        self.cookies_accepted = False
        
        # Article types and subjects to iterate through
        self.article_types = [
            'research',
            'reviews', 
            'protocols',
            'comments-and-opinion',
            'amendments-and-corrections',
            'research-highlights',
            'correspondence'
        ]
        
        self.subjects = [
            'biochemistry',
            'molecular-biology',
            'cell-biology',
            'biological-techniques',
            'biophysics',
            'biomarkers',
            'biotechnology',
            'drug-discovery',
            'diseases',
            'developing-world',
            'computational-biology-and-bioinformatics',
            'neuroscience',
            'structural-biology',
            'systems-biology',
            'cancer',
            'genetics',
            'immunology',
            'medical-research',
            'scientific-community',
            'social-sciences'
        ]
        
    def setup_driver(self):
        """Setup Chrome WebDriver with optimized settings"""
        chrome_options = Options()
        chrome_options.add_argument('--start-maximized')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        try:
            print("Initializing Chrome WebDriver...")
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.maximize_window()
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            print("✓ Chrome WebDriver initialized successfully\n")
        except Exception as e:
            print(f"✗ Error initializing WebDriver: {e}")
            sys.exit(1)
    
    def accept_cookies(self):
        """Accept cookies using the specific cookie banner structure"""
        if self.cookies_accepted:
            return
            
        try:
            cookie_button = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-cc-action="accept"]'))
            )
            cookie_button.click()
            print("✓ Cookies accepted\n")
            self.cookies_accepted = True
            time.sleep(2)
        except TimeoutException:
            print("ℹ No cookie banner found or already accepted\n")
            self.cookies_accepted = True
        except Exception as e:
            print(f"ℹ Cookie handling: {e}\n")
            self.cookies_accepted = True
    
    def create_output_directory(self, keyword, start_year, end_year):
        """Create output directory for results"""
        dir_name = f"{keyword.replace(' ', '_')}_{start_year}-{end_year}"
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
        self.output_dir = dir_name
        print(f"✓ Output directory: {os.path.abspath(dir_name)}\n")
        return dir_name
    
    def get_total_results(self, url):
        """Get total number of results from search page"""
        try:
            self.driver.get(url)
            
            if not self.cookies_accepted:
                self.accept_cookies()
            
            time.sleep(2)
            
            results_element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-test="results-data"] span:last-child'))
            )
            
            results_text = results_element.text.strip()
            total = int(results_text.split()[0].replace(',', ''))
            
            return total
            
        except Exception as e:
            return 0
    
    def scrape_links_from_url(self, base_url, links_file):
        """Scrape article links from a search URL and return list of links"""
        total_results = self.get_total_results(base_url + "&page=1")
        
        if total_results == 0:
            return []
        
        # Calculate pages - max 20 pages (1000 results / 50 per page)
        total_pages = min((total_results // 50) + 1, 20)
        
        print(f"      {total_results} results ({total_pages} pages)")
        
        links = []
        
        # Open CSV file in append mode
        with open(links_file, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            
            for page in range(1, total_pages + 1):
                url = base_url + f"&page={page}"
                
                try:
                    self.driver.get(url)
                    time.sleep(1.5)
                    
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, '.app-article-list-row__item'))
                    )
                    
                    article_elements = self.driver.find_elements(By.CSS_SELECTOR, '.app-article-list-row__item article')
                    
                    for article in article_elements:
                        try:
                            title_element = article.find_element(By.CSS_SELECTOR, '.c-card__title a')
                            link = title_element.get_attribute('href')
                            
                            if link:
                                writer.writerow([link])
                                csvfile.flush()
                                links.append(link)
                                
                        except Exception as e:
                            continue
                    
                    print(f"\r        Page {page}/{total_pages} - Articles: {len(links)}", end='')
                    time.sleep(1)
                    
                except Exception as e:
                    continue
            
            print()
            
        return links
    
    def extract_author_emails(self, article_url):
        """Extract author emails by clicking on author names (robust version with improved popup detection)."""
        import re
        
        
        
        from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException

        try:
            self.driver.get(article_url)
            time.sleep(2)

            # Accept cookies if needed
            if not getattr(self, "cookies_accepted", False):
                self.accept_cookies()
            time.sleep(0.5)

            authors_data = []

            # Wait for authors list
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[data-test="authors-list"]'))
                )
            except TimeoutException:
                print("        ✗ Authors list not found.")
                return []

            # === STEP 1: Try clicking "Show authors" button if it exists ===
            try:
                show_btn = WebDriverWait(self.driver, 3).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'button.c-article-author-list__button'))
                )
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", show_btn)
                time.sleep(1)

                # Retry clicking a few times
                for attempt in range(3):
                    try:
                        WebDriverWait(self.driver, 2).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button.c-article-author-list__button'))
                        )
                        show_btn.click()
                        print("        ✓ Clicked 'Show authors' button")
                        break
                    except (ElementClickInterceptedException, TimeoutException):
                        try:
                            self.driver.execute_script("arguments[0].click();", show_btn)
                            print("        ✓ Clicked 'Show authors' button (via JS)")
                            break
                        except Exception:
                            time.sleep(1)
                time.sleep(2)

            except TimeoutException:
                print("        ℹ 'Show authors' button not found - all authors visible")
            except Exception as e:
                print(f"        ⚠ Error handling 'Show authors' button: {e}")

            # === STEP 2: Find all authors ===
            author_links = self.driver.find_elements(By.CSS_SELECTOR, '[data-test="authors-list"] a[data-test="author-name"]')
            print(f"        Found {len(author_links)} author(s)")

            # === STEP 3: Process each author ===
            for idx in range(len(author_links)):
                try:
                    author_links = self.driver.find_elements(By.CSS_SELECTOR, '[data-test="authors-list"] a[data-test="author-name"]')
                    if idx >= len(author_links):
                        break

                    author_link = author_links[idx]
                    author_name = author_link.text.strip().replace('✉', '').strip()
                    safe_name = re.sub(r'[^a-zA-Z0-9]', '-', author_name)  # normalize for matching popup id

                    # Skip if no mail icon
                    try:
                        author_link.find_element(By.CSS_SELECTOR, 'svg use[href*="mail"], svg use[*|href*="mail"]')
                        has_email = True
                    except NoSuchElementException:
                        has_email = False

                    if not has_email:
                        print(f"          Author {idx+1}: {author_name[:30]} - No email icon (skipped)")
                        continue

                    # Click author to open popup
                    email = ''
                    try:
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", author_link)
                        time.sleep(0.5)
                        author_link.click()
                        time.sleep(1)

                        # Wait for popup (new method using partial id with author name)
                        popup_selector = f"div[id*='popup-auth-{safe_name[:5]}']"  # use first 20 chars of safe_name
                        try:
                            popup = WebDriverWait(self.driver, 5).until(
                                EC.visibility_of_element_located((By.CSS_SELECTOR, popup_selector))
                            )
                        except TimeoutException:
                            popup = WebDriverWait(self.driver, 3).until(
                                EC.visibility_of_element_located((By.CSS_SELECTOR, ".app-researcher-popup"))
                            )

                        # Wait for email inside popup
                        try:
                            email_link = WebDriverWait(self.driver, 3).until(
                                EC.visibility_of_element_located((By.CSS_SELECTOR, f"{popup_selector} a[href^='mailto:']"))
                            )
                            email = email_link.get_attribute('href').replace('mailto:', '').strip()
                        except TimeoutException:
                            print(f"          Author {idx+1}: {author_name[:30]} - Popup opened, email not found (timeout)")

                        if email:
                            print(f"          Author {idx+1}: {author_name[:30]} - ✓ Email: {email}")
                            authors_data.append({'name': author_name, 'email': email})
                        else:
                            print(f"          Author {idx+1}: {author_name[:30]} - Empty email (skipped)")

                    except Exception as e:
                        print(f"          Author {idx+1}: {author_name[:30]} - Popup or email not found ({str(e)[:40]})")

                    # Close popup
                    try:
                        close_btn = WebDriverWait(self.driver, 2).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button.c-popup__close'))
                        )
                        close_btn.click()
                        WebDriverWait(self.driver, 3).until(
                            EC.invisibility_of_element_located((By.CSS_SELECTOR, 'button.c-popup__close'))
                        )
                    except Exception:
                        self.driver.execute_script("document.body.click();")
                        time.sleep(0.5)

                except Exception as e:
                    print(f"          Author {idx+1}: Exception - {str(e)[:50]}")
                    continue

            print(f"        ✓ Total authors with emails: {len(authors_data)}")
            return authors_data

        except Exception as e:
            print(f"        ✗ Page error: {str(e)[:50]}")
            return []

    def extract_emails_for_links(self, links, emails_file, label=""):
        """Extract emails for a list of article links"""
        if not links:
            return
        
        total_links = len(links)
        print(f"\n      Extracting emails for {total_links} articles...")
        
        with open(emails_file, 'a', newline='', encoding='utf-8') as outfile:
            writer = csv.writer(outfile)
            
            for idx, article_url in enumerate(links, 1):
                print(f"\n      [{idx}/{total_links}] {article_url}")
                
                authors = self.extract_author_emails(article_url)
                
                if authors:
                    for author in authors:
                        writer.writerow([
                            article_url,
                            author['name'],
                            author['email']
                        ])
                    outfile.flush()
                    print(f"      ✓ Saved {len(authors)} author(s)")
                else:
                    print(f"      ⚠ No authors found")
                
                time.sleep(2)  # Increased delay between articles
    
    def scrape_year_data(self, keyword, year, extract_emails=True):
        """Scrape data for a specific year - extract emails immediately after each combination"""
        print(f"\n{'='*70}")
        print(f"  YEAR: {year}")
        print(f"{'='*70}\n")
        
        # Create files for this year
        links_file = os.path.join(self.output_dir, f"{keyword.replace(' ', '_')}-{year}-links.csv")
        emails_file = os.path.join(self.output_dir, f"{keyword.replace(' ', '_')}-{year}-emails.csv")
        
        # Initialize CSV files
        with open(links_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['article_link'])
        
        if extract_emails:
            with open(emails_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['article_link', 'author_name', 'email'])
        
        year_total_links = 0
        
        # Step 1: Search WITHOUT filters
        print(f"  [1/141] Searching WITHOUT filters...")
        base_url = f"https://www.nature.com/search?q={keyword}&date_range={year}-&order=relevance"
        links = self.scrape_links_from_url(base_url, links_file)
        year_total_links += len(links)
        
        if links:
            print(f"      ✓ Found {len(links)} articles")
            if extract_emails:
                self.extract_emails_for_links(links, emails_file, "No filters")
        else:
            print(f"      ⚠ No articles found")
        
        print()
        time.sleep(1)
        
        # Step 2: Iterate through combinations
        combination_num = 1
        for article_type in self.article_types:
            for subject in self.subjects:
                combination_num += 1
                
                print(f"  [{combination_num}/141] Type: {article_type[:20]:<20} | Subject: {subject[:30]:<30}")
                
                base_url = f"https://www.nature.com/search?q={keyword}&article_type={article_type}&subject={subject}&date_range={year}-&order=relevance"
                
                # Scrape links for this combination
                links = self.scrape_links_from_url(base_url, links_file)
                year_total_links += len(links)
                
                if links:
                    print(f"      ✓ Found {len(links)} articles")
                    
                    # Extract emails immediately if enabled
                    if extract_emails:
                        self.extract_emails_for_links(links, emails_file, f"{article_type} - {subject}")
                
                print()
                time.sleep(0.5)
        
        print(f"  {'─'*70}")
        print(f"  Year {year} Total: {year_total_links} article links")
        print(f"  Links saved to: {links_file}")
        if extract_emails:
            print(f"  Emails saved to: {emails_file}")
        print(f"  {'─'*70}\n")
        
        return year_total_links
    
    def scrape_all_years(self, keyword, start_year, end_year, extract_emails=True):
        """Scrape article links and emails for all years"""
        print(f"\n{'='*70}")
        print(f"  COLLECTING ARTICLE LINKS {'AND EMAILS' if extract_emails else ''}")
        print(f"{'='*70}")
        print(f"  Keyword: {keyword}")
        print(f"  Year Range: {start_year} - {end_year}")
        print(f"  Extract Emails: {'Yes' if extract_emails else 'No'}")
        print(f"  Strategy: Extract links, then {'immediately extract emails' if extract_emails else 'skip emails'}")
        print(f"  Article Types: {len(self.article_types)}")
        print(f"  Subjects: {len(self.subjects)}")
        print(f"{'='*70}\n")
        
        # Setup driver
        self.setup_driver()
        
        # Create output directory
        self.create_output_directory(keyword, start_year, end_year)
        
        years = range(int(start_year), int(end_year) + 1)
        grand_total_articles = 0
        
        # Process each year
        for year in years:
            year_total = self.scrape_year_data(keyword, year, extract_emails)
            grand_total_articles += year_total
        
        print(f"\n{'='*70}")
        print(f"  ✓ {'LINK AND EMAIL' if extract_emails else 'LINK'} COLLECTION COMPLETE!")
        print(f"  Grand Total Article Links: {grand_total_articles}")
        print(f"{'='*70}\n")
        
        return True
    
    def extract_emails_from_existing_links(self, keyword, start_year, end_year):
        """Extract emails from existing link files"""
        print(f"\n{'='*70}")
        print(f"  EXTRACTING EMAILS FROM EXISTING LINKS")
        print(f"{'='*70}\n")
        
        # Check if output directory exists
        if not self.output_dir or not os.path.exists(self.output_dir):
            print(f"  ✗ Output directory not found: {self.output_dir or 'Not set'}")
            return False
        
        # Find all link files
        link_files = glob.glob(os.path.join(self.output_dir, f"{keyword.replace(' ', '_')}-*-links.csv"))
        
        if not link_files:
            print(f"  ✗ No link files found in {self.output_dir}")
            return False
        
        print(f"  Found {len(link_files)} link file(s)\n")
        
        # Setup driver if not already setup
        if not self.driver:
            self.setup_driver()
        
        # Reset cookies_accepted flag to check cookies on first article
        self.cookies_accepted = False
        
        # Process each link file
        for link_file in sorted(link_files):
            year = link_file.split('-')[-2]  # Extract year from filename
            
            print(f"{'='*70}")
            print(f"  PROCESSING YEAR: {year}")
            print(f"{'='*70}\n")
            
            emails_file = link_file.replace('-links.csv', '-emails.csv')
            
            # Check if emails file already exists
            if os.path.exists(emails_file):
                overwrite = input(f"  Emails file exists: {emails_file}\n  Overwrite? (y/n): ").strip().lower()
                if overwrite != 'y':
                    print(f"  Skipping {year}...\n")
                    continue
            
            # Read unique links
            with open(link_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                links = list(set([row['article_link'] for row in reader]))
            
            total_links = len(links)
            print(f"  Processing {total_links} unique articles for year {year}...\n")
            
            # Create emails file
            with open(emails_file, 'w', newline='', encoding='utf-8') as outfile:
                writer = csv.writer(outfile)
                writer.writerow(['article_link', 'author_name', 'email'])
            
            # Extract emails
            self.extract_emails_for_links(links, emails_file, f"Year {year}")
            
            print(f"\n  ✓ Emails saved to: {emails_file}\n")
        
        print(f"{'='*70}")
        print(f"  ✓ ALL EMAIL EXTRACTION COMPLETE!")
        print(f"{'='*70}\n")
        
        return True
    
    def cleanup(self):
        """Close the WebDriver"""
        if self.driver:
            self.driver.quit()
            print("✓ WebDriver closed\n")


def main():
    """Main function to run the scraper"""
    print("\n" + "="*70)
    print("  NATURE.COM ARTICLE SCRAPER - IMPROVED EMAIL EXTRACTION")
    print("  With 'Show authors' button handling and better popup detection")
    print("="*70 + "\n")
    
    # Get user input
    print("Please enter search parameters:\n")
    
    keyword = input("  Search keyword (default: Bioinformatics): ").strip()
    if not keyword:
        keyword = "Bioinformatics"
    
    start_year = input("  Start year (default: 2020): ").strip()
    if not start_year or not start_year.isdigit():
        start_year = "2020"
    
    end_year = input("  End year (default: 2025): ").strip()
    if not end_year or not end_year.isdigit():
        end_year = str(datetime.now().year)
    
    # Ask about link extraction
    extract_new_links = input("  Extract NEW article links? (y/n, default: y): ").strip().lower()
    if not extract_new_links:
        extract_new_links = 'y'
    
    extract_emails = False
    
    if extract_new_links in ['y', 'yes']:
        # Ask about email extraction during link collection
        extract_emails_input = input("  Extract emails immediately after getting links? (y/n, default: y): ").strip().lower()
        if not extract_emails_input or extract_emails_input in ['y', 'yes']:
            extract_emails = True
    
    # Validate years
    if int(start_year) > int(end_year):
        print("\n✗ Error: Start year must be less than or equal to end year!")
        input("\nPress Enter to exit...")
        return
    
    # Create scraper
    scraper = NatureScraper()
    
    # Set output directory for existing files case
    scraper.output_dir = f"{keyword.replace(' ', '_')}_{start_year}-{end_year}"
    
    try:
        if extract_new_links in ['y', 'yes']:
            # Extract new links (and optionally emails)
            success = scraper.scrape_all_years(keyword, start_year, end_year, extract_emails)
            
            if success:
                print("="*70)
                print("  ✓ SCRAPING COMPLETED SUCCESSFULLY!")
                print(f"  Output directory: {os.path.abspath(scraper.output_dir)}")
                print("="*70)
        else:
            # Use existing link files to extract emails
            print("\nℹ Using existing link files to extract emails...\n")
            
            if not os.path.exists(scraper.output_dir):
                print(f"✗ Directory not found: {scraper.output_dir}")
                print("  Please run with 'y' to extract new links first.")
                input("\nPress Enter to exit...")
                return
            
            success = scraper.extract_emails_from_existing_links(keyword, start_year, end_year)
            
            if success:
                print("="*70)
                print("  ✓ EMAIL EXTRACTION COMPLETED SUCCESSFULLY!")
                print(f"  Output directory: {os.path.abspath(scraper.output_dir)}")
                print("="*70)
            else:
                print("\n✗ Email extraction failed.")
            
    except KeyboardInterrupt:
        print("\n\n⚠ Scraping interrupted by user.")
    except Exception as e:
        print(f"\n✗ An error occurred: {e}")
        import traceback
        traceback.print_exc()
    finally:
        scraper.cleanup()
        print("\nPress Enter to exit...")
        input()


if __name__ == "__main__":
    main()
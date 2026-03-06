# #!/usr/bin/env python3
# """
# EuropePMC Data Scraper - Command Line Tool
# Fetches author information from EuropePMC API with pagination support
# """

# import requests
# import json
# import csv
# import re
# import time
# import argparse
# from datetime import datetime
# from typing import List, Dict, Optional
# from urllib.parse import quote

# class EuropePMCScraper:
#     def __init__(self, query: str, start_date: str = None, end_date: str = None, 
#                  page_size: int = 1000, delay: float = 0.5):
#         """
#         Initialize the scraper with search parameters.
        
#         Args:
#             query: Search query string
#             start_date: Start date in YYYY-MM-DD format
#             end_date: End date in YYYY-MM-DD format
#             page_size: Number of results per page (max 1000)
#             delay: Delay between requests in seconds
#         """
#         self.base_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
#         self.query = query
#         self.start_date = start_date
#         self.end_date = end_date
#         self.page_size = min(page_size, 1000)  # API max is 1000
#         self.delay = delay
#         self.all_results = []
        
#     def build_query(self) -> str:
#         """Build the search query with optional date range."""
#         search_query = self.query
#         if self.start_date and self.end_date:
#             search_query += f" AND (FIRST_PDATE:[{self.start_date} TO {self.end_date}])"
#         return search_query
    
#     def extract_email_from_affiliation(self, affiliation: str) -> Optional[str]:
#         """Extract email address from affiliation string using regex."""
#         if not affiliation:
#             return None
#         email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
#         match = re.search(email_pattern, affiliation)
#         return match.group(0) if match else None
    
#     def extract_authors_and_emails(self, articles: List[Dict]) -> List[Dict]:
#         """
#         Extract author information and emails from articles.
        
#         Args:
#             articles: List of article dictionaries from API response
            
#         Returns:
#             List of dictionaries containing author information
#         """
#         extracted = []
        
#         for article in articles:
#             pmid = article.get('pmid') or article.get('id', 'N/A')
#             title = article.get('title', 'No title')
#             doi = article.get('doi', 'N/A')
            
#             author_list = article.get('authorList', {})
#             authors = author_list.get('author', [])
            
#             if not authors:
#                 continue
                
#             for author in authors:
#                 full_name = author.get('fullName', '')
#                 if not full_name:
#                     first = author.get('firstName', '')
#                     last = author.get('lastName', '')
#                     full_name = f"{first} {last}".strip()
                
#                 # Extract email from affiliation
#                 email = 'N/A'
#                 aff_details = author.get('authorAffiliationDetailsList', {})
#                 affiliations = aff_details.get('authorAffiliation', [])
                
#                 for aff in affiliations:
#                     aff_text = aff.get('affiliation', '')
#                     found_email = self.extract_email_from_affiliation(aff_text)
#                     if found_email:
#                         email = found_email
#                         break
                
#                 # Extract ORCID
#                 author_id = author.get('authorId', {})
#                 orcid = 'N/A'
#                 if isinstance(author_id, dict):
#                     orcid = author_id.get('value', 'N/A')
                
#                 # Only add entries with valid emails (not N/A)
#                 if email != 'N/A':
#                     extracted.append({
#                         'pmid': pmid,
#                         'title': title,
#                         'doi': doi,
#                         'author_name': full_name,
#                         'first_name': author.get('firstName', 'N/A'),
#                         'last_name': author.get('lastName', 'N/A'),
#                         'email': email,
#                         'orcid': orcid
#                     })
        
#         return extracted
    
#     def fetch_data(self, verbose: bool = True) -> List[Dict]:
#         """
#         Fetch all data from EuropePMC API using cursor-based pagination.
        
#         Args:
#             verbose: Print progress information
            
#         Returns:
#             List of all extracted author records
#         """
#         search_query = self.build_query()
#         cursor_mark = '*'
#         page_count = 0
#         total_hits = 0
        
#         if verbose:
#             print(f"Starting fetch for query: {search_query}")
#             print(f"Page size: {self.page_size}")
#             print("-" * 60)
        
#         while True:
#             page_count += 1
            
#             # Build request URL
#             params = {
#                 'query': search_query,
#                 'cursorMark': cursor_mark,
#                 'resultType': 'core',
#                 'pageSize': self.page_size,
#                 'format': 'json'
#             }
            
#             try:
#                 if verbose:
#                     print(f"Fetching page {page_count}...", end=' ', flush=True)
                
#                 response = requests.get(self.base_url, params=params, timeout=30)
#                 response.raise_for_status()
#                 data = response.json()
                
#                 # Get total hits from first page
#                 if page_count == 1:
#                     total_hits = data.get('hitCount', 0)
#                     if verbose:
#                         print(f"\nTotal records found: {total_hits:,}")
                
#                 # Extract results
#                 result_list = data.get('resultList', {})
#                 articles = result_list.get('result', [])
                
#                 if articles:
#                     extracted = self.extract_authors_and_emails(articles)
#                     self.all_results.extend(extracted)
                    
#                     if verbose:
#                         print(f"Extracted {len(extracted):,} author entries "
#                               f"(Total: {len(self.all_results):,}/{total_hits:,})")
                
#                 # Check for next page
#                 next_cursor = data.get('nextCursorMark')
#                 if not next_cursor or next_cursor == cursor_mark:
#                     if verbose:
#                         print("\nReached end of results")
#                     break
                
#                 cursor_mark = next_cursor
                
#                 # Rate limiting
#                 time.sleep(self.delay)
                
#             except requests.exceptions.RequestException as e:
#                 print(f"\nError fetching data: {e}")
#                 break
#             except json.JSONDecodeError as e:
#                 print(f"\nError parsing JSON: {e}")
#                 break
#             except KeyboardInterrupt:
#                 print("\n\nScraping interrupted by user")
#                 break
        
#         if verbose:
#             print("-" * 60)
#             print(f"Scraping complete! Total author entries: {len(self.all_results):,}")
        
#         return self.all_results
    
#     def save_to_csv(self, filename: str = None) -> str:
#         """
#         Save results to CSV file.
        
#         Args:
#             filename: Output filename (auto-generated if None)
            
#         Returns:
#             The filename used
#         """
#         if not filename:
#             # Generate filename: query-startdate-enddate-emails.csv
#             safe_query = re.sub(r'[^\w\s-]', '', self.query).replace(' ', '-')[:30]
#             if self.start_date and self.end_date:
#                 filename = f"{safe_query}-{self.start_date}-{self.end_date}-emails.csv"
#             else:
#                 timestamp = datetime.now().strftime("%Y%m%d")
#                 filename = f"{safe_query}-{timestamp}-emails.csv"
        
#         if not self.all_results:
#             print("No results to save")
#             return filename
        
#         with open(filename, 'w', newline='', encoding='utf-8') as f:
#             fieldnames = ['pmid', 'title', 'doi', 'author_name', 
#                          'first_name', 'last_name', 'email', 'orcid']
#             writer = csv.DictWriter(f, fieldnames=fieldnames)
#             writer.writeheader()
#             writer.writerows(self.all_results)
        
#         print(f"Results saved to: {filename}")
#         return filename
    
#     def save_to_json(self, filename: str = None) -> str:
#         """
#         Save results to JSON file.
        
#         Args:
#             filename: Output filename (auto-generated if None)
            
#         Returns:
#             The filename used
#         """
#         if not filename:
#             timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#             safe_query = re.sub(r'[^\w\s-]', '', self.query)[:30]
#             filename = f"europepmc_{safe_query}_{timestamp}.json"
        
#         if not self.all_results:
#             print("No results to save")
#             return filename
        
#         with open(filename, 'w', encoding='utf-8') as f:
#             json.dump(self.all_results, f, indent=2, ensure_ascii=False)
        
#         print(f"Results saved to: {filename}")
#         return filename


# def main():
#     parser = argparse.ArgumentParser(
#         description='Scrape author and email data from EuropePMC (only entries with valid emails)',
#         formatter_class=argparse.RawDescriptionHelpFormatter,
#         epilog="""
# Example:
#   python europepmc_scraper.py --query "malaria" --start-date 2025-01-01 --end-date 2025-12-31
  
#   Output: malaria-2025-01-01-2025-12-31-emails.csv
#         """
#     )
    
#     parser.add_argument('--query', '-q', required=True,
#                        help='Search query string (e.g., "malaria", "covid-19")')
#     parser.add_argument('--start-date', '-s', required=True,
#                        help='Start date in YYYY-MM-DD format')
#     parser.add_argument('--end-date', '-e', required=True,
#                        help='End date in YYYY-MM-DD format')
    
#     args = parser.parse_args()
    
#     # Validate dates
#     try:
#         datetime.strptime(args.start_date, "%Y-%m-%d")
#         datetime.strptime(args.end_date, "%Y-%m-%d")
#     except ValueError:
#         parser.error("Dates must be in YYYY-MM-DD format")
    
#     # Create scraper and fetch data
#     scraper = EuropePMCScraper(
#         query=args.query,
#         start_date=args.start_date,
#         end_date=args.end_date,
#         page_size=1000,
#         delay=0.5
#     )
    
#     # Fetch data
#     start_time = time.time()
#     scraper.fetch_data(verbose=True)
#     elapsed_time = time.time() - start_time
    
#     print(f"\nTime elapsed: {elapsed_time:.2f} seconds")
#     if scraper.all_results:
#         print(f"Average speed: {len(scraper.all_results)/elapsed_time:.1f} records/second")
#         print(f"Total entries with valid emails: {len(scraper.all_results):,}")
    
#     # Save results
#     if scraper.all_results:
#         scraper.save_to_csv()
#     else:
#         print("No results with valid emails found for the given query")


# if __name__ == "__main__":
#     main()


#!/usr/bin/env python3
"""
EuropePMC Data Scraper - Command Line Tool
Fetches author information from EuropePMC API with pagination support
"""

import requests
import json
import csv
import re
import time
import argparse
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import quote

class EuropePMCScraper:
    def __init__(self, query: str, start_date: str = None, end_date: str = None, 
                 page_size: int = 1000, delay: float = 0.5):
        """
        Initialize the scraper with search parameters.
        
        Args:
            query: Search query string
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            page_size: Number of results per page (max 1000)
            delay: Delay between requests in seconds
        """
        self.base_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        self.query = query
        self.start_date = start_date
        self.end_date = end_date
        self.page_size = min(page_size, 1000)  # API max is 1000
        self.delay = delay
        self.all_results = []
        
    def build_query(self) -> str:
        """Build the search query with optional date range."""
        search_query = self.query
        if self.start_date and self.end_date:
            search_query += f" AND (FIRST_PDATE:[{self.start_date} TO {self.end_date}])"
        return search_query
    
    def extract_email_from_affiliation(self, affiliation: str) -> Optional[str]:
        """Extract email address from affiliation string using regex."""
        if not affiliation:
            return None
        email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
        match = re.search(email_pattern, affiliation)
        return match.group(0) if match else None
    
    def extract_authors_and_emails(self, articles: List[Dict]) -> List[Dict]:
        """
        Extract author information and emails from articles.
        
        Args:
            articles: List of article dictionaries from API response
            
        Returns:
            List of dictionaries containing author information
        """
        extracted = []
        
        for article in articles:
            pmid = article.get('pmid') or article.get('id', 'N/A')
            title = article.get('title', 'No title')
            doi = article.get('doi', 'N/A')
            
            author_list = article.get('authorList', {})
            authors = author_list.get('author', [])
            
            if not authors:
                continue
                
            for author in authors:
                # Get first and last names
                first_name = author.get('firstName', '').strip()
                last_name = author.get('lastName', '').strip()
                
                # Create full_name by combining first_name and last_name
                if first_name and last_name:
                    full_name = f"{first_name} {last_name}"
                elif first_name:
                    full_name = first_name
                elif last_name:
                    full_name = last_name
                else:
                    # Fallback to fullName field if available
                    full_name = author.get('fullName', 'N/A')
                
                # Extract email from affiliation
                email = 'N/A'
                aff_details = author.get('authorAffiliationDetailsList', {})
                affiliations = aff_details.get('authorAffiliation', [])
                
                for aff in affiliations:
                    aff_text = aff.get('affiliation', '')
                    found_email = self.extract_email_from_affiliation(aff_text)
                    if found_email:
                        email = found_email
                        break
                
                # Extract ORCID
                author_id = author.get('authorId', {})
                orcid = 'N/A'
                if isinstance(author_id, dict):
                    orcid = author_id.get('value', 'N/A')
                
                # Only add entries with valid emails (not N/A)
                if email != 'N/A':
                    extracted.append({
                        'pmid': pmid,
                        'title': title,
                        'doi': doi,
                        'first_name': first_name if first_name else 'N/A',
                        'last_name': last_name if last_name else 'N/A',
                        'full_name': full_name,
                        'email': email,
                        'orcid': orcid
                    })
        
        return extracted
    
    def fetch_data(self, verbose: bool = True) -> List[Dict]:
        """
        Fetch all data from EuropePMC API using cursor-based pagination.
        
        Args:
            verbose: Print progress information
            
        Returns:
            List of all extracted author records
        """
        search_query = self.build_query()
        cursor_mark = '*'
        page_count = 0
        total_hits = 0
        
        if verbose:
            print(f"Starting fetch for query: {search_query}")
            print(f"Page size: {self.page_size}")
            print("-" * 60)
        
        while True:
            page_count += 1
            
            # Build request URL
            params = {
                'query': search_query,
                'cursorMark': cursor_mark,
                'resultType': 'core',
                'pageSize': self.page_size,
                'format': 'json'
            }
            
            try:
                if verbose:
                    print(f"Fetching page {page_count}...", end=' ', flush=True)
                
                response = requests.get(self.base_url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                # Get total hits from first page
                if page_count == 1:
                    total_hits = data.get('hitCount', 0)
                    if verbose:
                        print(f"\nTotal records found: {total_hits:,}")
                
                # Extract results
                result_list = data.get('resultList', {})
                articles = result_list.get('result', [])
                
                if articles:
                    extracted = self.extract_authors_and_emails(articles)
                    self.all_results.extend(extracted)
                    
                    if verbose:
                        print(f"Extracted {len(extracted):,} author entries "
                              f"(Total: {len(self.all_results):,}/{total_hits:,})")
                
                # Check for next page
                next_cursor = data.get('nextCursorMark')
                if not next_cursor or next_cursor == cursor_mark:
                    if verbose:
                        print("\nReached end of results")
                    break
                
                cursor_mark = next_cursor
                
                # Rate limiting
                time.sleep(self.delay)
                
            except requests.exceptions.RequestException as e:
                print(f"\nError fetching data: {e}")
                break
            except json.JSONDecodeError as e:
                print(f"\nError parsing JSON: {e}")
                break
            except KeyboardInterrupt:
                print("\n\nScraping interrupted by user")
                break
        
        if verbose:
            print("-" * 60)
            print(f"Scraping complete! Total author entries: {len(self.all_results):,}")
        
        return self.all_results
    
    def save_to_csv(self, filename: str = None) -> str:
        """
        Save results to CSV file.
        
        Args:
            filename: Output filename (auto-generated if None)
            
        Returns:
            The filename used
        """
        if not filename:
            # Generate filename: query-startdate-enddate-emails.csv
            safe_query = re.sub(r'[^\w\s-]', '', self.query).replace(' ', '-')[:30]
            if self.start_date and self.end_date:
                filename = f"{safe_query}-{self.start_date}-{self.end_date}-emails.csv"
            else:
                timestamp = datetime.now().strftime("%Y%m%d")
                filename = f"{safe_query}-{timestamp}-emails.csv"
        
        if not self.all_results:
            print("No results to save")
            return filename
        
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            # Updated fieldnames with full_name included
            fieldnames = ['pmid', 'title', 'doi', 'first_name', 
                         'last_name', 'full_name', 'email', 'orcid']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.all_results)
        
        print(f"Results saved to: {filename}")
        return filename
    
    def save_to_json(self, filename: str = None) -> str:
        """
        Save results to JSON file.
        
        Args:
            filename: Output filename (auto-generated if None)
            
        Returns:
            The filename used
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_query = re.sub(r'[^\w\s-]', '', self.query)[:30]
            filename = f"europepmc_{safe_query}_{timestamp}.json"
        
        if not self.all_results:
            print("No results to save")
            return filename
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.all_results, f, indent=2, ensure_ascii=False)
        
        print(f"Results saved to: {filename}")
        return filename


def main():
    parser = argparse.ArgumentParser(
        description='Scrape author and email data from EuropePMC (only entries with valid emails)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  python europepmc_scraper.py --query "malaria" --start-date 2025-01-01 --end-date 2025-12-31
  
  Output: malaria-2025-01-01-2025-12-31-emails.csv
        """
    )
    
    parser.add_argument('--query', '-q', required=True,
                       help='Search query string (e.g., "malaria", "covid-19")')
    parser.add_argument('--start-date', '-s', required=True,
                       help='Start date in YYYY-MM-DD format')
    parser.add_argument('--end-date', '-e', required=True,
                       help='End date in YYYY-MM-DD format')
    
    args = parser.parse_args()
    
    # Validate dates
    try:
        datetime.strptime(args.start_date, "%Y-%m-%d")
        datetime.strptime(args.end_date, "%Y-%m-%d")
    except ValueError:
        parser.error("Dates must be in YYYY-MM-DD format")
    
    # Create scraper and fetch data
    scraper = EuropePMCScraper(
        query=args.query,
        start_date=args.start_date,
        end_date=args.end_date,
        page_size=1000,
        delay=0.5
    )
    
    # Fetch data
    start_time = time.time()
    scraper.fetch_data(verbose=True)
    elapsed_time = time.time() - start_time
    
    print(f"\nTime elapsed: {elapsed_time:.2f} seconds")
    if scraper.all_results:
        print(f"Average speed: {len(scraper.all_results)/elapsed_time:.1f} records/second")
        print(f"Total entries with valid emails: {len(scraper.all_results):,}")
    
    # Save results
    if scraper.all_results:
        scraper.save_to_csv()
    else:
        print("No results with valid emails found for the given query")


if __name__ == "__main__":
    main()
"""
Scraper Adapter Module
Unified interface for running all scrapers in the background with progress tracking
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

import os
import sys
import logging
import importlib
import inspect
from datetime import datetime
from typing import Dict, List, Optional, Tuple


class ScraperAdapter:
    """
    Unified adapter to run any scraper with progress tracking
    Dynamically loads and executes scraper modules
    """
    
    # Mapping of scraper types to module names and class names
    SCRAPER_REGISTRY = {
        'bmj': {'module': 'bmjjournal_selenium', 'class': 'BMJJournalScraper', 'type': 'selenium'},
        'cambridge': {'module': 'cambridge_scraper', 'class': 'CambridgeScraper', 'type': 'selenium'},
        'europepmc': {'module': 'europepmc_scraper', 'class': 'EuropePMCScraper', 'type': 'api'},
        'nature': {'module': 'nature_scraper', 'class': 'NatureScraper', 'type': 'selenium'},
        'springer': {'module': 'sprngr_selenium', 'class': 'SpringerAuthorScraper', 'type': 'selenium'},
        'oxford': {'module': 'oxford_selenium', 'class': 'OxfordScraper', 'type': 'selenium'},
        'lippincott': {'module': 'lippincott_selenium', 'class': 'LippincottScraper', 'type': 'selenium'},
        'sage': {'module': 'sage_scraper', 'class': 'SageScraper', 'type': 'selenium'},
        'emerald': {'module': 'emerald_selenium', 'class': 'EmeraldInsights', 'type': 'selenium'},
        'mdpi': {'module': 'mdpi_app', 'class': 'MdpiScraperAdapter', 'type': 'selenium'},
        'pubmed': {'module': 'pubmed_mesh_scraper', 'class': 'PubMedScraper', 'type': 'api'},
    }
    
    def __init__(self, job_id: str, output_dir: str = 'results'):
        self.job_id = job_id
        self.output_dir = output_dir
        self.progress_callback = None
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
    
    def set_progress_callback(self, callback):
        """Set a callback function for progress updates"""
        self.progress_callback = callback
    
    def _report_progress(self, progress: int, status: str, current_url='', links_count=0, authors_count=0, emails_count=0):
        """Report progress to callback with stats"""
        if self.progress_callback:
            self.progress_callback(progress, status, current_url, links_count, authors_count, emails_count)
        self.logger.info(f"Progress: {progress}% - {status}")
    
    def load_scraper_module(self, scraper_type: str):
        """
        Dynamically load a scraper module
        
        Args:
            scraper_type: Type of scraper to load
            
        Returns:
            Module object
        """
        if scraper_type not in self.SCRAPER_REGISTRY:
            raise ValueError(f"Unknown scraper type: {scraper_type}")
        
        register = self.SCRAPER_REGISTRY[scraper_type]
        try:
            module = importlib.import_module(register['module'])
            return module, register['class']
        except ImportError as e:
            self.logger.error(f"Failed to load scraper module {register['module']}: {e}")
            raise
    
    def run_scraper(self, scraper_type: str, keyword: str, start_date: str, 
                   end_date: str, driver_path: str = None, conference_name: str = 'default',
                   mesh_type: str = 'all') -> Tuple[str, Dict]:
        """
        Run any scraper using unified interface
        
        Args:
            scraper_type: Type of scraper ('bmj', 'cambridge', etc.)
            keyword: Search keyword
            start_date: Start date in MM/DD/YYYY format
            end_date: End date in MM/DD/YYYY format
            driver_path: Path to ChromeDriver (optional)
            conference_name: Conference name for organizing results
            mesh_type: MeSH search type for PubMed (all/tiab/mesh)
            
        Returns:
            Tuple of (output_file_path, summary_dict)
        """
        try:
            self._report_progress(10, f"Loading {scraper_type} scraper...")
            
            # Load the scraper module
            module, class_name = self.load_scraper_module(scraper_type)
            scraper_class = getattr(module, class_name)
            
            self._report_progress(20, "Scraper module loaded")
            
            # Initialize scraper with appropriate parameters
            self._report_progress(30, "Initializing scraper...")
            
            # Different scrapers have different initialization signatures
            if scraper_type == 'pubmed':
                # PubMed uses query, search_field, and date range in YYYY/MM/DD format
                start_converted = self._convert_date_to_pubmed(start_date)
                end_converted = self._convert_date_to_pubmed(end_date)
                scraper = scraper_class(
                    query=keyword,
                    search_field=mesh_type,
                    start_date=start_converted,
                    end_date=end_converted
                )
            elif scraper_type == 'europepmc':
                # EuropePMC uses query, with optional date range
                start_converted = self._convert_date_format(start_date)
                end_converted = self._convert_date_format(end_date)
                scraper = scraper_class(
                    query=keyword,
                    start_date=start_converted,
                    end_date=end_converted
                )
            elif scraper_type == 'nature':
                # Nature scraper has a special interface - initialize without parameters
                scraper = scraper_class()
                # Set up driver and run scraping with parameters
                scraper.setup_driver()
                output_dir = scraper.create_output_directory(keyword, start_date, end_date)
                success = scraper.scrape_all_years(keyword, start_date.split('/')[-1], end_date.split('/')[-1])
                
                if success:
                    # Create a summary for the adapter
                    results = []  # Nature scraper doesn't return results directly
                    output_file = output_dir  # Use the output directory
                else:
                    raise Exception("Nature scraper failed to complete")
            else:
                # Selenium-based scrapers use keyword, start_year, end_year
                scraper = scraper_class(
                    keyword=keyword,
                    start_year=start_date,
                    end_year=end_date,
                    driver_path=driver_path
                )
            
            self._report_progress(50, f"Starting {scraper_type} scrape...")
            
            # Run the scraper
            if scraper_type == 'nature':
                # Nature scraper was already handled in initialization
                pass  # Results and output_file already set above
            elif scraper_type == 'pubmed':
                # PubMed scraper has a run() method that returns results list
                results = scraper.run()
                # Save results to CSV
                output_file = scraper.save_to_csv()
                if not output_file or not os.path.exists(output_file):
                    # Fallback: save using our own method
                    output_file = self._save_api_results(results, scraper_type)
            elif hasattr(scraper, 'scrape'):
                output_file, results = scraper.scrape()
            elif hasattr(scraper, 'run'):
                # Fallback for scrapers that use run() method
                output_file = scraper.run()
                results = scraper.results if hasattr(scraper, 'results') else []
            elif hasattr(scraper, 'fetch_data'):
                # Handle API-based scrapers like EuropePMC
                results = scraper.fetch_data()
                
                # Always save results to CSV for API scrapers
                if results and len(results) > 0:
                    if hasattr(scraper, 'save_to_csv'):
                        # Use scraper's built-in CSV saving
                        output_file = scraper.save_to_csv()
                    else:
                        # Use generic API results saver
                        output_file = self._save_api_results(results, scraper_type)
                else:
                    # No results, create empty file
                    self.logger.warning(f"No results from {scraper_type}, creating empty output file")
                    output_file = self._save_api_results([], scraper_type)
                
                # For API scrapers, results is already the data list
                # No need to access scraper.results since fetch_data() returns the data
            else:
                raise AttributeError(f"Scraper {scraper_type} has no compatible execution method (scrape, run, or fetch_data)")
            
            self._report_progress(90, "Saving results...")
            
            # Handle output file paths for different scraper types
            if scraper_type == 'europepmc':
                # EuropePMC saves to current directory, move to results folder
                if output_file and os.path.exists(output_file):
                    final_output = os.path.join(
                        self.output_dir,
                        f"{self.job_id}_{scraper_type}_results.csv"
                    )
                    # Copy or move the file to results directory
                    import shutil
                    shutil.move(output_file, final_output)
                else:
                    final_output = ""
            elif scraper_type == 'nature':
                # Nature scraper uses output directory
                final_output = output_file
            else:
                # For other scrapers, save to standardized output location
                final_output = os.path.join(
                    self.output_dir,
                    f"{self.job_id}_{scraper_type}_results.csv"
                )
                
                if output_file and os.path.exists(output_file):
                    os.rename(output_file, final_output)
            
            self._report_progress(100, "Scraping completed")
            
            # Create summary
            summary = {
                'scraper': scraper_type,
                'keyword': keyword,
                'output_file': final_output,
                'results_count': len(results) if results else 0,
                'status': 'completed'
            }
            
            self.logger.info(f"Scraper {scraper_type} completed: {summary}")
            return final_output, summary
            
        except Exception as e:
            error_msg = f"Scraper {scraper_type} failed: {str(e)}"
            self.logger.error(error_msg)
            self._report_progress(0, f"Error: {error_msg}")
            raise
    
    def _save_api_results(self, results: List[Dict], scraper_type: str) -> str:
        """
        Save API-based scraper results to CSV file
        
        Args:
            results: List of result dictionaries
            scraper_type: Type of scraper for naming
            
        Returns:
            Path to saved CSV file
        """
        import csv
        
        if not results:
            self.logger.warning(f"No results to save for {scraper_type}")
            # Still create an empty CSV file with headers
            output_file = os.path.join(
                self.output_dir,
                f"{self.job_id}_{scraper_type}_results.csv"
            )
            fieldnames = ['author_name', 'email', 'affiliation', 'journal', 'title', 'pmid']
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
            return output_file
        
        output_file = os.path.join(
            self.output_dir,
            f"{self.job_id}_{scraper_type}_results.csv"
        )
        
        # Get field names from first result
        fieldnames = ['author_name', 'email', 'affiliation', 'journal', 'title', 'pmid']
        
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for result in results:
                # Map result fields to standard field names
                row = {
                    'author_name': result.get('author', result.get('name', '')),
                    'email': result.get('email', ''),
                    'affiliation': result.get('affiliation', ''),
                    'journal': result.get('journal', result.get('journal_title', '')),
                    'title': result.get('title', ''),
                    'pmid': result.get('pmid', '')
                }
                writer.writerow(row)
        
        self.logger.info(f"Saved {len(results)} results to {output_file}")
        return output_file

    def _convert_date_format(self, date_str: str) -> str:
        """
        Convert date from MM/DD/YYYY to YYYY-MM-DD
        
        Args:
            date_str: Date in MM/DD/YYYY format
            
        Returns:
            Date in YYYY-MM-DD format
        """
        try:
            date_obj = datetime.strptime(date_str, "%m/%d/%Y")
            return date_obj.strftime("%Y-%m-%d")
        except ValueError as e:
            self.logger.error(f"Date conversion failed for {date_str}: {e}")
            raise
    
    def _convert_date_to_pubmed(self, date_str: str) -> str:
        """
        Convert date from MM/DD/YYYY to YYYY/MM/DD (PubMed format)
        
        Args:
            date_str: Date in MM/DD/YYYY format
            
        Returns:
            Date in YYYY/MM/DD format
        """
        try:
            date_obj = datetime.strptime(date_str, "%m/%d/%Y")
            return date_obj.strftime("%Y/%m/%d")
        except ValueError as e:
            self.logger.error(f"Date conversion failed for {date_str}: {e}")
            raise


def run_scraper(job_id: str, scraper_type: str, keyword: str, start_date: str, 
               end_date: str, driver_path: str = None) -> str:
    """
    Standalone function for backward compatibility
    Run a scraper with the given parameters
    
    Args:
        job_id: Unique job identifier
        scraper_type: Type of scraper
        keyword: Search keyword
        start_date: Start date in MM/DD/YYYY format
        end_date: End date in MM/DD/YYYY format
        driver_path: Path to ChromeDriver (optional)
        driver_path: Path to ChromeDriver (optional, will be auto-downloaded if not provided)
        
    Returns:
        Path to output CSV file
    """
    adapter = ScraperAdapter(job_id)
    
    # Auto-download ChromeDriver if not provided
    if driver_path is None:
        from webdriver_manager.chrome import ChromeDriverManager
        driver_path = ChromeDriverManager().install()
    
    # Run the unified scraper interface
    output_file, summary = adapter.run_scraper(
        scraper_type=scraper_type,
        keyword=keyword,
        start_date=start_date,
        end_date=end_date,
        driver_path=driver_path
    )
    
    return output_file

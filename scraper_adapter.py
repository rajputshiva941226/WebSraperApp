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
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Tuple


def _get_chrome_binary_path():
    """
    Find the Chrome/Chromium binary path on the current system.
    Returns path string or None if not found.
    """
    candidates = [
        # Linux (EC2 Ubuntu)
        '/usr/bin/google-chrome',
        '/usr/bin/google-chrome-stable',
        '/usr/bin/chromium-browser',
        '/usr/bin/chromium',
        '/snap/bin/chromium',
        # macOS
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        # Windows
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    # Try shutil.which
    for name in ('google-chrome', 'google-chrome-stable', 'chromium-browser', 'chromium'):
        found = shutil.which(name)
        if found:
            return found
    return None


def _get_chromedriver_path():
    """
    Find chromedriver binary. Tries system path first, then webdriver_manager.
    Returns path string.
    """
    # Check system path first (faster, no network needed)
    system_driver = shutil.which('chromedriver')
    if system_driver:
        return system_driver
    # Fall back to webdriver_manager
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        return ChromeDriverManager().install()
    except Exception as e:
        logging.getLogger(__name__).warning(f"ChromeDriverManager failed: {e}")
        return None


def _patch_uc_options(options):
    """
    Inject headless and server-safe arguments into undetected_chromedriver options.
    """
    args_to_add = [
        '--headless=new',
        '--no-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
        '--window-size=1920,1080',
    ]
    existing = getattr(options, 'arguments', [])
    for arg in args_to_add:
        if arg not in existing:
            options.add_argument(arg)
    return options


class ScraperAdapter:
    """
    Unified adapter to run any scraper with progress tracking
    Dynamically loads and executes scraper modules
    """
    
    # Mapping of scraper types to module names and class names
    SCRAPER_REGISTRY = {
        'bmj':        {'module': 'bmjjournal_selenium',  'class': 'BMJJournalScraper',     'type': 'selenium'},
        'cambridge':  {'module': 'cambridge_scraper',    'class': 'CambridgeScraper',      'type': 'selenium'},
        'europepmc':  {'module': 'europepmc_scraper',    'class': 'EuropePMCScraper',      'type': 'api'},
        'nature':     {'module': 'nature_scraper',       'class': 'NatureScraper',         'type': 'selenium'},
        'springer':   {'module': 'sprngr_selenium',      'class': 'SpringerAuthorScraper', 'type': 'selenium'},
        'oxford':     {'module': 'oxford_selenium',      'class': 'OxfordScraper',         'type': 'selenium'},
        'lippincott': {'module': 'lippincott_selenium',  'class': 'LippincottScraper',     'type': 'selenium'},
        'sage':       {'module': 'sage_scraper',         'class': 'SageScraper',           'type': 'selenium'},
        'emerald':    {'module': 'emerald_selenium',     'class': 'EmeraldInsights',       'type': 'selenium'},
        'mdpi':       {'module': 'mdpi_app',             'class': 'MdpiScraperAdapter',    'type': 'selenium'},
        'pubmed':     {'module': 'pubmed_mesh_scraper',  'class': 'PubMedScraper',         'type': 'api'},
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
    
    def _report_progress(self, progress: int, status: str, current_url='',
                         links_count=0, authors_count=0, emails_count=0):
        """Report progress to callback with stats"""
        if self.progress_callback:
            self.progress_callback(progress, status, current_url,
                                   links_count, authors_count, emails_count)
        self.logger.info(f"Progress: {progress}% - {status}")
    
    def load_scraper_module(self, scraper_type: str):
        """
        Dynamically load a scraper module

        Args:
            scraper_type: Type of scraper to load

        Returns:
            Tuple of (module, class_name)
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
                    end_date: str, driver_path: str = None,
                    conference_name: str = 'default',
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
            registry_type = self.SCRAPER_REGISTRY[scraper_type]['type']
            
            self._report_progress(20, "Scraper module loaded")
            self._report_progress(30, "Initializing scraper...")

            # Resolve Chrome binary and driver path for Selenium scrapers
            chrome_binary = _get_chrome_binary_path()
            if driver_path is None:
                driver_path = _get_chromedriver_path()
            self.logger.info(f"Chrome binary: {chrome_binary}, Driver: {driver_path}")

            # ── PubMed (API) ──────────────────────────────────────────────
            if scraper_type == 'pubmed':
                start_converted = self._convert_date_to_pubmed(start_date)
                end_converted   = self._convert_date_to_pubmed(end_date)
                scraper = scraper_class(
                    query=keyword,
                    search_field=mesh_type,
                    start_date=start_converted,
                    end_date=end_converted
                )

                self._report_progress(50, "Running PubMed scraper...")
                results = scraper.run()

                pubmed_output = os.path.join(
                    self.output_dir,
                    f"{self.job_id}_pubmed_results.csv"
                )
                output_file = scraper.save_to_csv(filename=pubmed_output)
                if not output_file or not os.path.exists(output_file):
                    output_file = self._save_api_results(results, scraper_type)

                self._report_progress(100, "PubMed scraping completed")
                summary = {
                    'scraper': scraper_type, 'keyword': keyword,
                    'output_file': output_file,
                    'results_count': len(results) if results else 0,
                    'status': 'completed'
                }
                return output_file, summary

            # ── EuropePMC (API) ───────────────────────────────────────────
            if scraper_type == 'europepmc':
                start_converted = self._convert_date_format(start_date)
                end_converted   = self._convert_date_format(end_date)
                scraper = scraper_class(
                    query=keyword,
                    start_date=start_converted,
                    end_date=end_converted
                )

                self._report_progress(50, "Running EuropePMC scraper...")

                if hasattr(scraper, 'fetch_data'):
                    results = scraper.fetch_data()
                elif hasattr(scraper, 'run'):
                    results = scraper.run()
                else:
                    results = []

                if results and len(results) > 0:
                    if hasattr(scraper, 'save_to_csv'):
                        output_file = scraper.save_to_csv()
                    else:
                        output_file = self._save_api_results(results, scraper_type)
                else:
                    self.logger.warning("No results from EuropePMC, creating empty output file")
                    output_file = self._save_api_results([], scraper_type)

                # Move to job output directory
                final_output = os.path.join(
                    self.output_dir,
                    f"{self.job_id}_europepmc_results.csv"
                )
                if output_file and os.path.exists(output_file):
                    if os.path.abspath(output_file) != os.path.abspath(final_output):
                        shutil.move(output_file, final_output)
                else:
                    final_output = output_file or ''

                self._report_progress(100, "EuropePMC scraping completed")
                summary = {
                    'scraper': scraper_type, 'keyword': keyword,
                    'output_file': final_output,
                    'results_count': len(results) if results else 0,
                    'status': 'completed'
                }
                return final_output, summary

            # ── Nature (Selenium, special interface) ──────────────────────
            if scraper_type == 'nature':
                scraper = scraper_class()
                scraper.setup_driver()
                output_dir_nature = scraper.create_output_directory(
                    keyword, start_date, end_date
                )
                success = scraper.scrape_all_years(
                    keyword,
                    start_date.split('/')[-1],
                    end_date.split('/')[-1]
                )
                if not success:
                    raise Exception("Nature scraper failed to complete")

                self._report_progress(100, "Nature scraping completed")
                summary = {
                    'scraper': scraper_type, 'keyword': keyword,
                    'output_file': output_dir_nature,
                    'results_count': 0,
                    'status': 'completed'
                }
                return output_dir_nature, summary

            # ── All other Selenium scrapers via SeleniumScraperWrapper ────
            #
            # FIX: Previously these scrapers were instantiated directly, then
            # the code tried to call .scrape()/.run()/.fetch_data() on the
            # SeleniumScraperWrapper object — which doesn't have those methods.
            # The wrapper's interface is a single .run() that returns
            # (output_file, summary).  Also, wrapping in a billiard subprocess
            # fixes "daemonic processes are not allowed to have children"
            # because Celery workers are daemonic and uc.Chrome() spawns
            # child processes internally.
            if registry_type == 'selenium':
                from selenium_scraper_wrapper import SeleniumScraperWrapper

                self._report_progress(40, f"Launching {scraper_type} via billiard subprocess...")

                wrapper = SeleniumScraperWrapper(
                    scraper_class=scraper_class,
                    keyword=keyword,
                    start_year=start_date,
                    end_year=end_date,
                    driver_path=driver_path,
                    output_dir=self.output_dir,
                    job_id=self.job_id,
                )
                wrapper.set_progress_callback(self.progress_callback)

                # wrapper.run() returns (output_file_path, summary_dict)
                output_file, summary = wrapper.run()

                self._report_progress(95, "Subprocess finished, locating output file...")

                # Standardise the output location
                final_output = os.path.join(
                    self.output_dir,
                    f"{self.job_id}_{scraper_type}_results.csv"
                )
                if output_file and os.path.exists(output_file):
                    if os.path.abspath(output_file) != os.path.abspath(final_output):
                        try:
                            shutil.move(output_file, final_output)
                        except Exception as mv_err:
                            self.logger.warning(f"Could not move output: {mv_err}")
                            final_output = output_file
                else:
                    # Wrapper may have written directly into output_dir already
                    import glob
                    existing = sorted(
                        glob.glob(os.path.join(self.output_dir, '*.csv')),
                        key=os.path.getmtime, reverse=True
                    )
                    final_output = existing[0] if existing else output_file or ''

                self._report_progress(100, "Scraping completed")
                summary['output_file'] = final_output
                return final_output, summary

            raise ValueError(f"Unhandled scraper type: {scraper_type}")

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

        output_file = os.path.join(
            self.output_dir,
            f"{self.job_id}_{scraper_type}_results.csv"
        )
        fieldnames = ['author_name', 'email', 'affiliation', 'journal', 'title', 'pmid']

        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for result in (results or []):
                writer.writerow({
                    'author_name': result.get('author', result.get('name', '')),
                    'email':       result.get('email', ''),
                    'affiliation': result.get('affiliation', ''),
                    'journal':     result.get('journal', result.get('journal_title', '')),
                    'title':       result.get('title', ''),
                    'pmid':        result.get('pmid', '')
                })

        self.logger.info(f"Saved {len(results or [])} results to {output_file}")
        return output_file

    def _convert_date_format(self, date_str: str) -> str:
        """Convert date from MM/DD/YYYY to YYYY-MM-DD"""
        try:
            return datetime.strptime(date_str, "%m/%d/%Y").strftime("%Y-%m-%d")
        except ValueError as e:
            self.logger.error(f"Date conversion failed for {date_str}: {e}")
            raise

    def _convert_date_to_pubmed(self, date_str: str) -> str:
        """Convert date from MM/DD/YYYY to YYYY/MM/DD (PubMed format)"""
        try:
            return datetime.strptime(date_str, "%m/%d/%Y").strftime("%Y/%m/%d")
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
        driver_path: Path to ChromeDriver (optional, will be auto-downloaded if not provided)

    Returns:
        Path to output CSV file
    """
    adapter = ScraperAdapter(job_id)

    if driver_path is None:
        from webdriver_manager.chrome import ChromeDriverManager
        driver_path = ChromeDriverManager().install()

    output_file, summary = adapter.run_scraper(
        scraper_type=scraper_type,
        keyword=keyword,
        start_date=start_date,
        end_date=end_date,
        driver_path=driver_path
    )

    return output_file
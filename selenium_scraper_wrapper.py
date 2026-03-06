"""
Wrapper to safely initialize Selenium-based scrapers with deferred driver setup.
Prevents worker crashes from Chrome initialization failures.
"""

import logging
import time

logger = logging.getLogger(__name__)


class SeleniumScraperWrapper:
    """
    Wraps Selenium scrapers to defer driver initialization until scraping starts.
    This prevents worker crashes when Chrome fails to initialize.
    """
    
    def __init__(self, scraper_class, keyword, start_year, end_year, driver_path):
        """
        Initialize wrapper without creating the driver yet.
        
        Args:
            scraper_class: The actual scraper class (e.g., SpringerAuthorScraper)
            keyword: Search keyword
            start_year: Start year/date
            end_year: End year/date
            driver_path: Path to ChromeDriver
        """
        self.scraper_class = scraper_class
        self.keyword = keyword
        self.start_year = start_year
        self.end_year = end_year
        self.driver_path = driver_path
        self.scraper_instance = None
        self._initialized = False
        
        logger.info(f"SeleniumScraperWrapper initialized for {scraper_class.__name__}")
    
    def _initialize_scraper(self):
        """
        Actually create the scraper instance (which initializes the driver).
        This is called lazily when scraping starts.
        """
        if self._initialized:
            return
        
        try:
            logger.info(f"Initializing {self.scraper_class.__name__} with driver_path={self.driver_path}")
            
            # Create the scraper instance - this will initialize the driver
            self.scraper_instance = self.scraper_class(
                keyword=self.keyword,
                start_year=self.start_year,
                end_year=self.end_year,
                driver_path=self.driver_path
            )
            self._initialized = True
            logger.info(f"{self.scraper_class.__name__} initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize {self.scraper_class.__name__}: {e}", exc_info=True)
            raise RuntimeError(f"Selenium scraper initialization failed: {str(e)}")
    
    def run(self):
        """
        Run the scraper (initializes driver if not already done).
        """
        self._initialize_scraper()
        if self.scraper_instance:
            return self.scraper_instance.run()
        raise RuntimeError("Scraper instance not initialized")
    
    def get_results(self):
        """Get results from the scraper."""
        if not self.scraper_instance:
            raise RuntimeError("Scraper not initialized")
        return getattr(self.scraper_instance, 'results', [])
    
    def __getattr__(self, name):
        """
        Delegate attribute access to the actual scraper instance.
        Initialize if needed.
        """
        if name.startswith('_'):
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
        
        self._initialize_scraper()
        return getattr(self.scraper_instance, name)

"""
Base Scraper Class - Unified Interface for All Scrapers
Provides a standard interface that all scraper implementations must follow
"""

import os
import csv
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Tuple


class BaseScraper(ABC):
    """Abstract base class for all scraper implementations"""
    
    def __init__(self, keyword: str, start_date: str = None, end_date: str = None, 
                 output_dir: str = 'results', job_id: str = None):
        """
        Initialize base scraper.
        
        Args:
            keyword: Search keyword/query
            start_date: Start date in MM/DD/YYYY format
            end_date: End date in MM/DD/YYYY format
            output_dir: Directory to save results
            job_id: Unique job identifier for tracking
        """
        self.keyword = keyword
        self.start_date = start_date
        self.end_date = end_date
        self.output_dir = output_dir
        self.job_id = job_id
        self.results = []
        self.progress = 0
        self.status = 'initialized'
        self.error_message = None
        
        # Setup logging
        self._setup_logging()
        os.makedirs(output_dir, exist_ok=True)
    
    def _setup_logging(self):
        """Configure logging for the scraper"""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    @abstractmethod
    def scrape(self) -> Tuple[str, List[Dict]]:
        """
        Main scraping method - must be implemented by subclasses
        
        Returns:
            Tuple of (output_file_path, results_list)
        """
        pass
    
    def update_progress(self, progress: int, status: str = None):
        """Update scraping progress"""
        self.progress = min(progress, 100)
        if status:
            self.status = status
        self.logger.info(f"Progress: {self.progress}% - {self.status}")
    
    def save_results_to_csv(self, results: List[Dict], output_file: str = None) -> str:
        """
        Save results to CSV file
        
        Args:
            results: List of result dictionaries
            output_file: Output file path (auto-generated if not provided)
            
        Returns:
            Path to saved file
        """
        if not output_file:
            safe_keyword = self.keyword.replace(" ", "_")[:50]
            output_file = os.path.join(
                self.output_dir,
                f"{self.__class__.__name__}_{safe_keyword}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )
        
        if not results:
            self.logger.warning(f"No results to save to {output_file}")
            return output_file
        
        # Get fieldnames from first result
        fieldnames = list(results[0].keys()) if results else ['name', 'email']
        
        # Deduplicate by email
        seen_emails = set()
        unique_results = []
        for result in results:
            email = result.get('email', result.get('Email', ''))
            if email and email not in seen_emails:
                seen_emails.add(email)
                unique_results.append(result)
            elif not email:  # Include records without email
                unique_results.append(result)
        
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(unique_results)
            
            self.logger.info(f"Saved {len(unique_results)} unique results to {output_file}")
            return output_file
        except Exception as e:
            self.logger.error(f"Error saving results: {e}")
            raise
    
    def get_summary(self) -> Dict:
        """Get scraping summary"""
        return {
            'scraper': self.__class__.__name__,
            'keyword': self.keyword,
            'total_results': len(self.results),
            'unique_emails': len(set(r.get('email', r.get('Email', '')) for r in self.results if r.get('email') or r.get('Email'))),
            'progress': self.progress,
            'status': self.status,
            'error': self.error_message
        }
    
    def handle_error(self, error: Exception):
        """Handle scraper errors"""
        error_msg = str(error)
        self.logger.error(f"Scraper error: {error_msg}")
        self.status = 'failed'
        self.error_message = error_msg
        self.progress = 0

"""
Utility functions for the web scraper application
"""

import re
import os

def sanitize_filename(filename):
    """
    Sanitize a string to make it safe for use in filenames.
    
    Args:
        filename (str): The input string to sanitize
        
    Returns:
        str: A sanitized filename safe for filesystem use
    """
    # Remove or replace invalid characters
    # Windows invalid characters: < > : " | ? * \ /
    # Also remove quotes and other problematic characters
    sanitized = re.sub(r'[<>:"|?*\\\/]', '', filename)
    
    # Replace spaces with hyphens
    sanitized = sanitized.replace(' ', '-')
    
    # Remove multiple consecutive hyphens
    sanitized = re.sub(r'-+', '-', sanitized)
    
    # Remove leading/trailing hyphens and dots
    sanitized = sanitized.strip('-.')
    
    # Ensure filename is not empty
    if not sanitized:
        sanitized = 'unnamed'
    
    return sanitized

def safe_log_file_path(class_name, directory, start_year, end_year):
    """
    Create a safe log file path.
    
    Args:
        class_name (str): Name of the scraper class
        directory (str): Directory name (usually keyword-based)
        start_year (str): Start year/date
        end_year (str): End year/date
        
    Returns:
        str: Safe file path for the log file
    """
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    
    # Sanitize all components
    safe_class_name = sanitize_filename(class_name)
    safe_directory = sanitize_filename(directory)
    safe_start_year = sanitize_filename(start_year.replace('/', '-'))
    safe_end_year = sanitize_filename(end_year.replace('/', '-'))
    
    log_filename = f"{safe_class_name}-{safe_directory}-{safe_start_year}-{safe_end_year}.log"
    return os.path.join(log_dir, log_filename)

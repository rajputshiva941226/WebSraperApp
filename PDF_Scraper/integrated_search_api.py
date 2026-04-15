import requests
import csv
import time
import os
import pandas as pd
import unicodedata
import re
from typing import List, Dict, Optional, Set, Tuple
from difflib import SequenceMatcher
from email_extraction_selenium import AuthorInfoExtractor


class IntegratedPaperSearchAndEmailExtractor:
    """
    Optimized integrated system with:
    - Title-based deduplication
    - Better author name matching (handles hyphens)
    - Efficient CSV writing
    - Paper tracking to avoid re-scraping
    - Skip logic for authors with existing emails
    """
    
    def __init__(self, headless: bool = False, output_dir: str = "results", existing_results_file: str = None):
        self.output_dir = output_dir
        self.headless = headless  # Always False now
        
        # Initialize email extractor
        self.email_extractor = AuthorInfoExtractor(
            headless=headless,
            timeout=30000,
            output_dir=output_dir
        )
        
        # Track authors with successfully extracted emails
        self.authors_with_emails: Set[str] = set()
        
        # Track processed paper titles to avoid duplicates
        self.processed_paper_titles: Set[str] = set()    
        # # Load existing results if provided
        # if existing_results_file and os.path.exists(existing_results_file):
        #     self.load_existing_results(existing_results_file)
        
        # Statistics
        self.stats = {
            'total_authors': 0,
            'authors_skipped_existing': 0,
            'authors_with_emails': 0,
            'papers_searched': 0,
            'papers_scraped': 0,
            'papers_skipped_duplicate': 0,
            'emails_found': 0,
            'wrong_author_emails': 0,
            'api_usage': {
                'semantic_scholar': 0,
                'openalex': 0,
                'pubmed': 0
            }
        }
        
        # Create output directory
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f"Created output directory: {output_dir}")
    
    def load_existing_results(self, filepath: str):
        """Load existing results CSV and mark authors who already have emails."""
        try:
            df = pd.read_csv(filepath)
            
            # Find authors where searched_author_found == 'Yes'
            authors_found = df[df['searched_author_found'] == 'Yes']['author_searched'].unique()
            
            for author in authors_found:
                normalized = self.normalize_author_name(author)
                self.authors_with_emails.add(normalized)
            
            print(f"Loaded {len(self.authors_with_emails)} authors with existing emails from: {filepath}")
            
        except Exception as e:
            print(f"Warning: Could not load existing results: {str(e)}")
    
    def normalize_title(self, title: str) -> str:
        """Normalize paper title for comparison."""
        if not title:
            return ""
        
        # Convert to lowercase
        title = title.lower()
        
        # Remove punctuation and extra whitespace
        title = re.sub(r'[^\w\s]', '', title)
        title = re.sub(r'\s+', ' ', title)
        
        return title.strip()
    
    def titles_match(self, title1: str, title2: str, threshold: float = 0.85) -> bool:
        """
        Check if two titles refer to the same paper.
        Uses fuzzy matching to handle minor variations.
        """
        norm1 = self.normalize_title(title1)
        norm2 = self.normalize_title(title2)
        
        if not norm1 or not norm2:
            return False
        
        # Direct match
        if norm1 == norm2:
            return True
        
        # Fuzzy match using SequenceMatcher
        similarity = SequenceMatcher(None, norm1, norm2).ratio()
        return similarity >= threshold
    
    def is_duplicate_paper(self, title: str) -> bool:
        """Check if paper title has already been processed."""
        norm_title = self.normalize_title(title)
        
        for processed_title in self.processed_paper_titles:
            if self.titles_match(title, processed_title):
                return True
        
        return False
    
    def normalize_author_name(self, name: str) -> str:
        """
        Normalize author name for consistent comparison.
        Handles hyphens by treating them as spaces.
        Expands common initials to handle variations.
        """
        if not name:
            return ""
        
        # Remove accents and convert to lowercase
        name = unicodedata.normalize('NFKD', name)
        name = ''.join([c for c in name if not unicodedata.combining(c)])
        
        # Replace hyphens with spaces for normalization
        name = name.replace('-', ' ')
        
        # Remove periods from initials
        name = name.replace('.', '')
        
        # Normalize whitespace
        name = ' '.join(name.lower().split())
        
        return name

    def extract_name_components(self, name: str) -> Dict[str, str]:
        """
        Extract first name, middle initials, and last name from author name.
        Handles initials and various formats.
        """
        # Replace hyphens with spaces and remove periods
        name = name.replace('-', ' ').replace('.', '').strip()
        
        # Handle comma-separated format (Last, First)
        if ',' in name:
            parts = name.split(',')
            last_name = parts[0].strip()
            first_part = parts[1].strip() if len(parts) > 1 else ""
            
            # Split first part into first name and middle
            first_parts = first_part.split()
            first_name = first_parts[0] if first_parts else ""
            middle = ' '.join(first_parts[1:]) if len(first_parts) > 1 else ""
            
            return {
                'first': first_name.lower(),
                'middle': middle.lower(),
                'last': last_name.lower(),
                'full': f"{first_name} {middle} {last_name}".strip().lower(),
                'is_initial': len(first_name) == 1
            }
        
        # Space-separated format
        parts = name.split()
        
        if len(parts) == 1:
            return {
                'first': '', 
                'middle': '', 
                'last': parts[0].lower(), 
                'full': parts[0].lower(),
                'is_initial': False
            }
        elif len(parts) == 2:
            # Could be "First Last" or "F Last" (initial)
            first = parts[0].lower()
            last = parts[1].lower()
            return {
                'first': first,
                'middle': '',
                'last': last,
                'full': f"{first} {last}",
                'is_initial': len(first) == 1
            }
        else:
            # Multiple parts - assume First Middle... Last
            first = parts[0].lower()
            middle = ' '.join(parts[1:-1]).lower()
            last = parts[-1].lower()
            return {
                'first': first,
                'middle': middle,
                'last': last,
                'full': f"{first} {middle} {last}".strip(),
                'is_initial': len(first) == 1
            }

    def author_name_matches(self, searched_name: str, found_name: str, threshold: float = 0.75) -> bool:
        """
        Enhanced author name matching with support for:
        - Name order variations (First Last vs Last First)
        - Initials (W Janni matches Wolfgang Janni)
        - Middle names
        - Hyphens (treated as spaces)
        """
        if not searched_name or not found_name:
            return False
        
        # Normalize both names (this handles hyphens and periods)
        norm_searched = self.normalize_author_name(searched_name)
        norm_found = self.normalize_author_name(found_name)
        
        # Direct match
        if norm_searched == norm_found:
            return True
        
        # Extract components
        searched_comp = self.extract_name_components(norm_searched)
        found_comp = self.extract_name_components(norm_found)
        
        # Last name must match
        if searched_comp['last'] != found_comp['last']:
            # Try fuzzy match on last name
            last_similarity = SequenceMatcher(None, searched_comp['last'], found_comp['last']).ratio()
            if last_similarity < 0.85:
                return False
        
        # Check first name or initial
        searched_first = searched_comp['first']
        found_first = found_comp['first']
        
        if searched_first and found_first:
            # If searched name is an initial (like "W")
            if searched_comp['is_initial']:
                # Initial must match first letter of found name
                return searched_first[0] == found_first[0]
            
            # If found name is an initial
            if found_comp['is_initial']:
                # Initial must match first letter of searched name
                return found_first[0] == searched_first[0]
            
            # Both are full first names
            if searched_first == found_first:
                return True
            
            # Fuzzy match on first name
            first_similarity = SequenceMatcher(None, searched_first, found_first).ratio()
            if first_similarity >= threshold:
                return True
        
        # Check full name similarity as fallback
        full_similarity = SequenceMatcher(None, norm_searched, norm_found).ratio()
        return full_similarity >= threshold

    def process_author(self, author_name: str, affiliation: str = None) -> bool:
        """
        Process a single author through all APIs until their email is found.
        Saves all emails found, but only stops when searched author's email is found.
        Returns True if searched author's email was found, False otherwise.
        """
        normalized_author = self.normalize_author_name(author_name)
        
        # Check if email already found for this author
        if normalized_author in self.authors_with_emails:
            print(f"  ✓ Email already found for {author_name} (skipping)")
            self.stats['authors_skipped_existing'] += 1
            return True
        
        print(f"\n  Processing: {author_name}")
        if affiliation:
            print(f"  Affiliation: {affiliation}")
        
        # Try each API in sequence
        apis = [
            ('PubMed', self.search_pubmed),
            ('Semantic Scholar', self.search_semantic_scholar),
            ('OpenAlex', self.search_openalex)
        ]
        
        for api_name, search_func in apis:
            print(f"\n  → Searching {api_name}...")
            
            try:
                papers = search_func(author_name, affiliation)
            except Exception as e:
                print(f"    Error calling {api_name}: {str(e)}")
                papers = []
            
            # Ensure papers is a list
            if not isinstance(papers, list):
                print(f"    Warning: {api_name} returned non-list result, skipping")
                papers = []
            
            self.stats['api_usage'][api_name.lower().replace(' ', '_')] += 1
            
            if not papers:
                print(f"    No NEW papers found in {api_name}, trying next API...")
                continue
            
            print(f"    Found {len(papers)} NEW papers in {api_name}")
            self.stats['papers_searched'] += len(papers)
            
            # Scrape each paper
            for idx, paper in enumerate(papers, 1):
                # Validate paper object
                if not paper or not isinstance(paper, dict):
                    print(f"    [{idx}/{len(papers)}] Invalid paper object, skipping...")
                    continue
                
                # Validate required fields
                if 'title' not in paper or 'url' not in paper:
                    print(f"    [{idx}/{len(papers)}] Paper missing required fields, skipping...")
                    continue
                
                try:
                    title = paper.get('title', 'Unknown')[:60]
                    print(f"    [{idx}/{len(papers)}] Scraping: {title}...")
                    
                    result = self.scrape_paper_for_email(paper, author_name, affiliation or 'N/A')
                    
                    # Handle None result (skipped domains, errors, etc.)
                    if result is None:
                        print(f"      → No result from scraping, continuing...")
                        continue
                    
                    # Validate result is a dictionary
                    if not isinstance(result, dict):
                        print(f"      Warning: scrape_paper_for_email returned non-dict result")
                        continue
                    
                    # Save extraction (regardless of whether it's the searched author)
                    self.save_extraction_result(result)
                    
                    # Check if this was the searched author's email
                    if result.get('searched_author_email_found'):
                        print(f"    ✓ Found searched author's email!")
                        self.authors_with_emails.add(normalized_author)
                        self.stats['authors_with_emails'] += 1
                        
                        # Skip remaining papers for this author
                        remaining = len(papers) - idx
                        if remaining > 0:
                            print(f"    → Skipping {remaining} remaining paper(s) for {author_name}")
                        
                        return True
                    else:
                        # Emails found but not for searched author, continue to next paper
                        print(f"    → Continuing to next paper to find {author_name}'s email...")
                    
                except Exception as e:
                    print(f"      ✗ Error processing paper: {str(e)[:100]}")
                    import traceback
                    traceback.print_exc()
                    continue
                
                time.sleep(2)  # Rate limiting between scrapes
            
            print(f"    Searched author's email not found in {api_name} papers, trying next API...")
            time.sleep(1)  # Delay between APIs
        
        print(f"  ⚠ Searched author's email not found for {author_name} in any API")
        return False

    def scrape_paper_for_email(self, paper: Dict, author_searched: str, affiliation_searched: str) -> Optional[Dict]:
        """
        Scrape a single paper for email addresses.
        Returns result with all found emails, and marks if searched author's email was found.
        Skips generic domains entirely.
        """
        try:
            # Validate paper has required fields
            if not paper or not isinstance(paper, dict):
                print(f"      ✗ Invalid paper object")
                return None
            
            url = paper.get('url')
            if not url:
                print(f"      ✗ No URL in paper object")
                return None
            
            result = self.email_extractor.extract_author_info_from_page(url)
            
            # Handle None result
            if result is None:
                print(f"      ✗ Extractor returned None")
                return None
            
            # Check if domain was skipped (generic)
            if result.get('status') == 'skipped':
                print(f"      ⊘ Skipped generic domain")
                return None
            
            result['author_searched'] = author_searched
            result['affiliation_searched'] = affiliation_searched
            result['paper_title'] = paper.get('title', 'Unknown')
            result['paper_source'] = paper.get('source', 'Unknown')
            result['paper_year'] = paper.get('year', 'N/A')
            result['paper_venue'] = paper.get('venue', 'N/A')
            result['searched_author_email_found'] = False
            
            self.stats['papers_scraped'] += 1
            
            # Check if this is a failure
            if result.get('status') == 'failed':
                error_msg = result.get('extraction_method', '')
                
                # Handle window errors - restart browser
                if self.is_window_error(error_msg):
                    print("      ⚠ Browser window closed, restarting...")
                    self.email_extractor._restart_driver()
                
                return None
            
            # Check if any email was found
            emails = result.get('emails', [])
            if not emails or not any(email.strip() for email in emails):
                print("      ✗ No emails found")
                return None
            
            # We found some emails - record this
            self.stats['emails_found'] += len(emails)
            
            # Check if any email belongs to searched author
            matched_author, matched_email = self.find_matching_author_email(result, author_searched)
            
            if matched_author and matched_email:
                # Found the searched author's email!
                print(f"      ✓ Found email for searched author {matched_author}: {matched_email}")
                result['searched_author_email_found'] = True
                result['matched_author'] = matched_author
                result['matched_email'] = matched_email
                
                # Mark title as processed
                self.processed_paper_titles.add(self.normalize_title(paper.get('title', '')))
                
                return result
            else:
                # Found emails but not for searched author
                extracted_authors = ', '.join(result.get('authors', []))[:100]
                print(f"      ℹ Found {len(emails)} email(s) for: {extracted_authors}")
                print(f"      ⚠ Searched author '{author_searched}' not in extracted authors")
                self.stats['wrong_author_emails'] += 1
                result['searched_author_email_found'] = False
                
                # Still mark as processed to avoid re-scraping
                self.processed_paper_titles.add(self.normalize_title(paper.get('title', '')))
                
                return result
            
        except Exception as e:
            error_msg = str(e)
            print(f"      ✗ Scraping error: {error_msg[:100]}")
            
            # Handle window errors
            if self.is_window_error(error_msg):
                print("      ⚠ Browser window closed, restarting...")
                try:
                    self.email_extractor._restart_driver()
                except:
                    print("      ✗ Failed to restart browser")
            
            return None

    # def normalize_author_name(self, name: str) -> str:
    #     """
    #     Normalize author name for consistent comparison.
    #     Handles hyphens by treating them as spaces.
    #     """
    #     if not name:
    #         return ""
        
    #     # Remove accents and convert to lowercase
    #     name = unicodedata.normalize('NFKD', name)
    #     name = ''.join([c for c in name if not unicodedata.combining(c)])
        
    #     # Replace hyphens with spaces for normalization
    #     name = name.replace('-', ' ')
        
    #     # Normalize whitespace
    #     name = ' '.join(name.lower().split())
        
    #     return name
    
    # def extract_name_components(self, name: str) -> Dict[str, str]:
    #     """
    #     Extract first name, middle initials, and last name from author name.
    #     Handles hyphens and various formats like:
    #     - "Pritam Singh"
    #     - "Singh Pritam" 
    #     - "P. Singh"
    #     - "Singh, P."
    #     - "Abdul Khalil-Gardezi" (treats hyphen as space)
    #     """
    #     # Replace hyphens with spaces for parsing
    #     name = name.replace('-', ' ').strip()
        
    #     # Handle comma-separated format (Last, First)
    #     if ',' in name:
    #         parts = name.split(',')
    #         last_name = parts[0].strip()
    #         first_part = parts[1].strip() if len(parts) > 1 else ""
            
    #         # Split first part into first name and middle
    #         first_parts = first_part.split()
    #         first_name = first_parts[0] if first_parts else ""
    #         middle = ' '.join(first_parts[1:]) if len(first_parts) > 1 else ""
            
    #         return {
    #             'first': first_name,
    #             'middle': middle,
    #             'last': last_name,
    #             'full': f"{first_name} {middle} {last_name}".strip()
    #         }
        
    #     # Space-separated format
    #     parts = name.split()
        
    #     if len(parts) == 1:
    #         return {'first': '', 'middle': '', 'last': parts[0], 'full': parts[0]}
    #     elif len(parts) == 2:
    #         # Could be "First Last" or "Last First"
    #         return {
    #             'first': parts[0],
    #             'middle': '',
    #             'last': parts[1],
    #             'full': name
    #         }
    #     else:
    #         # Multiple parts - assume First Middle... Last
    #         return {
    #             'first': parts[0],
    #             'middle': ' '.join(parts[1:-1]),
    #             'last': parts[-1],
    #             'full': name
    #         }
    
    # def author_name_matches(self, searched_name: str, found_name: str, threshold: float = 0.75) -> bool:
    #     """
    #     Enhanced author name matching with support for:
    #     - Name order variations (First Last vs Last First)
    #     - Initials
    #     - Middle names
    #     - Hyphens (treated as spaces)
    #     """
    #     if not searched_name or not found_name:
    #         return False
        
    #     # Normalize both names (this handles hyphens)
    #     norm_searched = self.normalize_author_name(searched_name)
    #     norm_found = self.normalize_author_name(found_name)
        
    #     # Direct match
    #     if norm_searched == norm_found:
    #         return True
        
    #     # Extract components
    #     searched_comp = self.extract_name_components(norm_searched)
    #     found_comp = self.extract_name_components(norm_found)
        
    #     # Last name must match
    #     if searched_comp['last'] != found_comp['last']:
    #         # Try fuzzy match on last name
    #         last_similarity = SequenceMatcher(None, searched_comp['last'], found_comp['last']).ratio()
    #         if last_similarity < 0.85:
    #             return False
        
    #     # Check first name or initial
    #     searched_first = searched_comp['first']
    #     found_first = found_comp['first']
        
    #     if searched_first and found_first:
    #         # Both have first names
    #         if searched_first == found_first:
    #             return True
            
    #         # Check if one is initial of the other
    #         if (searched_first[0] == found_first[0] and 
    #             (len(searched_first) == 1 or len(found_first) == 1)):
    #             return True
            
    #         # Fuzzy match on first name
    #         first_similarity = SequenceMatcher(None, searched_first, found_first).ratio()
    #         if first_similarity >= threshold:
    #             return True
        
    #     # Check full name similarity as fallback
    #     full_similarity = SequenceMatcher(None, norm_searched, norm_found).ratio()
    #     return full_similarity >= threshold
    
    def find_matching_author_email(self, result: Dict, searched_author: str) -> Tuple[str, str]:
        """
        Find email that corresponds to the searched author.
        Returns (author_name, email) tuple or (None, None) if not found.
        """
        authors = result.get('authors', [])
        emails = result.get('emails', [])
        
        if not authors or not emails:
            return None, None
        
        # Try to match author name with email
        for i, author_name in enumerate(authors):
            if self.author_name_matches(searched_author, author_name):
                # Found matching author
                if i < len(emails):
                    email = emails[i].strip()
                    if email:  # Make sure email is not empty
                        return author_name, email
        
        return None, None
    
    def resolve_author_with_affiliation(self, author_name: str, affiliation: str = None) -> Optional[Dict]:
        """Resolve author using Semantic Scholar API with affiliation matching."""
        try:
            rsp = requests.get('https://api.semanticscholar.org/graph/v1/author/search',
                             params={
                                 'query': author_name, 
                                 'fields': 'authorId,name,affiliations,paperCount,url',
                                 'limit': 100
                             },
                             timeout=10)
            rsp.raise_for_status()
            results = rsp.json()
            
            if results['total'] == 0:
                return None
            
            candidates = results['data']
            
            # If affiliation provided, try to match
            if affiliation:
                clean_affiliation = affiliation.split(',')[0].strip().lower()
                clean_affiliation = clean_affiliation.replace(' corporation', '').replace(' medical', '').strip()
                
                for candidate in candidates:
                    candidate_affiliations = candidate.get('affiliations', [])
                    for cand_aff in candidate_affiliations:
                        cand_aff_lower = cand_aff.lower()
                        if (clean_affiliation in cand_aff_lower or 
                            cand_aff_lower in clean_affiliation or
                            any(word in cand_aff_lower for word in clean_affiliation.split() if len(word) > 3)):
                            return candidate
                
                return candidates[0]
            
            return candidates[0]
                
        except Exception as e:
            print(f"    Error resolving author: {str(e)}")
            return None
    
    def search_semantic_scholar(self, author: str, affiliation: str = None) -> List[Dict]:
        """Search Semantic Scholar API for papers."""
        papers = []
        
        try:
            author_data = self.resolve_author_with_affiliation(author, affiliation)
            
            if not author_data:
                return papers  # Return empty list, not None
            
            author_id = author_data.get('authorId')
            if not author_id:
                return papers
            
            papers_url = f"https://api.semanticscholar.org/graph/v1/author/{author_id}/papers"
            params = {
                "fields": "paperId,title,externalIds,url,year,authors,venue",
                "limit": 100
            }
            
            time.sleep(0.5)
            response = requests.get(papers_url, params=params, timeout=10)
            response.raise_for_status()
            papers_data = response.json()
            
            for paper in papers_data.get('data', []):
                title = paper.get('title', '')
                
                # Skip if title already processed
                if self.is_duplicate_paper(title):
                    self.stats['papers_skipped_duplicate'] += 1
                    continue
                
                doi = None
                if paper.get('externalIds'):
                    doi = paper['externalIds'].get('DOI')
                
                if doi:
                    papers.append({
                        'title': title,
                        'doi': doi,
                        'url': f"https://doi.org/{doi}",
                        'year': paper.get('year', 'N/A'),
                        'venue': paper.get('venue', 'N/A'),
                        'source': 'Semantic Scholar'
                    })
            
        except Exception as e:
            print(f"    Semantic Scholar error: {str(e)}")
        
        return papers  # Always return a list


    def search_openalex(self, author: str, affiliation: str = None) -> List[Dict]:
        """Search OpenAlex API for papers."""
        papers = []
        
        try:
            author_url = "https://api.openalex.org/authors"
            author_params = {
                "search": author,
                "per-page": 100,
                "mailto": "pritham.pgc@gmail.com"
            }
            
            response = requests.get(author_url, params=author_params, timeout=10)
            response.raise_for_status()
            author_data = response.json()
            
            author_results = author_data.get('results', [])
            if not author_results:
                return papers  # Return empty list
            
            best_author = None
            author_name_lower = author.lower()
            
            for author_candidate in author_results:
                display_name = author_candidate.get('display_name', '').lower()
                if author_name_lower in display_name or display_name in author_name_lower:
                    best_author = author_candidate
                    break
            
            if not best_author:
                best_author = author_results[0]
            
            author_id = best_author.get('id')
            if not author_id:
                return papers
            
            author_id = author_id.split('/')[-1]
            
            works_url = "https://api.openalex.org/works"
            works_params = {
                "filter": f"authorships.author.id:{author_id}",
                "per-page": 100,
                "mailto": "pritham.pgc@gmail.com"
            }
            
            if affiliation:
                parts = affiliation.split(',')
                clean_affiliation = parts[0].strip()
                institution_id = self.search_institution_openalex(clean_affiliation)
                
                if institution_id:
                    inst_id_short = institution_id.split('/')[-1]
                    works_params["filter"] = f"authorships.author.id:{author_id},authorships.institutions.id:{inst_id_short}"
            
            time.sleep(0.5)
            response = requests.get(works_url, params=works_params, timeout=10)
            response.raise_for_status()
            works_data = response.json()
            
            for work in works_data.get('results', []):
                title = work.get('title', '')
                
                # Skip if title already processed
                if self.is_duplicate_paper(title):
                    self.stats['papers_skipped_duplicate'] += 1
                    continue
                
                doi = work.get('doi')
                if doi:
                    if doi.startswith('https://doi.org/'):
                        doi = doi.replace('https://doi.org/', '')
                    
                    venue = 'N/A'
                    try:
                        primary_location = work.get('primary_location')
                        if primary_location and primary_location.get('source'):
                            venue = primary_location['source'].get('display_name', 'N/A')
                    except:
                        pass
                    
                    papers.append({
                        'title': title,
                        'doi': doi,
                        'url': f"https://doi.org/{doi}",
                        'year': work.get('publication_year', 'N/A'),
                        'venue': venue,
                        'source': 'OpenAlex'
                    })
            
        except Exception as e:
            print(f"    OpenAlex error: {str(e)}")
        
        return papers  # Always return a list


    def search_pubmed(self, author: str, affiliation: str = None) -> List[Dict]:
        """Search PubMed API for papers."""
        papers = []
        
        try:
            query = f"{author}[au]"
            if affiliation:
                clean_affiliation = affiliation.split(',')[0].strip()
                query += f" AND {clean_affiliation}[ad:~10]"
            
            search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            params = {
                "db": "pubmed",
                "term": query,
                "retmax": 200,
                "retmode": "json"
            }
            
            response = requests.get(search_url, params=params, timeout=10)
            response.raise_for_status()
            search_data = response.json()
            
            id_list = search_data.get('esearchresult', {}).get('idlist', [])
            
            if not id_list:
                return papers  # Return empty list
            
            batch_size = 200
            for i in range(0, len(id_list), batch_size):
                batch_ids = id_list[i:i+batch_size]
                
                time.sleep(0.5)
                fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
                params = {
                    "db": "pubmed",
                    "id": ",".join(batch_ids),
                    "retmode": "json"
                }
                
                response = requests.get(fetch_url, params=params, timeout=10)
                response.raise_for_status()
                details_data = response.json()
                
                result = details_data.get('result')
                if not result:
                    continue
                
                for pmid, paper_data in result.items():
                    if pmid == 'uids' or not isinstance(paper_data, dict):
                        continue
                    
                    title = paper_data.get('title', '')
                    
                    # Skip if title already processed
                    if self.is_duplicate_paper(title):
                        self.stats['papers_skipped_duplicate'] += 1
                        continue
                    
                    doi = None
                    for article_id in paper_data.get('articleids', []):
                        if article_id.get('idtype') == 'doi':
                            doi = article_id.get('value')
                            break
                    
                    if doi:
                        papers.append({
                            'title': title,
                            'doi': doi,
                            'url': f"https://doi.org/{doi}",
                            'year': paper_data.get('pubdate', 'N/A').split()[0] if paper_data.get('pubdate') else 'N/A',
                            'venue': paper_data.get('source', 'N/A'),
                            'source': 'PubMed'
                        })
            
        except Exception as e:
            print(f"    PubMed error: {str(e)}")
        
        return papers  # Always return a list


    # def search_semantic_scholar(self, author: str, affiliation: str = None) -> List[Dict]:
    #     """Search Semantic Scholar API for papers."""
    #     papers = []
        
    #     try:
    #         author_data = self.resolve_author_with_affiliation(author, affiliation)
            
    #         if not author_data:
    #             return papers
            
    #         author_id = author_data['authorId']
    #         papers_url = f"https://api.semanticscholar.org/graph/v1/author/{author_id}/papers"
    #         params = {
    #             "fields": "paperId,title,externalIds,url,year,authors,venue",
    #             "limit": 100
    #         }
            
    #         time.sleep(0.5)
    #         response = requests.get(papers_url, params=params, timeout=10)
    #         response.raise_for_status()
    #         papers_data = response.json()
            
    #         for paper in papers_data.get('data', []):
    #             title = paper.get('title', '')
                
    #             # Skip if title already processed
    #             if self.is_duplicate_paper(title):
    #                 self.stats['papers_skipped_duplicate'] += 1
    #                 continue
                
    #             doi = None
    #             if paper.get('externalIds'):
    #                 doi = paper['externalIds'].get('DOI')
                
    #             if doi:
    #                 papers.append({
    #                     'title': title,
    #                     'doi': doi,
    #                     'url': f"https://doi.org/{doi}",
    #                     'year': paper.get('year', 'N/A'),
    #                     'venue': paper.get('venue', 'N/A'),
    #                     'source': 'Semantic Scholar'
    #                 })
            
    #     except Exception as e:
    #         print(f"    Semantic Scholar error: {str(e)}")
        
    #     return papers
    
    def search_institution_openalex(self, institution_name: str) -> Optional[str]:
        """Search for institution ID in OpenAlex."""
        try:
            parts = institution_name.split(',')
            clean_name = parts[0].strip()
            
            url = "https://api.openalex.org/institutions"
            params = {
                "search": clean_name,
                "per-page": 100,
                "mailto": "pritham.pgc@gmail.com"
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            results = data.get('results', [])
            if results:
                return results[0]['id']
            return None
                
        except Exception as e:
            return None
    
    # def search_openalex(self, author: str, affiliation: str = None) -> List[Dict]:
    #     """Search OpenAlex API for papers."""
    #     papers = []
        
    #     try:
    #         author_url = "https://api.openalex.org/authors"
    #         author_params = {
    #             "search": author,
    #             "per-page": 100,
    #             "mailto": "pritham.pgc@gmail.com"
    #         }
            
    #         response = requests.get(author_url, params=author_params, timeout=10)
    #         response.raise_for_status()
    #         author_data = response.json()
            
    #         author_results = author_data.get('results', [])
    #         if not author_results:
    #             return papers
            
    #         best_author = None
    #         author_name_lower = author.lower()
            
    #         for author_candidate in author_results:
    #             display_name = author_candidate.get('display_name', '').lower()
    #             if author_name_lower in display_name or display_name in author_name_lower:
    #                 best_author = author_candidate
    #                 break
            
    #         if not best_author:
    #             best_author = author_results[0]
            
    #         author_id = best_author['id'].split('/')[-1]
            
    #         works_url = "https://api.openalex.org/works"
    #         works_params = {
    #             "filter": f"authorships.author.id:{author_id}",
    #             "per-page": 100,
    #             "mailto": "pritham.pgc@gmail.com"
    #         }
            
    #         if affiliation:
    #             parts = affiliation.split(',')
    #             clean_affiliation = parts[0].strip()
    #             institution_id = self.search_institution_openalex(clean_affiliation)
                
    #             if institution_id:
    #                 inst_id_short = institution_id.split('/')[-1]
    #                 works_params["filter"] = f"authorships.author.id:{author_id},authorships.institutions.id:{inst_id_short}"
            
    #         time.sleep(0.5)
    #         response = requests.get(works_url, params=works_params, timeout=10)
    #         response.raise_for_status()
    #         works_data = response.json()
            
    #         for work in works_data.get('results', []):
    #             title = work.get('title', '')
                
    #             # Skip if title already processed
    #             if self.is_duplicate_paper(title):
    #                 self.stats['papers_skipped_duplicate'] += 1
    #                 continue
                
    #             doi = work.get('doi')
    #             if doi:
    #                 if doi.startswith('https://doi.org/'):
    #                     doi = doi.replace('https://doi.org/', '')
                    
    #                 venue = 'N/A'
    #                 try:
    #                     primary_location = work.get('primary_location')
    #                     if primary_location and primary_location.get('source'):
    #                         venue = primary_location['source'].get('display_name', 'N/A')
    #                 except:
    #                     pass
                    
    #                 papers.append({
    #                     'title': title,
    #                     'doi': doi,
    #                     'url': f"https://doi.org/{doi}",
    #                     'year': work.get('publication_year', 'N/A'),
    #                     'venue': venue,
    #                     'source': 'OpenAlex'
    #                 })
            
    #     except Exception as e:
    #         print(f"    OpenAlex error: {str(e)}")
        
    #     return papers
    
    # def search_pubmed(self, author: str, affiliation: str = None) -> List[Dict]:
    #     """Search PubMed API for papers."""
    #     papers = []
        
    #     try:
    #         query = f"{author}[au]"
    #         if affiliation:
    #             clean_affiliation = affiliation.split(',')[0].strip()
    #             query += f" AND {clean_affiliation}[ad:~10]"
            
    #         search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    #         params = {
    #             "db": "pubmed",
    #             "term": query,
    #             "retmax": 200,
    #             "retmode": "json"
    #         }
            
    #         response = requests.get(search_url, params=params, timeout=10)
    #         response.raise_for_status()
    #         search_data = response.json()
            
    #         id_list = search_data.get('esearchresult', {}).get('idlist', [])
            
    #         if not id_list:
    #             return papers
            
    #         batch_size = 200
    #         for i in range(0, len(id_list), batch_size):
    #             batch_ids = id_list[i:i+batch_size]
                
    #             time.sleep(0.5)
    #             fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    #             params = {
    #                 "db": "pubmed",
    #                 "id": ",".join(batch_ids),
    #                 "retmode": "json"
    #             }
                
    #             response = requests.get(fetch_url, params=params, timeout=10)
    #             response.raise_for_status()
    #             details_data = response.json()
                
    #             for pmid, paper_data in details_data.get('result', {}).items():
    #                 if pmid == 'uids':
    #                     continue
                    
    #                 title = paper_data.get('title', '')
                    
    #                 # Skip if title already processed
    #                 if self.is_duplicate_paper(title):
    #                     self.stats['papers_skipped_duplicate'] += 1
    #                     continue
                    
    #                 doi = None
    #                 for article_id in paper_data.get('articleids', []):
    #                     if article_id.get('idtype') == 'doi':
    #                         doi = article_id.get('value')
    #                         break
                    
    #                 if doi:
    #                     papers.append({
    #                         'title': title,
    #                         'doi': doi,
    #                         'url': f"https://doi.org/{doi}",
    #                         'year': paper_data.get('pubdate', 'N/A').split()[0] if paper_data.get('pubdate') else 'N/A',
    #                         'venue': paper_data.get('source', 'N/A'),
    #                         'source': 'PubMed'
    #                     })
            
    #     except Exception as e:
    #         print(f"    PubMed error: {str(e)}")
        
    #     return papers
    
    def is_window_error(self, error_msg: str) -> bool:
        """Check if error is related to window closure."""
        window_errors = [
            'no such window',
            'target window already closed',
            'web view not found',
            'Session info: chrome'
        ]
        return any(err in str(error_msg).lower() for err in window_errors)
    
    # def scrape_paper_for_email(self, paper: Dict, author_searched: str, affiliation_searched: str) -> Dict:
    #     """
    #     Scrape a single paper for email addresses.
    #     Returns result with all found emails, and marks if searched author's email was found.
    #     Skips generic domains entirely.
    #     """
    #     try:
    #         result = self.email_extractor.extract_author_info_from_page(paper['url'])
            
    #         # Check if domain was skipped (generic)
    #         if result.get('status') == 'skipped':
    #             print(f"      ⊘ Skipped generic domain")
    #             return None
            
    #         result['author_searched'] = author_searched
    #         result['affiliation_searched'] = affiliation_searched
    #         result['paper_title'] = paper['title']
    #         result['paper_source'] = paper['source']
    #         result['paper_year'] = paper['year']
    #         result['paper_venue'] = paper['venue']
    #         result['searched_author_email_found'] = False
            
    #         self.stats['papers_scraped'] += 1
            
    #         # Check if this is a failure
    #         if result.get('status') == 'failed':
    #             error_msg = result.get('extraction_method', '')
                
    #             # Handle window errors - restart browser
    #             if self.is_window_error(error_msg):
    #                 print("      ⚠ Browser window closed, restarting...")
    #                 self.email_extractor._restart_driver()
                
    #             return None
            
    #         # Check if any email was found
    #         emails = result.get('emails', [])
    #         if not emails or not any(email.strip() for email in emails):
    #             print("      ✗ No emails found")
    #             return None
            
    #         # We found some emails - record this
    #         self.stats['emails_found'] += len(emails)
            
    #         # Check if any email belongs to searched author
    #         matched_author, matched_email = self.find_matching_author_email(result, author_searched)
            
    #         if matched_author and matched_email:
    #             # Found the searched author's email!
    #             print(f"      ✓ Found email for searched author {matched_author}: {matched_email}")
    #             result['searched_author_email_found'] = True
    #             result['matched_author'] = matched_author
    #             result['matched_email'] = matched_email
                
    #             # Mark title as processed
    #             self.processed_paper_titles.add(self.normalize_title(paper['title']))
                
    #             return result
    #         else:
    #             # Found emails but not for searched author
    #             extracted_authors = ', '.join(result.get('authors', []))[:100]
    #             print(f"      ℹ Found {len(emails)} email(s) for: {extracted_authors}")
    #             print(f"      ⚠ Searched author '{author_searched}' not in extracted authors")
    #             self.stats['wrong_author_emails'] += 1
    #             result['searched_author_email_found'] = False
                
    #             # Still mark as processed to avoid re-scraping
    #             self.processed_paper_titles.add(self.normalize_title(paper['title']))
                
    #             return result
            
    #     except Exception as e:
    #         error_msg = str(e)
    #         print(f"      ✗ Scraping error: {error_msg[:100]}")
            
    #         # Handle window errors
    #         if self.is_window_error(error_msg):
    #             print("      ⚠ Browser window closed, restarting...")
    #             try:
    #                 self.email_extractor._restart_driver()
    #             except:
    #                 print("      ✗ Failed to restart browser")
            
    #         return None

    # def process_author(self, author_name: str, affiliation: str = None) -> bool:
    #     """
    #     Process a single author through all APIs until their email is found.
    #     Saves all emails found, but only stops when searched author's email is found.
    #     Returns True if searched author's email was found, False otherwise.
    #     """
    #     normalized_author = self.normalize_author_name(author_name)
        
    #     # Check if email already found for this author
    #     if normalized_author in self.authors_with_emails:
    #         print(f"  ✓ Email already found for {author_name} (skipping)")
    #         self.stats['authors_skipped_existing'] += 1
    #         return True
        
    #     print(f"\n  Processing: {author_name}")
    #     if affiliation:
    #         print(f"  Affiliation: {affiliation}")
        
    #     # Try each API in sequence
    #     apis = [
    #         ('PubMed', self.search_pubmed),
    #         ('Semantic Scholar', self.search_semantic_scholar),
    #         ('OpenAlex', self.search_openalex)
    #     ]
        
    #     for api_name, search_func in apis:
    #         print(f"\n  → Searching {api_name}...")
            
    #         try:
    #             papers = search_func(author_name, affiliation)
    #         except Exception as e:
    #             print(f"    Error calling {api_name}: {str(e)}")
    #             papers = []
            
    #         # Ensure papers is a list
    #         if not isinstance(papers, list):
    #             print(f"    Warning: {api_name} returned non-list result, skipping")
    #             papers = []
            
    #         self.stats['api_usage'][api_name.lower().replace(' ', '_')] += 1
            
    #         if not papers:
    #             print(f"    No NEW papers found in {api_name}, trying next API...")
    #             continue
            
    #         print(f"    Found {len(papers)} NEW papers in {api_name}")
    #         self.stats['papers_searched'] += len(papers)
            
    #         # Scrape each paper
    #         for idx, paper in enumerate(papers, 1):
    #             # Validate paper object
    #             if not paper or not isinstance(paper, dict):
    #                 print(f"    [{idx}/{len(papers)}] Invalid paper object, skipping...")
    #                 continue
                
    #             # Validate required fields
    #             if 'title' not in paper or 'url' not in paper:
    #                 print(f"    [{idx}/{len(papers)}] Paper missing required fields, skipping...")
    #                 continue
                
    #             try:
    #                 title = paper.get('title', 'Unknown')[:60]
    #                 print(f"    [{idx}/{len(papers)}] Scraping: {title}...")
                    
    #                 result = self.scrape_paper_for_email(paper, author_name, affiliation or 'N/A')
                    
    #                 # Handle None result (skipped domains, errors, etc.)
    #                 if result is None:
    #                     print(f"      → No result from scraping, continuing...")
    #                     continue
                    
    #                 # Validate result is a dictionary
    #                 if not isinstance(result, dict):
    #                     print(f"      Warning: scrape_paper_for_email returned non-dict result")
    #                     continue
                    
    #                 # Save extraction (regardless of whether it's the searched author)
    #                 self.save_extraction_result(result)
                    
    #                 # Check if this was the searched author's email
    #                 if result.get('searched_author_email_found'):
    #                     print(f"    ✓ Found searched author's email!")
    #                     self.authors_with_emails.add(normalized_author)
    #                     self.stats['authors_with_emails'] += 1
                        
    #                     # Skip remaining papers for this author
    #                     remaining = len(papers) - idx
    #                     if remaining > 0:
    #                         print(f"    → Skipping {remaining} remaining paper(s) for {author_name}")
                        
    #                     return True
    #                 else:
    #                     # Emails found but not for searched author, continue to next paper
    #                     print(f"    → Continuing to next paper to find {author_name}'s email...")
                    
    #             except Exception as e:
    #                 print(f"      ✗ Error processing paper: {str(e)[:100]}")
    #                 continue
                
    #             time.sleep(2)  # Rate limiting between scrapes
            
    #         print(f"    Searched author's email not found in {api_name} papers, trying next API...")
    #         time.sleep(1)  # Delay between APIs
        
    #     print(f"  ⚠ Searched author's email not found for {author_name} in any API")
    #     return False
    def save_extraction_result(self, result: Dict):
        """Save extraction result to CSV with optimized row structure (single row per paper)."""
        authors = result.get('authors', [])
        emails = result.get('emails', [])
        
        # Create a single row with all data
        # Authors and emails are stored as semicolon-separated lists
        row = {
            'author_searched': result.get('author_searched', ''),
            'affiliation_searched': result.get('affiliation_searched', ''),
            'searched_author_found': 'Yes' if result.get('searched_author_email_found') else 'No',
            'matched_author': result.get('matched_author', ''),
            'matched_email': result.get('matched_email', ''),
            'url': result.get('url', ''),
            'paper_title': result.get('paper_title', ''),
            'paper_source': result.get('paper_source', ''),
            'paper_year': result.get('paper_year', ''),
            'paper_venue': result.get('paper_venue', ''),
            'extracted_title': result.get('title', ''),
            'all_authors': '; '.join(authors) if authors else '',
            'all_emails': '; '.join(emails) if emails else '',
            'extraction_method': result.get('extraction_method', ''),
            'status': result.get('status', '')
        }
        
        fieldnames = [
            'author_searched', 'affiliation_searched', 'searched_author_found',
            'matched_author', 'matched_email',
            'url', 'paper_title', 'paper_source', 'paper_year', 'paper_venue',
            'extracted_title', 'all_authors', 'all_emails',
            'extraction_method', 'status'
        ]
        
        filepath = os.path.join(self.output_dir, "integrated_results.csv")
        file_exists = os.path.isfile(filepath)
        
        with open(filepath, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
    
    def process_csv_file(self, input_csv: str):
        """Process authors from CSV file."""
        print(f"Reading input CSV: {input_csv}")
        
        try:
            df = pd.read_csv(input_csv)
            
            if 'author_name' not in df.columns:
                raise ValueError("CSV must contain 'author_name' column")
            
            has_affiliation = 'affiliation' in df.columns
            
            self.stats['total_authors'] = len(df)
            print(f"Found {len(df)} authors to process")
            
            if self.authors_with_emails:
                print(f"Already have emails for {len(self.authors_with_emails)} authors (will skip)")
            
            print("="*60)
            
            for idx, row in df.iterrows():
                author = row['author_name']
                affiliation = row['affiliation'] if has_affiliation and pd.notna(row['affiliation']) else None
                
                print(f"\n[{idx+1}/{len(df)}] " + "="*50)
                self.process_author(author, affiliation)
                
                if idx < len(df) - 1:
                    time.sleep(2)
            
            self.print_statistics()
            
        except FileNotFoundError:
            print(f"Error: File '{input_csv}' not found!")
        except Exception as e:
            print(f"Error processing CSV: {str(e)}")
            raise
    
    def print_statistics(self):
        """Print final statistics."""
        print("\n" + "="*60)
        print("FINAL STATISTICS")
        print("="*60)
        print(f"Total authors:            {self.stats['total_authors']}")
        print(f"Authors skipped (exist):  {self.stats['authors_skipped_existing']}")
        print(f"Authors with emails:      {self.stats['authors_with_emails']}")
        print(f"Papers searched:          {self.stats['papers_searched']}")
        print(f"Papers skipped (dup):     {self.stats['papers_skipped_duplicate']}")
        print(f"Papers scraped:           {self.stats['papers_scraped']}")
        print(f"Emails found:             {self.stats['emails_found']}")
        print(f"Wrong author emails:      {self.stats['wrong_author_emails']}")
        print(f"\nAPI Usage:")
        print(f"  PubMed:                 {self.stats['api_usage']['pubmed']}")
        print(f"  Semantic Scholar:       {self.stats['api_usage']['semantic_scholar']}")
        print(f"  OpenAlex:               {self.stats['api_usage']['openalex']}")
        
        if self.stats['total_authors'] > 0:
            success_rate = (self.stats['authors_with_emails'] / self.stats['total_authors']) * 100
            print(f"\nSuccess rate:             {success_rate:.1f}%")
        
        print("="*60)
        print(f"\n📁 Results saved to: {self.output_dir}/integrated_results.csv")
    
    def close(self):
        """Close the email extractor."""
        self.email_extractor.close()

# Main execution block:

if __name__ == "__main__":
    print("="*60)
    print("Integrated Paper Search & Email Extractor (OPTIMIZED)")
    print("Searches APIs sequentially and validates author emails")
    print("="*60)
    
    input_file = input("\nEnter path to CSV file (with 'author_name' and optional 'affiliation' columns): ").strip()
    
    # Remove headless input - always use visible browser
    headless = False
    
    # Remove existing results input - not needed anymore
    existing_file = None
    
    print("\n" + "="*60)
    print("Starting integrated search and extraction...")
    print("Browser will open in visible mode")
    print("="*60)
    
    extractor = IntegratedPaperSearchAndEmailExtractor(
        headless=headless,
        output_dir="results",
        existing_results_file=existing_file
    )
    
    try:
        extractor.process_csv_file(input_file)
    except KeyboardInterrupt:
        print("\n\nScript interrupted by user!")
        print("Partial results have been saved.")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            extractor.close()
        except:
            pass
    
    print("\n" + "="*60)
    print("Script complete!")
    print("="*60)
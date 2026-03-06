
######################################################
import scrapy
from scrapy import Request
import scrapy.utils.misc
import scrapy.core.scraper
def warn_on_generator_with_return_value_stub(spider, callable):
    pass


scrapy.utils.misc.warn_on_generator_with_return_value = warn_on_generator_with_return_value_stub
scrapy.core.scraper.warn_on_generator_with_return_value = warn_on_generator_with_return_value_stub
import pandas as pd
import re
from fuzzywuzzy import fuzz
from fuzzywuzzy import process
#from ncbi_pmc.selenium_driver.selenium_part import NCBI_Crawler

class PmcCrawlerSpider(scrapy.Spider):
    name = "pmc_crawler"
    allowed_domains = ["ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov"] #https://www.

    def __init__(self, name=name, filename = None, **kwargs):
        super().__init__(name, **kwargs)
        print(f"Filename in class Spider is {filename}")
        #print(f"User Agent for Scrapy is --> {agent}")
        #self.agent = {"User-Agent": agent}
        # self.rename_file = filename + "_" + str(page_no)
        self.rename_file = filename
        self.email_pattern = re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            re.IGNORECASE
        )
        # Pattern to extract author names from various contexts
        self.author_patterns = [
            # Pattern for "Name, Email: email@domain.com"
            re.compile(r'([A-Za-z\s\.]+?)(?:,\s*)?(?:Email|E-mail|email):\s*([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,})', re.IGNORECASE),
            # Pattern for email in parentheses after name
            re.compile(r'([A-Za-z\s\.]+?)\s*\(([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,})\)', re.IGNORECASE),
            # Pattern for email after semicolon
            re.compile(r'([A-Za-z\s\.]+?);\s*([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,})', re.IGNORECASE),
        ]
        #rename_file = filename + "_" + str(page_no)
    def start_requests(self):
        super().start_requests()
        #"{self.rename_file}" + "_urls.csv"
        with open(f"{self.rename_file}", "r", encoding="utf-8", newline="") as f:
            #start_urls = [url.strip() for url in f.readlines()]
            start_urls = ["https://pmc.ncbi.nlm.nih.gov/articles/" + url.strip() + "/" for url in f.readlines()]
        for url in start_urls:
            yield scrapy.Request(url, callback=self.parse,)#headers=self.headers
    

        
    @classmethod    
    def update_settings(cls, settings):
            settings.setdefault("FEEDS",{}).update(cls.custom_settings)
            #settings.setdefault("LOG_FILE",{}).update(cls.custom_settings)           
    

    def parse(self, response):
        """Main parsing method to extract emails and authors"""
        # Step 1: Extract all author names with their metadata (sup elements, positions)
        authors_data = self.extract_authors_with_metadata(response)
        authors_list = [author['name'] for author in authors_data]
        self.logger.info(f"Found {len(authors_list)} authors in .cg p section")
        
        # Step 2: Look for emails in section with id "_ci93_" (100% match score)
        contrib_section = response.css('section#_ci93_')
        emails_found = []
        
        if contrib_section:
            self.logger.info("Found contributor information section (#_ci93_)")
            emails_from_contrib = self.extract_emails_from_contrib_section(contrib_section, authors_data)
            
            if emails_from_contrib:
                self.logger.info(f"Found {len(emails_from_contrib)} emails in contributor section")
                emails_found.extend(emails_from_contrib)
                
                # Yield separate row for each email-author pair
                for email_data in emails_found:
                    yield {
                        'url': response.url,
                        'email': email_data['email'],
                        'author': email_data['author'],
                        'match_score': email_data['match_score'],
                        'source_section': email_data['source_section'],
                        'extraction_method': 'contributor_section',
                        'total_authors_found': len(authors_list),
                        'all_authors': '; '.join(authors_list) if authors_list else None
                    }
                return
        
        # Step 3: If no emails in contrib section, search other sections with advanced matching
        self.logger.info("Searching for emails in other HTML sections")
        emails_from_other_sections = self.extract_emails_from_document_with_scoring(response, authors_data)
        emails_found.extend(emails_from_other_sections)
        
        # Yield separate row for each email-author pair
        if emails_found:
            for email_data in emails_found:
                yield {
                    'url': response.url,
                    'email': email_data['email'],
                    'author': email_data['author'],
                    'match_score': email_data['match_score'],
                    'source_section': email_data['source_section'],
                    'extraction_method': 'document_wide_search',
                    'total_authors_found': len(authors_list),
                    'all_authors': '; '.join(authors_list) if authors_list else None
                }
        else:
            # If no emails found, still yield a row with author information
            yield {
                'url': response.url,
                'email': None,
                'author': None,
                'match_score': 0,
                'source_section': 'no_emails_found',
                'extraction_method': 'no_emails_found',
                'total_authors_found': len(authors_list),
                'all_authors': '; '.join(authors_list) if authors_list else None
            }
    
    def extract_authors_with_metadata(self, response):
        """Extract author names with their metadata (sup elements, positions)"""
        authors_data = []
        
        # Look for the specific .cg p section that contains author information
        cg_section = response.css('div.cg.p')
        
        if not cg_section:
            self.logger.warning("No .cg p section found")
            return authors_data
        
        # Extract authors from anchor links with span.name elements
        author_elements = cg_section.css('a[href*="pubmed.ncbi.nlm.nih.gov"]')
        
        for i, author_element in enumerate(author_elements):
            author_name = author_element.css('span.name.western::text').get()
            if author_name and author_name.strip():
                cleaned_name = self.clean_author_name(author_name.strip())
                if cleaned_name:
                    # Extract sup elements (affiliation numbers and symbols)
                    sup_elements = author_element.xpath('.//sup//text()').getall()
                    sup_content = ''.join(sup_elements).strip()
                    
                    # Check for mail icon or asterisk in surrounding elements
                    has_mail_icon = False
                    has_asterisk = False
                    
                    # Check for mail icon (✉) in following siblings
                    following_text = ' '.join(author_element.xpath('./following-sibling::text()').getall())
                    if '✉' in following_text:
                        has_mail_icon = True
                    
                    # Check for asterisk in sup elements or following text
                    if '*' in sup_content or '*' in following_text:
                        has_asterisk = True
                    
                    authors_data.append({
                        'name': cleaned_name,
                        'position': i,
                        'sup_content': sup_content,
                        'has_mail_icon': has_mail_icon,
                        'has_asterisk': has_asterisk,
                        'original_element': author_element
                    })
        
        return authors_data

    def extract_emails_from_contrib_section(self, contrib_section, authors_data):
        """Extract emails from contributor section with 100% match score"""
        emails_data = []
        
        # Extract from p elements in the contributor section
        for p_element in contrib_section.css('p'):
            p_text_clean = ' '.join(p_element.css('::text').getall())
            if not p_text_clean:
                continue
                
            # Look for emails in this paragraph
            emails_in_p = self.email_pattern.findall(p_text_clean)
            
            for email in emails_in_p:
                # Extract author name from the paragraph text
                author_name = self.extract_author_name_from_contrib_text(p_text_clean, email)
                
                emails_data.append({
                    'email': email,
                    'author': author_name,
                    'match_score': 100,  # 100% match score for _ci93_ section
                    'source_section': 'contributor_info'
                })
        
        return emails_data
    
    def extract_emails_from_document_with_scoring(self, response, authors_data):
        """Extract emails with advanced matching and scoring"""
        emails_data = []
        authors_list = [author['name'] for author in authors_data]
        
        # Strategy 1: Look for emails with initials in parentheses (100% match)
        correspondence_text = self.extract_correspondence_text(response)
        if correspondence_text:
            initials_matches = self.match_emails_with_initials(correspondence_text, authors_data)
            emails_data.extend(initials_matches)
        
        # Strategy 2: Match single email in correspondence section with * or mail icon authors (100% match)
        single_email_matches = self.match_single_email_with_special_authors(response, authors_data)
        emails_data.extend(single_email_matches)
        
        # Strategy 3: Extract emails from various sections and use fuzzy matching
        other_emails = self.extract_emails_from_sections(response)
        
        for email_info in other_emails:
            # Skip if already matched with high confidence
            if any(ed['email'].lower() == email_info['email'].lower() for ed in emails_data):
                continue
            
            # Use fuzzy matching to find best author match
            best_match = self.fuzzy_match_email_to_author(email_info['email'], authors_data)
            
            emails_data.append({
                'email': email_info['email'],
                'author': best_match['author'],
                'match_score': best_match['score'],
                'source_section': email_info['source_section']
            })
        
        return emails_data
    
    def extract_correspondence_text(self, response):
        """Extract correspondence section text that contains email-initial patterns"""
        correspondence_selectors = [
            '*[class*="correspondence"]',
            '*[class*="contact"]',
            '*[id*="cor"]',
            '.author-notes',
            '.d-panel',
            'p:contains("Correspondence")',
            'div:contains("Correspondence")'
        ]
        
        correspondence_text = ""
        for selector in correspondence_selectors:
            elements = response.css(selector)
            for element in elements:
                element_text = ' '.join(element.css('*::text').getall())
                correspondence_text += " " + element_text
        
        return correspondence_text.strip()
    
    def match_emails_with_initials(self, correspondence_text, authors_data):
        """Match emails that have initials in parentheses with authors (100% match score)"""
        matches = []
        
        # Pattern to find emails followed by initials in parentheses
        # e.g., "gxfeng2024@163.com (X.G.)"
        initials_pattern = re.compile(
            r'([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,})\s*\(([A-Z]\.(?:[A-Z]\.)*)\)',
            re.IGNORECASE
        )
        
        initials_matches = initials_pattern.findall(correspondence_text)
        
        for email, initials in initials_matches:
            # Match initials with author names
            matched_author = self.match_initials_to_author(initials, authors_data)
            
            if matched_author:
                matches.append({
                    'email': email,
                    'author': matched_author,
                    'match_score': 100,  # 100% confidence for initial matching
                    'source_section': 'correspondence_with_initials'
                })
            else:
                # If no exact initial match, still record with lower confidence
                matches.append({
                    'email': email,
                    'author': None,
                    'match_score': 50,  # Lower confidence when initials don't match
                    'source_section': 'correspondence_with_unmatched_initials'
                })
        
        return matches
    
    def match_initials_to_author(self, initials, authors_data):
        """Match initials like 'X.G.' to author names"""
        # Remove dots and convert to uppercase
        clean_initials = initials.replace('.', '').upper()
        
        for author_data in authors_data:
            author_name = author_data['name']
            name_parts = author_name.split()
            
            if len(name_parts) >= len(clean_initials):
                # Generate initials from author name
                author_initials = ''.join([part[0].upper() for part in name_parts[:len(clean_initials)]])
                
                if author_initials == clean_initials:
                    return author_name
                
                # Also try different combinations (first name + last name, etc.)
                if len(name_parts) >= 2:
                    # Try first + last name initials
                    first_last_initials = name_parts[0][0].upper() + name_parts[-1][0].upper()
                    if first_last_initials == clean_initials:
                        return author_name
        
        return None
    
    def match_single_email_with_special_authors(self, response, authors_data):
        """Match single email in correspondence with authors having * or mail icon (100% match)"""
        matches = []
        
        # Find correspondence sections
        correspondence_elements = response.css('*:contains("Correspondence"), *[class*="correspondence"], *[class*="contact"]')
        
        for element in correspondence_elements:
            element_text = ' '.join(element.css('*::text').getall())
            emails_in_element = self.email_pattern.findall(element_text)
            
            # If exactly one email found, try to match with special authors
            if len(emails_in_element) == 1:
                email = emails_in_element[0]
                
                # Find authors with asterisk or mail icon
                special_authors = [
                    author for author in authors_data 
                    if author['has_asterisk'] or author['has_mail_icon']
                ]
                
                if len(special_authors) == 1:
                    # Perfect match: one email, one special author
                    matches.append({
                        'email': email,
                        'author': special_authors[0]['name'],
                        'match_score': 100,
                        'source_section': 'single_email_special_author'
                    })
                elif len(special_authors) > 1:
                    # Multiple special authors, use fuzzy matching
                    best_match = self.fuzzy_match_email_to_author(email, special_authors)
                    matches.append({
                        'email': email,
                        'author': best_match['author'],
                        'match_score': min(90, best_match['score']),  # Cap at 90% for multiple candidates
                        'source_section': 'single_email_multiple_special_authors'
                    })
        
        return matches
    
    def extract_emails_from_sections(self, response):
        """Extract emails from various sections for fuzzy matching"""
        emails_info = []
        
        # Define sections to search
        sections = [
            {'selector': '*[class*="correspondence"]', 'name': 'correspondence'},
            {'selector': '*[class*="contact"]', 'name': 'contact'},
            {'selector': '*[id*="cor"]', 'name': 'correspondence_by_id'},
            {'selector': 'div.fn', 'name': 'footnote'},
            {'selector': '.author-notes', 'name': 'author_notes'},
            {'selector': '.d-panel', 'name': 'd_panel'},
            {'selector': 'body', 'name': 'document_wide'}  # Fallback to entire document
        ]
        
        found_emails = set()
        
        for section in sections:
            elements = response.css(section['selector'])
            for element in elements:
                element_text = ' '.join(element.css('*::text').getall())
                emails_in_element = self.email_pattern.findall(element_text)
                
                for email in emails_in_element:
                    if email.lower() not in found_emails:
                        found_emails.add(email.lower())
                        emails_info.append({
                            'email': email,
                            'source_section': section['name']
                        })
        
        return emails_info
    
    def fuzzy_match_email_to_author(self, email, authors_data):
        """Use fuzzy matching to match email with author names"""
        if not authors_data:
            return {'author': None, 'score': 0}
        
        email_local = email.split('@')[0].lower()
        author_names = [author['name'] if isinstance(author, dict) else author for author in authors_data]
        
        best_score = 0
        best_author = None
        
        for i, author_data in enumerate(authors_data):
            author_name = author_data['name'] if isinstance(author_data, dict) else author_data
            
            # Try different matching strategies
            scores = []
            
            # 1. Full name fuzzy match
            normalized_name = self.normalize_name_for_matching(author_name)
            scores.append(fuzz.partial_ratio(email_local, normalized_name))
            
            # 2. Individual name parts
            name_parts = normalized_name.split()
            for part in name_parts:
                if len(part) >= 3:  # Only consider meaningful parts
                    scores.append(fuzz.ratio(email_local, part))
            
            # 3. Initials + last name
            if len(name_parts) >= 2:
                initials_lastname = name_parts[0][0] + name_parts[-1]
                scores.append(fuzz.ratio(email_local, initials_lastname))
            
            # 4. First name + last name concatenated
            if len(name_parts) >= 2:
                first_last = name_parts[0] + name_parts[-1]
                scores.append(fuzz.partial_ratio(email_local, first_last))
            
            # Take the best score for this author
            max_score = max(scores) if scores else 0
            
            # Boost score if author has special markers (asterisk or mail icon)
            if isinstance(author_data, dict) and (author_data.get('has_asterisk') or author_data.get('has_mail_icon')):
                max_score = min(100, max_score + 15)  # Boost by 15 points, cap at 100
            
            if max_score > best_score:
                best_score = max_score
                best_author = author_name
        
        return {'author': best_author, 'score': best_score}
    
    def extract_author_name_from_contrib_text(self, text, email):
        """Extract author name directly from contributor section text"""
        # Common patterns in #_ci93_ section:
        # "Author Name, Email: email@domain.com"
        # "Author Name: email@domain.com"  
        # "Author Name, email@domain.com"
        
        patterns = [
            # "Author Name, Email: email@domain.com"
            rf'^([^,]+?)(?:,\s*)?(?:Email|E-mail|email):\s*{re.escape(email)}',
            # "Author Name, email@domain.com"  
            rf'^([^,]+?)(?:,\s*){re.escape(email)}',
            # "Author Name: email@domain.com"
            rf'^([^:]+?):\s*{re.escape(email)}',
            # Just "Author Name" at the beginning, email somewhere after
            rf'^([A-Za-z\s\.]+?)(?:\.|,|:).*?{re.escape(email)}'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text.strip(), re.IGNORECASE)
            if match:
                potential_name = match.group(1).strip()
                cleaned_name = self.clean_author_name(potential_name)
                if self.is_valid_author_name(cleaned_name):
                    return cleaned_name
        
        return None

    def normalize_name_for_matching(self, name):
        """Normalize name for better matching by handling special characters"""
        if not name:
            return ""
        
        # Convert to lowercase
        normalized = name.lower()
        
        # Handle common character substitutions
        char_mappings = {
            'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss',
            'á': 'a', 'à': 'a', 'â': 'a', 'ã': 'a', 'å': 'a',
            'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
            'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
            'ó': 'o', 'ò': 'o', 'ô': 'o', 'õ': 'o', 'ø': 'o',
            'ú': 'u', 'ù': 'u', 'û': 'u', 'ý': 'y', 'ÿ': 'y',
            'ñ': 'n', 'ç': 'c'
        }
        
        for special_char, replacement in char_mappings.items():
            normalized = normalized.replace(special_char, replacement)
        
        # Remove punctuation and extra spaces
        import string
        normalized = ''.join(char if char.isalnum() or char.isspace() else ' ' for char in normalized)
        normalized = ' '.join(normalized.split())  # Remove extra spaces
        
        return normalized
    
    def clean_author_name(self, name):
        """Clean and format author name"""
        if not name:
            return None
            
        # Remove extra whitespace and common prefixes/suffixes
        name = re.sub(r'\s+', ' ', name.strip())
        name = re.sub(r'^(Dr\.|Prof\.|Mr\.|Ms\.|Mrs\.)\s*', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s*(,\s*(Jr\.|Sr\.|PhD|MD|Ph\.D\.|M\.D\.))$', '', name, flags=re.IGNORECASE)
        
        return name.strip() if name.strip() else None
    
    def is_valid_author_name(self, name):
        """Validate if the extracted text is likely an author name"""
        if not name or len(name) < 2:
            return False
        
        # Check if it contains at least one letter
        if not re.search(r'[A-Za-z]', name):
            return False
        
        # Reject if it's mostly numbers or special characters
        if len(re.sub(r'[A-Za-z\s\.]', '', name)) > len(name) * 0.3:
            return False
        
        # Reject single word names that are too short (like "mail", "to", etc.)
        words = name.strip().split()
        if len(words) == 1 and len(words[0]) < 4:
            return False
            
        # Reject common non-name phrases and words
        non_name_phrases = [
            'correspondence', 'email', 'e-mail', 'contact', 'author', 'information',
            'department', 'university', 'institute', 'center', 'centre',
            'mail', 'addressed', 'should', 'be', 'to', 'the', 'and', 'or', 'of',
            'japan', 'tokyo', 'wako', 'saitama', 'riken', 'bikaken'
        ]
        
        name_lower = name.lower().strip()
        for phrase in non_name_phrases:
            if phrase.lower() == name_lower or phrase.lower() in name_lower.split():
                return False
        
        # Must contain at least one capital letter (proper names)
        if not re.search(r'[A-Z]', name):
            return False
        
        # Should look like a person's name (at least 2 characters, contains letters)
        if len(name.strip()) < 2:
            return False
            
        return True
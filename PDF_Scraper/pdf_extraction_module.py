#!/usr/bin/env python3
"""
PDF Author and Affiliation Extraction Module
Modular, class-based implementation for integration with automated systems
"""

import os
import json
import re
import csv
import tempfile
import shutil
import logging
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

import fitz

try:
    from PyPDF2 import PdfReader, PdfWriter
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False

try:
    import pymupdf.layout
    import pymupdf4llm
    PYMUPDF4LLM_AVAILABLE = True
except ImportError:
    PYMUPDF4LLM_AVAILABLE = False

try:
    import pymupdf
    pymupdf4llm
    PYMUPDF4LLM_AVAILABLE = True
except ImportError:
    PYMUPDF4LLM_AVAILABLE = False

try:
    from grobid_client.grobid_client import GrobidClient
    from lxml import etree
    GROBID_AVAILABLE = True
except ImportError:
    GrobidClient = None  # keeps type hints valid when package is absent
    etree = None
    GROBID_AVAILABLE = False


# ==================== MODULE LOGGER ====================
_log = logging.getLogger('pdf_extraction')


def _setup_file_logger(log_path: Path) -> None:
    """Attach a FileHandler to the module logger so every debug line is saved."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if any(
        isinstance(h, logging.FileHandler)
        and getattr(h, 'baseFilename', '') == str(log_path.resolve())
        for h in _log.handlers
    ):
        return
    fh = logging.FileHandler(str(log_path), mode='a', encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S'))
    _log.addHandler(fh)
    _log.setLevel(logging.DEBUG)
    _log.debug('--- pdf_extraction_module logger attached to %s ---', log_path)


# ==================== CONFIGURATION ====================
@dataclass
class ExtractionConfig:
    """Configuration for PDF extraction"""
    output_dir: Path = Path("output")
    temp_pages_dir: Path = Path("temp_pages")
    temp_tei_dir: Path = Path("temp_tei")
    grobid_server: str = "http://localhost:8070"
    log_path: Optional[Path] = None   # if set, debug log is written here
    
    def __post_init__(self):
        # Convert strings to Path objects
        self.output_dir = Path(self.output_dir)
        self.temp_pages_dir = Path(self.temp_pages_dir)
        self.temp_tei_dir = Path(self.temp_tei_dir)
        
        # Create directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_pages_dir.mkdir(parents=True, exist_ok=True)
        self.temp_tei_dir.mkdir(parents=True, exist_ok=True)

        # Activate file logger if a path was supplied
        if self.log_path is not None:
            _setup_file_logger(Path(self.log_path))


# ==================== CONSTANTS ====================
class ExtractionConstants:
    """Centralized constants for extraction"""
    
    COUNTRIES = {
        'USA', 'UK', 'CANADA', 'BRAZIL', 'INDIA', 'JAPAN', 'SPAIN', 'ITALY',
        'PORTUGAL', 'TURKEY', 'NORWAY', 'ICELAND', 'QATAR', 'JORDAN', 'KOREA',
        'REPUBLIC OF KOREA', 'SOUTH AFRICA', 'AUSTRALIA', 'IRELAND', 'FINLAND',
        'CZECH REPUBLIC', 'TANZANIA', 'LESOTHO', 'PUERTO RICO', 'DENMARK',
        'THAILAND', 'UAE', 'NEW ZEALAND', 'UNITED KINGDOM', 'UNITED STATES',
        'GERMANY', 'FRANCE', 'CHINA', 'SWITZERLAND', 'AUSTRIA', 'NETHERLANDS',
        'BELGIUM', 'SWEDEN', 'POLAND', 'GREECE', 'ISRAEL', 'SINGAPORE'
    }
    
    INSTITUTION_KEYWORDS = [
        'UNIVERSITY', 'HOSPITAL', 'COLLEGE', 'INSTITUTE', 'SCHOOL',
        'CENTER', 'CENTRE', 'HEALTH', 'MEDICAL', 'FOUNDATION', 'CLINIC',
        'DEPARTMENT', 'FACULTY', 'RESEARCH', 'LABORATORY', 'LABS', 'TRUST'
    ]
    
    SKIP_TERMS = [
        'CONTENTS', 'WELCOME', 'SPEAKER', 'FACULTY', 'AGENDA', 'CONFERENCE',
        'WORKSHOP', 'SESSION', 'KEYNOTE', 'POSTER', 'ABSTRACT', 'BIOGRAPHY',
        'INTRODUCTION', 'METHODS', 'RESULTS', 'CONCLUSION', 'BACKGROUND'
    ]


# ==================== CSV WRITER ====================
class ImmediateCSVWriter:
    """Immediate CSV writer for author data"""
    
    def __init__(self, output_path: Path):
        self.output_path = output_path
        self.fieldnames = [
            'original_pdf', 'page_number', 'author_name',
            'affiliation', 'extraction_method'
        ]
        
        # Create file with header if it doesn't exist
        if not output_path.exists():
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                writer.writeheader()
    
    def write_authors(self, authors: List[Dict]) -> None:
        """Write authors to CSV, filtering out those without affiliations"""
        if not authors:
            return
        
        # Filter and clean
        valid_authors = []
        for author in authors:
            # Clean text
            author['author_name'] = re.sub(r'\s+', ' ', author['author_name']).strip()
            author['affiliation'] = re.sub(r'\s+', ' ', author['affiliation']).strip()
            
            # Only keep if affiliation exists
            if author['affiliation'] and len(author['affiliation']) > 2:
                valid_authors.append(author)
        
        if not valid_authors:
            return
        
        # Append to CSV
        with open(self.output_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            writer.writerows(valid_authors)


# ==================== ENHANCED VALIDATION UTILITIES ====================
class ValidationUtils:
    """Static validation methods"""
    
    @staticmethod
    def is_valid_name(text: str) -> bool:
        """Validate proper Title Case name"""
        if not text or len(text) < 5 or len(text) > 100:
            return False
        
        # CRITICAL FIX: Reject any name containing a comma
        # Commas indicate either location data or multiple names in one string
        if ',' in text:
            return False
        
        # Remove credentials
        text_clean = re.sub(r'\s+(MD|PhD|MPH|RN|MSN|BSN|CHES)', '', text, flags=re.IGNORECASE)
        
        # No special characters (including @)
        if re.search(r'[?:(){}[\]!#%^0-9•\*→·@]', text_clean):
            return False
        
        words = text_clean.split()
        if len(words) < 2 or len(words) > 8:
            return False
        
        # No ALL CAPS
        caps_words = [w for w in words if w.isalpha() and len(w) > 1]
        if caps_words and all(w.isupper() for w in caps_words):
            return False
        
        # Check for lowercase words (except common particles)
        allowed_lowercase = {'de', 'van', 'von', 'del', 'della', 'da', 'le', 'la', 'di', 'du', 'des'}
        for word in words:
            if len(word) > 1 and word.isalpha() and word.islower():
                if word.lower() not in allowed_lowercase:
                    return False
        
        # Must have 2+ capitalized words
        if sum(1 for w in words if w and w[0].isupper()) < 2:
            return False
        
        # No institutional keywords
        if any(kw in text.upper() for kw in ExtractionConstants.INSTITUTION_KEYWORDS):
            return False
        
        if any(term in text.upper() for term in ExtractionConstants.SKIP_TERMS):
            return False
        
        return True
    
    @staticmethod
    def is_country(text: str) -> bool:
        """Check if text is a country name"""
        text_clean = text.strip().rstrip(',').upper()
        return (text_clean in ExtractionConstants.COUNTRIES or 
                any(c in text.upper() for c in ExtractionConstants.COUNTRIES))
    
    @staticmethod
    def should_skip_block(text: str) -> bool:
        """Check if text block should be skipped"""
        if not text or len(text) > 200 or len(text) < 3:
            return True
        if re.search(r'^\d{1,3}[,.]?\s*$', text):
            return True
        if text.isupper() and len(text.split()) > 2:
            return True
        if any(term in text.upper() for term in ExtractionConstants.SKIP_TERMS):
            return True
        return False
    
    @staticmethod
    def clean_name(name: str) -> str:
        """Clean author name"""
        name = re.sub(r'[\*\d]+$', '', name)
        name = re.sub(r',?\s+(MD|PhD|MPH|RN|MSN|BSN)', '', name, flags=re.IGNORECASE)
        return re.sub(r'\s+', ' ', name).strip()
    
    @staticmethod
    def clean_text(text: str) -> str:
        """Remove newlines and normalize spaces"""
        return re.sub(r'\s+', ' ', text).strip()

# ==================== PDF UTILITIES ====================
class PDFUtils:
    """PDF-related utility functions"""
    
    @staticmethod
    def has_images(pdf_path: Path) -> bool:
        """Check if PDF page contains images"""
        try:
            doc = fitz.open(pdf_path)
            for page in doc:
                if page.get_images():
                    doc.close()
                    return True
            doc.close()
            return False
        except:
            return False
    
    @staticmethod
    def has_extractable_text(pdf_path: Path) -> bool:
        """Check if PDF has extractable text"""
        try:
            doc = fitz.open(pdf_path)
            for page in doc:
                text = page.get_text().strip()
                if text and len(text) > 50:
                    doc.close()
                    return True
            doc.close()
            return False
        except:
            return False
    
    @staticmethod
    def split_pdf_pages(pdf_path: Path, output_dir: Path) -> List[Dict]:
        """Split PDF into individual pages (PyPDF2 preferred, fitz fallback)"""
        page_files = []
        pdf_name = pdf_path.stem

        if PYPDF2_AVAILABLE:
            try:
                reader = PdfReader(pdf_path)
                for page_num in range(len(reader.pages)):
                    writer = PdfWriter()
                    writer.add_page(reader.pages[page_num])
                    page_filename = f"{pdf_name}_page_{page_num+1:03d}.pdf"
                    page_path = output_dir / page_filename
                    with open(page_path, 'wb') as f:
                        writer.write(f)
                    page_files.append({
                        'page_path': page_path,
                        'page_number': page_num + 1,
                        'original_pdf': pdf_path.name
                    })
                return page_files
            except Exception as e:
                print(f"⚠ PyPDF2 split failed ({e}), trying fitz fallback…")

        # fitz (PyMuPDF) fallback
        try:
            doc = fitz.open(str(pdf_path))
            for page_num in range(len(doc)):
                page_filename = f"{pdf_name}_page_{page_num+1:03d}.pdf"
                page_path = output_dir / page_filename
                new_doc = fitz.open()
                new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
                new_doc.save(str(page_path))
                new_doc.close()
                page_files.append({
                    'page_path': page_path,
                    'page_number': page_num + 1,
                    'original_pdf': pdf_path.name
                })
            doc.close()
            return page_files
        except Exception as e:
            print(f"❌ Error splitting PDF: {e}")
            return []


# ==================== EXTRACTION PARSERS ====================
class ExtractionParsers:
    """Parsers for different author formats with enhanced comma handling"""
    
    @staticmethod
    def extract_multiline_author(text: str) -> Optional[Dict]:
        """Extract author from multiline text block"""
        text = _norm(text)  # normalise superscripts before any processing
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if len(lines) < 2:
            return None
        
        name = ValidationUtils.clean_name(lines[0])
        
        # Reject only if the first line is NOT a valid name AND has a comma
        # (i.e. it is a multi-author comma list handled elsewhere)
        if ',' in lines[0] and not ValidationUtils.is_valid_name(name):
            return None
        
        if not ValidationUtils.is_valid_name(name):
            return None
        
        affiliations = []
        for line in lines[1:]:
            line_clean = re.sub(r'^[\*\d\s]+', '', line).strip()
            if line_clean and len(line_clean) > 2:
                affiliations.append(line_clean)
        
        if not affiliations:
            return None
        
        return {
            'name': name,
            'affiliation': ValidationUtils.clean_text(' '.join(affiliations))
        }
    
    @staticmethod
    def parse_numbered_authors(text: str) -> List[Tuple[str, Optional[str]]]:
        """Parse comma-separated authors with superscript numbers"""
        text = _norm(text)  # convert ¹²³ → 123 before regex
        cleaned = re.sub(r'(Dr\.|Prof\.|Dra?\.)\ *', '', text, flags=re.IGNORECASE)
        parts = [p.strip() for p in cleaned.split(',') if p.strip()]
        
        authors = []
        for part in parts:
            part = part.replace('*', '').strip()
            
            # Extract name and number
            match = re.search(r'^(.+?)\s*([\d,]+)\s*$', part)
            
            if match:
                name = ValidationUtils.clean_name(match.group(1))
                # Validate BEFORE adding
                if ValidationUtils.is_valid_name(name):
                    authors.append((name, match.group(2)))
            else:
                name = ValidationUtils.clean_name(part)
                # Validate BEFORE adding
                if ValidationUtils.is_valid_name(name):
                    authors.append((name, None))
        
        return authors
    
    @staticmethod
    def parse_comma_separated_simple(text: str) -> List[str]:
        """
        NEW: Parse simple comma-separated author list (no numbers)
        Example: "Mary L. Perrin, Teresa Kim, Rodica Stan, Pamela Giesie"
        """
        text = _norm(text)  # convert ¹²³ → 123 before regex
        # Remove common prefixes
        cleaned = re.sub(r'(Dr\.|Prof\.|Dra?\.)\ *', '', text, flags=re.IGNORECASE)
        
        # Split by comma
        parts = [p.strip() for p in cleaned.split(',') if p.strip()]
        
        # Validate each part as a name
        valid_names = []
        for part in parts:
            name = ValidationUtils.clean_name(part)
            # Must pass validation AND not contain comma
            if ValidationUtils.is_valid_name(name) and ',' not in name:
                valid_names.append(name)
        
        # Only return if we got multiple valid names (indicates real list)
        if len(valid_names) >= 2:
            return valid_names
        
        return []


# ==================== GROBID EXTRACTOR ====================
# ==================== FIXED GROBID EXTRACTOR ====================
class GrobidExtractor:
    """GROBID-based extraction with comma-separated name handling"""
    
    def __init__(self, grobid_client, temp_tei_dir: Path):
        self.grobid_client = grobid_client
        self.temp_tei_dir = temp_tei_dir
    
    def process_page(self, page_path: Path) -> bool:
        """Process page with GROBID"""
        _log.debug('GROBID process_page: %s', page_path.name)

        has_text = PDFUtils.has_extractable_text(page_path)
        _log.debug('  has_extractable_text=%s', has_text)
        if not has_text:
            _log.debug('  SKIPPED — no extractable text')
            return False
        
        try:
            import sys
            from io import StringIO
            
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = StringIO()
            sys.stderr = StringIO()
            
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_page_dir = Path(temp_dir)
                    temp_page_file = temp_page_dir / page_path.name
                    shutil.copy(page_path, temp_page_file)
                    
                    _log.debug('  calling grobid_client.process(processHeaderDocument) '
                               'input=%s output=%s', temp_page_dir, self.temp_tei_dir)
                    self.grobid_client.process(
                        service="processHeaderDocument",
                        input_path=str(temp_page_dir),
                        output=str(self.temp_tei_dir),
                        n=1,
                        consolidate_header=True,
                        include_raw_affiliations=True,
                        tei_coordinates=True,
                        force=True
                    )
                    _log.debug('  grobid_client.process() returned')

                    possible_names = [
                        self.temp_tei_dir / f"{page_path.stem}.tei.xml",
                        self.temp_tei_dir / f"{page_path.stem}.grobid.tei.xml",
                        self.temp_tei_dir / f"{page_path.name}.tei.xml"
                    ]
                    _log.debug('  checking TEI candidates: %s',
                               [p.name for p in possible_names])
                    
                    for tei_file in possible_names:
                        if tei_file.exists():
                            _log.debug('  TEI FOUND: %s (size=%d bytes)',
                                       tei_file.name, tei_file.stat().st_size)
                            return True
                    
                    # List all files actually in tei dir for diagnosis
                    actual = list(self.temp_tei_dir.iterdir()) if self.temp_tei_dir.exists() else []
                    _log.warning('  TEI NOT FOUND — GROBID wrote nothing for %s. '
                                 'tei_dir contents: %s',
                                 page_path.name,
                                 [f.name for f in actual[:20]])
                    return False
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr
        except Exception as exc:
            _log.error('GROBID process_page EXCEPTION for %s: %s', page_path.name, exc,
                       exc_info=True)
            return False
    
    def extract_authors(self, page_path: Path, page_number: int, 
                       original_pdf: str) -> List[Dict]:
        """Extract authors from GROBID TEI with comma-list detection"""
        authors = []
        _log.debug('extract_authors: %s', page_path.name)

        possible_tei_files = [
            self.temp_tei_dir / f"{page_path.stem}.tei.xml",
            self.temp_tei_dir / f"{page_path.stem}.grobid.tei.xml",
            self.temp_tei_dir / f"{page_path.name}.tei.xml"
        ]
        tei_file = None
        for tf in possible_tei_files:
            if tf.exists():
                tei_file = tf
                break
        
        if not tei_file:
            _log.warning('extract_authors: no TEI file for %s — skipping', page_path.name)
            return authors
        
        _log.debug('extract_authors: parsing %s', tei_file.name)
        try:
            tree = etree.parse(str(tei_file))
            root = tree.getroot()
            ns = {'tei': 'http://www.tei-c.org/ns/1.0'}
            
            author_nodes = root.xpath('//tei:sourceDesc//tei:author', namespaces=ns)
            if not author_nodes:
                author_nodes = root.xpath('//tei:fileDesc//tei:author', namespaces=ns)
            if not author_nodes:
                author_nodes = root.xpath('//tei:analytic//tei:author', namespaces=ns)
            _log.debug('  found %d author node(s) in TEI', len(author_nodes))
            
            for author in author_nodes:
                # Extract name components
                forename = author.xpath('.//tei:persName/tei:forename/text()', namespaces=ns)
                surname = author.xpath('.//tei:persName/tei:surname/text()', namespaces=ns)
                
                name_parts = [f.strip() for f in forename if f.strip()]
                name_parts.extend([s.strip() for s in surname if s.strip()])
                full_name = ' '.join(name_parts).strip()
                
                if not full_name or len(full_name) < 3:
                    _log.debug('  REJECTED (too short): %r', full_name)
                    continue
                
                full_name = ValidationUtils.clean_name(full_name)
                
                # CRITICAL FIX: Detect if GROBID merged comma-separated names
                surname_text = ' '.join([s.strip() for s in surname if s.strip()])
                if ',' in surname_text:
                    _log.debug('  REJECTED (comma in surname — merged list): %r', surname_text)
                    continue
                
                if not ValidationUtils.is_valid_name(full_name):
                    _log.debug('  REJECTED (is_valid_name=False): %r', full_name)
                    continue
                
                # Extract affiliation
                aff_parts = []
                for aff in author.xpath('.//tei:affiliation', namespaces=ns):
                    raw = aff.xpath('.//tei:note[@type="raw_affiliation"]/text()', namespaces=ns)
                    if raw:
                        raw_text = ' '.join([r.strip() for r in raw if r.strip()])
                        raw_text = re.sub(r'^\d+\s*', '', raw_text).strip()
                        if raw_text:
                            aff_parts.append(raw_text)
                    else:
                        dept = aff.xpath('.//tei:orgName[@type="department"]/text()', namespaces=ns)
                        inst = aff.xpath('.//tei:orgName[@type="institution"]/text()', namespaces=ns)
                        org = aff.xpath('.//tei:orgName/text()', namespaces=ns)
                        city = aff.xpath('.//tei:address/tei:settlement/text()', namespaces=ns)
                        country = aff.xpath('.//tei:address/tei:country/text()', namespaces=ns)
                        
                        aff_parts.extend([d.strip() for d in dept if d.strip()])
                        aff_parts.extend([i.strip() for i in inst if i.strip()])
                        if not inst:
                            aff_parts.extend([o.strip() for o in org if o.strip()])
                        aff_parts.extend([c.strip() for c in city if c.strip()])
                        aff_parts.extend([c.strip() for c in country if c.strip()])
                
                affiliation = ValidationUtils.clean_text(', '.join(dict.fromkeys(aff_parts)))
                
                if affiliation and len(affiliation) > 5:
                    _log.debug('  ACCEPTED: name=%r  affil=%r', full_name, affiliation[:80])
                    authors.append({
                        'original_pdf': original_pdf,
                        'page_number': page_number,
                        'author_name': full_name,
                        'affiliation': affiliation,
                        'extraction_method': 'grobid'
                    })
                else:
                    _log.debug('  SKIPPED (no/short affil): name=%r  affil=%r',
                               full_name, affiliation)
        except Exception as e:
            _log.error('extract_authors XML parse error for %s: %s', tei_file.name, e,
                       exc_info=True)
        
        _log.debug('extract_authors: returning %d author(s) from %s',
                   len(authors), page_path.name)
        return authors


# ==================== FIXED PYMUPDF4LLM EXTRACTOR ====================
class PyMuPDF4LLMExtractor:
    """PyMuPDF4LLM JSON-based extraction with improved name validation"""
    
    @staticmethod
    def extract_authors(page_path: Path, page_number: int, 
                       original_pdf: str) -> List[Dict]:
        """Extract authors using pymupdf4llm JSON output with enhanced validation"""
        authors = []
        if not PYMUPDF4LLM_AVAILABLE:
            return authors
        
        try:
            import pymupdf
            doc = pymupdf.open(str(page_path))
            page_json_str = pymupdf4llm.to_json(doc)
            doc.close()
            
            page_data = json.loads(page_json_str)
            pages = page_data.get('pages', [])
            if not pages:
                return authors
            
            page = pages[0]
            boxes = page.get('boxes', [])
            
            for box in boxes:
                box_class = box.get('boxclass', '').lower()
                if box_class not in ('caption', 'text'):
                    continue
                
                textlines = box.get('textlines', [])
                if not textlines:
                    continue
                
                first_line_spans = textlines[0].get('spans', [])
                name_text = ''
                for sp in first_line_spans:
                    t = sp.get('text', '').strip()
                    if t:
                        name_text = t
                        break
                
                if not name_text:
                    continue
                
                name_text = ValidationUtils.clean_name(name_text)
                
                if not ValidationUtils.is_valid_name(name_text):
                    continue
                
                aff_parts = []
                for tl in textlines[1:]:
                    for sp in tl.get('spans', []):
                        s = sp.get('text', '').strip()
                        if s:
                            aff_parts.append(s)
                
                affiliation = ValidationUtils.clean_text(' '.join(aff_parts))
                
                if affiliation and len(affiliation) > 5:
                    authors.append({
                        'original_pdf': original_pdf,
                        'page_number': page_number,
                        'author_name': name_text,
                        'affiliation': affiliation,
                        'extraction_method': 'pymupdf4llm_json'
                    })
        
        except Exception:
            return []
        
        return authors


# ==================== PYMUPDF EXTRACTOR ====================
class PyMuPDFExtractor:
    """PyMuPDF block-based extraction with comma-list support"""
    
    @staticmethod
    def extract_authors(page_path: Path, page_number: int, 
                       original_pdf: str) -> List[Dict]:
        """Extract authors using PyMuPDF blocks with comma handling"""
        authors = []
        
        try:
            doc = fitz.open(page_path)
            blocks_raw = doc[0].get_text("blocks")
            doc.close()
            
            blocks = [{"text": b[4].strip()} for b in blocks_raw if b[4].strip()]
            
            i = 0
            while i < len(blocks):
                text = blocks[i]['text']
                
                if ValidationUtils.should_skip_block(text):
                    i += 1
                    continue
                
                # Normalise Unicode superscripts before any regex checks
                text_norm = _norm(text)

                # Try parsing as simple comma-separated list FIRST
                if ',' in text and '\n' not in text:
                    simple_names = ExtractionParsers.parse_comma_separated_simple(text_norm)
                    if simple_names:
                        affiliations = []
                        for j in range(1, 5):
                            if i + j >= len(blocks):
                                break
                            next_text = blocks[i + j]['text']
                            if ValidationUtils.should_skip_block(next_text):
                                break
                            if ValidationUtils.is_valid_name(next_text) or ',' in next_text:
                                break
                            next_clean = ValidationUtils.clean_text(
                                re.sub(r'^[\d\*\s]+', '', next_text)
                            )
                            if next_clean and len(next_clean) > 5:
                                affiliations.append(next_clean)
                            if ValidationUtils.is_country(next_text):
                                break
                        
                        if affiliations:
                            shared_aff = ValidationUtils.clean_text(' '.join(affiliations))
                            for name in simple_names:
                                authors.append({
                                    'original_pdf': original_pdf,
                                    'page_number': page_number,
                                    'author_name': name,
                                    'affiliation': shared_aff,
                                    'extraction_method': 'pymupdf'
                                })
                        i += 1
                        continue
                
                # Multiline author block
                if '\n' in text:
                    result = ExtractionParsers.extract_multiline_author(text)
                    if result:
                        authors.append({
                            'original_pdf': original_pdf,
                            'page_number': page_number,
                            'author_name': result['name'],
                            'affiliation': result['affiliation'],
                            'extraction_method': 'pymupdf'
                        })
                    i += 1
                    continue
                
                # Numbered authors
                if ',' in text_norm and re.search(r'[A-Z][a-z]+.*[\d\*]', text_norm):
                    parsed = ExtractionParsers.parse_numbered_authors(text_norm)
                    if parsed and len(parsed) >= 2:
                        affiliations_map = {}
                        for j in range(1, 10):
                            if i + j >= len(blocks):
                                break
                            next_text = blocks[i + j]['text']
                            match = re.match(r'^(\d+,?)\s*(.+)$', next_text)
                            if match:
                                nums = match.group(1)
                                aff_text = ValidationUtils.clean_text(
                                    re.sub(r'[\d\*]+$', '', match.group(2))
                                )
                                for num in nums.split(','):
                                    affiliations_map[num.strip()] = aff_text
                        
                        for name, num in parsed:
                            aff = affiliations_map.get(num, '') if num else ''
                            if aff:
                                authors.append({
                                    'original_pdf': original_pdf,
                                    'page_number': page_number,
                                    'author_name': name,
                                    'affiliation': aff,
                                    'extraction_method': 'pymupdf'
                                })
                        i += 1
                        continue
                
                # Single name
                if ValidationUtils.is_valid_name(text):
                    affiliations = []
                    for j in range(1, 4):
                        if i + j >= len(blocks):
                            break
                        next_text = blocks[i + j]['text']
                        if (ValidationUtils.should_skip_block(next_text) or
                                ValidationUtils.is_valid_name(next_text)):
                            break
                        next_clean = ValidationUtils.clean_text(
                            re.sub(r'^[\d\*\s]+', '', next_text)
                        )
                        if next_clean:
                            affiliations.append(next_clean)
                        if ValidationUtils.is_country(next_text):
                            break
                    
                    if affiliations:
                        authors.append({
                            'original_pdf': original_pdf,
                            'page_number': page_number,
                            'author_name': text,
                            'affiliation': ValidationUtils.clean_text(' '.join(affiliations)),
                            'extraction_method': 'pymupdf'
                        })
                
                i += 1
        except Exception:
            pass
        
        return authors


# ==================== MAIN EXTRACTOR CLASS ====================
class PDFAuthorExtractor:
    """Main PDF author extraction orchestrator"""
    
    def __init__(self, config: Optional[ExtractionConfig] = None,
                 grobid_client: Optional[GrobidClient] = None):
        self.config = config or ExtractionConfig()
        self.grobid_client = grobid_client
        
        # Initialize extractors
        if grobid_client and GROBID_AVAILABLE:
            self.grobid_extractor = GrobidExtractor(
                grobid_client, self.config.temp_tei_dir
            )
        else:
            self.grobid_extractor = None
        
        self.pymupdf4llm_extractor = PyMuPDF4LLMExtractor()
        self.pymupdf_extractor = PyMuPDFExtractor()
    
    def process_pdf(self, pdf_path: Path) -> Tuple[int, Dict]:
        """Process a single PDF file"""
        _log.info('=== process_pdf START: %s ===', pdf_path)
        _log.info('  grobid_extractor present: %s', self.grobid_extractor is not None)
        _log.info('  PYMUPDF4LLM_AVAILABLE: %s', PYMUPDF4LLM_AVAILABLE)
        _log.info('  GROBID_AVAILABLE (import): %s', GROBID_AVAILABLE)
        print(f"\n{'='*70}")
        print(f"Processing: {pdf_path}")
        print(f"{'='*70}")
        
        # Split into pages
        print("Splitting PDF into pages...")
        page_files = PDFUtils.split_pdf_pages(pdf_path, self.config.temp_pages_dir)
        if not page_files:
            _log.warning('process_pdf: no pages extracted from %s', pdf_path)
            return 0, {}
        _log.info('  split into %d page(s)', len(page_files))
        print(f"✓ Created {len(page_files)} page(s)")
        
        # Initialize CSV writer
        output_csv = self.config.output_dir / f"{pdf_path.stem}_authors.csv"
        csv_writer = ImmediateCSVWriter(output_csv)
        
        total_authors = 0
        method_stats = defaultdict(int)
        
        # Process pages
        print(f"\n{'Page':<8} {'Type':<15} {'Method':<15} {'Authors':<10}")
        print("-" * 50)
        
        for i, page_info in enumerate(page_files, 1):
            page_path = page_info['page_path']
            page_num = page_info['page_number']
            original_pdf = page_info['original_pdf']
            
            # Progress indicator
            if i % 10 == 0:
                print(f"[Progress: {i}/{len(page_files)} pages ({i*100//len(page_files)}%)]")
            
            has_img = PDFUtils.has_images(page_path)
            has_text = PDFUtils.has_extractable_text(page_path)
            
            if not has_text:
                _log.debug('  SKIPPED (no text) — page %d', page_num)
                print(f"{page_num:<8} {'image-only':<15} {'SKIPPED':<15} {'-':<10}")
                continue
            
            page_type = "text+images" if has_img else "text-only"
            print(f"{page_num:<8} {page_type:<15}", end=" ", flush=True)
            
            # Extract authors
            authors, method = self._extract_from_page(
                page_path, page_num, original_pdf
            )
            
            count = len(authors) if authors else 0
            print(f"{method:<15} {count:<10}")
            
            if authors:
                csv_writer.write_authors(authors)
                total_authors += count
                for author in authors:
                    method_stats[author['extraction_method']] += 1
        
        # Summary
        print(f"\n{'='*70}")
        print(f"✅ Extracted {total_authors} author(s)")
        print(f"💾 Saved to: {output_csv}")
        print(f"{'='*70}")
        
        if method_stats:
            print("\n📊 Methods:")
            for method, count in method_stats.items():
                print(f"  - {method.upper()}: {count}")
        
        return total_authors, dict(method_stats)
    
    def _extract_from_page(self, page_path: Path, page_num: int,
                          original_pdf: str) -> Tuple[List[Dict], str]:
        """Extract authors from a single page using priority cascade"""
        authors = []
        method = "None"
        _log.debug('--- _extract_from_page: page=%d file=%s ---', page_num, page_path.name)
        
        # Priority 1: GROBID
        if self.grobid_extractor:
            grobid_ok = self.grobid_extractor.process_page(page_path)
            _log.debug('  GROBID process_page result: grobid_ok=%s', grobid_ok)
            if grobid_ok:
                authors = self.grobid_extractor.extract_authors(
                    page_path, page_num, original_pdf
                )
                _log.debug('  GROBID extract_authors returned %d author(s)', len(authors))
                if authors:
                    method = "GROBID"
            else:
                _log.debug('  GROBID did not write TEI — falling through to PyMuPDF')
        else:
            _log.debug('  grobid_extractor is None — GROBID disabled or not connected')
        
        # Priority 2: PyMuPDF4LLM JSON (if GROBID found nothing)
        if not authors and PYMUPDF4LLM_AVAILABLE:
            _log.debug('  trying PyMuPDF4LLM_JSON...')
            authors = self.pymupdf4llm_extractor.extract_authors(
                page_path, page_num, original_pdf
            )
            _log.debug('  PyMuPDF4LLM_JSON returned %d author(s)', len(authors))
            if authors:
                method = "PyMuPDF4LLM_JSON"
        
        # Priority 3: PyMuPDF fallback
        if not authors:
            _log.debug('  trying PyMuPDF fallback...')
            authors = self.pymupdf_extractor.extract_authors(
                page_path, page_num, original_pdf
            )
            _log.debug('  PyMuPDF returned %d author(s)', len(authors))
            if authors:
                method = "PyMuPDF"
        
        _log.debug('  FINAL: method=%s  authors=%d', method, len(authors))
        return authors, method
    
    def cleanup(self) -> None:
        """Clean up temporary files"""
        shutil.rmtree(self.config.temp_pages_dir, ignore_errors=True)
        shutil.rmtree(self.config.temp_tei_dir, ignore_errors=True)
        _log.info('  cleaned up temp files')
        print("✓ Cleaned temp files")


# ==================== STANDALONE CLI ====================
def main():
    """Standalone CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="PDF Author and Affiliation Extraction System"
    )
    parser.add_argument('pdf_path', help='PDF file or directory to process')
    parser.add_argument('--grobid-server', default='http://localhost:8070',
                       help='GROBID server URL (default: http://localhost:8070)')
    parser.add_argument('--no-grobid', action='store_true',
                       help='Skip GROBID, use only PyMuPDF methods')
    parser.add_argument('--cleanup', action='store_true',
                       help='Clean up temporary files after processing')
    parser.add_argument('--output-dir', default='output',
                       help='Output directory (default: output)')
    args = parser.parse_args()
    
    print("="*70)
    print("PDF AUTHOR EXTRACTION SYSTEM")
    print("="*70)
    
    # Initialize configuration
    config = ExtractionConfig(
        output_dir=Path(args.output_dir),
        grobid_server=args.grobid_server
    )
    
    # Initialize GROBID client
    grobid_client = None
    if not args.no_grobid and GROBID_AVAILABLE:
        try:
            grobid_client = GrobidClient(grobid_server=args.grobid_server)
            print(f"✓ GROBID ready ({args.grobid_server})")
        except Exception as e:
            print(f"⚠ GROBID unavailable: {e}")
    else:
        if args.no_grobid:
            print("⚠ GROBID disabled (--no-grobid flag)")
        else:
            print("⚠ GROBID client not available")
    
    if PYMUPDF4LLM_AVAILABLE:
        print("✓ PyMuPDF4LLM ready")
    else:
        print("⚠ PyMuPDF4LLM not available")
    
    print()
    
    # Initialize extractor
    extractor = PDFAuthorExtractor(config=config, grobid_client=grobid_client)
    
    # Process PDF(s)
    pdf_path = Path(args.pdf_path)
    if pdf_path.is_file():
        total_authors, stats = extractor.process_pdf(pdf_path)
    elif pdf_path.is_dir():
        total_authors_all = 0
        for pdf_file in sorted(pdf_path.glob('*.pdf')):
            total_authors, stats = extractor.process_pdf(pdf_file)
            total_authors_all += total_authors
        print(f"\n{'='*70}")
        print(f"✅ Total authors extracted from all PDFs: {total_authors_all}")
        print(f"{'='*70}")
    else:
        print(f"❌ Not found: {pdf_path}")
        return 1
    
    # Cleanup
    if args.cleanup:
        print("\n🧹 Cleaning up temporary files...")
        extractor.cleanup()
    
    print(f"\n{'='*70}")
    print("🎉 COMPLETE!")
    print(f"{'='*70}\n")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
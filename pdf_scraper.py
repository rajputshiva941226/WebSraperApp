#!/usr/bin/env python3
"""
PDF Scraper — integrated with WebScraperApp ScraperAdapter.

Pipeline:
  1. Direct email extraction from the PDF's raw text (regex, first 10 pages).
     Author names are inferred from the email local-part and surrounding lines.
  2. Structural author / affiliation extraction via:
       GROBID     (if Docker container reachable on :8070)  — highest quality
       PyMuPDF4LLM JSON blocks                              — medium quality
       PyMuPDF raw blocks                                   — final fallback
  3. For any author still missing an email, query public APIs:
       Semantic Scholar → OpenAlex → Crossref (via DOI)
  4. Write output CSV: Author_Name | Email | Affiliation | Article_URL

Called by ScraperAdapter as:
    PDFScraper(pdf_path=<path>, output_dir=..., job_id=...,
               conference_name=..., progress_callback=...)
"""

import os
import re
import csv
import sys
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# ── Optional heavy dependencies ──────────────────────────────────────────────
try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

try:
    import pymupdf4llm
    PYMUPDF4LLM_AVAILABLE = True
except ImportError:
    PYMUPDF4LLM_AVAILABLE = False

try:
    from grobid_client.grobid_client import GrobidClient
    GROBID_CLIENT_AVAILABLE = True
except ImportError:
    GROBID_CLIENT_AVAILABLE = False

_EMAIL_RE = re.compile(r'\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b')

_NAME_RE = re.compile(
    r'^([A-Z][a-z]+(?:[\-\s][A-Z][a-z]+)*'
    r'(?:\s+[A-Z]\.?)?'
    r'\s+[A-Z][a-z]+(?:[\-][A-Z][a-z]+)*)'
    r'\s*[,;*†‡\d]*$'
)

_AFFIL_KEYWORDS = (
    'university', 'college', 'institute', 'hospital', 'department',
    'faculty', 'school', 'center', 'centre', 'laboratory', 'labs',
    'research', 'health', 'medical', 'clinic', 'foundation', 'trust',
)


# ─────────────────────────────────────────────────────────────────────────────
class PDFScraper:
    """Adapter-compatible PDF author + email extractor."""

    JOURNAL_NAME = 'PDF Document'

    def __init__(
        self,
        pdf_path: str,
        output_dir: str = 'results',
        job_id: Optional[str] = None,
        progress_callback=None,
        conference_name: str = 'default',
        grobid_server: str = 'http://localhost:8070',
        **kwargs,
    ):
        self.pdf_path    = pdf_path
        self.output_dir  = output_dir
        self.job_id      = job_id or 'pdf_job'
        self.progress_cb = progress_callback
        self.conference  = conference_name
        self.grobid_url  = grobid_server
        os.makedirs(output_dir, exist_ok=True)

    def set_progress_callback(self, cb):
        self.progress_cb = cb

    # ── Internal helpers ──────────────────────────────────────────────────────
    def _p(self, pct: int, msg: str, **kw):
        self._last_pct = pct
        if self.progress_cb:
            try:
                self.progress_cb(pct, msg, **kw)
            except KeyboardInterrupt:
                raise  # propagate cooperative stop signal
            except Exception:
                pass
        logger.info('[PDFScraper] %d%% — %s', pct, msg)

    def _stop_check(self):
        """Force a stop check without updating displayed progress."""
        pct = getattr(self, '_last_pct', 0)
        if self.progress_cb:
            try:
                self.progress_cb(pct, '')
            except KeyboardInterrupt:
                raise

    def _grobid_alive(self) -> bool:
        try:
            r = requests.get(f'{self.grobid_url}/api/isalive', timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def _warn_no_grobid(self):
        """Log and surface a user-visible warning when GROBID is not reachable."""
        msg = (
            f'GROBID not reachable at {self.grobid_url} '
            '(Docker not running?). Falling back to PyMuPDF for extraction.'
        )
        logger.warning('[PDFScraper] %s', msg)
        return msg

    # ── Phase 1 : direct email extraction from raw PDF text ──────────────────
    def _extract_direct_emails(self) -> List[Dict]:
        """
        Scan the first 10 pages for email addresses.
        For each email infer the author name (from local-part) and affiliation
        (from a nearby line containing an institution keyword).
        Returns deduplicated list of {email, author_name, affiliation, page}.
        """
        results = []
        if not FITZ_AVAILABLE:
            logger.warning('[PDFScraper] PyMuPDF not available — skipping direct email scan')
            return results

        try:
            doc = fitz.open(self.pdf_path)
            scan_pages = min(len(doc), 10)
            for page_num in range(scan_pages):
                text  = doc[page_num].get_text()
                lines = text.splitlines()
                for i, line in enumerate(lines):
                    found = _EMAIL_RE.findall(line)
                    for raw_email in found:
                        email = raw_email.strip().lower()
                        if not email or '@' not in email:
                            continue
                        domain = email.split('@')[-1]
                        if '.' not in domain or domain in ('gmail.com', 'yahoo.com',
                                                            'hotmail.com', 'outlook.com'):
                            continue  # skip generic/personal addresses
                        ctx = lines[max(0, i - 6): i + 7]
                        author = self._author_from_context(ctx, email)
                        affil  = self._affil_from_context(ctx)
                        results.append({
                            'email': email, 'author_name': author,
                            'affiliation': affil, 'page': page_num + 1,
                        })
            doc.close()
        except Exception as exc:
            logger.warning('[PDFScraper] Direct email scan error: %s', exc)

        # Deduplicate by email
        seen: set = set()
        unique = []
        for r in results:
            if r['email'] not in seen:
                seen.add(r['email'])
                unique.append(r)
        return unique

    @staticmethod
    def _author_from_context(lines: List[str], email: str) -> str:
        # Strategy 1 — infer from email local-part (firstname.lastname@…)
        local = email.split('@')[0]
        parts = re.split(r'[._\-]', local)
        parts = [p for p in parts if len(p) > 1 and p.isalpha()]
        if len(parts) >= 2:
            return ' '.join(p.capitalize() for p in parts[:3])

        # Strategy 2 — look for a Title-Case name line nearby
        for line in lines:
            line = line.strip()
            m = _NAME_RE.match(line)
            if m:
                name = m.group(1).strip()
                if len(name.split()) >= 2:
                    return name
        return ''

    @staticmethod
    def _affil_from_context(lines: List[str]) -> str:
        for line in lines:
            if any(k in line.lower() for k in _AFFIL_KEYWORDS):
                return line.strip()
        return ''

    # ── Phase 2 : structural extraction via GROBID / PyMuPDF ─────────────────
    def _extract_structural(self) -> List[Dict]:
        """
        Run the PDF_Scraper/pdf_extraction_module pipeline.
        Returns list of {author_name, affiliation, article_url}.
        """
        scraper_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'PDF_Scraper')
        if scraper_dir not in sys.path:
            sys.path.insert(0, scraper_dir)

        try:
            from pdf_extraction_module import ExtractionConfig, PDFAuthorExtractor
        except ImportError as exc:
            logger.warning('[PDFScraper] pdf_extraction_module unavailable: %s', exc)
            return []

        import tempfile, shutil as _shutil

        with tempfile.TemporaryDirectory() as tmpdir:
            config = ExtractionConfig(
                output_dir      = Path(tmpdir) / 'out',
                temp_pages_dir  = Path(tmpdir) / 'pages',
                temp_tei_dir    = Path(tmpdir) / 'tei',
                grobid_server   = self.grobid_url,
            )

            grobid_client = None
            if self._grobid_alive() and GROBID_CLIENT_AVAILABLE:
                try:
                    grobid_client = GrobidClient(grobid_server=self.grobid_url)
                    logger.info('[PDFScraper] GROBID connected at %s', self.grobid_url)
                except Exception as e:
                    logger.warning('[PDFScraper] GROBID init failed: %s', e)
            else:
                logger.info('[PDFScraper] GROBID unavailable — using PyMuPDF fallback')

            extractor = PDFAuthorExtractor(config=config, grobid_client=grobid_client)
            try:
                extractor.process_pdf(Path(self.pdf_path))
            except Exception as exc:
                logger.warning('[PDFScraper] Structural extraction error: %s', exc)
                return []

            out_csv = config.output_dir / f'{Path(self.pdf_path).stem}_authors.csv'
            if not out_csv.exists():
                csvs = list(config.output_dir.glob('*.csv'))
                out_csv = csvs[0] if csvs else None

            rows = []
            if out_csv and out_csv.exists():
                with open(out_csv, 'r', encoding='utf-8', errors='replace') as fh:
                    for row in csv.DictReader(fh):
                        aname = (row.get('author_name') or '').strip()
                        affil = (row.get('affiliation') or '').strip()
                        if aname:
                            rows.append({'author_name': aname, 'affiliation': affil,
                                         'article_url': ''})
        return rows

    # ── Phase 3 : API-based email lookup (no Selenium) ────────────────────────
    def _ss_resolve_author(self, author: str, affil: str) -> Optional[str]:
        """Return Semantic Scholar authorId or None."""
        try:
            r = requests.get(
                'https://api.semanticscholar.org/graph/v1/author/search',
                params={'query': author, 'fields': 'authorId,name,affiliations', 'limit': 10},
                timeout=10,
            )
            if r.status_code != 200:
                return None
            data = r.json().get('data', [])
            if not data:
                return None
            # Prefer candidate whose affiliation matches
            clean_affil = affil.lower()[:60] if affil else ''
            for cand in data:
                if clean_affil:
                    for ca in cand.get('affiliations', []):
                        if any(w in ca.lower() for w in clean_affil.split() if len(w) > 3):
                            return cand['authorId']
            return data[0]['authorId']
        except Exception:
            return None

    def _ss_dois_for_author(self, author_id: str) -> List[str]:
        """Return up to 5 DOIs from Semantic Scholar for this author."""
        try:
            r = requests.get(
                f'https://api.semanticscholar.org/graph/v1/author/{author_id}/papers',
                params={'fields': 'externalIds', 'limit': 20},
                timeout=10,
            )
            if r.status_code != 200:
                return []
            dois = []
            for paper in r.json().get('data', []):
                doi = (paper.get('externalIds') or {}).get('DOI', '')
                if doi:
                    dois.append(doi)
                if len(dois) >= 5:
                    break
            return dois
        except Exception:
            return []

    def _crossref_email(self, doi: str, author: str) -> str:
        """Try to extract an email from Crossref metadata for a given DOI."""
        try:
            r = requests.get(
                f'https://api.crossref.org/works/{doi}',
                timeout=8,
                headers={'User-Agent': 'WebScraperApp/1.0 (mailto:admin@example.com)'},
            )
            if r.status_code != 200:
                return ''
            last = author.split()[-1].lower() if author else ''
            for a in r.json().get('message', {}).get('author', []):
                full_lower = f"{a.get('given','')} {a.get('family','')}".lower()
                if last and last in full_lower:
                    email = a.get('email', '')
                    if email and '@' in email:
                        return email.strip().lower()
        except Exception:
            pass
        return ''

    def _openalex_dois(self, author: str) -> List[str]:
        """Return up to 5 DOIs from OpenAlex for this author."""
        try:
            r = requests.get(
                'https://api.openalex.org/authors',
                params={'search': author, 'per-page': 5, 'mailto': 'admin@example.com'},
                timeout=10,
            )
            if r.status_code != 200:
                return []
            results = r.json().get('results', [])
            if not results:
                return []
            aid = results[0].get('id', '').split('/')[-1]
            wr = requests.get(
                'https://api.openalex.org/works',
                params={'filter': f'authorships.author.id:{aid}',
                        'per-page': 10, 'mailto': 'admin@example.com'},
                timeout=10,
            )
            if wr.status_code != 200:
                return []
            dois = []
            for work in wr.json().get('results', []):
                doi = (work.get('doi') or '').replace('https://doi.org/', '')
                if doi:
                    dois.append(doi)
                if len(dois) >= 5:
                    break
            return dois
        except Exception:
            return []

    def _lookup_email(self, author: str, affil: str) -> str:
        """Try Semantic Scholar → OpenAlex → Crossref to find email."""
        if not author or len(author) < 4:
            return ''

        # Semantic Scholar path
        try:
            aid = self._ss_resolve_author(author, affil)
            if aid:
                for doi in self._ss_dois_for_author(aid):
                    email = self._crossref_email(doi, author)
                    if email:
                        return email
                    time.sleep(0.3)
        except Exception:
            pass

        # OpenAlex path
        try:
            for doi in self._openalex_dois(author):
                email = self._crossref_email(doi, author)
                if email:
                    return email
                time.sleep(0.3)
        except Exception:
            pass

        return ''

    # ── Main entry point ──────────────────────────────────────────────────────
    def run(self) -> Tuple[str, Dict]:
        """
        Execute the full pipeline.
        Returns (output_csv_path, summary_dict).
        """
        pdf = Path(self.pdf_path)
        self._p(5, f'Validating PDF: {pdf.name}')
        if not pdf.exists():
            raise FileNotFoundError(f'PDF not found: {self.pdf_path}')

        # ── Phase 1 ──
        self._p(10, 'Scanning PDF text for emails…')
        direct = self._extract_direct_emails()
        logger.info('[PDFScraper] Direct emails: %d', len(direct))

        # ── Phase 1.5 : stop check before slow phase ──
        self._stop_check()

        # ── Phase 2 ──
        grobid_up = self._grobid_alive()
        if not grobid_up:
            fallback_msg = self._warn_no_grobid()
            self._p(30, f'⚠ {fallback_msg}')
        else:
            self._p(30, 'Extracting author/affiliation structure via GROBID…')
        structural = self._extract_structural()
        logger.info('[PDFScraper] Structural authors: %d', len(structural))

        # ── Merge ──
        # email → record dict
        records: Dict[str, Dict] = {}

        # Build author→email lookup from direct extraction
        email_by_author: Dict[str, str] = {}
        for r in direct:
            email_by_author[r['email']] = r  # keyed by email
            if r['author_name']:
                email_by_author[r['author_name'].lower()] = r

        # Seed from direct results
        for r in direct:
            records[r['email']] = {
                'Author_Name': r['author_name'],
                'Email':       r['email'],
                'Affiliation': r['affiliation'],
                'Article_URL': pdf.name,
            }

        # Enrich / add from structural
        for s in structural:
            aname = s['author_name']
            if not aname:
                continue
            # Try to match this author to a direct-extracted email
            email = ''
            aname_lower = aname.lower()
            for key, val in email_by_author.items():
                if isinstance(val, dict):
                    k_email = val['email']
                    k_name  = (val['author_name'] or '').lower()
                else:
                    continue
                tokens_s = aname_lower.split()
                tokens_k = k_name.split()
                if tokens_s and tokens_k:
                    # Last name match OR first token match
                    if (tokens_s[-1] in tokens_k or tokens_k[-1] in tokens_s
                            or tokens_s[0] in tokens_k):
                        email = k_email
                        break

            key = email if email else f'__noemail__{aname}'
            if key not in records:
                records[key] = {
                    'Author_Name': aname,
                    'Email':       email,
                    'Affiliation': s['affiliation'],
                    'Article_URL': s.get('article_url', pdf.name),
                }
            else:
                # Enrich existing: fill in missing affiliation
                if not records[key]['Affiliation'] and s['affiliation']:
                    records[key]['Affiliation'] = s['affiliation']
                if not records[key]['Author_Name'] and aname:
                    records[key]['Author_Name'] = aname

        # ── Stop check after structural phase ──
        self._stop_check()

        # ── Phase 3 : API email search for authors still missing emails ──
        no_email = [r for r in records.values()
                    if not r['Email'] and r['Author_Name']]
        total_no_email = len(no_email)
        if no_email:
            self._p(55, f'API email search for {total_no_email} authors…')
            for idx, r in enumerate(no_email):
                pct = 55 + int(idx / max(total_no_email, 1) * 30)
                self._p(pct, f'Searching: {r["Author_Name"][:40]}…')
                email = self._lookup_email(r['Author_Name'], r['Affiliation'])
                if email:
                    old_key = f'__noemail__{r["Author_Name"]}'
                    if old_key in records:
                        records[email] = records.pop(old_key)
                    r['Email'] = email
                time.sleep(0.5)

        # ── Write CSV ──
        self._p(92, 'Writing output CSV…')
        safe_stem   = re.sub(r'[^\w\-]', '_', pdf.stem)
        output_file = os.path.join(
            self.output_dir,
            f'{self.job_id}_{safe_stem}_results.csv',
        )
        fieldnames = ['Author_Name', 'Email', 'Affiliation', 'Article_URL']
        rows_out   = [r for r in records.values()
                      if r.get('Author_Name') or r.get('Email')]

        with open(output_file, 'w', newline='', encoding='utf-8') as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows_out)

        total      = len(rows_out)
        with_email = sum(1 for r in rows_out if r['Email'])
        self._p(100, f'Done — {total} authors, {with_email} with emails')
        logger.info('[PDFScraper] Output: %s  rows=%d  emails=%d',
                    output_file, total, with_email)

        return output_file, {
            'scraper':       'pdf_scraper',
            'pdf_file':      pdf.name,
            'output_file':   output_file,
            'authors_found': total,
            'emails_found':  with_email,
            'status':        'completed',
        }

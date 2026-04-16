#!/usr/bin/env python3
"""
PDF Scraper — integrated with WebScraperApp ScraperAdapter.

Phase 1 — PDF extraction (no external API calls):
    Delegates to PDF_Scraper/pdf_extraction_module.PDFAuthorExtractor.
    Cascade: GROBID (if running on :8070) → PyMuPDF4LLM JSON → PyMuPDF blocks.
    Output CSV columns:
        Author_Name | Email | Affiliation | Page_Number | Extraction_Method | Article_URL

Phase 2 — API email search:
    Reads Phase 1 CSV, finds authors without emails, queries
    Semantic Scholar → OpenAlex → Crossref to get email + DOI.
    Adds PubMed and EuropePMC author-search URLs for every row.
    Output CSV adds:
        DOI | PubMed_Search_URL | EuropePMC_Search_URL

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
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

try:
    from grobid_client.grobid_client import GrobidClient
    GROBID_CLIENT_AVAILABLE = True
except ImportError:
    GROBID_CLIENT_AVAILABLE = False


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

    # ── API-based email lookup helpers ────────────────────────────────────────
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
        return self._lookup_email_with_doi(author, affil)['email']

    def _lookup_email_with_doi(self, author: str, affil: str) -> Dict:
        """Same as _lookup_email but also returns the DOI that produced the hit."""
        empty = {'email': '', 'doi': ''}
        if not author or len(author) < 4:
            return empty

        # Semantic Scholar path
        try:
            aid = self._ss_resolve_author(author, affil)
            if aid:
                for doi in self._ss_dois_for_author(aid):
                    email = self._crossref_email(doi, author)
                    if email:
                        return {'email': email, 'doi': doi}
                    time.sleep(0.3)
        except Exception:
            pass

        # OpenAlex path
        try:
            for doi in self._openalex_dois(author):
                email = self._crossref_email(doi, author)
                if email:
                    return {'email': email, 'doi': doi}
                time.sleep(0.3)
        except Exception:
            pass

        return empty

    # ── Phase 1 : PDF extraction via PDFAuthorExtractor (no API calls) ─────────
    def run_phase1(self) -> Tuple[str, Dict]:
        """
        Delegate entirely to PDF_Scraper/pdf_extraction_module.PDFAuthorExtractor.
        Cascade: GROBID (if reachable) → PyMuPDF4LLM JSON → PyMuPDF blocks.
        NO email regex scanning — conference / brochure PDFs contain org emails,
        not author emails.
        Output columns: Author_Name | Email | Affiliation | Page_Number |
                        Extraction_Method | Article_URL
        """
        pdf = Path(self.pdf_path)
        self._p(5, f'Validating PDF: {pdf.name}')
        if not pdf.exists():
            raise FileNotFoundError(f'PDF not found: {self.pdf_path}')

        # ── Import extraction module ──
        scraper_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'PDF_Scraper')
        if scraper_dir not in sys.path:
            sys.path.insert(0, scraper_dir)
        try:
            from pdf_extraction_module import ExtractionConfig, PDFAuthorExtractor
        except ImportError as exc:
            raise RuntimeError(f'pdf_extraction_module unavailable: {exc}') from exc

        self._p(10, 'Initialising extraction pipeline…')

        # Use persistent work dir so pages/ tei/ out/ survive for inspection
        workdir = Path(self.output_dir) / f'{self.job_id}_work'
        workdir.mkdir(parents=True, exist_ok=True)
        logger.info('[PDFScraper] Work directory: %s', workdir)

        if True:  # replaces 'with tempfile.TemporaryDirectory()' — keep indent
            tmpdir = str(workdir)
            config = ExtractionConfig(
                output_dir     = workdir / 'out',
                temp_pages_dir = workdir / 'pages',
                temp_tei_dir   = workdir / 'tei',
                grobid_server  = self.grobid_url,
            )

            grobid_client = None
            if self._grobid_alive():
                try:
                    from grobid_client.grobid_client import GrobidClient as _GrobidClient
                    grobid_client = _GrobidClient(grobid_server=self.grobid_url)
                    self._p(15, f'GROBID connected at {self.grobid_url}')
                except Exception as exc:
                    logger.warning('[PDFScraper] GROBID init failed: %s', exc)
                    self._p(15, f'⚠ {self._warn_no_grobid()}')
            else:
                self._p(15, f'⚠ {self._warn_no_grobid()}')

            extractor = PDFAuthorExtractor(config=config, grobid_client=grobid_client)

            self._stop_check()
            self._p(20, f'Processing PDF pages…')

            try:
                total_found, method_stats = extractor.process_pdf(pdf)
            except Exception as exc:
                logger.error('[PDFScraper] Extraction failed: %s', exc)
                raise

            # Log what GROBID actually wrote so we can debug naming mismatches
            tei_files = list((workdir / 'tei').glob('*')) if (workdir / 'tei').exists() else []
            logger.info('[PDFScraper] TEI dir contents (%d files): %s',
                        len(tei_files), [f.name for f in tei_files[:20]])

            self._stop_check()
            self._p(85, 'Reading extracted results…')

            # Find output CSV written by PDFAuthorExtractor
            out_csv = config.output_dir / f'{pdf.stem}_authors.csv'
            if not out_csv.exists():
                csvs = list(config.output_dir.glob('*.csv'))
                out_csv = csvs[0] if csvs else None

            rows_out: List[Dict] = []
            seen_names: set = set()
            if out_csv and out_csv.exists():
                with open(out_csv, 'r', encoding='utf-8', errors='replace') as fh:
                    for row in csv.DictReader(fh):
                        name = (row.get('author_name') or '').strip()
                        if not name:
                            continue
                        name_key = name.lower()
                        if name_key in seen_names:
                            continue  # deduplicate across pages
                        seen_names.add(name_key)
                        rows_out.append({
                            'Author_Name':       name,
                            'Email':             '',
                            'Affiliation':       (row.get('affiliation') or '').strip(),
                            'Page_Number':       row.get('page_number', ''),
                            'Extraction_Method': row.get('extraction_method', ''),
                            'Article_URL':       row.get('original_pdf', pdf.name),
                        })

        # ── Write Phase 1 CSV ──
        self._p(92, 'Writing Phase 1 CSV…')
        safe_stem   = re.sub(r'[^\w\-]', '_', pdf.stem)
        output_file = os.path.join(
            self.output_dir,
            f'{self.job_id}_{safe_stem}_phase1.csv',
        )
        fieldnames = ['Author_Name', 'Email', 'Affiliation',
                      'Page_Number', 'Extraction_Method', 'Article_URL']

        with open(output_file, 'w', newline='', encoding='utf-8') as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows_out)

        total    = len(rows_out)
        no_email = total  # Phase 1 never has emails — that's Phase 2's job
        methods_str = ', '.join(f'{m}: {c}' for m, c in (method_stats or {}).items())
        self._p(100, f'Phase 1 done — {total} unique authors extracted'
                     + (f' ({methods_str})' if methods_str else '')
                     + f'; {no_email} need Phase 2 API email search')
        logger.info('[PDFScraper] Phase1 output: %s  rows=%d', output_file, total)

        return output_file, {
            'scraper':         'pdf_scraper',
            'phase':           1,
            'pdf_file':        pdf.name,
            'output_file':     output_file,
            'authors_found':   total,
            'emails_found':    0,
            'need_api_search': no_email,
            'method_stats':    method_stats or {},
            'status':          'completed',
        }

    # ── Phase 2 : API email search + DOI collection ───────────────────────────
    def run_phase2(self, phase1_csv: str) -> Tuple[str, Dict]:
        """
        Read a Phase 1 CSV, look up missing emails via Semantic Scholar /
        OpenAlex / Crossref, collect DOIs, and generate PubMed / EuropePMC
        search URLs for every author.
        Returns (output_csv_path, summary_dict).
        """
        p1 = Path(phase1_csv)
        self._p(5, f'Loading Phase 1 results: {p1.name}')
        if not p1.exists():
            raise FileNotFoundError(f'Phase 1 CSV not found: {phase1_csv}')

        records: List[Dict] = []
        with open(p1, 'r', encoding='utf-8', errors='replace') as fh:
            records = list(csv.DictReader(fh))
        logger.info('[PDFScraper] Phase2 loaded %d rows from %s', len(records), p1.name)

        # Ensure extra columns exist
        for r in records:
            r.setdefault('DOI', '')
            r.setdefault('PubMed_Search_URL', '')
            r.setdefault('EuropePMC_Search_URL', '')

        no_email_rows = [r for r in records
                         if not r.get('Email') or r['Email'].strip() in ('', 'N/A')]
        total_no_email = len(no_email_rows)

        self._p(10, f'Phase 2: API search for {total_no_email} of '
                    f'{len(records)} authors without emails…')

        for idx, r in enumerate(no_email_rows):
            self._stop_check()
            pct    = 10 + int(idx / max(total_no_email, 1) * 72)
            author = r.get('Author_Name', '').strip()
            affil  = r.get('Affiliation', '').strip()
            self._p(pct, f'[{idx + 1}/{total_no_email}] Searching: {author[:45]}…')

            hit = self._lookup_email_with_doi(author, affil)
            if hit['email']:
                r['Email'] = hit['email']
            if hit['doi']:
                r['DOI'] = hit['doi']
            time.sleep(0.5)

        # Build search URLs for every author (with or without email)
        for r in records:
            author = r.get('Author_Name', '').strip()
            if author:
                enc = requests.utils.quote(author)
                r['PubMed_Search_URL']    = (f'https://pubmed.ncbi.nlm.nih.gov/'
                                              f'?term={enc}[Author]')
                r['EuropePMC_Search_URL'] = (f'https://europepmc.org/search'
                                              f'?query=AUTH:{enc}')

        self._p(92, 'Writing Phase 2 CSV…')
        # Output in the same directory as phase 1
        safe_stem   = re.sub(r'[^\w\-]', '_', p1.stem.replace('_phase1', ''))
        output_file = os.path.join(
            self.output_dir,
            f'{self.job_id}_{safe_stem}_phase2.csv',
        )
        fieldnames = ['Author_Name', 'Email', 'Affiliation',
                      'Page_Number', 'Extraction_Method', 'Article_URL',
                      'DOI', 'PubMed_Search_URL', 'EuropePMC_Search_URL']

        with open(output_file, 'w', newline='', encoding='utf-8') as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(records)

        total      = len(records)
        with_email = sum(1 for r in records if r.get('Email') and
                         r['Email'].strip() not in ('', 'N/A'))
        with_doi   = sum(1 for r in records if r.get('DOI'))
        self._p(100, f'Phase 2 done — {total} authors, {with_email} emails, '
                     f'{with_doi} DOIs found')
        logger.info('[PDFScraper] Phase2 output: %s  rows=%d  emails=%d  dois=%d',
                    output_file, total, with_email, with_doi)

        return output_file, {
            'scraper':       'pdf_scraper_phase2',
            'phase':         2,
            'phase1_csv':    phase1_csv,
            'output_file':   output_file,
            'authors_found': total,
            'emails_found':  with_email,
            'dois_found':    with_doi,
            'status':        'completed',
        }

    # ── Backwards-compatible entry point ─────────────────────────────────────
    def run(self) -> Tuple[str, Dict]:
        """Runs Phase 1 only (extraction without API calls). Use run_phase2() separately."""
        return self.run_phase1()


# ─────────────────────────────────────────────────────────────────────────────
class PDFScraperPhase2:
    """
    Adapter-compatible wrapper for Phase 2 (API email lookup).
    The ScraperAdapter passes the Phase 1 CSV path via the `pdf_path` kwarg
    (which carries the `keyword` field from the Job row).
    """

    JOURNAL_NAME = 'PDF Email Search (Phase 2)'

    def __init__(
        self,
        pdf_path: str,            # receives the phase1 CSV path stored in Job.keyword
        output_dir: str = 'results',
        job_id: Optional[str] = None,
        progress_callback=None,
        conference_name: str = 'default',
        **kwargs,
    ):
        self._phase1_csv  = pdf_path
        self._output_dir  = output_dir
        self._job_id      = job_id or 'pdf_phase2'
        self._progress_cb = progress_callback
        self._conference  = conference_name

    def set_progress_callback(self, cb):
        self._progress_cb = cb

    def run(self) -> Tuple[str, Dict]:
        scraper = PDFScraper(
            pdf_path        = '',          # not used in phase 2
            output_dir      = self._output_dir,
            job_id          = self._job_id,
            progress_callback = self._progress_cb,
            conference_name = self._conference,
        )
        return scraper.run_phase2(self._phase1_csv)

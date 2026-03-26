# #!/usr/bin/env python3
# """
# Springer Nature Open Access API Scraper
# =========================================
# Mirrors EuropePMCScraper interface for drop-in webapp / Celery integration.

# Search types
# ─────────────
#   'text'    →  ("gene editing")           full-text / metadata — broad results
#   'keyword' →  (keyword:"gene editing")   exact keyword tag   — precise / low volume

# Date format : YYYY-MM-DD
# API page cap: 10 records per page (Springer hard limit)

# Critical HTTP note
# ───────────────────
# requests.get(url) re-encodes parentheses and quotes in the query string,
# turning (keyword:"x") into %28keyword%3A%22x%22%29 → Springer returns 403.
# Fix: PreparedRequest + session.send() keeps the URL exactly as built.
# """

# import os
# import re
# import csv
# import math
# import time
# import requests
# import xml.etree.ElementTree as ET
# from datetime import datetime
# from typing import List, Dict, Optional, Callable


# BASE_URL    = 'https://api.springernature.com/openaccess/jats'
# DEFAULT_KEY = os.environ.get('SPRINGER_API_KEY', 'c904ff1b51765d5b62e6af740adcff37')


# class SpringerNatureScraper:
#     """
#     Full-pagination scraper for the Springer Nature Open Access JATS API.

#     Constructor mirrors EuropePMCScraper so scraper_adapter.py needs
#     zero special-casing beyond registering the module.

#     Webapp usage (via scraper_adapter):
#         scraper = SpringerNatureScraper(
#             query=keyword,
#             start_date=start_converted,   # YYYY-MM-DD
#             end_date=end_converted,       # YYYY-MM-DD
#         )
#         scraper.progress_callback = self.progress_callback
#         results     = scraper.fetch_data()
#         output_file = scraper.save_to_csv(filename=path)

#     Standalone CLI:
#         python springernature_scraper.py --keyword "gene editing" \\
#                --date-from 2025-01-01 --date-to 2025-12-31
#     """

#     def __init__(
#         self,
#         query:             str,
#         start_date:        Optional[str]      = None,
#         end_date:          Optional[str]      = None,
#         api_key:           str                = DEFAULT_KEY,
#         page_size:         int                = 10,
#         delay:             float              = 0.5,
#         progress_callback: Optional[Callable] = None,
#     ):
#         self.query             = query
#         self.start_date        = start_date
#         self.end_date          = end_date
#         self.api_key           = api_key or DEFAULT_KEY
#         self.page_size         = min(max(int(page_size), 1), 10)
#         self.delay             = max(float(delay), 0)
#         self.progress_callback = progress_callback
#         self.all_results: List[Dict] = []
#         self._session          = requests.Session()

#     # ── Progress ──────────────────────────────────────────────────────────────

#     def _progress(self, pct: int, msg: str, **kwargs):
#         if self.progress_callback:
#             try:
#                 self.progress_callback(pct, msg, **kwargs)
#             except Exception:
#                 pass

#     # ── URL builder ───────────────────────────────────────────────────────────

#     def _build_url(self, s: int) -> str:
#         """
#         All query terms go inside ONE set of parentheses.

#         Working format (verified):
#           (keyword:"gene editing" AND datefrom:"2026-01-01" AND dateto:"2026-03-09")

#         Broken format — Springer returns 403:
#           (keyword:"gene editing") AND datefrom:"2026-01-01" AND dateto:"2026-03-09"
#         """
#         parts = [f'keyword:"{self.query}"']
#         if self.start_date:
#             parts.append(f'datefrom:"{self.start_date}"')
#         if self.end_date:
#             parts.append(f'dateto:"{self.end_date}"')

#         q = '(' + ' AND '.join(parts) + ')'

#         return (
#             f'{BASE_URL}'
#             f'?api_key={self.api_key}'
#             f'&callback='
#             f'&s={s}'
#             f'&p={self.page_size}'
#             f'&q={q}'
#         )

#     # ── HTTP — no re-encoding ─────────────────────────────────────────────────

#     def _fetch_raw(self, url: str) -> str:
#         req     = requests.Request('GET', url)
#         prepped = req.prepare()
#         prepped.url = url   # override — keeps parentheses and quotes intact

#         for attempt in range(3):
#             try:
#                 resp = self._session.send(prepped, timeout=30)
#                 if resp.status_code == 429:
#                     wait = 2 ** (attempt + 1)
#                     print(f"  [Springer][429] rate-limit — retrying in {wait}s ...")
#                     time.sleep(wait)
#                     continue
#                 resp.raise_for_status()
#                 return resp.text
#             except requests.HTTPError as exc:
#                 if attempt == 2:
#                     raise RuntimeError(f"Springer API HTTP error: {exc}") from exc
#                 time.sleep(2 * (attempt + 1))
#             except Exception as exc:
#                 if attempt == 2:
#                     raise RuntimeError(f"Springer API fetch failed: {exc}") from exc
#                 time.sleep(2 * (attempt + 1))

#         raise RuntimeError("Springer API: exhausted retries")

#     # ── XML helpers ───────────────────────────────────────────────────────────

#     @staticmethod
#     def _strip_doctype(xml_text: str) -> str:
#         text = re.sub(r'<\?xml-stylesheet[^?]*\?>', '', xml_text, flags=re.DOTALL)
#         text = re.sub(r'<!DOCTYPE\s+\w+\s*\[.*?\]\s*>', '', text, flags=re.DOTALL)
#         text = re.sub(r'<!DOCTYPE\s+\w+[^>]*>',         '', text, flags=re.DOTALL)
#         return text

#     def _get_total(self, xml_text: str) -> int:
#         root = ET.fromstring(self._strip_doctype(xml_text))
#         raw  = root.findtext('.//result/total') or root.findtext('.//total') or '0'
#         try:
#             return int(raw.strip())
#         except (ValueError, AttributeError):
#             return 0

#     # ── Page parser ───────────────────────────────────────────────────────────

#     def _parse_page(self, xml_text: str) -> List[Dict]:
#         """
#         Parse one page of JATS XML into author rows.
#         Only keeps authors with a non-empty email address.

#         Columns match count_results_detailed() in app.py:
#             full_name   -> authors_count
#             email       -> emails_count
#             article_url -> links_count
#         """
#         root    = ET.fromstring(self._strip_doctype(xml_text))
#         records = []

#         for article in root.iter('article'):
#             front = article.find('front')
#             if front is None:
#                 continue
#             article_meta = front.find('article-meta')
#             if article_meta is None:
#                 continue

#             # Article metadata
#             title_e = article_meta.find('.//article-title')
#             title   = ''.join(title_e.itertext()).strip() if title_e is not None else 'N/A'

#             doi_e       = article_meta.find('.//article-id[@pub-id-type="doi"]')
#             doi         = (doi_e.text or '').strip() if doi_e is not None else 'N/A'
#             article_url = f'https://doi.org/{doi}' if doi and doi != 'N/A' else 'N/A'

#             pub_date = 'N/A'
#             for attr in ('epub', 'ppub', 'collection', ''):
#                 pd_e = (article_meta.find(f".//pub-date[@pub-type='{attr}']")
#                         if attr else article_meta.find('.//pub-date'))
#                 if pd_e is not None:
#                     parts    = [pd_e.findtext('year',  '').strip(),
#                                 pd_e.findtext('month', '').strip(),
#                                 pd_e.findtext('day',   '').strip()]
#                     pub_date = '/'.join(p for p in parts if p) or 'N/A'
#                     break

#             # Affiliation map
#             aff_map: Dict[str, str] = {}
#             for aff in article_meta.findall('.//aff'):
#                 aff_id       = aff.get('id', '')
#                 institutions = [
#                     (inst.text or '').strip()
#                     for inst in aff.findall('.//institution')
#                     if (inst.text or '').strip()
#                 ]
#                 city_e    = aff.find(".//addr-line[@content-type='city']")
#                 country_e = aff.find('country')
#                 city      = (city_e.text    or '').strip() if city_e    is not None else ''
#                 country   = (country_e.text or '').strip() if country_e is not None else ''
#                 parts     = institutions + ([city] if city else []) + ([country] if country else [])
#                 aff_map[aff_id] = ', '.join(filter(None, parts)) or 'N/A'

#             # Authors
#             contrib_group = article_meta.find('.//contrib-group')
#             if contrib_group is None:
#                 continue

#             for contrib in contrib_group.findall('contrib'):
#                 if contrib.get('contrib-type') != 'author':
#                     continue

#                 name_e = contrib.find('name')
#                 if name_e is None:
#                     continue

#                 email_e = contrib.find('.//email')
#                 email   = (email_e.text or '').strip() if email_e is not None else ''
#                 if not email:
#                     continue   # skip authors without email

#                 first_name = (name_e.findtext('given-names') or '').strip()
#                 last_name  = (name_e.findtext('surname')     or '').strip()
#                 full_name  = f'{first_name} {last_name}'.strip() or 'N/A'

#                 affiliations = [
#                     aff_map[xref.get('rid', '')]
#                     for xref in contrib.findall("xref[@ref-type='aff']")
#                     if xref.get('rid', '') in aff_map
#                     and aff_map[xref.get('rid', '')] != 'N/A'
#                 ]
#                 affiliation = ' | '.join(affiliations) if affiliations else 'N/A'

#                 records.append({
#                     'title':       title,
#                     'doi':         doi,
#                     'article_url': article_url,
#                     'pub_date':    pub_date,
#                     'first_name':  first_name or 'N/A',
#                     'last_name':   last_name  or 'N/A',
#                     'full_name':   full_name,
#                     'email':       email,
#                     'affiliation': affiliation,
#                 })

#         return records

#     # ── Main pagination loop ──────────────────────────────────────────────────

#     def fetch_data(self, verbose: bool = True) -> List[Dict]:
#         """
#         Paginate through ALL Springer Nature API pages and collect author rows.

#         Mirrors EuropePMCScraper.fetch_data() — this is what scraper_adapter
#         calls first (hasattr check on 'fetch_data').

#         Returns list of dicts, also stored in self.all_results.
#         """
#         self.all_results = []
#         self._progress(2, f"Starting Springer Nature search for '{self.query}'...")

#         url1 = self._build_url(s=1)
#         self._progress(5, "Fetching page 1 to read total result count...")

#         if verbose:
#             print(f"\n{'='*60}")
#             print(f"  Springer Nature Open Access")
#             print(f"  Keyword     : {self.query}")
#             if self.start_date:
#                 print(f"  Date from   : {self.start_date}")
#             if self.end_date:
#                 print(f"  Date to     : {self.end_date}")
#             print(f"{'='*60}")

#         try:
#             xml1 = self._fetch_raw(url1)
#         except Exception as exc:
#             print(f"  [Springer] Failed to fetch page 1: {exc}")
#             self._progress(100, f"Springer Nature failed: {exc}")
#             return []

#         total       = self._get_total(xml1)
#         total_pages = math.ceil(total / self.page_size) if total > 0 else 0

#         if verbose:
#             print(f"  Total records  : {total:,}")
#             print(f"  Total pages    : {total_pages}")
#             print(f"  (Authors without email are skipped)")
#             print(f"{'='*60}\n")

#         self._progress(8, f"Found {total:,} articles — {total_pages} pages to process")

#         if total == 0:
#             self._progress(100, "No results found for this query / date range.")
#             if verbose:
#                 print("  No results found.")
#                 print("  Tip: try a different keyword or wider date range.")
#             return []

#         # Page 1 already fetched — parse it without re-fetching
#         page1_rows = self._parse_page(xml1)
#         self.all_results.extend(page1_rows)

#         if verbose:
#             print(f"  Page   1 / {total_pages}  |  "
#                   f"{len(page1_rows):>4} email-rows  |  "
#                   f"running total: {len(self.all_results):,}")

#         self._progress(
#             10 if total_pages > 1 else 90,
#             f"Page 1/{total_pages} — {len(self.all_results):,} email records so far",
#             emails_count=len(self.all_results),
#             authors_count=len(self.all_results),
#         )

#         for page_num in range(2, total_pages + 1):
#             s = 1 + (page_num - 1) * self.page_size
#             time.sleep(self.delay)

#             try:
#                 xml_text  = self._fetch_raw(self._build_url(s=s))
#                 page_rows = self._parse_page(xml_text)
#                 self.all_results.extend(page_rows)
#             except Exception as exc:
#                 page_rows = []
#                 print(f"  Page {page_num:>3}/{total_pages}  |  ERROR: {exc}  (skipping)")

#             if verbose:
#                 print(f"  Page {page_num:>3} / {total_pages}  |  s={s:<7}  |  "
#                       f"{len(page_rows):>4} email-rows  |  "
#                       f"running total: {len(self.all_results):,}")

#             pct = int(10 + (page_num / total_pages) * 80)
#             self._progress(
#                 min(pct, 89),
#                 f"Page {page_num}/{total_pages} — {len(self.all_results):,} email records",
#                 emails_count=len(self.all_results),
#                 authors_count=len(self.all_results),
#             )

#         # Deduplicate by email
#         before  = len(self.all_results)
#         seen: set = set()
#         deduped: List[Dict] = []
#         for row in self.all_results:
#             key = row['email'].lower().strip()
#             if key not in seen:
#                 seen.add(key)
#                 deduped.append(row)
#         self.all_results = deduped

#         if verbose:
#             print(f"\n  Unique emails   : {len(self.all_results):,}  "
#                   f"(removed {before - len(self.all_results):,} duplicates)")
#             print(f"{'='*60}")

#         return self.all_results

#     # ── Save ──────────────────────────────────────────────────────────────────

#     @staticmethod
#     def _fieldnames() -> List[str]:
#         return [
#             'title', 'doi', 'article_url', 'pub_date',
#             'first_name', 'last_name', 'full_name',
#             'email', 'affiliation',
#         ]

#     def save_to_csv(self, filename: str = None) -> str:
#         """
#         Write results to CSV — mirrors EuropePMCScraper.save_to_csv(filename=None).

#         Args:
#             filename : Full output path.  Auto-generated if None.
#         Returns:
#             Path of the written file.
#         """
#         if not filename:
#             safe_q = re.sub(r'[^\w\s-]', '', self.query).replace(' ', '-')[:30]
#             if self.start_date and self.end_date:
#                 filename = f"springer-{safe_q}-{self.start_date}-{self.end_date}-emails.csv"
#             else:
#                 timestamp = datetime.now().strftime('%Y%m%d')
#                 filename  = f"springer-{safe_q}-{timestamp}-emails.csv"

#         parent = os.path.dirname(filename)
#         if parent:
#             os.makedirs(parent, exist_ok=True)

#         with open(filename, 'w', newline='', encoding='utf-8') as f:
#             writer = csv.DictWriter(f, fieldnames=self._fieldnames())
#             writer.writeheader()
#             if self.all_results:
#                 writer.writerows(self.all_results)

#         print(f"Results saved to: {filename}  ({len(self.all_results):,} rows)")
#         return filename


# # ── Standalone CLI ─────────────────────────────────────────────────────────────

# if __name__ == '__main__':
#     import argparse, sys

#     parser = argparse.ArgumentParser(
#         description='Springer Nature Open Access — full-pagination email scraper',
#         formatter_class=argparse.RawTextHelpFormatter,
#     )
#     parser.add_argument('--api-key',     default=DEFAULT_KEY,
#                         help='Springer Nature API key  (or set SPRINGER_API_KEY env var)')
#     parser.add_argument('--keyword',     required=True,
#                         help='Search term, e.g. "gene editing"')
#     parser.add_argument('--page-size',   type=int, default=10,
#                         help='Records per page  (default: 10, max: 10)')
#     parser.add_argument('--date-from',   default=None, help='Start date  YYYY-MM-DD')
#     parser.add_argument('--date-to',     default=None, help='End date    YYYY-MM-DD')
#     parser.add_argument('--delay',       type=float, default=0.5,
#                         help='Seconds between requests  (default: 0.5)')
#     parser.add_argument('--output',      default=None, help='Output CSV path')
#     args = parser.parse_args()

#     scraper = SpringerNatureScraper(
#         query      = args.keyword,
#         start_date = args.date_from,
#         end_date   = args.date_to,
#         api_key    = args.api_key,
#         page_size  = args.page_size,
#         delay      = args.delay,
#     )

#     results = scraper.fetch_data(verbose=True)

#     if not results:
#         print('\nNo authors with email addresses found.')
#         sys.exit(1)

#     scraper.save_to_csv(args.output)

#!/usr/bin/env python3
"""
Springer Nature Open Access API Scraper
=========================================
Mirrors EuropePMCScraper interface for drop-in webapp / Celery integration.

URL format (all terms inside ONE set of parentheses — verified working):
  (keyword:"gene editing" AND datefrom:"2026-01-01" AND dateto:"2026-03-09")

Date format : YYYY-MM-DD
API page cap: 10 records per page (Springer hard limit)

Critical HTTP note
───────────────────
requests.get(url) re-encodes parentheses and quotes in the query string,
turning (keyword:"x") into %28keyword%3A%22x%22%29 → Springer returns 403.
Fix: PreparedRequest + session.send() keeps the URL exactly as built.
"""

import os
import re
import csv
import math
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Optional, Callable


BASE_URL    = 'https://api.springernature.com/openaccess/jats'
DEFAULT_KEY = os.environ.get('SPRINGER_API_KEY', 'c904ff1b51765d5b62e6af740adcff37')


class SpringerNatureScraper:
    """
    Full-pagination scraper for the Springer Nature Open Access JATS API.

    Constructor mirrors EuropePMCScraper so scraper_adapter.py needs
    zero special-casing beyond registering the module.

    Webapp usage (via scraper_adapter):
        scraper = SpringerNatureScraper(
            query=keyword,
            start_date=start_converted,   # YYYY-MM-DD
            end_date=end_converted,       # YYYY-MM-DD
        )
        scraper.progress_callback = self.progress_callback
        results     = scraper.fetch_data()
        output_file = scraper.save_to_csv(filename=path)

    Standalone CLI:
        python springernature_scraper.py --keyword "gene editing" \\
               --date-from 2025-01-01 --date-to 2025-12-31
    """

    def __init__(
        self,
        query:             str,
        start_date:        Optional[str]      = None,
        end_date:          Optional[str]      = None,
        api_key:           str                = DEFAULT_KEY,
        page_size:         int                = 10,
        delay:             float              = 0.5,
        progress_callback: Optional[Callable] = None,
    ):
        self.query             = query
        self.start_date        = start_date
        self.end_date          = end_date
        self.api_key           = api_key or DEFAULT_KEY
        self.page_size         = min(max(int(page_size), 1), 10)
        self.delay             = max(float(delay), 0)
        self.progress_callback = progress_callback
        self.all_results: List[Dict] = []
        self._session          = requests.Session()

    # ── Progress ──────────────────────────────────────────────────────────────

    def _progress(self, pct: int, msg: str, **kwargs):
        if self.progress_callback:
            try:
                self.progress_callback(pct, msg, **kwargs)
            except Exception:
                pass

    # ── URL builder ───────────────────────────────────────────────────────────

    def _build_url(self, s: int) -> str:
        """
        All query terms go inside ONE set of parentheses.

        Working format (verified):
          (keyword:"gene editing" AND datefrom:"2026-01-01" AND dateto:"2026-03-09")

        Broken format — Springer returns 403:
          (keyword:"gene editing") AND datefrom:"2026-01-01" AND dateto:"2026-03-09"
        """
        parts = [f'keyword:"{self.query}"']
        if self.start_date:
            parts.append(f'datefrom:"{self.start_date}"')
        if self.end_date:
            parts.append(f'dateto:"{self.end_date}"')

        q = '(' + ' AND '.join(parts) + ')'

        return (
            f'{BASE_URL}'
            f'?api_key={self.api_key}'
            f'&callback='
            f'&s={s}'
            f'&p={self.page_size}'
            f'&q={q}'
        )

    # ── HTTP — no re-encoding ─────────────────────────────────────────────────

    def _fetch_raw(self, url: str) -> str:
        req     = requests.Request('GET', url)
        prepped = req.prepare()
        prepped.url = url   # override — keeps parentheses and quotes intact

        for attempt in range(3):
            try:
                resp = self._session.send(prepped, timeout=30)
                if resp.status_code == 429:
                    wait = 2 ** (attempt + 1)
                    print(f"  [Springer][429] rate-limit — retrying in {wait}s ...")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.text
            except requests.HTTPError as exc:
                if attempt == 2:
                    raise RuntimeError(f"Springer API HTTP error: {exc}") from exc
                time.sleep(2 * (attempt + 1))
            except Exception as exc:
                if attempt == 2:
                    raise RuntimeError(f"Springer API fetch failed: {exc}") from exc
                time.sleep(2 * (attempt + 1))

        raise RuntimeError("Springer API: exhausted retries")

    # ── XML helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _strip_doctype(xml_text: str) -> str:
        text = re.sub(r'<\?xml-stylesheet[^?]*\?>', '', xml_text, flags=re.DOTALL)
        text = re.sub(r'<!DOCTYPE\s+\w+\s*\[.*?\]\s*>', '', text, flags=re.DOTALL)
        text = re.sub(r'<!DOCTYPE\s+\w+[^>]*>',         '', text, flags=re.DOTALL)
        return text

    def _get_total(self, xml_text: str) -> int:
        root = ET.fromstring(self._strip_doctype(xml_text))
        raw  = root.findtext('.//result/total') or root.findtext('.//total') or '0'
        try:
            return int(raw.strip())
        except (ValueError, AttributeError):
            return 0

    # ── Page parser ───────────────────────────────────────────────────────────

    def _parse_page(self, xml_text: str) -> List[Dict]:
        """
        Parse one page of JATS XML into author rows.
        Only keeps authors with a non-empty email address.

        Columns match count_results_detailed() in app.py:
            full_name   -> authors_count
            email       -> emails_count
            article_url -> links_count
        """
        root    = ET.fromstring(self._strip_doctype(xml_text))
        records = []

        for article in root.iter('article'):
            front = article.find('front')
            if front is None:
                continue
            article_meta = front.find('article-meta')
            if article_meta is None:
                continue

            # Article metadata
            title_e = article_meta.find('.//article-title')
            title   = ''.join(title_e.itertext()).strip() if title_e is not None else 'N/A'

            doi_e       = article_meta.find('.//article-id[@pub-id-type="doi"]')
            doi         = (doi_e.text or '').strip() if doi_e is not None else 'N/A'
            article_url = f'https://doi.org/{doi}' if doi and doi != 'N/A' else 'N/A'

            pub_date = 'N/A'
            for attr in ('epub', 'ppub', 'collection', ''):
                pd_e = (article_meta.find(f".//pub-date[@pub-type='{attr}']")
                        if attr else article_meta.find('.//pub-date'))
                if pd_e is not None:
                    parts    = [pd_e.findtext('year',  '').strip(),
                                pd_e.findtext('month', '').strip(),
                                pd_e.findtext('day',   '').strip()]
                    pub_date = '/'.join(p for p in parts if p) or 'N/A'
                    break

            # Affiliation map
            aff_map: Dict[str, str] = {}
            for aff in article_meta.findall('.//aff'):
                aff_id       = aff.get('id', '')
                institutions = [
                    (inst.text or '').strip()
                    for inst in aff.findall('.//institution')
                    if (inst.text or '').strip()
                ]
                city_e    = aff.find(".//addr-line[@content-type='city']")
                country_e = aff.find('country')
                city      = (city_e.text    or '').strip() if city_e    is not None else ''
                country   = (country_e.text or '').strip() if country_e is not None else ''
                parts     = institutions + ([city] if city else []) + ([country] if country else [])
                aff_map[aff_id] = ', '.join(filter(None, parts)) or 'N/A'

            # Authors
            contrib_group = article_meta.find('.//contrib-group')
            if contrib_group is None:
                continue

            for contrib in contrib_group.findall('contrib'):
                if contrib.get('contrib-type') != 'author':
                    continue

                name_e = contrib.find('name')
                if name_e is None:
                    continue

                email_e = contrib.find('.//email')
                email   = (email_e.text or '').strip() if email_e is not None else ''
                if not email:
                    continue   # skip authors without email

                first_name = (name_e.findtext('given-names') or '').strip()
                last_name  = (name_e.findtext('surname')     or '').strip()
                full_name  = f'{first_name} {last_name}'.strip() or 'N/A'

                affiliations = [
                    aff_map[xref.get('rid', '')]
                    for xref in contrib.findall("xref[@ref-type='aff']")
                    if xref.get('rid', '') in aff_map
                    and aff_map[xref.get('rid', '')] != 'N/A'
                ]
                affiliation = ' | '.join(affiliations) if affiliations else 'N/A'

                records.append({
                    'title':       title,
                    'doi':         doi,
                    'article_url': article_url,
                    'pub_date':    pub_date,
                    'first_name':  first_name or 'N/A',
                    'last_name':   last_name  or 'N/A',
                    'full_name':   full_name,
                    'email':       email,
                    'affiliation': affiliation,
                })

        return records

    # ── Main pagination loop ──────────────────────────────────────────────────

    def fetch_data(self, verbose: bool = True) -> List[Dict]:
        """
        Paginate through ALL Springer Nature API pages and collect author rows.

        Mirrors EuropePMCScraper.fetch_data() — this is what scraper_adapter
        calls first (hasattr check on 'fetch_data').

        Returns list of dicts, also stored in self.all_results.
        """
        self.all_results = []
        self._progress(2, f"Starting Springer Nature search for '{self.query}'...")

        url1 = self._build_url(s=1)
        self._progress(5, "Fetching page 1 to read total result count...")

        if verbose:
            print(f"\n{'='*60}")
            print(f"  Springer Nature Open Access")
            print(f"  Keyword     : {self.query}")
            if self.start_date:
                print(f"  Date from   : {self.start_date}")
            if self.end_date:
                print(f"  Date to     : {self.end_date}")
            print(f"{'='*60}")

        try:
            xml1 = self._fetch_raw(url1)
        except Exception as exc:
            print(f"  [Springer] Failed to fetch page 1: {exc}")
            self._progress(100, f"Springer Nature failed: {exc}")
            return []

        total       = self._get_total(xml1)
        total_pages = math.ceil(total / self.page_size) if total > 0 else 0

        if verbose:
            print(f"  Total records  : {total:,}")
            print(f"  Total pages    : {total_pages}")
            print(f"  (Authors without email are skipped)")
            print(f"{'='*60}\n")

        self._progress(8, f"Found {total:,} articles — {total_pages} pages to process")

        if total == 0:
            self._progress(100, "No results found for this query / date range.")
            if verbose:
                print("  No results found.")
                print("  Tip: try a different keyword or wider date range.")
            return []

        # Page 1 already fetched — parse it without re-fetching
        page1_rows = self._parse_page(xml1)
        self.all_results.extend(page1_rows)

        if verbose:
            print(f"  Page   1 / {total_pages}  |  "
                  f"{len(page1_rows):>4} email-rows  |  "
                  f"running total: {len(self.all_results):,}")

        self._progress(
            10 if total_pages > 1 else 90,
            f"Page 1/{total_pages} — {len(self.all_results):,} email records so far",
            emails_count=len(self.all_results),
            authors_count=len(self.all_results),
        )

        for page_num in range(2, total_pages + 1):
            s = 1 + (page_num - 1) * self.page_size
            time.sleep(self.delay)

            try:
                xml_text  = self._fetch_raw(self._build_url(s=s))
                page_rows = self._parse_page(xml_text)
                self.all_results.extend(page_rows)
            except Exception as exc:
                page_rows = []
                print(f"  Page {page_num:>3}/{total_pages}  |  ERROR: {exc}  (skipping)")

            if verbose:
                print(f"  Page {page_num:>3} / {total_pages}  |  s={s:<7}  |  "
                      f"{len(page_rows):>4} email-rows  |  "
                      f"running total: {len(self.all_results):,}")

            pct = int(10 + (page_num / total_pages) * 80)
            self._progress(
                min(pct, 89),
                f"Page {page_num}/{total_pages} — {len(self.all_results):,} email records",
                emails_count=len(self.all_results),
                authors_count=len(self.all_results),
            )

        # Deduplicate by email
        before  = len(self.all_results)
        seen: set = set()
        deduped: List[Dict] = []
        for row in self.all_results:
            key = row['email'].lower().strip()
            if key not in seen:
                seen.add(key)
                deduped.append(row)
        self.all_results = deduped

        if verbose:
            print(f"\n  Unique emails   : {len(self.all_results):,}  "
                  f"(removed {before - len(self.all_results):,} duplicates)")
            print(f"{'='*60}")

        return self.all_results

    # ── Save ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _fieldnames() -> List[str]:
        return [
            'title', 'doi', 'article_url', 'pub_date',
            'first_name', 'last_name', 'full_name',
            'email', 'affiliation',
        ]

    def save_to_csv(self, filename: str = None) -> str:
        """
        Write results to CSV — mirrors EuropePMCScraper.save_to_csv(filename=None).

        Args:
            filename : Full output path.  Auto-generated if None.
        Returns:
            Path of the written file.
        """
        if not filename:
            safe_q = re.sub(r'[^\w\s-]', '', self.query).replace(' ', '-')[:30]
            if self.start_date and self.end_date:
                filename = f"springer-{safe_q}-{self.start_date}-{self.end_date}-emails.csv"
            else:
                timestamp = datetime.now().strftime('%Y%m%d')
                filename  = f"springer-{safe_q}-{timestamp}-emails.csv"

        parent = os.path.dirname(filename)
        if parent:
            os.makedirs(parent, exist_ok=True)

        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=self._fieldnames())
            writer.writeheader()
            if self.all_results:
                writer.writerows(self.all_results)

        print(f"Results saved to: {filename}  ({len(self.all_results):,} rows)")
        return filename


# ── Standalone CLI ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse, sys

    parser = argparse.ArgumentParser(
        description='Springer Nature Open Access — full-pagination email scraper',
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument('--api-key',     default=DEFAULT_KEY,
                        help='Springer Nature API key  (or set SPRINGER_API_KEY env var)')
    parser.add_argument('--keyword',     required=True,
                        help='Search term, e.g. "gene editing"')
    parser.add_argument('--page-size',   type=int, default=10,
                        help='Records per page  (default: 10, max: 10)')
    parser.add_argument('--date-from',   default=None, help='Start date  YYYY-MM-DD')
    parser.add_argument('--date-to',     default=None, help='End date    YYYY-MM-DD')
    parser.add_argument('--delay',       type=float, default=0.5,
                        help='Seconds between requests  (default: 0.5)')
    parser.add_argument('--output',      default=None, help='Output CSV path')
    args = parser.parse_args()

    scraper = SpringerNatureScraper(
        query      = args.keyword,
        start_date = args.date_from,
        end_date   = args.date_to,
        api_key    = args.api_key,
        page_size  = args.page_size,
        delay      = args.delay,
    )

    results = scraper.fetch_data(verbose=True)

    if not results:
        print('\nNo authors with email addresses found.')
        sys.exit(1)

    scraper.save_to_csv(args.output)
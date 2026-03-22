"""
sciencedirect_selenium.py
══════════════════════════════════════════════════════════════════════════════
Python wrapper for the ScienceDirect Puppeteer scraper (index.cjs).

Architecture:
    Celery → SeleniumScraperWrapper → billiard.Process
                                           └─ ScienceDirectScraper.run()
                                                └─ subprocess.Popen(node index.cjs ...)
                                                     └─ Puppeteer / Chrome (headful)

The Node.js scraper (index.cjs) is called with CLI args:
    node index.cjs --keyword "..." --start-year YYYY --end-year YYYY
                   --output-dir "/path/" --log-dir "logs/"
                   --conf-name "ConferenceName"

It writes:
    {output_dir}/{conf}_{keyword}_{start}_{end}_{HH-MM-SS}_authors.csv
    logs/ScienceDirectScraper-{keyword}-{start}-{end}.log

Progress is forwarded via stdout lines: PROGRESS:{pct}:{message}
══════════════════════════════════════════════════════════════════════════════
"""

import csv
import logging
import os
import subprocess
import sys
import time
import threading
from datetime import datetime


class ScienceDirectScraper:
    """
    Python interface matching the standard SeleniumScraperWrapper contract:
        __init__(keyword, start_year, end_year, driver_path,
                 output_dir=None, progress_callback=None, conference_name="")
        run() → (authors_csv_path, summary_str)
    """

    # Path to the Node.js scraper — same directory as this file
    _NODE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sciencedirect", "index.cjs")

    def __init__(self, keyword, start_year, end_year, driver_path=None,
                 output_dir=None, progress_callback=None, conference_name=""):
        self.keyword           = keyword
        self.start_year        = start_year   # MM/DD/YYYY
        self.end_year          = end_year     # MM/DD/YYYY
        self.driver_path       = driver_path  # not used (puppeteer manages Chrome)
        self.output_dir        = output_dir
        self.progress_callback = progress_callback
        self.conference_name   = conference_name
        self.directory         = keyword.replace(" ", "-")

        self._setup_logger()

        # Timestamped output filenames
        _ts   = datetime.now().strftime("%H-%M-%S")
        _conf = f"_{conference_name}" if conference_name else ""
        _sd   = start_year.replace("/", "-")
        _ed   = end_year.replace("/", "-")
        _base = f"ScienceDirect{_conf}_{self.directory}_{_sd}_{_ed}_{_ts}"
        self.authors_csv = f"{_base}_authors.csv"
        self.url_csv     = f"{_base}_urls.csv"

    # ── Logger — writes to logs/ same as BMJ/Taylor ────────────────────────

    def _setup_logger(self):
        self.logger = logging.getLogger(f"ScienceDirectScraper-{id(self)}")
        self.logger.setLevel(logging.INFO)
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(
            log_dir,
            f"ScienceDirectScraper-{self.directory}"
            f"-{self.start_year.replace('/', '-')}"
            f"-{self.end_year.replace('/', '-')}.log"
        )
        if self.logger.hasHandlers():
            self.logger.handlers.clear()
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
        try:
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            ))
            self.logger.addHandler(fh)
        except Exception:
            pass
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
        self.logger.addHandler(sh)
        self.logger.info(f"ScienceDirect ==> Logger initialised → {log_file}")

    # ── Helpers ────────────────────────────────────────────────────────────

    def _work_dir(self) -> str:
        d = self.output_dir if self.output_dir else self.directory
        os.makedirs(d, exist_ok=True)
        return d

    def _progress(self, pct: int, msg: str, **kwargs):
        self.logger.info(f"ScienceDirect ==> [{pct}%] {msg}")
        if self.progress_callback:
            try:
                self.progress_callback(pct, msg, **kwargs)
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception:
                pass

    def _extract_year(self, date_str: str) -> str:
        """Extract YYYY from MM/DD/YYYY or return as-is if already YYYY."""
        parts = date_str.split("/")
        return parts[-1] if len(parts) >= 3 else date_str

    # ── Main entry point ───────────────────────────────────────────────────

    def run(self):
        """
        Launch the Node.js Puppeteer scraper, relay progress, wait for completion.
        Returns (authors_csv_path, summary_string).
        Raises RuntimeError on failure so Celery marks the job FAILED.
        """
        work_dir     = self._work_dir()
        authors_path = os.path.join(work_dir, self.authors_csv)
        url_path     = os.path.join(work_dir, self.url_csv)

        start_yr = self._extract_year(self.start_year)
        end_yr   = self._extract_year(self.end_year)

        # Verify Node.js script exists
        node_script = self._NODE_SCRIPT
        if not os.path.exists(node_script):
            raise RuntimeError(
                f"ScienceDirect Node.js script not found at {node_script}. "
                "Deploy sciencedirect/index.cjs to the project directory."
            )

        # Verify node is available
        try:
            node_bin = subprocess.check_output(
                ["which", "node"], text=True
            ).strip() or "node"
        except Exception:
            node_bin = "node"

        cmd = [
            node_bin, node_script,
            "--keyword",    self.keyword,
            "--start-year", start_yr,
            "--end-year",   end_yr,
            "--output-dir", work_dir,
            "--log-dir",    "logs",
            "--conf-name",  self.conference_name or "",
            "--url-csv",    url_path,
            "--authors-csv", authors_path,
        ]

        # Pass DISPLAY so Puppeteer can open Chrome on Xvfb
        env = os.environ.copy()
        if not env.get("DISPLAY"):
            env["DISPLAY"] = ":99"

        self.logger.info(
            f"ScienceDirect ==> Launching Node.js scraper: {' '.join(cmd[:3])} ..."
        )
        self._progress(2, "Launching ScienceDirect Puppeteer scraper...")

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                bufsize=1,
            )
        except FileNotFoundError as e:
            raise RuntimeError(f"node not found: {e}. Install Node.js on the server.")

        # ── Stream stdout and parse PROGRESS lines ─────────────────────────
        authors_found = 0
        links_found   = 0
        output_file   = None

        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue

            # Log everything from Node.js to our Python logger
            self.logger.info(f"[node] {line}")

            # Parse structured progress: PROGRESS:{pct}:{message}
            if line.startswith("PROGRESS:"):
                parts = line.split(":", 2)
                if len(parts) == 3:
                    try:
                        pct = int(parts[1])
                        msg = parts[2]
                        # Parse optional counters from message
                        if "authors=" in msg:
                            for token in msg.split():
                                if token.startswith("authors="):
                                    authors_found = int(token.split("=")[1])
                                elif token.startswith("links="):
                                    links_found = int(token.split("=")[1])
                        self._progress(
                            pct, msg.split("|")[0].strip(),
                            current_url="",
                            authors_count=authors_found,
                            links_count=links_found,
                        )
                    except (ValueError, IndexError):
                        pass

            # Parse OUTPUT_FILE line written by Node at the end
            elif line.startswith("OUTPUT_FILE:"):
                output_file = line.split(":", 1)[1].strip()
                self.logger.info(f"ScienceDirect ==> Output file: {output_file}")

        proc.wait()

        if proc.returncode != 0:
            raise RuntimeError(
                f"ScienceDirect Node.js scraper exited with code {proc.returncode}. "
                "Check logs/ScienceDirectScraper-*.log for details."
            )

        # Prefer the path reported by Node; fall back to our pre-computed path
        if output_file and os.path.exists(output_file):
            final_path = output_file
        elif os.path.exists(authors_path):
            final_path = authors_path
        else:
            # Scan output_dir for newest CSV
            import glob
            csvs = sorted(
                glob.glob(os.path.join(work_dir, "*.csv")),
                key=os.path.getmtime,
                reverse=True
            )
            # Prefer author/email files
            author_csvs = [f for f in csvs if "author" in os.path.basename(f).lower() or
                           "email" in os.path.basename(f).lower()]
            final_path = author_csvs[0] if author_csvs else (csvs[0] if csvs else authors_path)

        self._progress(100, "ScienceDirect scraping completed.")
        self.logger.info(f"ScienceDirect ==> Done. Output: {final_path}")
        return final_path, f"ScienceDirect scrape complete"

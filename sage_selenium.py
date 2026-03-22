"""
sage_selenium.py  — Python/Celery wrapper for the Sage Puppeteer scraper.
Replaces the old Selenium-based sage_scraper.py for the Celery pipeline.
Calls: node sage_puppeteer.js --keyword ... --start-year ... --end-year ...
"""

import glob, logging, os, subprocess, sys
from datetime import datetime


class SageScraper:
    _NODE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sage_puppeteer.js")

    def __init__(self, keyword, start_year, end_year, driver_path=None,
                 output_dir=None, progress_callback=None, conference_name=""):
        self.keyword           = keyword
        self.start_year        = start_year
        self.end_year          = end_year
        self.output_dir        = output_dir
        self.progress_callback = progress_callback
        self.conference_name   = conference_name
        self.directory         = keyword.replace(" ", "-")
        self._setup_logger()
        _ts   = datetime.now().strftime("%H-%M-%S")
        _conf = f"_{conference_name}" if conference_name else ""
        _sd   = start_year.replace("/", "-")
        _ed   = end_year.replace("/", "-")
        _base = f"Sage{_conf}_{self.directory}_{_sd}_{_ed}_{_ts}"
        self.authors_csv = f"{_base}_authors.csv"
        self.url_csv     = f"{_base}_urls.csv"

    def _setup_logger(self):
        self.logger = logging.getLogger(f"SageScraper-{id(self)}")
        self.logger.setLevel(logging.INFO)
        log_dir  = "logs"
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir,
            f"SageScraper-{self.directory}"
            f"-{self.start_year.replace('/','')}-{self.end_year.replace('/','')}.log")
        self.logger.handlers.clear()
        try: sys.stdout.reconfigure(encoding="utf-8")
        except Exception: pass
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        self.logger.addHandler(fh)
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        self.logger.addHandler(sh)

    def _work_dir(self):
        d = self.output_dir or self.directory
        os.makedirs(d, exist_ok=True)
        return d

    def _progress(self, pct, msg, **kwargs):
        self.logger.info(f"Sage ==> [{pct}%] {msg}")
        if self.progress_callback:
            try: self.progress_callback(pct, msg, **kwargs)
            except Exception: pass

    def run(self):
        work_dir     = self._work_dir()
        authors_path = os.path.join(work_dir, self.authors_csv)
        url_path     = os.path.join(work_dir, self.url_csv)

        if not os.path.exists(self._NODE_SCRIPT):
            raise RuntimeError(f"sage_puppeteer.js not found at {self._NODE_SCRIPT}")

        node_bin = subprocess.check_output(["which", "node"], text=True).strip() or "node"
        cmd = [node_bin, self._NODE_SCRIPT,
               "--keyword",     self.keyword,
               "--start-year",  self.start_year,
               "--end-year",    self.end_year,
               "--output-dir",  work_dir,
               "--log-dir",     "logs",
               "--conf-name",   self.conference_name or "",
               "--url-csv",     url_path,
               "--authors-csv", authors_path]

        env = os.environ.copy()
        if not env.get("DISPLAY"): env["DISPLAY"] = ":99"

        self.logger.info(f"Sage ==> Launching: node sage_puppeteer.js ...")
        self._progress(2, "Launching Sage Puppeteer scraper...")

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, env=env, bufsize=1)
        output_file = None
        for line in proc.stdout:
            line = line.rstrip()
            if not line: continue
            self.logger.info(f"[node] {line}")
            if line.startswith("PROGRESS:"):
                parts = line.split(":", 2)
                if len(parts) == 3:
                    try:
                        pct = int(parts[1]); msg = parts[2]
                        self._progress(pct, msg.split("|")[0].strip())
                    except ValueError: pass
            elif line.startswith("OUTPUT_FILE:"):
                output_file = line.split(":", 1)[1].strip()

        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"Sage Puppeteer scraper exited with code {proc.returncode}.")

        if output_file and os.path.exists(output_file):
            final = output_file
        elif os.path.exists(authors_path):
            final = authors_path
        else:
            csvs = sorted(glob.glob(os.path.join(work_dir, "*.csv")),
                          key=os.path.getmtime, reverse=True)
            final = next((f for f in csvs if "author" in f.lower()), csvs[0] if csvs else authors_path)

        self._progress(100, "Sage scraping completed.")
        return final, "Sage scrape complete"
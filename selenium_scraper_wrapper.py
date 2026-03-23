"""
SeleniumScraperWrapper — Safely runs Selenium-based scrapers inside Celery workers.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  WHY THIS EXISTS
  ───────────────
  Celery workers are daemonic processes.  Python's multiprocessing
  forbids daemonic processes from spawning children.
  undetected_chromedriver calls multiprocessing.Process internally
  when it patches the Chrome binary, so uc.Chrome() raises:

      "daemonic processes are not allowed to have children"

  SOLUTION
  ────────
  This wrapper spawns a *non-daemonic* billiard subprocess for every
  Selenium scraper.  billiard is Celery's own multiprocessing fork
  (already a dependency) that does NOT enforce the daemon restriction.

  API scrapers (EuropePMC, PubMed) bypass this wrapper entirely —
  they never touch Chrome and run directly in the Celery task.

  ARCHITECTURE FOR SCALE
  ──────────────────────
  Celery task
    └─ ScraperAdapter.run_scraper()
         └─ SeleniumScraperWrapper.run()          ← this file
              └─ billiard.Process (non-daemonic)
                   └─ _scraper_subprocess_entry()
                        └─ SpringerAuthorScraper / CambridgeScraper / …
                             └─ uc.Chrome()       ← works ✓

  Progress flows back via a billiard.Queue:
    child puts (type, progress, message, extra_kwargs)
    parent drains the queue in a background thread and calls
    the progress_callback supplied by ScraperAdapter.

  TIMEOUT COORDINATION
  ────────────────────
  _DEFAULT_TIMEOUT (this file)   →  28,200s  (7h 50m)  fires first → raises RuntimeError
  Celery soft_time_limit         →  28,800s  (8h 00m)  fires second → saves partial results
  Celery hard time_limit         →  30,600s  (8h 30m)  SIGKILL

  The wrapper timeout MUST be shorter than Celery's soft limit so that
  when a job times out, the wrapper raises a catchable Exception →
  Celery's except block runs → partial results are saved to DB →
  download buttons appear in the UI.

  To add a new Selenium scraper, register it in scraper_adapter.py
  and wrap it here — zero changes needed to this file.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from __future__ import annotations

import logging
import os
import time
from typing import Callable, Optional, Type

import billiard
import billiard.context

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────
# FIX: Was 3_600 (1 hour) — Springer jobs with 1000+ articles need much longer.
# This MUST stay below Celery's soft_time_limit (28_800s) so the exception
# is catchable and partial results can be saved before Celery hard-kills the task.
_DEFAULT_TIMEOUT         = 28_200   # 7h 50m — safely below Celery's 8h soft limit
_QUEUE_POLL_SLEEP        = 0.2      # seconds between queue drain iterations
_SUBPROCESS_JOIN_TIMEOUT = 30       # seconds to wait for clean subprocess exit

# Message type constants — sent over the inter-process Queue
_MSG_PROGRESS = 'progress'  # (type, pct, msg, extra)
_MSG_DONE     = 'done'       # (type, pct, msg, extra)
_MSG_ERROR    = 'error'      # (type, pct, msg, extra)


# ── Subprocess entry point ───────────────────────────────────────
# This function runs inside the billiard child process.
# It must be a module-level function (not a lambda / closure) so
# billiard can pickle it for the spawn start method.

def _scraper_subprocess_entry(
    scraper_class,
    init_kwargs:   dict,
    progress_queue,          # billiard.Queue  — send progress back to parent
    stop_event,              # billiard.Event  — set by parent to request stop
) -> None:
    """
    Runs the scraper inside a non-daemonic billiard process.

    Sends structured messages back to the parent via progress_queue:
        (type: str, progress: int, message: str, extra: dict)

    The scraper classes call self.run() inside __init__, so instantiation
    IS execution.  We wrap it in try/except and relay all outcomes.
    """
    def _stop_requested() -> bool:
        return stop_event.is_set()

    scraper_class._stop_requested = staticmethod(_stop_requested)

    try:
        progress_queue.put((_MSG_PROGRESS, 1, 'Initializing Chrome driver…', {}))

        def _relay_progress(
            progress:      int,
            status:        str,
            current_url:   str = '',
            links_count:   int = 0,
            authors_count: int = 0,
            emails_count:  int = 0,
        ):
            if _stop_requested():
                raise KeyboardInterrupt('Stop requested via stop_event')
            progress_queue.put((_MSG_PROGRESS, progress, status, {
                'current_url':   current_url,
                'links_count':   links_count,
                'authors_count': authors_count,
                'emails_count':  emails_count,
            }))

        if 'progress_callback' in scraper_class.__init__.__code__.co_varnames:
            init_kwargs['progress_callback'] = _relay_progress

        _instance = scraper_class(**init_kwargs)

        output_file = None
        if hasattr(_instance, 'run') and callable(_instance.run):
            result = _instance.run()
            if isinstance(result, tuple) and len(result) >= 1:
                output_file = result[0]
            elif isinstance(result, str) and os.path.exists(result):
                output_file = result

        progress_queue.put((_MSG_DONE, 100, 'Scraping completed successfully', {
            'output_file': output_file or '',
        }))

    except KeyboardInterrupt:
        progress_queue.put((_MSG_ERROR, 0, 'Scraper stopped by user', {}))

    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        logger.error("[SubProcess] Scraper %s raised: %s\n%s",
                     scraper_class.__name__, exc, tb)
        progress_queue.put((_MSG_ERROR, 0, str(exc), {'traceback': tb}))


# ── Main wrapper class ───────────────────────────────────────────

class SeleniumScraperWrapper:
    """
    Safely wraps any Selenium-based scraper for execution inside a Celery worker.

    Usage (in scraper_adapter.py):
        from selenium_scraper_wrapper import SeleniumScraperWrapper
        from springer_scraper import SpringerAuthorScraper

        wrapper = SeleniumScraperWrapper(
            scraper_class=SpringerAuthorScraper,
            keyword=keyword,
            start_year=start_date,
            end_year=end_date,
            driver_path=driver_path,
        )
        wrapper.set_progress_callback(callback)
        output_file, summary = wrapper.run()
    """

    def __init__(
        self,
        scraper_class: Type,
        keyword:       str,
        start_year:    str,
        end_year:      str,
        driver_path:   Optional[str] = None,
        timeout:       int           = _DEFAULT_TIMEOUT,
        output_dir:    Optional[str] = None,
        job_id:        Optional[str] = None,
        conference_name: str         = '',
    ):
        self.scraper_class   = scraper_class
        self.keyword         = keyword
        self.start_year      = start_year
        self.end_year        = end_year
        self.driver_path     = driver_path
        self.timeout         = timeout
        self.output_dir      = output_dir
        self.job_id          = job_id or 'unknown'
        self.conference_name = conference_name

        self._progress_callback: Optional[Callable] = None
        self._subprocess: Optional[billiard.Process] = None
        self._stop_event:  Optional[billiard.Event]  = None

        logger.info(
            "[Wrapper][%s] Created for %s (timeout=%ds / %.1fh)",
            self.job_id[:8], scraper_class.__name__, timeout, timeout / 3600,
        )

    # ── Public interface ─────────────────────────────────────────

    def set_progress_callback(self, callback: Callable) -> None:
        """Register the progress callback supplied by ScraperAdapter."""
        self._progress_callback = callback

    def run(self) -> tuple[Optional[str], dict]:
        """
        Spawn the scraper in a billiard subprocess, relay progress, and block
        until the scraper finishes or the timeout is exceeded.

        Returns:
            (output_file_path, summary_dict)
            output_file_path is None if the scraper produced no output.
        """
        ctx       = billiard.get_context('spawn')
        q         = ctx.Queue(maxsize=1_000)
        stop_evt  = ctx.Event()

        self._stop_event = stop_evt

        init_kwargs = {
            'keyword':         self.keyword,
            'start_year':      self.start_year,
            'end_year':        self.end_year,
            'driver_path':     self.driver_path,
            'conference_name': self.conference_name,
        }
        if self.output_dir:
            init_kwargs['output_dir'] = self.output_dir

        process = ctx.Process(
            target=_scraper_subprocess_entry,
            args=(self.scraper_class, init_kwargs, q, stop_evt),
            name=f'scraper-{self.scraper_class.__name__}-{self.job_id[:8]}',
        )
        # Explicitly mark as non-daemonic so it can spawn Chrome
        process.daemon = False
        self._subprocess = process

        logger.info(
            "[Wrapper][%s] Launching subprocess for %s (timeout=%ds / %.1fh)",
            self.job_id[:8], self.scraper_class.__name__,
            self.timeout, self.timeout / 3600,
        )
        process.start()

        outcome = self._drain_queue_until_done(q, process)
        self._join_subprocess(process)

        if outcome['type'] == _MSG_ERROR:
            raise RuntimeError(
                f"Selenium scraper failed: {outcome['message']}"
            )

        # Prefer the output_file path returned by the subprocess DONE message,
        # then fall back to scanning the output directory — always preferring
        # author/email files over Phase-1 URL-collection files.
        output_file = outcome.get('output_file') or ''
        if not output_file or not os.path.exists(output_file):
            output_file = self._find_output_file()

        summary = {
            'scraper':    self.scraper_class.__name__,
            'keyword':    self.keyword,
            'start_year': self.start_year,
            'end_year':   self.end_year,
        }
        logger.info(
            "[Wrapper][%s] Subprocess finished. Output: %s",
            self.job_id[:8], output_file,
        )
        return output_file, summary

    def stop(self) -> None:
        """
        Request cooperative stop.  The subprocess checks the stop_event
        via _stop_requested() in its progress relay loop.
        If the subprocess does not exit within _SUBPROCESS_JOIN_TIMEOUT seconds
        it is terminated forcefully.
        """
        if self._stop_event:
            self._stop_event.set()
            logger.info("[Wrapper][%s] Stop event set", self.job_id[:8])

    # ── Internal helpers ─────────────────────────────────────────

    def _drain_queue_until_done(
        self,
        q,
        process: billiard.Process,
    ) -> dict:
        """
        Block until the subprocess puts a DONE or ERROR message, or until
        the timeout is exceeded.  Calls the progress_callback for every
        PROGRESS message received.

        Returns the final outcome dict.
        """
        deadline = time.monotonic() + self.timeout
        outcome  = {'type': _MSG_ERROR, 'message': f'Timed out after {self.timeout}s'}

        while True:
            # ── Hard timeout ─────────────────────────────────────
            if time.monotonic() > deadline:
                elapsed_h = self.timeout / 3600
                logger.error(
                    "[Wrapper][%s] Timeout after %ds (%.1fh) — terminating subprocess",
                    self.job_id[:8], self.timeout, elapsed_h,
                )
                self.stop()
                time.sleep(2)
                if process.is_alive():
                    process.terminate()
                outcome = {
                    'type':    _MSG_ERROR,
                    'message': f'Timed out after {self.timeout}s ({elapsed_h:.1f}h)',
                }
                break

            # ── Subprocess died without a terminal message ───────
            if not process.is_alive() and q.empty():
                exit_code = process.exitcode
                if exit_code != 0:
                    msg = f'Subprocess exited unexpectedly with code {exit_code}'
                    logger.error("[Wrapper][%s] %s", self.job_id[:8], msg)
                    outcome = {'type': _MSG_ERROR, 'message': msg}
                else:
                    # Scraper completed but forgot to send DONE — treat as success
                    outcome = {
                        'type':    _MSG_DONE,
                        'message': 'Completed (no terminal message)',
                        'output_file': '',
                    }
                break

            # ── Drain all available queue messages ───────────────
            drained_terminal = False
            while not q.empty():
                try:
                    msg = q.get_nowait()
                    msg_type, progress, message, extra = msg

                    if msg_type == _MSG_PROGRESS:
                        self._relay_progress(progress, message, extra)

                    elif msg_type == _MSG_DONE:
                        self._relay_progress(100, message, extra)
                        outcome = {
                            'type':        _MSG_DONE,
                            'message':     message,
                            'output_file': extra.get('output_file', ''),
                        }
                        drained_terminal = True

                    elif msg_type == _MSG_ERROR:
                        outcome = {'type': _MSG_ERROR, 'message': message}
                        drained_terminal = True

                except Exception:
                    break

            if drained_terminal:
                break

            time.sleep(_QUEUE_POLL_SLEEP)

        return outcome

    def _relay_progress(self, progress: int, message: str, extra: dict) -> None:
        """Forward a progress message to the registered callback."""
        if not self._progress_callback:
            return
        try:
            self._progress_callback(
                progress,
                message,
                current_url   = extra.get('current_url',   ''),
                links_count   = extra.get('links_count',   0),
                authors_count = extra.get('authors_count', 0),
                emails_count  = extra.get('emails_count',  0),
            )
        except KeyboardInterrupt:
            # progress_callback raises KeyboardInterrupt for cooperative stop
            self.stop()
        except Exception as exc:
            logger.warning("[Wrapper][%s] Progress callback error: %s", self.job_id[:8], exc)

    def _join_subprocess(self, process: billiard.Process) -> None:
        """Wait for subprocess to exit gracefully, then force-terminate if needed."""
        process.join(timeout=_SUBPROCESS_JOIN_TIMEOUT)
        if process.is_alive():
            logger.warning(
                "[Wrapper][%s] Subprocess still alive after %ds — terminating",
                self.job_id[:8], _SUBPROCESS_JOIN_TIMEOUT,
            )
            process.terminate()
            process.join(timeout=5)
            if process.is_alive():
                logger.error(
                    "[Wrapper][%s] Subprocess did not die after SIGTERM — sending SIGKILL",
                    self.job_id[:8],
                )
                process.kill()
        logger.info(
            "[Wrapper][%s] Subprocess exited with code %s",
            self.job_id[:8], process.exitcode,
        )

    def _find_output_file(self) -> Optional[str]:
        """
        Locate the CSV produced by the scraper.

        Priority order (same logic as celery_worker._find_partial_csv):
          1. Files with 'author', 'email', or 'result' in the name
             that are NOT pure Phase-1 URL collection files (_urls.csv).
          2. Any non-url file (by modification time, newest first).
          3. Last resort: the newest file regardless of name.

        This ensures Springer's *_authors.csv is always preferred over
        *_urls.csv when both exist in the output directory.
        """
        import glob as _glob

        search_dirs = []
        if self.output_dir and os.path.isdir(self.output_dir):
            search_dirs.append(self.output_dir)
        # Legacy: scrapers that write to keyword-named subdirs
        keyword_dir = self.keyword.replace(' ', '-')
        if os.path.isdir(keyword_dir):
            search_dirs.append(keyword_dir)

        for d in search_dirs:
            all_csvs = sorted(
                _glob.glob(os.path.join(d, '*.csv')),
                key=os.path.getmtime,
                reverse=True,  # newest first
            )
            if not all_csvs:
                continue

            # Priority 1: author/email/result files that aren't url-only
            email_files = [
                f for f in all_csvs
                if any(k in os.path.basename(f).lower()
                       for k in ('author', 'email', 'result'))
                and '_urls' not in os.path.basename(f).lower()
            ]
            if email_files:
                logger.info(
                    "[Wrapper][%s] Found email/author file: %s",
                    self.job_id[:8], email_files[0],
                )
                return email_files[0]

            # Priority 2: any file that isn't a pure url-collection file
            non_url_files = [
                f for f in all_csvs
                if '_urls' not in os.path.basename(f).lower()
            ]
            if non_url_files:
                logger.info(
                    "[Wrapper][%s] Found non-url file: %s",
                    self.job_id[:8], non_url_files[0],
                )
                return non_url_files[0]

            # Last resort: return newest regardless of name
            logger.warning(
                "[Wrapper][%s] Only url files found — returning: %s",
                self.job_id[:8], all_csvs[0],
            )
            return all_csvs[0]

        return None

    # ── Context manager support ──────────────────────────────────

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        if self._subprocess and self._subprocess.is_alive():
            self._subprocess.terminate()
        return False


# ── Convenience factory ──────────────────────────────────────────

def create_wrapper(
    scraper_class: Type,
    keyword:       str,
    start_date:    str,
    end_date:      str,
    driver_path:   Optional[str] = None,
    output_dir:    Optional[str] = None,
    job_id:        Optional[str] = None,
    timeout:       int           = _DEFAULT_TIMEOUT,
) -> SeleniumScraperWrapper:
    """
    Factory function for ScraperAdapter to call instead of instantiating
    SeleniumScraperWrapper directly.

    Example usage in scraper_adapter.py:
        from selenium_scraper_wrapper import create_wrapper

        wrapper = create_wrapper(
            scraper_class=SpringerAuthorScraper,
            keyword=keyword,
            start_date=start_date,
            end_date=end_date,
            driver_path=driver_path,
            output_dir=output_dir,
            job_id=job_id,
        )
        wrapper.set_progress_callback(progress_callback)
        output_file, summary = wrapper.run()
    """
    return SeleniumScraperWrapper(
        scraper_class=scraper_class,
        keyword=keyword,
        start_year=start_date,
        end_year=end_date,
        driver_path=driver_path,
        output_dir=output_dir,
        job_id=job_id,
        timeout=timeout,
    )
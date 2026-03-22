'use strict';
/**
 * oxford_puppeteer.js
 * ══════════════════════════════════════════════════════════════════════════
 * Puppeteer scraper for Oxford Academic (academic.oup.com).
 * Called by oxford_selenium.py via:
 *   node oxford_puppeteer.js --keyword "..." --start-year MM/DD/YYYY
 *                            --end-year MM/DD/YYYY --output-dir /path
 *                            --log-dir logs --conf-name ""
 *                            --url-csv /path/urls.csv --authors-csv /path/authors.csv
 *
 * Search URL:
 *   https://academic.oup.com/search-results
 *     ?q={kw}&f_ContentType=Journal Article
 *     &rg_ArticleDate=MM/DD/YYYY TO MM/DD/YYYY
 *     &dateFilterType=range&noDateTypes=true
 *
 * Article links  : a.article-link.at-sr-article-title-link
 * Next page      : a.sr-nav-next.al-nav-next  → data-url attribute
 * Author click   : span.al-author-name-more a.js-linked-name-trigger (each author)
 * Email popup    : span.al-author-info-wrap.open → a[href^='mailto']
 * Fallback       : a.js-linked-footnotes → popup → a[href^='mailto']
 *
 * Progress output: PROGRESS:{pct}:{msg}
 * Output signal : OUTPUT_FILE:{path}
 * ══════════════════════════════════════════════════════════════════════════
 */

// resolve deps from sciencedirect/node_modules
const fsSync    = require('fs');
const path      = require('path');
// Resolve puppeteer-core from sciencedirect/node_modules (shared install)
const puppeteer = (() => {
    const path = require('path');
    const attempts = [
        'puppeteer-core',  // if globally installed
        path.join(__dirname, 'sciencedirect', 'node_modules', 'puppeteer-core'),
        path.join(__dirname, '..', 'sciencedirect', 'node_modules', 'puppeteer-core'),
    ];
    for (const p of attempts) {
        try { return require(p); } catch(e) {}
    }
    throw new Error('puppeteer-core not found. Run: cd sciencedirect && npm install');
})();
const { createObjectCsvWriter } = (() => {
    const path = require('path');
    const attempts = [
        'csv-writer',
        path.join(__dirname, 'sciencedirect', 'node_modules', 'csv-writer'),
        path.join(__dirname, '..', 'sciencedirect', 'node_modules', 'csv-writer'),
    ];
    for (const p of attempts) { try { return require(p); } catch(e) {} }
    throw new Error('csv-writer not found');
})();
const csv = (() => {
    const path = require('path');
    const attempts = [
        'csv-parser',
        path.join(__dirname, 'sciencedirect', 'node_modules', 'csv-parser'),
        path.join(__dirname, '..', 'sciencedirect', 'node_modules', 'csv-parser'),
    ];
    for (const p of attempts) { try { return require(p); } catch(e) {} }
    throw new Error('csv-parser not found');
})();

// ── CLI args ────────────────────────────────────────────────────────────────
function parseArgs() {
    const args = process.argv.slice(2);
    const opts = {};
    for (let i = 0; i < args.length; i += 2)
        opts[args[i].replace(/^--/, '')] = args[i + 1] || '';
    return opts;
}

function sanitize(s) { return (s || '').replace(/[<>:"/\\|?*]/g, '_').trim(); }
function reportProgress(pct, msg) { process.stdout.write(`PROGRESS:${pct}:${msg}\n`); }

// ── Logger ───────────────────────────────────────────────────────────────────
class Logger {
    constructor(logPath) {
        this.logPath = logPath;
        fsSync.writeFileSync(logPath, `Log initialized at ${new Date().toISOString()}\n`);
    }
    _write(level, msg) {
        const line = `${new Date().toISOString()} - ${level} - ${msg}`;
        fsSync.appendFileSync(this.logPath, line + '\n');
        process.stdout.write(line + '\n');
    }
    info(msg)  { this._write('INFO',    msg); }
    warn(msg)  { this._write('WARNING', msg); }
    error(msg) { this._write('ERROR',   msg); }
}

// ── Main scraper ─────────────────────────────────────────────────────────────
class OxfordScraper {
    constructor(opts, logger) {
        this.opts    = opts;
        this.logger  = logger;
        this.browser = null;
        this.page    = null;
        this.lastUA  = '';
        this.userAgents = this._loadUAs();
    }

    _loadUAs() {
        try {
            const uaFile = path.join(__dirname, 'db-1.txt');
            const lines  = fsSync.readFileSync(uaFile, 'utf8')
                .split('\n').map(l => l.trim())
                .filter(l => {
                    if (l.length < 20 || /Mobile|Android|iPhone|iPad|UCBrowser|SamsungBrowser/i.test(l)) return false;
                    const m = l.match(/Chrome\/(\d+)/);
                    return m && parseInt(m[1], 10) >= 100;
                });
            if (lines.length > 5) {
                this.logger && this.logger.info(`[UA] Loaded ${lines.length} desktop UAs`);
                return lines;
            }
        } catch (e) {}
        return [
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ];
    }

    _randomUA() {
        let ua = this.userAgents[Math.floor(Math.random() * this.userAgents.length)];
        let tries = 0;
        while (ua === this.lastUA && tries++ < 10)
            ua = this.userAgents[Math.floor(Math.random() * this.userAgents.length)];
        this.lastUA = ua;
        return ua;
    }

    _chromePath() {
        for (const p of [
            '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable',
            '/usr/bin/chromium-browser', '/usr/bin/chromium',
            process.env.CHROME_PATH, process.env.CHROME_BIN,
        ].filter(Boolean)) { if (fsSync.existsSync(p)) return p; }
        return null;
    }

    delay(ms) { return new Promise(r => setTimeout(r, ms)); }

    // ── Bot / CAPTCHA detection ──────────────────────────────────────────────
    async _isCaptcha() {
        try {
            const url = this.page.url();
            if (url.includes('unsupported_browser') || url.includes('outdated')) return 'hard';
            const result = await this.page.evaluate(() => {
                const txt = ((document.title || '') + ' ' +
                    (document.body ? document.body.innerText.slice(0, 600) : '')).toLowerCase();
                const CF_AUTO  = ['verifying you are human', 'just a moment',
                                  'checking your browser', 'performing security verification'];
                const HARD_BOT = ['access denied', 'robot', 'unusual traffic',
                                  'security check', 'bot detection', 'are you a robot'];
                if (HARD_BOT.some(p => txt.includes(p))) return 'hard';
                if (CF_AUTO.some(p => txt.includes(p)))  return 'cf_auto';
                return 'none';
            });
            return result !== 'none' ? result : false;
        } catch (e) { return false; }
    }

    async _waitForCFClear(maxWaitMs = 30000) {
        const CF_PHRASES = ['verifying you are human', 'just a moment', 'checking your browser',
                            'please wait', 'performing security verification'];
        const deadline = Date.now() + maxWaitMs;
        this.logger.info(`CF auto-challenge — waiting up to ${maxWaitMs/1000}s for auto-clear...`);
        while (Date.now() < deadline) {
            await this.delay(3000);
            try {
                const stillCF = await this.page.evaluate((phrases) => {
                    const txt = ((document.title || '') + ' ' +
                        (document.body ? document.body.innerText.slice(0, 400) : '')).toLowerCase();
                    return phrases.some(p => txt.includes(p));
                }, CF_PHRASES);
                if (!stillCF) { this.logger.info('✓ CF challenge auto-cleared'); return true; }
            } catch (e) { break; }
        }
        this.logger.warn('CF did not auto-clear — rotating UA');
        return false;
    }


    async _launch(ua) {
        const cp   = this._chromePath();
        const opts = {
            headless: false,
            args: ['--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage',
                   '--disable-accelerated-2d-canvas','--disable-gpu','--window-size=1400,900',
                   '--disable-blink-features=AutomationControlled','--disable-infobars',
                   '--disable-notifications','--disable-popup-blocking'],
            defaultViewport: null, ignoreHTTPSErrors: true, timeout: 60000,
        };
        if (cp) opts.executablePath = cp;
        this.browser = await puppeteer.launch(opts);
        this.page    = await this.browser.newPage();
        await this.page.setUserAgent(ua);
        await this.page.evaluateOnNewDocument(
            () => Object.defineProperty(navigator, 'webdriver', { get: () => false })
        );
        this.logger.info(`Browser launched UA: ${ua.slice(0, 65)}...`);
    }

    async initialize() { await this._launch(this._randomUA()); }

    async rotateAndRestart(returnUrl) {
        const ua = this._randomUA();
        this.logger.warn(`🔄 Bot detected — rotating UA & restarting. New: ${ua.slice(0, 65)}...`);
        try { if (this.browser) await this.browser.close(); } catch (e) {}
        this.browser = null; this.page = null;
        await this.delay(8000);
        await this._launch(ua);
        if (returnUrl) {
            await this.page.goto(returnUrl, { waitUntil: 'networkidle2', timeout: 60000 });
            await this._acceptCookies();
        }
    }

    async _acceptCookies() {
        const selectors = ['#onetrust-accept-btn-handler', 'button.oup-cookie-consent__btn--accept',
                           '[aria-label="Accept all cookies"]', 'button[id*="accept"]'];
        const deadline = Date.now() + 15000;
        while (Date.now() < deadline) {
            for (const sel of selectors) {
                try {
                    const btn = await this.page.$(sel);
                    if (btn) {
                        await btn.click();
                        this.logger.info(`Cookies accepted (${sel})`);
                        await this.delay(1500);
                        return;
                    }
                } catch (e) {}
            }
            await this.delay(1000);
        }
        this.logger.info('No cookie banner found — continuing');
    }

    async _closePopups() {
        for (const sel of [
            '#onetrust-accept-btn-handler','[id*="pendo-close"]','button[aria-label="Close"]',
            '.el-close', '.close-button',
        ]) {
            try { const b = await this.page.$(sel); if (b) { await b.click(); await this.delay(400); } } catch (e) {}
        }
    }

    // ── Safe goto with bot-check ─────────────────────────────────────────────
    async _goto(url, homeUrl) {
        for (let attempt = 1; attempt <= 3; attempt++) {
            try {
                await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
                const _captcha = await this._isCaptcha();
                if (_captcha === 'cf_auto') {
                    const _cleared = await this._waitForCFClear(30000);
                    if (!_cleared) { await this.rotateAndRestart(homeUrl || 'https://academic.oup.com'); await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 }); }
                } else if (_captcha === 'hard' || _captcha) {
                    await this.rotateAndRestart(homeUrl || 'https://academic.oup.com'); await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
                }
                return;
            } catch (e) {
                this.logger.error(`_goto attempt ${attempt}: ${e.message}`);
                if (attempt < 3) { await this.delay(5000); await this.rotateAndRestart(null); }
                else throw e;
            }
        }
    }

    // ── Phase 1: collect URLs ────────────────────────────────────────────────
    async _extractLinks() {
        try {
            await this.page.waitForSelector('a.article-link.at-sr-article-title-link', { timeout: 12000 });
            return await this.page.evaluate(() =>
                Array.from(document.querySelectorAll(
                    'a.article-link.at-sr-article-title-link'
                )).map(a => a.href).filter(Boolean)
            );
        } catch (e) {
            this.logger.warn(`extractLinks: ${e.message}`);
            return [];
        }
    }

    async _getNextPageUrl() {
        try {
            const btn = await this.page.$('a.sr-nav-next.al-nav-next');
            if (!btn) return null;
            const dataUrl = await btn.getProperty('dataset');
            // Use evaluate to get the data-url attribute
            const nextParams = await this.page.evaluate(
                el => el.getAttribute('data-url'), btn
            );
            if (!nextParams) return null;
            const base = this.page.url().split('?')[0];
            return base + '?' + nextParams;
        } catch (e) { return null; }
    }

    async _getTotalPages() {
        try {
            await this.page.waitForSelector(
                '.search-results-count, .al-article-items-wrapper, [class*="result"]',
                { timeout: 12000 }
            );
            const count = await this.page.evaluate(() => {
                // Oxford shows "Showing X - Y of Z results" or just total count
                const selectors = [
                    '.search-results-count',
                    '.al-format-count',
                    '[class*="result-count"]',
                    'p.search-results-indicator',
                ];
                for (const s of selectors) {
                    const el = document.querySelector(s);
                    if (el) {
                        const m = el.textContent.match(/of\s+([\d,]+)/);
                        if (m) return parseInt(m[1].replace(/,/g, ''), 10);
                        const m2 = el.textContent.match(/[\d,]+/);
                        if (m2) return parseInt(m2[0].replace(/,/g, ''), 10);
                    }
                }
                // Count actual articles visible and assume single page
                return document.querySelectorAll('a.article-link.at-sr-article-title-link').length;
            });
            // Oxford shows 10-20 per page
            const perPage = await this.page.evaluate(() =>
                document.querySelectorAll('a.article-link.at-sr-article-title-link').length
            ) || 10;
            const pages = Math.ceil(count / perPage) || 1;
            this.logger.info(`Total results: ~${count} → ~${pages} pages`);
            return pages;
        } catch (e) {
            this.logger.error(`getTotalPages: ${e.message}`);
            return 1;
        }
    }

    // ── Phase 2: author email extraction ─────────────────────────────────────
    async _scrapeArticle(url) {
        const rows = [];
        try {
            await this.page.setDefaultNavigationTimeout(30000);
            await this._goto(url, 'https://academic.oup.com');
            await this.delay(2000);
            await this._closePopups();

            // Show all authors if button exists
            try {
                const showMore = await this.page.$('a#show-meta-authors, button#show-meta-authors');
                if (showMore) { await showMore.click(); await this.delay(1500); }
            } catch (e) {}

            // Click each author popup icon that has an envelope
            const authorTriggers = await this.page.$$(
                'span.al-author-name-more a.js-linked-name-trigger'
            );

            for (const trigger of authorTriggers) {
                try {
                    const authorName = await this.page.evaluate(el => el.textContent.trim(), trigger);
                    await trigger.click();
                    await this.delay(1500);

                    // Wait for popup
                    try {
                        await this.page.waitForSelector(
                            'span.al-author-info-wrap.open', { timeout: 5000 }
                        );
                    } catch (e) { continue; }

                    const emails = await this.page.evaluate(() => {
                        const popup = document.querySelector('span.al-author-info-wrap.open');
                        if (!popup) return [];
                        return Array.from(popup.querySelectorAll('a[href^="mailto"]'))
                            .map(a => a.getAttribute('href').replace('mailto:', '').trim())
                            .filter(e => e.includes('@'));
                    });

                    for (const email of emails) {
                        rows.push({ Article_URL: url, Author_Name: authorName, Email: email });
                        this.logger.info(`✅ ${authorName} — ${email}`);
                    }

                    // Close popup by pressing Escape or clicking elsewhere
                    try { await this.page.keyboard.press('Escape'); await this.delay(500); } catch (e) {}
                } catch (e) {
                    this.logger.warn(`Author trigger error: ${e.message}`);
                }
            }

            // Fallback: Author Notes link
            if (rows.length === 0) {
                try {
                    const notesLink = await this.page.$('a.js-linked-footnotes');
                    if (notesLink) {
                        await notesLink.click();
                        await this.delay(1500);
                        const noteRows = await this.page.evaluate(() => {
                            const popup = document.querySelector('span.al-author-info-wrap');
                            if (!popup) return [];
                            const nameEl = popup.querySelector('.al-author-name, .author-name');
                            const name   = nameEl ? nameEl.textContent.trim() : '';
                            return Array.from(popup.querySelectorAll('a[href^="mailto"]'))
                                .map(a => ({
                                    name,
                                    email: a.getAttribute('href').replace('mailto:', '').trim(),
                                }))
                                .filter(r => r.email.includes('@'));
                        });
                        for (const { name, email } of noteRows) {
                            rows.push({ Article_URL: url, Author_Name: name, Email: email });
                            this.logger.info(`✅ [notes] ${name} — ${email}`);
                        }
                    }
                } catch (e) {}
            }

            // Second fallback: bare mailto links in .footnote-compatibility
            if (rows.length === 0) {
                try {
                    const fallbackEmails = await this.page.evaluate(() =>
                        Array.from(document.querySelectorAll(
                            'p.footnote-compatibility a[href^="mailto"], .author-notes a[href^="mailto"]'
                        )).map(a => a.getAttribute('href').replace('mailto:', '').trim())
                          .filter(e => e.includes('@'))
                    );
                    for (const email of fallbackEmails) {
                        rows.push({ Article_URL: url, Author_Name: '', Email: email });
                        this.logger.info(`✅ [fallback] ${email}`);
                    }
                } catch (e) {}
            }

        } catch (e) {
            this.logger.error(`Article error ${url}: ${e.message}`);
        } finally {
            await this.page.setDefaultNavigationTimeout(60000);
        }
        return rows;
    }

    // ── Main run ─────────────────────────────────────────────────────────────
    async run() {
        const kw        = this.opts['keyword'] || '';
        const startDate = this.opts['start-year'] || '';
        const endDate   = this.opts['end-year'] || '';
        const urlCsv    = this.opts['url-csv'];
        const authCsv   = this.opts['authors-csv'];

        reportProgress(2, `Oxford: starting "${kw}" ${startDate}→${endDate}`);

        // Build search URL (Oxford uses YYYY-MM-DD format in date range)
        const fmtDate = (mmddyyyy) => {
            const [mm, dd, yyyy] = mmddyyyy.split('/');
            return `${yyyy}-${mm.padStart(2,'0')}-${dd.padStart(2,'0')}`;
        };
        const searchBase = 'https://academic.oup.com/search-results';
        const searchUrl  = `${searchBase}?q=${encodeURIComponent(kw)}` +
            `&f_ContentType=Journal%20Article` +
            `&rg_ArticleDate=${fmtDate(startDate)}+TO+${fmtDate(endDate)}` +
            `&dateFilterType=range&noDateTypes=true`;

        // Initialise CSVs
        for (const [csvPath, header] of [
            [urlCsv, [{ id: 'Article_URL', title: 'Article_URL' }]],
            [authCsv, [{ id: 'Article_URL', title: 'Article_URL' },
                       { id: 'Author_Name', title: 'Author_Name' },
                       { id: 'Email', title: 'Email' }]],
        ]) {
            await createObjectCsvWriter({ path: csvPath, header, append: false }).writeRecords([]);
        }
        const urlAppend  = createObjectCsvWriter({
            path: urlCsv, header: [{ id: 'Article_URL', title: 'Article_URL' }], append: true,
        });
        const authAppend = createObjectCsvWriter({
            path: authCsv,
            header: [{ id: 'Article_URL', title: 'Article_URL' },
                     { id: 'Author_Name', title: 'Author_Name' },
                     { id: 'Email', title: 'Email' }], append: true,
        });

        // ── Phase 1 ──────────────────────────────────────────────────────────
        reportProgress(5, 'Landing on Oxford homepage...');
        await this.page.goto('https://academic.oup.com', { waitUntil: 'networkidle2', timeout: 60000 });
        await this._acceptCookies();

        await this._goto(searchUrl, 'https://academic.oup.com');
        const _pc = await this._isCaptcha(); if (_pc === 'cf_auto') { await this._waitForCFClear(30000); } else if (_pc) { await this.rotateAndRestart('https://academic.oup.com'); }

        const totalPages = await this._getTotalPages();
        this.logger.info(`Collecting URLs across ~${totalPages} pages`);

        const allLinks = [];
        let currentUrl = this.page.url();

        for (let pg = 0; pg < totalPages; pg++) {
            await this._closePopups();
            const links = await this._extractLinks();
            allLinks.push(...links);
            await urlAppend.writeRecords(links.map(u => ({ Article_URL: u })));
            const pct = 5 + Math.floor(((pg + 1) / totalPages) * 33);
            reportProgress(pct, `Page ${pg+1}/${totalPages}: ${links.length} links (total ${allLinks.length})`);
            this.logger.info(`Oxford ==> Page ${pg+1}/${totalPages}: ${links.length} links`);

            const nextUrl = await this._getNextPageUrl();
            if (!nextUrl) { this.logger.info('No next page button — done paginating'); break; }
            await this._goto(nextUrl, 'https://academic.oup.com');
            await this.delay(3000);
        }

        reportProgress(40, `Phase 1 done: ${allLinks.length} URLs`);

        // ── Phase 2 ──────────────────────────────────────────────────────────
        reportProgress(42, `Phase 2: extracting emails from ${allLinks.length} articles`);
        let authorsFound = 0;
        for (let i = 0; i < allLinks.length; i++) {
            const rows = await this._scrapeArticle(allLinks[i]);
            if (rows.length > 0) {
                await authAppend.writeRecords(rows);
                authorsFound += rows.length;
            }
            const pct = 42 + Math.floor(((i + 1) / allLinks.length) * 55);
            reportProgress(pct, `Author extraction: ${i+1}/${allLinks.length} (${authorsFound} found)`);
            await this.delay(1500);
        }

        reportProgress(100, `Done: ${authorsFound} authors found`);
        process.stdout.write(`OUTPUT_FILE:${authCsv}\n`);
        this.logger.info(`OUTPUT_FILE:${authCsv}`);
        return authCsv;
    }

    async close() {
        try { if (this.browser) await this.browser.close(); } catch (e) {}
    }
}

// ── Entry point ───────────────────────────────────────────────────────────────
async function main() {
    const opts = parseArgs();
    if (!opts.keyword) { process.stderr.write('--keyword required\n'); process.exit(1); }

    const logDir  = opts['log-dir'] || 'logs';
    const kw      = sanitize(opts.keyword);
    const logPath = path.join(logDir,
        `OxfordScraper-${kw}-${(opts['start-year']||'').replace(/\//g,'-')}-${(opts['end-year']||'').replace(/\//g,'-')}.log`
    );
    fsSync.mkdirSync(logDir, { recursive: true });
    fsSync.mkdirSync(opts['output-dir'] || 'results', { recursive: true });

    const logger  = new Logger(logPath);
    const scraper = new OxfordScraper(opts, logger);

    try {
        await scraper.initialize();
        await scraper.run();
    } catch (err) {
        logger.error(`Fatal: ${err.message}`);
        process.stderr.write(`ERROR: ${err.message}\n`);
        process.exit(1);
    } finally {
        await scraper.close();
    }
}

if (require.main === module) main().catch(e => { process.stderr.write(e.message + '\n'); process.exit(1); });
module.exports = OxfordScraper;
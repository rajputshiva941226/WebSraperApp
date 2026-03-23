'use strict';
/**
 * sage_puppeteer.js
 * ══════════════════════════════════════════════════════════════════════════
 * Puppeteer scraper for SAGE Journals (journals.sagepub.com).
 * Called by sage_selenium.py via:
 *   node sage_puppeteer.js --keyword "..." --start-year MM/DD/YYYY
 *                          --end-year MM/DD/YYYY --output-dir /path
 *                          --log-dir logs --conf-name "" 
 *                          --url-csv /path/urls.csv --authors-csv /path/authors.csv
 *
 * Search URL:
 *   https://journals.sagepub.com/action/doSearch
 *     ?field1=AllField&text1={kw}
 *     &AfterMonth=M&AfterYear=YYYY&BeforeMonth=M&BeforeYear=YYYY
 *     &pageSize=100&startPage=N
 *
 * Article links : div.issue-item__title > a[data-id="srp-article-title"]
 * Authors block : a.to-authors-affiliations  (click to expand)
 * Expand button : button[data-label-expand="Show all"]
 * Each author   : section.core-authors div[property='author']
 *   Name        : span[property='givenName'] + span[property='familyName']
 *   Email       : div.core-email > a[property='email'] → href (strip mailto:)
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
    for (let i = 0; i < args.length; i += 2) {
        opts[args[i].replace(/^--/, '')] = args[i + 1] || '';
    }
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

// ── Main Scraper ─────────────────────────────────────────────────────────────
class SageScraper {
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
            const uaFile = fsSync.existsSync(path.join(__dirname, 'modern_useragents.txt')) ? path.join(__dirname, 'modern_useragents.txt') : path.join(__dirname, 'db-1.txt');
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
        ].filter(Boolean)) {
            if (fsSync.existsSync(p)) return p;
        }
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

    async _waitForCFClear(maxWaitMs = 120000) {
        const CF_PHRASES = ['verifying you are human', 'just a moment', 'checking your browser',
                            'please wait', 'performing security verification'];
        const deadline = Date.now() + maxWaitMs;
        this.logger.warn(`⚠️ CF challenge — open VNC: http://3.108.210.45:6080/vnc.html`);
        this.logger.warn(`   Click "Verify you are human" checkbox within ${maxWaitMs/1000}s`);
        while (Date.now() < deadline) {
            await this.delay(3000);
            try {
                const stillCF = await this.page.evaluate((phrases) => {
                    const txt = ((document.title || '') + ' ' +
                        (document.body ? document.body.innerText.slice(0, 400) : '')).toLowerCase();
                    return phrases.some(p => txt.includes(p));
                }, CF_PHRASES);
                if (!stillCF) { this.logger.info('✓ CF challenge cleared'); return true; }
                const rem = Math.round((deadline - Date.now()) / 1000);
                this.logger.info(`CF waiting... (${rem}s left)`);
            } catch (e) { break; }
        }
        this.logger.error('CF not solved — rotating UA and retrying');
        return false;
    }


    async _launch(ua) {
        const cp = this._chromePath();
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
        this.logger.warn(`🔄 Bot detected — rotating UA & restarting. New: ${ua.slice(0,65)}...`);
        try { if (this.browser) await this.browser.close(); } catch (e) {}
        this.browser = null; this.page = null;
        await this.delay(8000);
        await this._launch(ua);
        if (returnUrl) {
            await this.page.goto(returnUrl, { waitUntil: 'networkidle2', timeout: 60000 });
            await this._acceptCookies();
        }
    }

    // ── Cookie / popup handling ──────────────────────────────────────────────
    async _acceptCookies() {
        // Poll up to 15s for cookie banner — dismiss as soon as it appears
        const selectors = ['#onetrust-accept-btn-handler', 'button.onetrust-close-btn-handler',
                           '[aria-label="Accept all cookies"]', 'button[id*="accept"]'];
        const deadline = Date.now() + 15000;
        while (Date.now() < deadline) {
            for (const sel of selectors) {
                try {
                    const btn = await this.page.$(sel);
                    if (btn) {
                        await btn.click();
                        this.logger.info(`Cookies accepted (${sel})`);
                        await this.delay(3000 + Math.floor(Math.random() * 3000));
                        return;
                    }
                } catch (e) {}
            }
            await this.delay(1000);
        }
        this.logger.info('No cookie banner found — continuing');
    }

    async _closePopups() {
        for (const sel of ['#onetrust-accept-btn-handler','button[id*="pendo-close"]',
                           'button[aria-label="Close"]']) {
            try { const b = await this.page.$(sel); if (b) { await b.click(); await this.delay(500); } } catch(e) {}
        }
    }

    // ── Safe goto with bot-check ─────────────────────────────────────────────
    async _goto(url, homeUrl) {
        for (let attempt = 1; attempt <= 3; attempt++) {
            try {
                await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
                const _captcha = await this._isCaptcha();
                if (_captcha === 'cf_auto') {
                    const _cleared = await this._waitForCFClear(120000);
                    if (!_cleared) { await this.rotateAndRestart(homeUrl || 'https://journals.sagepub.com'); await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 }); }
                } else if (_captcha === 'hard' || _captcha) {
                    await this.rotateAndRestart(homeUrl || 'https://journals.sagepub.com'); await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
                }
                return;
            } catch (e) {
                this.logger.error(`_goto attempt ${attempt}: ${e.message}`);
                if (attempt < 3) { await this.delay(5000); await this.rotateAndRestart(null); }
                else throw e;
            }
        }
    }

    // ── Phase 1: Collect article URLs ────────────────────────────────────────
    async _getTotalPages(query) {
        // Sage result count selectors — confirmed from live Selenium logs
        // "span.result__count" is the primary selector used in working Selenium version
        const COUNT_SELECTORS = [
            'span.result__count',
            '[class*="result__count"]',
            '.search-body-results-text',
            '.resultsCount',
            '[class*="result-count"]',
            '[data-test="results-count"]',
            'p.results-desc',
        ];
        for (let attempt = 0; attempt < 3; attempt++) {
            try {
                // Try all selectors
                for (const sel of COUNT_SELECTORS) {
                    try {
                        await this.page.waitForSelector(sel, { timeout: 6000 });
                        const count = await this.page.evaluate((s) => {
                            const el = document.querySelector(s);
                            if (!el || !el.textContent.trim()) return 0;
                            const m = el.textContent.match(/[\d,]+/);
                            return m ? parseInt(m[0].replace(/,/g, ''), 10) : 0;
                        }, sel);
                        if (count > 0) {
                            const pages = Math.ceil(count / 100);
                            this.logger.info(`Total results: ${count} → ${pages} pages (via ${sel})`);
                            return pages;
                        }
                    } catch (e) {}
                }
                // Fallback: count article items on page
                const itemCount = await this.page.evaluate(() =>
                    document.querySelectorAll('div.issue-item__title > a[data-id="srp-article-title"]').length
                );
                if (itemCount > 0) {
                    this.logger.info(`Counted ${itemCount} items on first page — treating as 1 page`);
                    return 1;
                }
                if (attempt < 2) await this.delay(3000);
            } catch (e) {
                this.logger.error(`getTotalPages attempt ${attempt+1}: ${e.message}`);
            }
        }
        this.logger.error('getTotalPages: could not determine result count');
        return 0;
    }

    async _extractLinks() {
        try {
            await this.page.waitForSelector(
                'div.issue-item__title > a[data-id="srp-article-title"]', { timeout: 10000 }
            );
            return await this.page.evaluate(() =>
                Array.from(document.querySelectorAll(
                    'div.issue-item__title > a[data-id="srp-article-title"]'
                )).map(a => a.href).filter(Boolean)
            );
        } catch (e) {
            this.logger.warn(`extractLinks: ${e.message}`);
            return [];
        }
    }

    // ── Phase 2: Extract author emails ───────────────────────────────────────
    async _scrapeArticle(url) {
        const rows = [];
        try {
            // Short page-load timeout per article
            await this.page.setDefaultNavigationTimeout(30000);
            await this._goto(url, 'https://journals.sagepub.com');
            await this.delay(2000);
            await this._closePopups();

            // Expand author section
            try {
                const authBtn = await this.page.$('a.to-authors-affiliations');
                if (authBtn) { await authBtn.click(); await this.delay(2000); }
            } catch (e) {}

            // Expand "Show all" if present
            try {
                const showAll = await this.page.$('button[data-label-expand="Show all"]');
                if (showAll) { await showAll.click(); await this.delay(1500); }
            } catch (e) {}

            // Wait for author section
            try {
                await this.page.waitForSelector(
                    'section.core-authors div[property="author"]', { timeout: 8000 }
                );
            } catch (e) { return rows; }

            // Extract: each author with an email only
            const results = await this.page.evaluate(() => {
                const authors = document.querySelectorAll(
                    'section.core-authors div[property="author"]'
                );
                const out = [];
                for (const author of authors) {
                    const given   = author.querySelector('span[property="givenName"]');
                    const family  = author.querySelector('span[property="familyName"]');
                    const emailEl = author.querySelector('div.core-email > a[property="email"]');
                    if (!emailEl) continue;                         // skip authors without email
                    const email   = emailEl.getAttribute('href').replace('mailto:', '').trim();
                    if (!email || !email.includes('@')) continue;
                    const name = ((given ? given.textContent : '') + ' ' +
                                  (family ? family.textContent : '')).trim();
                    out.push({ name, email });
                }
                return out;
            });

            for (const { name, email } of results) {
                rows.push({ Article_URL: url, Author_Name: name, Email: email });
                this.logger.info(`✅ ${name} — ${email}`);
            }
        } catch (e) {
            this.logger.error(`Article error ${url}: ${e.message}`);
        } finally {
            await this.page.setDefaultNavigationTimeout(60000);
        }
        return rows;
    }

    // ── Main run ─────────────────────────────────────────────────────────────
    async _fillSearchForm(keyword, fromMonth, fromYear, toMonth, toYear) {
        /**
         * Fill the Sage advanced search form using confirmed HTML selectors.
         *
         * Form structure (from live HTML):
         *   #searchArea1     — select (field1): set to "Abstract" or "AllField"
         *   #text1           — input: keyword
         *   #customRange     — radio: enables custom date range
         *   #dropdown100     — button: From month toggle (options: data-value="1"-"12")
         *   #dropdown565     — button: From year toggle (options: data-value="YYYY")
         *   #dropdown650     — button: To month toggle
         *   #dropdown154     — button: To year toggle
         *   #advanced-search-btn — submit button
         *
         * Dropdowns are Bootstrap listbox dropdowns disabled until #customRange is clicked.
         * Must: click radio → wait → click toggle btn → wait → click option[data-value]
         */
        this.logger.info(`Filling form: "${keyword}" from ${fromMonth}/${fromYear} to ${toMonth}/${toYear}`);

        // 1. Wait for form to be ready
        try {
            await this.page.waitForSelector('#text1', { timeout: 15000 });
        } catch(e) {
            await this.page.screenshot({ path: 'logs/sage_form_missing.png' }).catch(()=>{});
            throw new Error(`Sage advanced search form not found: ${e.message}`);
        }

        // 2. Click Custom Range radio to enable date dropdowns
        try {
            await this.page.evaluate(() => {
                const radio = document.getElementById('customRange');
                if (radio) { radio.click(); }
            });
            await this.delay(1500);
            this.logger.info('Custom Range radio clicked');
        } catch(e) {
            this.logger.warn(`Could not click customRange: ${e.message}`);
        }

        // 3. Helper: open a Bootstrap dropdown and click the option with data-value
        const selectDropdownOption = async (btnId, value, label) => {
            try {
                // Enable the button in case it's still disabled
                await this.page.evaluate((id) => {
                    const btn = document.getElementById(id);
                    if (btn) {
                        btn.removeAttribute('disabled');
                        btn.removeAttribute('aria-disabled');
                        btn.setAttribute('aria-disabled', 'false');
                    }
                    // Also enable the hidden input
                    const parentDropdown = btn ? btn.closest('.dropdown') : null;
                    if (parentDropdown) {
                        const input = parentDropdown.querySelector('input[type="hidden"]');
                        if (input) {
                            input.removeAttribute('disabled');
                            input.setAttribute('aria-disabled', 'false');
                        }
                    }
                }, btnId);

                // Click the toggle button to open dropdown
                await this.page.click(`#${btnId}`);
                await this.delay(800);

                // Click the option with matching data-value
                const optionSel = `[aria-labelledby="${btnId}"] a[data-value="${value}"]`;
                await this.page.waitForSelector(optionSel, { visible: true, timeout: 5000 });
                await this.page.click(optionSel);
                await this.delay(600);
                this.logger.info(`Set ${label}: ${value}`);
            } catch(e) {
                // Fallback: set hidden input directly via JS
                this.logger.warn(`Dropdown ${btnId} click failed, using JS: ${e.message}`);
                await this.page.evaluate((id, val) => {
                    const btn = document.getElementById(id);
                    const parent = btn ? btn.closest('.dropdown') : null;
                    if (parent) {
                        const input = parent.querySelector('input[type="hidden"]');
                        if (input) {
                            input.value = val;
                            input.removeAttribute('disabled');
                            input.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                        // Update button text
                        const span = btn ? btn.querySelector('span') : null;
                        if (span) span.textContent = val;
                    }
                }, id, value);
                this.logger.info(`Set ${label} via JS: ${value}`);
            }
        };

        // 4. Set date dropdowns
        await selectDropdownOption('dropdown100', fromMonth,  'From month');
        await selectDropdownOption('dropdown565', fromYear,   'From year');
        await selectDropdownOption('dropdown650', toMonth,    'To month');
        await selectDropdownOption('dropdown154', toYear,     'To year');

        // 5. Type keyword (clear first, then type char by char)
        try {
            const input = await this.page.$('#text1');
            await input.click({ clickCount: 3 });
            await input.type(keyword, { delay: 80 });
            const actual = await this.page.$eval('#text1', el => el.value);
            this.logger.info(`Keyword field value: "${actual}"`);
            if (actual !== keyword) {
                // Force via JS
                await this.page.evaluate((kw) => {
                    const el = document.getElementById('text1');
                    if (el) { el.value = kw; el.dispatchEvent(new Event('input', { bubbles: true })); }
                }, keyword);
            }
        } catch(e) {
            throw new Error(`Cannot type keyword into #text1: ${e.message}`);
        }

        await this.delay(1000);

        // 6. Enable and click Search button
        await this.page.evaluate(() => {
            const btn = document.getElementById('advanced-search-btn');
            if (btn) {
                btn.removeAttribute('disabled');
                btn.removeAttribute('aria-disabled');
            }
        });
        await this.delay(500);
        await this.page.click('#advanced-search-btn');
        this.logger.info('Search form submitted');
    }

    async run() {
        // Step 1: Land on homepage to set cookies
        reportProgress(5, 'Landing on Sage homepage...');
        await this.page.goto('https://journals.sagepub.com', { waitUntil: 'networkidle2', timeout: 60000 });
        await this._acceptCookies();

        // Step 2: Navigate to advanced search form
        reportProgress(7, 'Loading advanced search form...');
        await this.page.goto('https://journals.sagepub.com/search/advanced', { waitUntil: 'networkidle2', timeout: 60000 });
        const cfState = await this._isCaptcha();
        if (cfState === 'cf_auto') {
            await this._waitForCFClear(120000);
        } else if (cfState) {
            await this.rotateAndRestart('https://journals.sagepub.com');
            await this.page.goto('https://journals.sagepub.com/search/advanced', { waitUntil: 'networkidle2', timeout: 60000 });
        }
        await this.delay(3000);

        // Step 3: Fill the advanced search form
        reportProgress(8, `Filling search form: "${kw}" ${startDate}→${endDate}`);
        await this._fillSearchForm(kw, smm, syyyy, emm, eyyyy);

        // Step 4: Wait for results page
        reportProgress(10, 'Waiting for search results...');
        await this.page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 }).catch(() => {});
        const cfState2 = await this._isCaptcha();
        if (cfState2 === 'cf_auto') await this._waitForCFClear(120000);
        await this.delay(6000);
        await this._closePopups();

        this.logger.info(`Sage ==> Results URL: ${this.page.url()}`);

        const totalPages = await this._getTotalPages();
        if (totalPages === 0) {
            try {
                fsSync.mkdirSync('logs', { recursive: true });
                await this.page.screenshot({ path: 'logs/sage_no_results.png', fullPage: false });
                this.logger.error(`No results. URL: ${this.page.url()}`);
            } catch(e) {}
            throw new Error(`No results found for "${kw}"`);
        }

        const allLinks = [];
        for (let pg = 0; pg < totalPages; pg++) {
            const pageUrl = buildUrl(pg);
            if (pg > 0) {
                await this._goto(pageUrl, 'https://journals.sagepub.com');
                await this.delay(3000);
            }
            await this._closePopups();
            const links = await this._extractLinks();
            allLinks.push(...links);
            await urlAppend.writeRecords(links.map(u => ({ Article_URL: u })));
            const pct = 5 + Math.floor(((pg + 1) / totalPages) * 33);
            reportProgress(pct, `Page ${pg+1}/${totalPages}: ${links.length} links (total ${allLinks.length})`);
            this.logger.info(`Sage ==> Page ${pg+1}/${totalPages}: ${links.length} links`);
            await this.delay(6000 + Math.floor(Math.random() * 3000));
        }

        reportProgress(40, `Phase 1 done: ${allLinks.length} URLs`);
        this.logger.info(`Phase 1 complete: ${allLinks.length} URLs`);

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
        `SageScraper-${kw}-${(opts['start-year']||'').replace(/\//g,'-')}-${(opts['end-year']||'').replace(/\//g,'-')}.log`
    );
    fsSync.mkdirSync(logDir, { recursive: true });
    fsSync.mkdirSync(opts['output-dir'] || 'results', { recursive: true });

    const logger  = new Logger(logPath);
    const scraper = new SageScraper(opts, logger);

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
module.exports = SageScraper;
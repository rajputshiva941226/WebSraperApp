/**
 * sciencedirect/index.cjs
 * ═══════════════════════════════════════════════════════════════════════════
 * ScienceDirect Puppeteer scraper — integrated with the Python/Celery stack.
 *
 * CLI usage (called by sciencedirect_selenium.py):
 *   node index.cjs --keyword "cancer" --start-year 2023 --end-year 2023
 *                  --output-dir /path/results/job_id
 *                  --log-dir logs
 *                  --conf-name "CancerConf"
 *                  --url-csv /path/urls.csv
 *                  --authors-csv /path/authors.csv
 *
 * Progress output (parsed by Python wrapper):
 *   PROGRESS:{0-100}:{message}
 *   OUTPUT_FILE:{absolute_path_to_authors_csv}
 *
 * Log output goes to:
 *   {log-dir}/ScienceDirectScraper-{keyword}-{start}-{end}.log
 *   (same logs/ directory as BMJ / Taylor scrapers)
 * ═══════════════════════════════════════════════════════════════════════════
 */

'use strict';

const puppeteer      = require('puppeteer-core');
// puppeteer-core: stealth applied via evaluateOnNewDocument (no plugin needed)
const fsSync         = require('fs');
const path           = require('path');
const { createObjectCsvWriter } = require('csv-writer');
const csv            = require('csv-parser');
const os             = require('os');


// ── Parse CLI args ──────────────────────────────────────────────────────────
function parseArgs() {
    const args = process.argv.slice(2);
    const opts = {};
    for (let i = 0; i < args.length; i += 2) {
        const key = args[i].replace(/^--/, '');
        opts[key] = args[i + 1] || '';
    }
    return opts;
}

function sanitizeKeyword(kw) {
    return kw.replace(/[<>:"/\\|?*]/g, '_').trim();
}

// ── Progress reporter ────────────────────────────────────────────────────────
function reportProgress(pct, msg, extra) {
    let line = `PROGRESS:${pct}:${msg}`;
    if (extra) {
        const parts = Object.entries(extra).map(([k, v]) => `${k}=${v}`);
        line += ' | ' + parts.join(' ');
    }
    process.stdout.write(line + '\n');
}

// ── Logger ────────────────────────────────────────────────────────────────────
class Logger {
    constructor(logPath) {
        this.logPath = logPath;
        if (fsSync.existsSync(logPath)) fsSync.unlinkSync(logPath);
        fsSync.writeFileSync(logPath, `Log initialized at ${new Date().toISOString()}\n`);
    }
    write(level, msg) {
        const ts  = new Date().toISOString();
        const line = `${ts} - ${level} - ${msg}`;
        fsSync.appendFileSync(this.logPath, line + '\n');
        process.stdout.write(line + '\n');
    }
    info(msg)    { this.write('INFO',    msg); }
    warn(msg)    { this.write('WARNING', msg); }
    error(msg)   { this.write('ERROR',   msg); }
}

// ── Main Scraper class ────────────────────────────────────────────────────────
class ScienceDirectScraper {
    constructor(opts, logger) {
        this.opts    = opts;
        this.logger  = logger;
        this.browser = null;
        this.page    = null;
        this.currentUserAgentIndex = 0;
        // Load UAs from db-1.txt (6,718 entries) — falls back to defaults
        this.userAgents = (() => {
            // Filter to MODERN desktop Chrome 100+ only
            // Old UAs (Chrome/70 etc.) get "Your browser is outdated" from ScienceDirect
            const MODERN_DEFAULTS = [
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            ];
            try {
                const uaFile = fsSync.existsSync(path.join(__dirname, '..', 'modern_useragents.txt'))
                    ? path.join(__dirname, '..', 'modern_useragents.txt')
                    : path.join(__dirname, '..', 'db-1.txt');
                const all = fsSync.readFileSync(uaFile, 'utf8').split('\n').map(l => l.trim());
                const modern = all.filter(l => {
                    if (l.length < 20) return false;
                    // Skip mobile UAs
                    if (/Mobile|Android|iPhone|iPad|UCBrowser|SamsungBrowser/i.test(l)) return false;
                    // Must be Chrome 100+ (ScienceDirect rejects older)
                    const m = l.match(/Chrome\/(\d+)/);
                    return m && parseInt(m[1], 10) >= 100;
                });
                if (modern.length > 10) {
                    console.log(`[UA] Loaded ${modern.length} modern desktop Chrome 100+ UAs from db-1.txt`);
                    return modern;
                }
            } catch (e) {
                console.log('[UA] db-1.txt not found, using defaults');
            }
            return MODERN_DEFAULTS;
        })();
        this.articleTypes = ['REV', 'FLA', 'DAT', 'CH'];
        this.seenUrls = {};
    }

    delay(ms) { return new Promise(r => setTimeout(r, ms)); }

    getNextUserAgent() {
        // Pick a random UA each time for better anti-bot evasion
        const ua = this.userAgents[Math.floor(Math.random() * this.userAgents.length)];
        return ua;
    }

    findChromePath() {
        const candidates = [
            '/usr/bin/google-chrome',
            '/usr/bin/google-chrome-stable',
            '/usr/bin/chromium-browser',
            '/usr/bin/chromium',
            '/snap/bin/chromium',
            process.env.CHROME_PATH,
            process.env.CHROME_BIN,
        ].filter(Boolean);

        for (const p of candidates) {
            if (fsSync.existsSync(p)) {
                this.logger.info(`Found Chrome at: ${p}`);
                return p;
            }
        }
        this.logger.info('Chrome binary not found — Puppeteer will use bundled Chromium');
        return null;
    }

    async initialize() {
        const ua = this.getNextUserAgent();
        this.lastUsedUA = ua;
        await this.initializeWithUA(ua);
        this.logger.info('Browser initialized ✓');
    }

    async handleCookiesAndPopups() {
        this.logger.info('Handling cookies/popups...');
        // Poll for cookie banner up to 20s — dismiss as soon as it appears
        const cookieSelectors = [
            '#onetrust-accept-btn-handler',
            'button[data-testid="accept-all-cookies"]',
            'button.onetrust-close-btn-handler',
        ];
        const deadline = Date.now() + 20000;
        let accepted = false;
        while (Date.now() < deadline && !accepted) {
            for (const sel of cookieSelectors) {
                try {
                    const btn = await this.page.$(sel);
                    if (btn) {
                        await btn.click();
                        this.logger.info(`Accepted cookies (${sel})`);
                        await this.delay(2000);
                        accepted = true;
                        break;
                    }
                } catch (e) {}
            }
            if (!accepted) await this.delay(1000);
        }
        if (!accepted) this.logger.info('No cookie banner found — continuing');

        // Close any AI / institution popups
        for (const sel of ['._pendo-close-guide', '#pendo-close-guide-bfad995f', '#bdd-els-close']) {
            try { const btn = await this.page.$(sel); if (btn) { await btn.click(); await this.delay(400); } } catch (e) {}
        }
    }

    isCaptchaPage() {
        try {
            const title = document.title || '';
            const body  = document.body ? document.body.innerText.slice(0, 1000) : '';
            const PATTERNS = [
                'verify you are human', 'captcha', 'robot', 'User Agent:',
                'Access Denied', 'Please verify', 'unusual traffic',
                'challenge', 'security check', 'bot detection',
            ];
            return PATTERNS.some(p =>
                title.toLowerCase().includes(p.toLowerCase()) ||
                body.toLowerCase().includes(p.toLowerCase())
            );
        } catch(e) { return false; }
    }

    async checkBotDetection() {
        try {
            // Detect "Your browser is outdated" — caused by old UA
            const currentUrl = this.page.url();
            if (currentUrl.includes('unsupported_browser') || currentUrl.includes('outdated')) {
                this.logger.warn('⚠️  "Browser outdated" page — UA too old, rotating...');
                await this.rotateAndRestart('https://www.sciencedirect.com/');
                await this.delay(15000);
                return true;
            }
            const detected = await this.page.evaluate(this.isCaptchaPage.toString() + '\nreturn isCaptchaPage();');
            if (detected) {
                this.logger.warn('⚠️  Bot/CAPTCHA detected — rotating UA and restarting browser...');
                await this.rotateAndRestart('https://www.sciencedirect.com/');
                await this.delay(15000);  // settle before next navigation
                return true;
            }
        } catch (e) {}
        return false;
    }

    async rotateAndRestart(returnUrl) {
        // Force-pick a DIFFERENT UA before restarting so the site sees a new browser fingerprint
        this.lastUsedUA = this.lastUsedUA || '';
        let newUA = this.getNextUserAgent();
        let tries = 0;
        while (newUA === this.lastUsedUA && tries < 10) {
            newUA = this.getNextUserAgent();
            tries++;
        }
        this.lastUsedUA = newUA;
        this.logger.info(`[UA rotate] New UA: ${newUA.slice(0, 60)}...`);

        try { if (this.browser) await this.browser.close(); } catch (e) {}
        this.browser = null; this.page = null;
        await this.delay(8000);   // longer wait after bot detection

        // Reinitialize with new UA
        await this.initializeWithUA(newUA);
        if (returnUrl) {
            await this.page.goto(returnUrl, { waitUntil: 'networkidle2', timeout: 60000 });
            await this.handleCookiesAndPopups();
        }
    }

    async restartBrowser() {
        await this.rotateAndRestart('https://www.sciencedirect.com/');
    }

    async initializeWithUA(ua) {
        const executablePath = this.findChromePath();
        const launchOpts = {
            headless: false,
            args: [
                '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas', '--disable-gpu', '--window-size=1400,900',
                '--disable-blink-features=AutomationControlled', '--disable-infobars',
                '--disable-notifications', '--disable-popup-blocking',
            ],
            defaultViewport: null,
            ignoreHTTPSErrors: true,
            timeout: 60000,
        };
        if (executablePath) launchOpts.executablePath = executablePath;
        this.browser = await puppeteer.launch(launchOpts);
        this.page    = await this.browser.newPage();
        await this.page.setUserAgent(ua);
        await this.page.evaluateOnNewDocument(() => {
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
        });
        this.logger.info(`Browser restarted with UA: ${ua.slice(0, 60)}...`);
    }

    async getTotalResults(url) {
        for (let attempt = 1; attempt <= 3; attempt++) {
            try {
                await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
                if (await this.checkBotDetection()) {
                    await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
                }
                await this.delay(4000);
                await this.handleCookiesAndPopups();
                try { const btn = await this.page.$('#bdd-els-close'); if (btn) { await btn.click(); await this.delay(1000); } } catch (e) {}

                // Wait for ANY result count element
                for (const sel of ['.search-body-results-text','.ResultsFound','[data-testid="search-count"]',
                                    'div[class*="SearchResults"] span','ol.search-result-cont']) {
                    try { await this.page.waitForSelector(sel, { timeout: 5000 }); break; } catch (e) {}
                }

                const total = await this.page.evaluate(() => {
                    const SELECTORS = [
                        '.search-body-results-text',
                        '.ResultsFound',
                        '[data-testid="search-count"]',
                        'div[class*="ResultsFound"]',
                        'span[class*="result-count"]',
                    ];
                    for (const sel of SELECTORS) {
                        const el = document.querySelector(sel);
                        if (!el) continue;
                        const m = el.textContent.match(/[\d,]+/);
                        if (m) return parseInt(m[0].replace(/,/g, ''), 10);
                    }
                    // Last resort: count article items on page
                    const items = document.querySelectorAll('#srp-results-list .result-item-content');
                    return items.length;
                });
                this.logger.info(`Total results: ${total} (url: ${url.slice(0,80)}...)`);
                return total;
            } catch (e) {
                this.logger.error(`getTotalResults attempt ${attempt}: ${e.message}`);
                if (attempt < 3) await this.rotateAndRestart(null);
            }
        }
        return 0;
    }

    async getArticleLinks(url) {
        for (let attempt = 1; attempt <= 3; attempt++) {
            try {
                await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
                if (await this.checkBotDetection()) await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
                await this.delay(2000);
                try { const btn = await this.page.$('#bdd-els-close'); if (btn) await btn.click(); } catch (e) {}
                await this.page.waitForSelector('#srp-results-list', { timeout: 10000 });
                const results = await this.page.evaluate(() => {
                    return Array.from(
                        document.querySelectorAll('#srp-results-list .result-list-title-link')
                    ).map(a => ({ url: a.href, title: (a.textContent || '').trim() }));
                });
                return results;
            } catch (e) {
                this.logger.error(`getArticleLinks attempt ${attempt}: ${e.message}`);
                if (attempt < 3) await this.restartBrowser();
            }
        }
        return [];
    }

    async scrapeUrlsForYear(year, urlCsvWriter, progressBase, progressRange) {
        const kw       = this.opts.keyword;
        const query    = kw.replace(/ /g, '%20');
        const baseUrl  = `https://www.sciencedirect.com/search?qs=${query}&date=${year}&show=100`;
        let   totalNew = 0;

        const writeNew = async (results) => {
            const fresh = results.filter(r => r.url && !this.seenUrls[r.url]);
            fresh.forEach(r => { this.seenUrls[r.url] = true; });
            if (fresh.length > 0) {
                await urlCsvWriter.writeRecords(fresh);
                totalNew += fresh.length;
            }
        };

        // Step 1: base search
        const total = await this.getTotalResults(baseUrl);
        this.logger.info(`Year ${year}: ${total} results`);
        reportProgress(progressBase, `Year ${year}: ${total} results`);

        if (total > 0) {
            let offset = 0;
            while (offset <= 900) {
                const results = await this.getArticleLinks(`${baseUrl}&offset=${offset}`);
                await writeNew(results);
                reportProgress(
                    progressBase + Math.floor((offset / 900) * (progressRange * 0.5)),
                    `Year ${year} base search: offset ${offset}, ${totalNew} URLs`,
                    { links: Object.keys(this.seenUrls).length }
                );
                if (results.length < 100 || offset >= 900) break;
                offset += 100;
                await this.delay(2000);
            }
        }

        // Step 2: by article type
        const typeStep = (progressRange * 0.25) / this.articleTypes.length;
        for (let t = 0; t < this.articleTypes.length; t++) {
            const atype   = this.articleTypes[t];
            const typeUrl = `${baseUrl}&articleTypes=${atype}&lastSelectedFacet=articleTypes`;
            const typeTotal = await this.getTotalResults(typeUrl);
            if (typeTotal === 0) continue;
            let off = 0;
            while (off <= 900) {
                const r = await this.getArticleLinks(`${typeUrl}&offset=${off}`);
                await writeNew(r);
                if (r.length < 100 || off >= 900) break;
                off += 100;
                await this.delay(2000);
            }
            reportProgress(
                progressBase + Math.floor(progressRange * 0.5 + t * typeStep),
                `Year ${year} type ${atype}: ${totalNew} URLs total`
            );
        }

        return Object.keys(this.seenUrls).length;
    }

    async extractEmailsFromArticle(url, keyword, year) {
        const results = [];
        try {
            // Short per-article timeout — don't hang 60s on slow/broken pages
            this.page.setDefaultNavigationTimeout(25000);

            try {
                await this.page.goto(url, { waitUntil: 'domcontentloaded', timeout: 25000 });
            } catch (e) {
                this.logger.warn(`Article load timeout, skipping: ${url.slice(0, 80)}`);
                return results;
            }

            // Check bot detection — rotate UA, then settle 20s before retry
            const botState = await this.checkBotDetection();
            if (botState) {
                this.logger.warn(`Bot detected on article — rotated UA, settling 20s...`);
                await this.delay(20000);
                try {
                    await this.page.goto(url, { waitUntil: 'domcontentloaded', timeout: 25000 });
                    if (await this.checkBotDetection()) {
                        this.logger.warn('Still bot page after rotate — skipping article');
                        return results;
                    }
                } catch (e) { return results; }
            }

            await this.delay(2000);

            // Dismiss popups
            for (const sel of ['#pendo-close-guide-bfad995f', '#bdd-els-close',
                                '._pendo-close-guide', 'button[aria-label="Close"]']) {
                try { const b = await this.page.$(sel); if (b) { await b.click(); await this.delay(300); } } catch (e) {}
            }

            // Expand author list
            try { await this.page.click('#show-more-btn'); await this.delay(1000); } catch (e) {}

            // ── Method A: Envelope SVG icon → side panel ────────────────
            const authorBtns = await this.page.$$('svg[title="Author email or social media contact details icon"]');
            if (authorBtns.length > 0) {
                for (let i = 0; i < authorBtns.length; i++) {
                    try {
                        const btns = await this.page.$$('svg[title="Author email or social media contact details icon"]');
                        if (!btns[i]) continue;
                        await this.page.evaluate(el => el.scrollIntoView({ block: 'center' }), btns[i]);
                        await this.delay(500);
                        await btns[i].click();
                        await this.delay(2000);

                        try { await this.page.waitForSelector('#side-panel-author', { timeout: 5000 }); } catch (e) { continue; }

                        const data = await this.page.evaluate(() => {
                            const emailEl   = document.querySelector('#side-panel-author .e-address a')
                                           || document.querySelector('#side-panel-author a[href^="mailto"]');
                            const givenEl   = document.querySelector('#side-panel-author .given-name');
                            const surnameEl = document.querySelector('#side-panel-author .surname');
                            const nameEl    = document.querySelector('#side-panel-author .author-name')
                                           || document.querySelector('#side-panel-author .name');
                            const email = emailEl ? (emailEl.textContent.trim() || emailEl.getAttribute('href').replace('mailto:','').trim()) : null;
                            const given   = givenEl   ? givenEl.textContent.trim() : '';
                            const surname = surnameEl ? surnameEl.textContent.trim() : '';
                            const fullName = (given + ' ' + surname).trim()
                                          || (nameEl ? nameEl.textContent.trim() : '');
                            return { email, name: fullName };
                        });

                        if (data.email && data.email.includes('@')) {
                            results.push({ Article_URL: url, Author_Name: data.name, Email: data.email });
                            this.logger.info(`✅ ${data.name} — ${data.email}`);
                        }

                        try {
                            const close = await this.page.$('#side-panel-author button[aria-label="Close"]')
                                       || await this.page.$('.side-panel-close-btn');
                            if (close) { await close.click(); await this.delay(400); }
                        } catch (e) {}
                    } catch (e) {
                        this.logger.warn(`Author button ${i+1} error: ${e.message}`);
                    }
                }
            }

            // ── Method B: Direct mailto links anywhere on page (fallback) ──
            if (results.length === 0) {
                try {
                    const emailData = await this.page.evaluate(() => {
                        // Find all mailto links
                        const links = Array.from(document.querySelectorAll('a[href^="mailto:"]'));
                        return links.map(a => {
                            const email = a.getAttribute('href').replace('mailto:','').trim();
                            // Try to find author name nearby
                            const parent = a.closest('.author-info, .author, [class*="author"]') || a.parentElement;
                            const nameEl = parent ? (parent.querySelector('.given-name, .surname, .author-name, .name') || parent) : null;
                            const name   = nameEl ? nameEl.textContent.replace(email, '').trim().slice(0, 80) : '';
                            return { email, name };
                        }).filter(d => d.email.includes('@') && !d.email.includes('sciencedirect'));
                    });
                    for (const { email, name } of emailData) {
                        if (!results.some(r => r.Email === email)) {
                            results.push({ Article_URL: url, Author_Name: name, Email: email });
                            this.logger.info(`✅ [mailto] ${name} — ${email}`);
                        }
                    }
                } catch (e) {}
            }

        } catch (e) {
            this.logger.error(`extractEmailsFromArticle error ${url.slice(0,80)}: ${e.message}`);
        } finally {
            this.page.setDefaultNavigationTimeout(60000);
        }
        return results;
    }

    async run() {
        const { keyword, 'start-year': startYr, 'end-year': endYr,
                'output-dir': outDir, 'conf-name': confName,
                'url-csv': urlCsvPath, 'authors-csv': authorsCsvPath } = this.opts;

        const kw       = keyword || '';
        const safe     = sanitizeKeyword(kw);
        const start    = parseInt(startYr, 10) || new Date().getFullYear();
        const end      = parseInt(endYr,   10) || start;
        const conf     = confName ? `_${confName}` : '';

        reportProgress(2, `Starting ScienceDirect scrape: "${kw}" ${start}–${end}`);

        // ── Phase 1: Collect article URLs ────────────────────────────────
        const urlWriter = createObjectCsvWriter({
            path:   urlCsvPath,
            header: [{ id: 'url', title: 'Article_URL' }, { id: 'title', title: 'Title' }],
            append: false,
        });
        await urlWriter.writeRecords([]); // initialise file

        const appendUrlWriter = createObjectCsvWriter({
            path:   urlCsvPath,
            header: [{ id: 'url', title: 'Article_URL' }, { id: 'title', title: 'Title' }],
            append: true,
        });

        reportProgress(5, 'Phase 1: Landing on ScienceDirect homepage...');
        await this.page.goto('https://www.sciencedirect.com/', { waitUntil: 'networkidle2', timeout: 60000 });
        await this.handleCookiesAndPopups();

        const years = [];
        for (let y = start; y <= end; y++) years.push(y);
        const yearProgressSlice = Math.floor(33 / years.length);

        for (let i = 0; i < years.length; i++) {
            const progressBase = 5 + i * yearProgressSlice;
            await this.scrapeUrlsForYear(years[i], appendUrlWriter, progressBase, yearProgressSlice);
        }

        const totalUrls = Object.keys(this.seenUrls).length;
        this.logger.info(`Phase 1 complete: ${totalUrls} unique URLs`);
        reportProgress(40, `Phase 1 done: ${totalUrls} URLs collected`, { links: totalUrls });

        // ── Phase 2: Extract author emails ────────────────────────────────
        const urlRows = [];
        await new Promise((resolve, reject) => {
            fsSync.createReadStream(urlCsvPath)
                .pipe(csv())
                .on('data', row => urlRows.push(row))
                .on('end', resolve)
                .on('error', reject);
        });

        this.logger.info(`Phase 2: extracting emails from ${urlRows.length} articles`);
        reportProgress(42, `Phase 2: extracting emails from ${urlRows.length} articles`);

        // Initialise authors CSV
        const authorWriter = createObjectCsvWriter({
            path:   authorsCsvPath,
            header: [
                { id: 'Article_URL',  title: 'Article_URL'  },
                { id: 'Author_Name',  title: 'Author_Name'  },
                { id: 'Email',        title: 'Email'        },
            ],
            append: false,
        });
        await authorWriter.writeRecords([]);

        const appendAuthorWriter = createObjectCsvWriter({
            path:   authorsCsvPath,
            header: [
                { id: 'Article_URL',  title: 'Article_URL'  },
                { id: 'Author_Name',  title: 'Author_Name'  },
                { id: 'Email',        title: 'Email'        },
            ],
            append: true,
        });

        let authorsFound = 0;
        for (let i = 0; i < urlRows.length; i++) {
            const row = urlRows[i];
            if (!row.Article_URL && !row.url) continue;
            const articleUrl = row.Article_URL || row.url;

            try {
                const results = await this.extractEmailsFromArticle(articleUrl, kw, startYr);
                if (results.length > 0) {
                    await appendAuthorWriter.writeRecords(results);
                    authorsFound += results.length;
                }
            } catch (e) {
                this.logger.error(`Article ${i+1} error: ${e.message}`);
            }

            const pct = 42 + Math.floor(((i + 1) / urlRows.length) * 55);
            reportProgress(pct, `Author extraction: ${i+1}/${urlRows.length} (${authorsFound} found)`, {
                authors: authorsFound,
                links: urlRows.length,
            });
            // Random delay 3-7s between articles to avoid rate limiting
            await this.delay(3000 + Math.floor(Math.random() * 4000));
        }

        reportProgress(100, `Scraping complete: ${authorsFound} authors found`);
        // Signal the output file path back to Python
        process.stdout.write(`OUTPUT_FILE:${authorsCsvPath}\n`);
        this.logger.info(`OUTPUT_FILE:${authorsCsvPath}`);

        return authorsCsvPath;
    }

    async close() {
        try { if (this.browser) await this.browser.close(); } catch (e) {}
    }
}

// ── Entry point ────────────────────────────────────────────────────────────────
async function main() {
    const opts = parseArgs();

    if (!opts.keyword) {
        process.stderr.write('Error: --keyword is required\n');
        process.exit(1);
    }

    // Setup log file in logs/ directory (same as Python scrapers)
    const logDir      = opts['log-dir'] || 'logs';
    const kw          = sanitizeKeyword(opts.keyword || 'unknown');
    const startLabel  = (opts['start-year'] || '').replace(/\//g, '-');
    const endLabel    = (opts['end-year'] || '').replace(/\//g, '-');
    const logPath     = path.join(logDir, `ScienceDirectScraper-${kw}-${startLabel}-${endLabel}.log`);

    fsSync.mkdirSync(logDir, { recursive: true });
    fsSync.mkdirSync(opts['output-dir'] || 'results', { recursive: true });

    const logger  = new Logger(logPath);
    const scraper = new ScienceDirectScraper(opts, logger);

    logger.info(`Starting ScienceDirect: "${opts.keyword}" ${opts['start-year']}→${opts['end-year']}`);

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

if (require.main === module) {
    main().catch(err => {
        process.stderr.write(`Fatal error: ${err.message}\n`);
        process.exit(1);
    });
}

module.exports = ScienceDirectScraper;
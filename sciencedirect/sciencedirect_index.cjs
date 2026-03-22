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

const puppeteer      = require('puppeteer-extra');
const StealthPlugin  = require('puppeteer-extra-plugin-stealth');
const fsSync         = require('fs');
const path           = require('path');
const { createObjectCsvWriter } = require('csv-writer');
const csv            = require('csv-parser');
const os             = require('os');

puppeteer.use(StealthPlugin());

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
        this.userAgents = [
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        ];
        this.articleTypes = ['REV', 'FLA', 'DAT', 'CH'];
        this.seenUrls = {};
    }

    delay(ms) { return new Promise(r => setTimeout(r, ms)); }

    getNextUserAgent() {
        const ua = this.userAgents[this.currentUserAgentIndex];
        this.currentUserAgentIndex = (this.currentUserAgentIndex + 1) % this.userAgents.length;
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
        const executablePath = this.findChromePath();
        const launchOpts = {
            headless: false,   // must be visible for VNC / Xvfb
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--disable-gpu',
                '--window-size=1400,900',
                '--disable-blink-features=AutomationControlled',
                '--disable-infobars',
                '--disable-notifications',
                '--disable-popup-blocking',
            ],
            defaultViewport: null,
            ignoreHTTPSErrors: true,
            timeout: 60000,
        };
        if (executablePath) launchOpts.executablePath = executablePath;

        this.browser = await puppeteer.launch(launchOpts);
        this.page    = await this.browser.newPage();

        const ua = this.getNextUserAgent();
        await this.page.setUserAgent(ua);
        this.logger.info(`User-Agent: ${ua}`);

        await this.page.evaluateOnNewDocument(() => {
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
        });
        this.logger.info('Browser initialized ✓');
    }

    async handleCookiesAndPopups() {
        this.logger.info('Handling cookies/popups (15s settle)...');
        await this.delay(15000);

        for (const sel of [
            '#onetrust-accept-btn-handler',
            'button[data-testid="accept-all-cookies"]',
        ]) {
            try {
                const btn = await this.page.$(sel);
                if (btn) { await btn.click(); this.logger.info(`Accepted cookies (${sel})`); await this.delay(2000); break; }
            } catch (e) {}
        }
        for (const sel of ['._pendo-close-guide', '#pendo-close-guide-bfad995f', '#bdd-els-close']) {
            try { const btn = await this.page.$(sel); if (btn) { await btn.click(); await this.delay(500); } } catch (e) {}
        }
    }

    async checkBotDetection() {
        try {
            const content = await this.page.content();
            if (content.includes('User Agent:') || content.includes('robot.txt')) {
                this.logger.warn('Bot detection page! Restarting browser...');
                await this.restartBrowser();
                return true;
            }
        } catch (e) {}
        return false;
    }

    async restartBrowser() {
        try { if (this.browser) await this.browser.close(); } catch (e) {}
        this.browser = null; this.page = null;
        await this.delay(5000);
        await this.initialize();
        await this.page.goto('https://www.sciencedirect.com/', { waitUntil: 'networkidle2', timeout: 60000 });
        await this.handleCookiesAndPopups();
    }

    async getTotalResults(url) {
        for (let attempt = 1; attempt <= 3; attempt++) {
            try {
                await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
                if (await this.checkBotDetection()) {
                    await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
                }
                await this.delay(3000);
                try { const btn = await this.page.$('#bdd-els-close'); if (btn) { await btn.click(); await this.delay(1000); } } catch (e) {}
                try { await this.page.waitForSelector('.search-body-results-text', { timeout: 10000 }); } catch (e) {}

                const total = await this.page.evaluate(() => {
                    const el = document.querySelector('.search-body-results-text') || document.querySelector('.ResultsFound');
                    if (!el) return 0;
                    const m = el.textContent.match(/[\d,]+/);
                    return m ? parseInt(m[0].replace(/,/g, ''), 10) : 0;
                });
                this.logger.info(`Total results: ${total}`);
                return total;
            } catch (e) {
                this.logger.error(`getTotalResults attempt ${attempt}: ${e.message}`);
                if (attempt < 3) await this.restartBrowser();
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
        for (let attempt = 1; attempt <= 3; attempt++) {
            try {
                await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
                if (await this.checkBotDetection()) await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
                await this.delay(2000);

                try { const btn = await this.page.$('#pendo-close-guide-bfad995f'); if (btn) await btn.click(); } catch (e) {}
                try { const btn = await this.page.$('#bdd-els-close'); if (btn) await btn.click(); } catch (e) {}
                await this.delay(1000);

                try { await this.page.click('#show-more-btn'); await this.delay(1000); } catch (e) {}

                const authorBtns = await this.page.$$('svg[title="Author email or social media contact details icon"]');
                if (authorBtns.length === 0) return [];

                const results = [];
                for (let i = 0; i < authorBtns.length; i++) {
                    try {
                        const btns = await this.page.$$('svg[title="Author email or social media contact details icon"]');
                        if (!btns[i]) continue;
                        await btns[i].click();
                        await this.delay(2000);
                        try { await this.page.waitForSelector('#side-panel-author', { timeout: 5000 }); } catch (e) { continue; }

                        const data = await this.page.evaluate(() => {
                            const emailEl   = document.querySelector('#side-panel-author .e-address a');
                            const givenEl   = document.querySelector('#side-panel-author .given-name');
                            const surnameEl = document.querySelector('#side-panel-author .surname');
                            return {
                                email:   emailEl   ? emailEl.textContent.trim()   : null,
                                given:   givenEl   ? givenEl.textContent.trim()   : '',
                                surname: surnameEl ? surnameEl.textContent.trim() : '',
                            };
                        });

                        if (data.email) {
                            results.push({
                                Article_URL:  url,
                                Author_Name:  `${data.given} ${data.surname}`.trim(),
                                Email:        data.email,
                            });
                            this.logger.info(`✅ ${data.given} ${data.surname} — ${data.email}`);
                        }

                        try { const close = await this.page.$('#side-panel-author button[aria-label="Close"]'); if (close) await close.click(); } catch (e) {}
                        await this.delay(500);
                    } catch (e) {
                        this.logger.warn(`Author ${i+1} error: ${e.message}`);
                    }
                }
                return results;
            } catch (e) {
                this.logger.error(`extractEmailsFromArticle attempt ${attempt}: ${e.message}`);
                if (attempt < 3) await this.restartBrowser();
            }
        }
        return [];
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
            await this.delay(1000);
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

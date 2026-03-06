
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const fs = require('fs/promises');
const fsSync = require('fs');
const path = require('path');
const { createObjectCsvWriter } = require('csv-writer');
const csv = require('csv-parser');
const os = require('os');
const readline = require('readline');


puppeteer.use(StealthPlugin());

// import puppeteer from 'puppeteer-extra';
// import StealthPlugin from 'puppeteer-extra-plugin-stealth';
// import fs from 'fs/promises';
// import fsSync from 'fs';
// import path from 'path';
// import { createObjectCsvWriter } from 'csv-writer';
// import csv from 'csv-parser';
// import { fileURLToPath } from 'url';
// import readline from 'readline';
// import os from 'os';

// puppeteer.use(StealthPlugin());

class ScienceDirectScraper {
    constructor() {
        this.browser = null;
        this.page = null;
        this.logFile = null;
        this.outputDir = 'output';
        this.currentUserAgentIndex = 0;
        this.userAgents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
        ];
        this.articleTypes = ["REV", "FLA", "DAT", "CH"];
    }

    async delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    initializeLog(keywordDir) {
        this.logFile = path.join(keywordDir, 'scraper_log.log');
        if (fsSync.existsSync(this.logFile)) {
            fsSync.unlinkSync(this.logFile);
        }
        fsSync.writeFileSync(this.logFile, `Log initialized at ${new Date().toISOString()}\n`);
        console.log(`Log file created at: ${this.logFile}`);
    }

    log(level, message) {
        const timestamp = new Date().toISOString();
        const logMessage = `${timestamp} - ${level} - ${message}\n`;
        if (this.logFile) {
            fsSync.appendFileSync(this.logFile, logMessage);
        }
        console.log(logMessage.trim());
    }

    getNextUserAgent() {
        const userAgent = this.userAgents[this.currentUserAgentIndex];
        this.currentUserAgentIndex = (this.currentUserAgentIndex + 1) % this.userAgents.length;
        return userAgent;
    }

    findChromePath() {
        const platform = os.platform();
        let possiblePaths = [];

        if (platform === 'win32') {
            possiblePaths = [
                'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
                'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
                path.join(os.homedir(), 'AppData\\Local\\Google\\Chrome\\Application\\chrome.exe'),
                process.env.CHROME_PATH,
                process.env.CHROME_BIN
            ];
        } else if (platform === 'darwin') {
            possiblePaths = [
                '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                path.join(os.homedir(), 'Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
                process.env.CHROME_PATH,
                process.env.CHROME_BIN
            ];
        } else if (platform === 'linux') {
            possiblePaths = [
                '/usr/bin/google-chrome',
                '/usr/bin/google-chrome-stable',
                '/usr/bin/chromium-browser',
                '/usr/bin/chromium',
                '/snap/bin/chromium',
                process.env.CHROME_PATH,
                process.env.CHROME_BIN
            ];
        }

        for (const chromePath of possiblePaths.filter(Boolean)) {
            if (fsSync.existsSync(chromePath)) {
                this.log('INFO', `Found Chrome at: ${chromePath}`);
                return chromePath;
            }
        }

        this.log('INFO', 'Chrome not found, Puppeteer will use bundled Chromium');
        return null;
    }

    async handleCookiesAndPopups() {
        try {
            this.log('INFO', 'Starting cookie and popup handling with 30 second delay...');
            await this.delay(30000);

            try {
                const cookieButton = await this.page.waitForSelector('#onetrust-accept-btn-handler', { timeout: 5000 });
                if (cookieButton) {
                    await cookieButton.click();
                    this.log('INFO', '✅ Accepted cookies');
                    await this.delay(2000);
                }
            } catch (e) {
                this.log('INFO', 'No cookie banner found or already accepted');
            }
            
            try {
                const closeButton = await this.page.$("._pendo-close-guide");
                if (closeButton) {
                    await closeButton.click();
                    this.log('INFO', '✅ Closed AI popup');
                    await this.delay(1000);
                }
            } catch (e) {
                this.log('INFO', 'No AI popup found');
            }

            try {
                const pendoCloseButton = await this.page.$('#pendo-close-guide-bfad995f');
                if (pendoCloseButton) {
                    await pendoCloseButton.click();
                    this.log('INFO', '✅ Closed Science Direct AI popup');
                    await this.delay(1000);
                }
            } catch (e) {}

            try {
                const closeButton = await this.page.$('#bdd-els-close');
                if (closeButton) {
                    await closeButton.click();
                    this.log('INFO', '✅ Closed institution popup');
                    await this.delay(1000);
                }
            } catch (e) {}
        } catch (error) {
            this.log('ERROR', `Error handling cookies/popups: ${error.message}`);
        }
    }

    async checkAndRotateUserAgent() {
        try {
            const pageContent = await this.page.content().catch(() => '');
            const userAgentElement = await this.page.$('#userAgent').catch(() => null);
            const isBotPage = pageContent.includes('User Agent:') || userAgentElement !== null;
            
            if (isBotPage) {
                this.log('WARNING', `⚠️ BOT DETECTION PAGE DETECTED!`);
                
                if (userAgentElement) {
                    const userAgentText = await this.page.$eval('#userAgent', el => el.textContent).catch(() => '');
                    this.log('WARNING', `Detected User Agent on page: ${userAgentText}`);
                }
                
                this.log('WARNING', '🔄 Closing browser and restarting with new User Agent...');
                
                if (this.browser) {
                    try {
                        await this.browser.close();
                        this.log('INFO', '✅ Browser closed successfully');
                    } catch (e) {
                        this.log('WARNING', `Error closing browser: ${e.message}`);
                    }
                    this.browser = null;
                    this.page = null;
                }
                
                this.log('INFO', 'Waiting 5 seconds before restarting...');
                await this.delay(5000);
                
                this.log('INFO', 'Initializing new browser session...');
                await this.initialize(false);
                
                this.log('INFO', 'Loading homepage with new session...');
                await this.page.goto('https://www.sciencedirect.com/', {
                    waitUntil: 'networkidle2',
                    timeout: 30000
                });
                
                await this.handleCookiesAndPopups();
                
                this.log('INFO', '✅ Successfully rotated to new User Agent and handled popups');
                return true;
            }
            
            return false;
        } catch (error) {
            this.log('ERROR', `Error checking User Agent: ${error.message}`);
            return false;
        }
    }

    async initialize(headless = false) {
        try {
            const executablePath = this.findChromePath();

            const launchOptions = {
                headless: headless ? 'new' : false,
                args: [
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--disable-gpu',
                    '--start-maximized',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-infobars',
                    '--disable-notifications',
                    '--disable-popup-blocking',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process'
                ],
                defaultViewport: null,
                ignoreHTTPSErrors: true,
                timeout: 60000
            };

            if (executablePath) {
                launchOptions.executablePath = executablePath;
            }

            this.browser = await puppeteer.launch(launchOptions);
            this.page = await this.browser.newPage();
            
            const userAgent = this.getNextUserAgent();
            await this.page.setUserAgent(userAgent);
            this.log('INFO', `Set User Agent: ${userAgent}`);

            await this.page.evaluateOnNewDocument(() => {
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => false,
                });
            });

            this.log('INFO', 'Browser initialized successfully');
        } catch (error) {
            this.log('ERROR', `Failed to initialize browser: ${error.message}`);
            throw error;
        }
    }

    async landFirstPage() {
        try {
            await this.page.goto('https://www.sciencedirect.com/', {
                waitUntil: 'networkidle2',
                timeout: 30000
            });
            
            await this.checkAndRotateUserAgent();
            this.log('INFO', 'Landed on ScienceDirect homepage');
            await this.handleCookiesAndPopups();
            
        } catch (error) {
            this.log('ERROR', `Failed to load homepage: ${error.message}`);
            throw error;
        }
    }

    async extractPublicationTitles(keywordInput, yearRange) {
        try {
            const query = keywordInput.replace(/ /g, '%20');
            const url = `https://www.sciencedirect.com/search?qs=${query}&date=${yearRange}&show=100`;
            
            await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
            await this.delay(3000);

            try {
                const showMoreBtn = await this.page.waitForSelector('button[data-aa-button="srp-show-more-publicationTitles-facet"]', { timeout: 5000 });
                if (showMoreBtn) {
                    await showMoreBtn.click();
                    this.log('INFO', '✅ Clicked show more for publication titles');
                    await this.delay(2000);
                }
            } catch (e) {
                this.log('WARNING', 'Could not find show more button for publication titles');
            }

            const publicationTitles = await this.page.evaluate(() => {
                const inputs = Array.from(document.querySelectorAll('input[id^="publicationTitles-"]'));
                return inputs.map(input => {
                    const id = input.getAttribute('id');
                    return id.replace('publicationTitles-', '');
                });
            });

            this.log('INFO', `Found ${publicationTitles.length} publication titles`);
            return publicationTitles;
        } catch (error) {
            this.log('ERROR', `Failed to extract publication titles: ${error.message}`);
            return [];
        }
    }

    async extractSubjectAreas(keywordInput, yearRange) {
        try {
            const query = keywordInput.replace(/ /g, '%20');
            const url = `https://www.sciencedirect.com/search?qs=${query}&date=${yearRange}&show=100`;
            
            await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
            
            const wasRotated = await this.checkAndRotateUserAgent();
            if (wasRotated) {
                await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
            }
            
            await this.delay(3000);

            try {
                const showMoreBtn = await this.page.waitForSelector('button[data-aa-button="srp-show-more-subjectAreas-facet"]', { timeout: 5000 });
                if (showMoreBtn) {
                    await showMoreBtn.click();
                    this.log('INFO', '✅ Clicked show more for subject areas');
                    await this.delay(2000);
                }
            } catch (e) {
                this.log('WARNING', 'Could not find show more button for subject areas');
            }

            const subjectAreas = await this.page.evaluate(() => {
                const inputs = Array.from(document.querySelectorAll('input[id^="subjectAreas-"]'));
                return inputs.map(input => {
                    const id = input.getAttribute('id');
                    return id.replace('subjectAreas-', '');
                });
            });

            this.log('INFO', `Found ${subjectAreas.length} subject areas`);
            return subjectAreas;
        } catch (error) {
            this.log('ERROR', `Failed to extract subject areas: ${error.message}`);
            return [];
        }
    }

    async getTotalResults(url, retries = 3) {
        for (let attempt = 1; attempt <= retries; attempt++) {
            try {
                await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
                
                const wasRotated = await this.checkAndRotateUserAgent();
                if (wasRotated) {
                    await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
                }
                
                await this.delay(2000);

                try {
                    const closeButton = await this.page.$('#bdd-els-close');
                    if (closeButton) {
                        await closeButton.click();
                        await this.delay(1000);
                    }
                } catch (e) {}

                const totalResults = await this.page.evaluate(() => {
                    const resultsElement = document.querySelector('h1.text-l .search-body-results-text');
                    if (!resultsElement) return 0;
                    const text = resultsElement.textContent.trim();
                    const match = text.match(/[\d,]+/);
                    return match ? parseInt(match[0].replace(/,/g, '')) : 0;
                });

                return totalResults;
            } catch (error) {
                this.log('ERROR', `Failed to get total results (attempt ${attempt}/${retries}): ${error.message}`);
                
                if (attempt < retries) {
                    this.log('INFO', `Retrying after browser restart...`);
                    await this.restartBrowser();
                } else {
                    return 0;
                }
            }
        }
        return 0;
    }

    async restartBrowser() {
        try {
            if (this.browser) {
                await this.browser.close();
                this.browser = null;
                this.page = null;
            }
            
            await this.delay(5000);
            await this.initialize(false);
            
            await this.page.goto('https://www.sciencedirect.com/', {
                waitUntil: 'networkidle2',
                timeout: 60000
            });
            
            await this.handleCookiesAndPopups();
        } catch (error) {
            this.log('ERROR', `Failed to restart browser: ${error.message}`);
            throw error;
        }
    }

    async getArticleLinksFromPage(url, retries = 3) {
        for (let attempt = 1; attempt <= retries; attempt++) {
            try {
                await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
                
                const rotated = await this.checkAndRotateUserAgent();
                if (rotated) {
                    await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
                }
                
                await this.delay(2000);

                try {
                    const closeButton = await this.page.$('#bdd-els-close');
                    if (closeButton) {
                        await closeButton.click();
                        await this.delay(1000);
                    }
                } catch (e) {}

                await this.page.waitForSelector('#srp-results-list', { timeout: 10000 });
                
                const results = await this.page.evaluate(() => {
                    const linkElements = Array.from(document.querySelectorAll('#srp-results-list .result-list-title-link'));
                    return linkElements.map(link => ({
                        url: link.href,
                        title: link.textContent.trim()
                    }));
                });

                return results;
            } catch (error) {
                this.log('ERROR', `Failed to get article links (attempt ${attempt}/${retries}): ${error.message}`);
                
                if (attempt < retries) {
                    this.log('INFO', `Retrying after browser restart...`);
                    await this.restartBrowser();
                } else {
                    return [];
                }
            }
        }
        return [];
    }

    async scrapeWithFacetFilters(keywordInput, yearRange, keywordDir) {
        const csvFile = path.join(keywordDir, `articles_${yearRange}.csv`);
        const query = keywordInput.replace(/ /g, '%20');

        if (fsSync.existsSync(csvFile)) {
            fsSync.unlinkSync(csvFile);
        }

        const csvWriter = createObjectCsvWriter({
            path: csvFile,
            header: [
                { id: 'url', title: 'url' },
                { id: 'title', title: 'Title' }
            ],
            append: false
        });

        await csvWriter.writeRecords([]);

        const seenUrls = new Set();

        const writeResults = async (results) => {
            const uniqueNew = results.filter(r => !seenUrls.has(r.url));
            uniqueNew.forEach(r => seenUrls.add(r.url));
            
            if (uniqueNew.length > 0) {
                const appendWriter = createObjectCsvWriter({
                    path: csvFile,
                    header: [
                        { id: 'url', title: 'url' },
                        { id: 'title', title: 'Title' }
                    ],
                    append: true
                });
                await appendWriter.writeRecords(uniqueNew);
                this.log('INFO', `✅ Wrote ${uniqueNew.length} new articles to CSV (Total unique: ${seenUrls.size})`);
            }
        };

        this.log('INFO', '========== Step 1: Getting total results for keyword ==========');
        const baseUrl = `https://www.sciencedirect.com/search?qs=${query}&date=${yearRange}&show=100`;
        const totalResults = await this.getTotalResults(baseUrl);
        this.log('INFO', `Total results for keyword "${keywordInput}": ${totalResults}`);

        if (totalResults > 0) {
            this.log('INFO', '========== Step 2: Scraping all pages for keyword (with offset +100) ==========');
            let offset = 0;
            let hasMoreResults = true;
            
            while (hasMoreResults && offset <= 900) {
                const url = `${baseUrl}&offset=${offset}`;
                this.log('INFO', `Scraping keyword page at offset ${offset}`);
                
                const results = await this.getArticleLinksFromPage(url);
                await writeResults(results);
                
                if (results.length < 100) {
                    this.log('INFO', `Got ${results.length} results (less than 100), stopping pagination`);
                    hasMoreResults = false;
                } else if (offset >= 900) {
                    this.log('WARNING', `Reached maximum offset of 900, stopping pagination for keyword`);
                    hasMoreResults = false;
                } else {
                    offset += 100;
                    await this.delay(2000);
                }
            }
        }

        this.log('INFO', '========== Step 3: Scraping by Article Types ==========');
        for (const articleType of this.articleTypes) {
            this.log('INFO', `Processing article type: ${articleType}`);
            
            const baseUrlWithFilter = `https://www.sciencedirect.com/search?qs=${query}&date=${yearRange}&show=100&articleTypes=${articleType}&lastSelectedFacet=articleTypes`;
            const totalResults = await this.getTotalResults(baseUrlWithFilter);
            
            this.log('INFO', `Total results for ${articleType}: ${totalResults}`);
            
            if (totalResults === 0) {
                this.log('INFO', `No results for article type ${articleType}, skipping`);
                continue;
            }

            let offset = 0;
            let hasMoreResults = true;
            
            while (hasMoreResults && offset <= 900) {
                const url = `${baseUrlWithFilter}&offset=${offset}`;
                this.log('INFO', `Scraping ${articleType} at offset ${offset}`);
                
                const results = await this.getArticleLinksFromPage(url);
                await writeResults(results);
                
                if (results.length < 100) {
                    hasMoreResults = false;
                } else if (offset >= 900) {
                    this.log('WARNING', `Reached maximum offset of 900 for ${articleType}`);
                    hasMoreResults = false;
                } else {
                    offset += 100;
                    await this.delay(2000);
                }
            }
        }

        this.log('INFO', '========== Step 4: Scraping by Publication Titles ==========');
        const publicationTitles = await this.extractPublicationTitles(keywordInput, yearRange);
        
        for (const pubTitle of publicationTitles.slice(0, 10)) {
            this.log('INFO', `Processing publication title: ${pubTitle}`);
            
            const baseUrlWithFilter = `https://www.sciencedirect.com/search?qs=${query}&date=${yearRange}&show=100&publicationTitles=${pubTitle}&lastSelectedFacet=publicationTitles`;
            const totalResults = await this.getTotalResults(baseUrlWithFilter);
            
            this.log('INFO', `Total results for publication ${pubTitle}: ${totalResults}`);
            
            if (totalResults === 0) {
                continue;
            }

            let offset = 0;
            let hasMoreResults = true;
            
            while (hasMoreResults && offset <= 900) {
                const url = `${baseUrlWithFilter}&offset=${offset}`;
                this.log('INFO', `Scraping publication ${pubTitle} at offset ${offset}`);
                
                const results = await this.getArticleLinksFromPage(url);
                await writeResults(results);
                
                if (results.length < 100) {
                    hasMoreResults = false;
                } else if (offset >= 900) {
                    this.log('WARNING', `Reached maximum offset of 900 for publication ${pubTitle}`);
                    hasMoreResults = false;
                } else {
                    offset += 100;
                    await this.delay(2000);
                }
            }
        }

        this.log('INFO', '========== Step 5: Scraping by Subject Areas ==========');
        const subjectAreas = await this.extractSubjectAreas(keywordInput, yearRange);
        
        for (const subjectArea of subjectAreas.slice(0, 10)) {
            this.log('INFO', `Processing subject area: ${subjectArea}`);
            
            const baseUrlWithFilter = `https://www.sciencedirect.com/search?qs=${query}&date=${yearRange}&show=100&subjectAreas=${subjectArea}&lastSelectedFacet=subjectAreas`;
            const totalResults = await this.getTotalResults(baseUrlWithFilter);
            
            this.log('INFO', `Total results for subject area ${subjectArea}: ${totalResults}`);
            
            if (totalResults === 0) {
                continue;
            }

            let offset = 0;
            let hasMoreResults = true;
            
            while (hasMoreResults && offset < 1000) {
                const url = `${baseUrlWithFilter}&offset=${offset}`;
                this.log('INFO', `Scraping subject ${subjectArea} at offset ${offset}`);
                
                const results = await this.getArticleLinksFromPage(url);
                await writeResults(results);
                
                if (results.length < 100) {
                    hasMoreResults = false;
                } else {
                    offset += 100;
                    await this.delay(2000);
                }
            }
        }

        this.log('INFO', `✅ SCRAPING COMPLETE! Total unique articles: ${seenUrls.size}`);
        this.log('INFO', `Saved to: ${csvFile}`);
        
        return csvFile;
    }

    async clickEnvelopes(keywords, yearRange, url, title, retries = 3) {
        for (let attempt = 1; attempt <= retries; attempt++) {
            try {
                const results = [];
                
                await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
                
                const rotated = await this.checkAndRotateUserAgent();
                if (rotated) {
                    await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
                }
                
                await this.delay(2000);

                try {
                    const pendoCloseButton = await this.page.$('#pendo-close-guide-bfad995f');
                    if (pendoCloseButton) {
                        await pendoCloseButton.click();
                        await this.delay(1500);
                    }
                } catch (e) {}

                try {
                    const closeButton = await this.page.$('#bdd-els-close');
                    if (closeButton) {
                        await closeButton.click();
                        await this.delay(1000);
                    }
                } catch (e) {}

                await this.page.waitForSelector('#banner', { timeout: 5000 });
                
                try {
                    await this.page.click('#show-more-btn');
                    await this.delay(1000);
                } catch (e) {}
                
                const authorButtons = await this.page.$$('.AuthorGroups .author-group button[data-sd-ui-side-panel-opener="true"][data-xocs-content-type="author"]');

                this.log('INFO', `Found ${authorButtons.length} author buttons`);

                if (authorButtons.length === 0) {
                    return results;
                }

                for (let i = 0; i < authorButtons.length; i++) {
                    try {
                        const buttons = await this.page.$$('svg[title="Author email or social media contact details icon"]');
                        
                        if (!buttons[i]) {
                            continue;
                        }
                        
                        await buttons[i].click();
                        await this.delay(2000);

                        await this.page.waitForSelector('#side-panel-author', { timeout: 5000 });

                        const emailExists = await this.page.$('#side-panel-author .e-address a').catch(() => null);

                        if (emailExists) {
                            const email = await this.page.evaluate(() => {
                                const emailEl = document.querySelector('#side-panel-author .e-address a');
                                return emailEl ? emailEl.textContent.trim() : null;
                            });

                            const givenName = await this.page.evaluate(() => {
                                const nameEl = document.querySelector('#side-panel-author .given-name');
                                return nameEl ? nameEl.textContent.trim() : '';
                            });

                            const surname = await this.page.evaluate(() => {
                                const surnameEl = document.querySelector('#side-panel-author .surname');
                                return surnameEl ? surnameEl.textContent.trim() : '';
                            });

                            const authorName = `${givenName} ${surname}`.trim();

                            if (email) {
                                results.push({
                                    runDate: new Date().toISOString().split('T')[0],
                                    keywordInput: keywords,
                                    yearRange: yearRange,
                                    url: url,
                                    email: email,
                                    name: authorName
                                });

                                this.log('INFO', `✅ Extracted email: ${email} for ${authorName}`);
                            }
                        }

                        try {
                            const closePanel = await this.page.$('#side-panel-author button[aria-label="Close"]');
                            if (closePanel) {
                                await closePanel.click();
                                await this.delay(500);
                            }
                        } catch (e) {}
                    } catch (e) {
                        this.log('WARNING', `Error extracting info from author ${i + 1}: ${e.message}`);
                    }
                }

                return results;
            } catch (error) {
                this.log('ERROR', `Error in clickEnvelopes (attempt ${attempt}/${retries}): ${error.message}`);
                
                if (attempt < retries) {
                    this.log('INFO', `Retrying after browser restart...`);
                    await this.restartBrowser();
                } else {
                    return [];
                }
            }
        }
        return [];
    }

    async extractEmails(csvFilePath, keywords, yearRange, keywordDir) {
        const writeFilePath = path.join(keywordDir, `emails_${yearRange}.csv`);

        if (fsSync.existsSync(writeFilePath)) {
            fsSync.unlinkSync(writeFilePath);
        }

        const csvWriter = createObjectCsvWriter({
            path: writeFilePath,
            header: [
                { id: 'runDate', title: 'Run_Date' },
                { id: 'keywordInput', title: 'Keyword_input' },
                { id: 'yearRange', title: 'Year_Range' },
                { id: 'url', title: 'URLs' },
                { id: 'email', title: 'emails' },
                { id: 'name', title: 'names' }
            ],
            append: false
        });

        await csvWriter.writeRecords([]);

        let count = 0;

        const stream = fsSync.createReadStream(csvFilePath).pipe(csv());

        for await (const row of stream) {
            try {
                if (!row.url || row.url === 'undefined') {
                    this.log('WARNING', `Skipping invalid URL at row ${count + 1}`);
                    count++;
                    continue;
                }

                this.log('INFO', `Processing article ${++count}: ${row.url}`);
                
                const results = await this.clickEnvelopes(keywords, yearRange, row.url, row.title);
                
                if (results.length > 0) {
                    const appendWriter = createObjectCsvWriter({
                        path: writeFilePath,
                        header: [
                            { id: 'runDate', title: 'Run_Date' },
                            { id: 'keywordInput', title: 'Keyword_input' },
                            { id: 'yearRange', title: 'Year_Range' },
                            { id: 'url', title: 'URLs' },
                            { id: 'email', title: 'emails' },
                            { id: 'name', title: 'names' }
                        ],
                        append: true
                    });
                    await appendWriter.writeRecords(results);
                    this.log('INFO', `✅ Wrote ${results.length} emails to CSV`);
                }
                
                await this.delay(1000);
            } catch (error) {
                this.log('ERROR', `Error processing article: ${error.message}`);
            }
        }

        this.log('INFO', `✅ Email extraction completed. Saved to ${writeFilePath}`);
    }

    async close() {
        if (this.browser) {
            await this.browser.close();
            this.log('INFO', 'Browser closed');
        }
    }
}

function getUserInput(question) {
    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout
    });

    return new Promise(resolve => {
        rl.question(question, answer => {
            rl.close();
            resolve(answer);
        });
    });
}

function validateYearRange(yearRange) {
    const singleYearPattern = /^\d{4}$/;
    const rangePattern = /^\d{4}-\d{4}$/;
    
    if (singleYearPattern.test(yearRange)) {
        return true;
    }
    
    if (rangePattern.test(yearRange)) {
        const [startYear, endYear] = yearRange.split('-').map(Number);
        return startYear <= endYear;
    }
    
    return false;
}

function sanitizeKeyword(keyword) {
    return keyword.replace(/[<>:"/\\|?*]/g, '_').trim();
}

async function main() {
    const scraper = new ScienceDirectScraper();
    
    try {
        console.log('\n=== ScienceDirect Scraper with Enhanced Features ===\n');
        
        // Get keyword input
        const keyword = await getUserInput('Enter search keyword (e.g., "Bioinformatics"): ');
        if (!keyword.trim()) {
            console.error('Error: Keyword cannot be empty');
            process.exit(1);
        }
        
        // Get year range input with validation
        let yearRange;
        let isValidYear = false;
        while (!isValidYear) {
            yearRange = await getUserInput('Enter year or year range (e.g., "2018" or "2017-2025"): ');
            if (validateYearRange(yearRange)) {
                isValidYear = true;
            } else {
                console.log('Invalid year format. Please use YYYY or YYYY-YYYY format.');
            }
        }
        
        // Create output directory structure
        const sanitizedKeyword = sanitizeKeyword(keyword);
        const keywordDir = path.join('output', sanitizedKeyword);
        
        if (!fsSync.existsSync('output')) {
            fsSync.mkdirSync('output');
            console.log('Created output directory');
        }
        
        if (!fsSync.existsSync(keywordDir)) {
            fsSync.mkdirSync(keywordDir, { recursive: true });
            console.log(`Created directory: ${keywordDir}`);
        }
        
        // Initialize log file
        scraper.initializeLog(keywordDir);
        
        // Check if articles CSV exists
        const articlesCSVPath = path.join(keywordDir, `articles_${yearRange}.csv`);
        const articlesExist = fsSync.existsSync(articlesCSVPath);
        
        let extractNewLinks = true;
        
        if (articlesExist) {
            console.log(`\nFound existing articles file: ${articlesCSVPath}`);
            const extractNewInput = await getUserInput('Extract new article links? (y/n): ');
            extractNewLinks = extractNewInput.toLowerCase() === 'y' || extractNewInput.toLowerCase() === 'yes';
        }
        
        let csvFile = articlesCSVPath;
        
        if (extractNewLinks || !articlesExist) {
            console.log('\nInitializing browser...');
            await scraper.initialize(false);
            
            console.log('Loading homepage (with 30 second delay for cookies/popups)...');
            await scraper.landFirstPage();
            
            console.log(`\nSearching for: "${keyword}" in year range: ${yearRange}`);
            
            csvFile = await scraper.scrapeWithFacetFilters(keyword, yearRange, keywordDir);
            
            console.log('\n✅ Article links extraction completed!');
        } else {
            console.log('\nSkipping article link extraction, using existing file.');
            
            // Still need to initialize browser for email extraction
            console.log('\nInitializing browser for email extraction...');
            await scraper.initialize(false);
            
            console.log('Loading homepage (with 30 second delay for cookies/popups)...');
            await scraper.landFirstPage();
        }
        
        // Ask about email extraction
        const extractEmailsInput = await getUserInput('\nDo you want to extract author emails? (y/n): ');
        const extractEmails = extractEmailsInput.toLowerCase() === 'y' || extractEmailsInput.toLowerCase() === 'yes';
        
        if (extractEmails) {
            console.log('\nExtracting author emails...');
            await scraper.extractEmails(csvFile, keyword, yearRange, keywordDir);
            console.log('\n✅ Email extraction completed!');
        }

        console.log('\n✅ All operations completed successfully!');
        console.log(`\nOutput files saved in: ${keywordDir}`);
        
    } catch (error) {
        console.error('❌ Error in main execution:', error);
    } finally {
        console.log('\nClosing browser...');
        await scraper.close();
    }
}

module.exports = ScienceDirectScraper;


if (process.argv[1] === __filename) {
    console.log('Starting ScienceDirect scraper...');
    main().catch(console.error);
}
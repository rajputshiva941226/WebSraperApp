#!/usr/bin/env node

// import puppeteer from 'puppeteer-extra';
// import StealthPlugin from 'puppeteer-extra-plugin-stealth';
// import fs from 'fs/promises';
// import fsSync from 'fs';
// import path from 'path';
// import { createObjectCsvWriter } from 'csv-writer';
// import csv from 'csv-parser';
// import { fileURLToPath } from 'url';
// import readline from 'readline';

// // Use stealth plugin to avoid detection
// puppeteer.use(StealthPlugin());

// class ScienceDirectScraper {
//     constructor() {
//         this.browser = null;
//         this.page = null;
//         this.logFile = 'scraper_log_file.log';
//         this.currentUserAgentIndex = 0;
//         this.userAgents = [
//             'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
//             'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
//             'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
//             'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
//             'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
//             'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
//         ];
//         this.blockedUserAgent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36';
//         this.initializeLog();
//     }

//     // Helper function to wait/delay
//     async delay(ms) {
//         return new Promise(resolve => setTimeout(resolve, ms));
//     }

//     initializeLog() {
//         if (fsSync.existsSync(this.logFile)) {
//             fsSync.unlinkSync(this.logFile);
//         }
//         fsSync.writeFileSync(this.logFile, 'Log initialized\n');
//         console.log('Log file created');
//     }

//     log(level, message) {
//         const timestamp = new Date().toISOString();
//         const logMessage = `${timestamp} - ${level} - ${message}\n`;
//         fsSync.appendFileSync(this.logFile, logMessage);
//         console.log(logMessage.trim());
//     }

//     getNextUserAgent() {
//         const userAgent = this.userAgents[this.currentUserAgentIndex];
//         this.currentUserAgentIndex = (this.currentUserAgentIndex + 1) % this.userAgents.length;
//         return userAgent;
//     }

//     async handleCookiesAndPopups() {
//         try {
//             // Handle cookie consent banner
//             this.log('INFO', 'Checking for cookie banner...');
//             try {
//                 const cookieButton = await this.page.waitForSelector('#onetrust-accept-btn-handler', { timeout: 5000 });
//                 if (cookieButton) {
//                     await cookieButton.click();
//                     this.log('INFO', '✅ Accepted cookies');
//                     await this.delay(2000);
//                 }
//             } catch (e) {
//                 this.log('INFO', 'No cookie banner found or already accepted');
//             }
            
//             // Handle the Pendo guide popup (ScienceDirect AI popup)
//             this.log('INFO', 'Checking for AI popup...');
//             try {
//                 const closeButton = await this.page.$("._pendo-close-guide");
//                 if (closeButton) {
//                     await closeButton.click();
//                     this.log('INFO', '✅ Closed AI popup');
//                     await this.delay(1000);
//                 }
//             } catch (e) {
//                 this.log('INFO', 'No AI popup found');
//             }

//             // Handle alternate AI popup
//             try {
//                 const pendoCloseButton = await this.page.$('#pendo-close-guide-bfad995f');
//                 if (pendoCloseButton) {
//                     await pendoCloseButton.click();
//                     this.log('INFO', '✅ Closed Science Direct AI popup');
//                     await this.delay(1000);
//                 }
//             } catch (e) {
//                 // No popup
//             }

//             // Handle institute login popup
//             try {
//                 const closeButton = await this.page.$('#bdd-els-close');
//                 if (closeButton) {
//                     await closeButton.click();
//                     this.log('INFO', '✅ Closed institution popup');
//                     await this.delay(1000);
//                 }
//             } catch (e) {
//                 // No popup
//             }
//         } catch (error) {
//             this.log('ERROR', `Error handling cookies/popups: ${error.message}`);
//         }
//     }

//     async checkAndRotateUserAgent() {
//         try {
//             // Check if the page has the userAgent element (bot detection page)
//             const userAgentElement = await this.page.$('#userAgent').catch(() => null);
            
//             if (userAgentElement) {
//                 const userAgentText = await this.page.$eval('#userAgent', el => el.textContent).catch(() => '');
//                 this.log('WARNING', `⚠️ BOT DETECTION PAGE DETECTED!`);
//                 this.log('WARNING', `Detected User Agent on page: ${userAgentText}`);
                
//                 // Extract the actual UA string (remove "User Agent: " prefix)
//                 const uaMatch = userAgentText.match(/User Agent:\s*(.+)/);
//                 const actualUA = uaMatch ? uaMatch[1].trim() : userAgentText;
                
//                 this.log('WARNING', `Parsed UA: ${actualUA}`);
//                 this.log('WARNING', '🔄 Rotating to new User Agent and restarting browser...');
                
//                 // Close current browser
//                 await this.close();
                
//                 // Wait a bit before reconnecting
//                 await this.delay(3000);
                
//                 // Reinitialize with new user agent
//                 await this.initialize(false);
                
//                 // Navigate to homepage to handle cookies and popups
//                 this.log('INFO', 'Loading homepage with new session...');
//                 await this.page.goto('https://www.sciencedirect.com/', {
//                     waitUntil: 'networkidle2',
//                     timeout: 60000
//                 });
                
//                 // Handle cookies and popups in the new session
//                 await this.handleCookiesAndPopups();
                
//                 this.log('INFO', '✅ Successfully rotated to new User Agent and handled popups');
//                 return true;
//             }
            
//             return false;
//         } catch (error) {
//             this.log('ERROR', `Error checking User Agent: ${error.message}`);
//             return false;
//         }
//     }

//     async initialize(headless = false) {
//         try {
//             // Try to find Chrome executable
//             const chromePaths = [
//                 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
//                 'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
//                 process.env.CHROME_PATH,
//             ].filter(Boolean);

//             let executablePath = null;
//             for (const chromePath of chromePaths) {
//                 if (fsSync.existsSync(chromePath)) {
//                     executablePath = chromePath;
//                     console.log(`Found Chrome at: ${chromePath}`);
//                     break;
//                 }
//             }

//             const launchOptions = {
//                 headless: headless ? 'new' : false,
//                 args: [
//                     '--no-sandbox',
//                     '--disable-setuid-sandbox',
//                     '--disable-dev-shm-usage',
//                     '--disable-accelerated-2d-canvas',
//                     '--disable-gpu',
//                     '--start-maximized',
//                     '--disable-blink-features=AutomationControlled',
//                     '--disable-infobars',
//                     '--disable-notifications',
//                     '--disable-popup-blocking',
//                     '--disable-web-security',
//                     '--disable-features=IsolateOrigins,site-per-process'
//                 ],
//                 defaultViewport: null,
//                 ignoreHTTPSErrors: true,
//                 timeout: 60000
//             };

//             // Add executablePath if found, otherwise let Puppeteer download Chromium
//             if (executablePath) {
//                 launchOptions.executablePath = executablePath;
//             } else {
//                 console.log('Chrome not found, Puppeteer will use bundled Chromium');
//             }

//             this.browser = await puppeteer.launch(launchOptions);

//             this.page = await this.browser.newPage();
            
//             // Set user agent - get next one from rotation
//             const userAgent = this.getNextUserAgent();
//             await this.page.setUserAgent(userAgent);
//             this.log('INFO', `Set User Agent: ${userAgent}`);

//             // Additional stealth measures
//             await this.page.evaluateOnNewDocument(() => {
//                 Object.defineProperty(navigator, 'webdriver', {
//                     get: () => false,
//                 });
//             });

//             this.log('INFO', 'Browser initialized successfully');
//         } catch (error) {
//             this.log('ERROR', `Failed to initialize browser: ${error.message}`);
//             throw error;
//         }
//     }

//     async landFirstPage() {
//         try {
//             await this.page.goto('https://www.sciencedirect.com/', {
//                 waitUntil: 'networkidle2',
//                 timeout: 60000
//             });
            
//             // Check for User Agent rotation
//             await this.checkAndRotateUserAgent();
            
//             this.log('INFO', 'Landed on ScienceDirect homepage');
            
//             // Handle cookies and popups
//             await this.handleCookiesAndPopups();
            
//         } catch (error) {
//             this.log('ERROR', `Failed to load homepage: ${error.message}`);
//             throw error;
//         }
//     }

//     async getNextLinks(keywordInput, year, offset = 0) {
//         try {
//             const query = keywordInput.replace(/ /g, '%20');
//             const showPages = 100;
//             const url = `https://www.sciencedirect.com/search?qs=${query}&show=${showPages}&date=${year}&offset=${offset}`;

//             this.log('INFO', `Navigating to: ${url}`);
//             await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });

//             // Check for User Agent rotation
//             const rotated = await this.checkAndRotateUserAgent();
//             if (rotated) {
//                 // If we rotated, need to navigate again
//                 await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
//             }

//             // Wait a bit for page to load
//             await this.delay(3000);

//             // Check for errors or zero results
//             const hasZeroResults = await this.page.$('.error-zero-results').catch(() => null);
//             const hasError400 = await this.page.$('.error-400').catch(() => null);

//             if (hasZeroResults || hasError400) {
//                 this.log('WARNING', 'No results found or error 400');
//                 return null;
//             }

//             // Close institute login popup if present
//             try {
//                 const closeButton = await this.page.$('#bdd-els-close');
//                 if (closeButton) {
//                     await closeButton.click();
//                     await this.delay(1000);
//                 }
//             } catch (e) {
//                 // Popup not present
//             }

//             // Get total results from the page
//             const totalResults = await this.page.$eval(
//                 'h1.text-l .search-body-results-text',
//                 el => el.textContent.trim()
//             ).catch(() => null);

//             if (!totalResults) {
//                 this.log('WARNING', 'Could not find total results');
//                 return null;
//             }

//             this.log('INFO', `Found: ${totalResults}`);
//             return totalResults;
//         } catch (error) {
//             this.log('ERROR', `Failed to get next links: ${error.message}`);
//             return null;
//         }
//     }

//     getTotalPages(resultsText) {
//         if (!resultsText) return null;
        
//         // Extract number from "537,095 results"
//         const match = resultsText.match(/[\d,]+/);
//         if (!match) return null;
        
//         const totalResults = parseInt(match[0].replace(/,/g, ''));
//         const totalPages = Math.floor(totalResults / 100) + 1;
        
//         this.log('INFO', `Total results: ${totalResults}, Total pages: ${totalPages}`);
//         return totalPages;
//     }

//     getOffsetValues(totalPages, maxPages = 10) {
//         if (!totalPages) return null;
        
//         // Limit to maxPages or totalPages, whichever is smaller
//         const pagesToScrape = Math.min(totalPages, maxPages);
//         const offsets = Array.from({ length: pagesToScrape }, (_, i) => i * 100);
        
//         this.log('INFO', `Will scrape ${pagesToScrape} pages with offsets: ${offsets}`);
//         return offsets;
//     }

//     async getArticleLinks(keywordInput, yearRange, offset) {
//         try {
//             const query = keywordInput.replace(/ /g, '%20');
//             const showPages = 100;
//             const url = `https://www.sciencedirect.com/search?qs=${query}&show=${showPages}&date=${yearRange}&offset=${offset}`;

//             this.log('INFO', `Scraping page at offset ${offset}`);
//             await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
            
//             // Check for User Agent rotation
//             const rotated = await this.checkAndRotateUserAgent();
//             if (rotated) {
//                 await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
//             }
            
//             await this.delay(2000);

//             // Close popup if present
//             try {
//                 const closeButton = await this.page.$('#bdd-els-close');
//                 if (closeButton) {
//                     await closeButton.click();
//                     await this.delay(1000);
//                 }
//             } catch (e) {
//                 // No popup
//             }

//             // Wait for results to load
//             await this.page.waitForSelector('#srp-results-list', { timeout: 10000 });
            
//             // Extract article links using the correct selector
//             const results = await this.page.$$eval(
//                 '#srp-results-list .result-list-title-link',
//                 links => links.map(link => ({
//                     url: link.href,
//                     title: link.textContent.trim()
//                 }))
//             );

//             this.log('INFO', `Extracted ${results.length} articles from offset ${offset}`);
//             return results;
//         } catch (error) {
//             this.log('ERROR', `Failed to get article links at offset ${offset}: ${error.message}`);
//             return [];
//         }
//     }

//     async scrapeAllPages(keywordInput, yearRange) {
//         try {
//             // First, get total pages
//             const resultsText = await this.getNextLinks(keywordInput, yearRange, 0);
//             if (!resultsText) {
//                 this.log('ERROR', 'No results found');
//                 return null;
//             }

//             const totalPages = this.getTotalPages(resultsText);
//             const offsets = this.getOffsetValues(totalPages, 10); // Scrape first 10 pages

//             const fileName = keywordInput.replace(/"/g, '').replace(/\s+/g, '_');
//             const csvFile = `${fileName}_${yearRange}_articles.csv`;

//             // Remove existing file
//             if (fsSync.existsSync(csvFile)) {
//                 fsSync.unlinkSync(csvFile);
//             }

//             const csvWriter = createObjectCsvWriter({
//                 path: csvFile,
//                 header: [
//                     { id: 'url', title: 'url' },
//                     { id: 'title', title: 'Title' }
//                 ]
//             });

//             let allResults = [];

//             // Scrape each page
//             for (const offset of offsets) {
//                 const results = await this.getArticleLinks(keywordInput, yearRange, offset);
//                 allResults.push(...results);
                
//                 // Add a delay between requests
//                 await this.delay(2000);
//             }

//             // Remove duplicates
//             const uniqueResults = [];
//             const seenUrls = new Set();
            
//             for (const result of allResults) {
//                 if (!seenUrls.has(result.url)) {
//                     seenUrls.add(result.url);
//                     uniqueResults.push(result);
//                 }
//             }

//             await csvWriter.writeRecords(uniqueResults);
            
//             this.log('INFO', `Saved ${uniqueResults.length} unique articles to ${csvFile}`);
//             return csvFile;
//         } catch (error) {
//             this.log('ERROR', `Failed to scrape pages: ${error.message}`);
//             throw error;
//         }
//     }

//     async clickEnvelopes(keywords, yearRange, url, title) {
//         const results = [];
        
//         try {
//             await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
            
//             // Check for User Agent rotation
//             const rotated = await this.checkAndRotateUserAgent();
//             if (rotated) {
//                 await this.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
//             }
            
//             await this.delay(2000);

//             // Close Science Direct AI popup if present
//             try {
//                 const pendoCloseButton = await this.page.$('#pendo-close-guide-bfad995f');
//                 if (pendoCloseButton) {
//                     await pendoCloseButton.click();
//                     this.log('INFO', 'Closed Science Direct AI popup');
//                     await this.delay(1500);
//                 }
//             } catch (e) {
//                 this.log('INFO', 'No Science Direct AI popup found');
//             }

//             await this.page.waitForSelector('#banner', { timeout: 5000 });
            
//             // Click "Show more" button if present
//             try {
//                 await this.page.click('#show-more-btn');
//                 await this.delay(1000);
//             } catch (e) {
//                 // Show more button not present
//             }
            
//             // Get all author buttons from the AuthorGroups section
//             const authorButtons = await this.page.$$('.AuthorGroups .author-group button[data-sd-ui-side-panel-opener="true"][data-xocs-content-type="author"]');

//             this.log('INFO', `Found ${authorButtons.length} author buttons`);

//             if (authorButtons.length === 0) {
//                 this.log('WARNING', 'No author buttons found on this page');
//                 return results;
//             }

//             // Click each author button and check for email
//             for (let i = 0; i < authorButtons.length; i++) {
//                 try {
//                     // Re-query the buttons to avoid stale element references
//                     const buttons = await this.page.$$('svg[title="Author email or social media contact details icon"]');
                    
//                     if (!buttons[i]) {
//                         this.log('WARNING', `Author button ${i + 1} not found (stale reference)`);
//                         continue;
//                     }
                    
//                     await buttons[i].click();
//                     this.log('INFO', `Clicked author button ${i + 1}`);
//                     await this.delay(2000);

//                     // Wait for side panel to open
//                     await this.page.waitForSelector('#side-panel-author', { timeout: 5000 });

//                     // Check if email exists
//                     const emailExists = await this.page.$('#side-panel-author .e-address a').catch(() => null);

//                     if (emailExists) {
//                         // Extract email
//                         const email = await this.page.$eval(
//                             '#side-panel-author .e-address a',
//                             el => el.textContent.trim()
//                         ).catch(() => null);

//                         // Extract given name
//                         const givenName = await this.page.$eval(
//                             '#side-panel-author .given-name',
//                             el => el.textContent.trim()
//                         ).catch(() => '');

//                         // Extract surname
//                         const surname = await this.page.$eval(
//                             '#side-panel-author .surname',
//                             el => el.textContent.trim()
//                         ).catch(() => '');

//                         const authorName = `${givenName} ${surname}`.trim();

//                         if (email) {
//                             results.push({
//                                 runDate: new Date().toISOString().split('T')[0],
//                                 keywordInput: keywords,
//                                 yearRange: yearRange,
//                                 url: url,
//                                 email: email,
//                                 name: authorName
//                             });

//                             this.log('INFO', `Extracted email: ${email} for ${authorName}`);
//                         }
//                     } else {
//                         this.log('INFO', `No email found for author ${i + 1}`);
//                     }

//                     // Close the side panel before clicking next author
//                     try {
//                         const closePanel = await this.page.$('#side-panel-author button[aria-label="Close"]');
//                         if (closePanel) {
//                             await closePanel.click();
//                             await this.delay(500);
//                         }
//                     } catch (e) {
//                         // Try alternate close button selector
//                         try {
//                             const closePanelAlt = await this.page.$('#side-panel-author .close-button');
//                             if (closePanelAlt) {
//                                 await closePanelAlt.click();
//                                 await this.delay(500);
//                             }
//                         } catch (e2) {
//                             this.log('WARNING', 'Could not close side panel');
//                         }
//                     }
//                 } catch (e) {
//                     this.log('WARNING', `Error extracting info from author ${i + 1}: ${e.message}`);
                    
//                     // Try to close panel if it's open
//                     try {
//                         const closePanel = await this.page.$('#side-panel-author button[aria-label="Close"]');
//                         if (closePanel) {
//                             await closePanel.click();
//                             await this.delay(500);
//                         }
//                     } catch (e2) {
//                         // Ignore
//                     }
//                 }
//             }
//         } catch (error) {
//             this.log('ERROR', `Error in clickEnvelopes: ${error.message}`);
//         }

//         return results;
//     }

//     async extractEmails(csvFilePath, keywords, yearRange) {
//         const fileName = keywords.replace(/"/g, '').replace(/\s+/g, '_');
//         const writeFilePath = `${fileName}_${yearRange}_emails.csv`;

//         const csvWriter = createObjectCsvWriter({
//             path: writeFilePath,
//             header: [
//                 { id: 'runDate', title: 'Run_Date' },
//                 { id: 'keywordInput', title: 'Keyword_input' },
//                 { id: 'yearRange', title: 'Year_Range' },
//                 { id: 'url', title: 'URLs' },
//                 { id: 'email', title: 'emails' },
//                 { id: 'name', title: 'names' }
//             ]
//         });

//         const emailRecords = [];
//         let count = 0;

//         const stream = fsSync.createReadStream(csvFilePath)
//             .pipe(csv());

//         for await (const row of stream) {
//             try {
//                 this.log('INFO', `Processing article ${++count}: ${row.url}`);
                
//                 const results = await this.clickEnvelopes(keywords, yearRange, row.url, row.title);
//                 emailRecords.push(...results);
                
//                 // Add delay between articles
//                 await this.delay(1000);
//             } catch (error) {
//                 this.log('ERROR', `Error processing article: ${error.message}`);
//             }
//         }

//         await csvWriter.writeRecords(emailRecords);
//         this.log('INFO', `Email extraction completed. Saved to ${writeFilePath}`);
//     }

//     async close() {
//         if (this.browser) {
//             await this.browser.close();
//             this.log('INFO', 'Browser closed');
//         }
//     }
// }

// // Helper function to get user input
// function getUserInput(question) {
//     const rl = readline.createInterface({
//         input: process.stdin,
//         output: process.stdout
//     });

//     return new Promise(resolve => {
//         rl.question(question, answer => {
//             rl.close();
//             resolve(answer);
//         });
//     });
// }

// // Main execution function
// async function main() {
//     const scraper = new ScienceDirectScraper();
    
//     try {
//         // Get user inputs
//         console.log('\n=== ScienceDirect Scraper ===\n');
        
//         const keyword = await getUserInput('Enter search keyword (e.g., "cancer research"): ');
//         const yearRange = await getUserInput('Enter year range (e.g., "2020-2023" or "2023"): ');
//         const extractEmails = await getUserInput('Do you want to extract author emails? (yes/no): ');

//         console.log('\nInitializing browser...');
//         await scraper.initialize(false); // Set to true for headless mode
        
//         console.log('Loading homepage...');
//         await scraper.landFirstPage();
        
//         console.log(`\nSearching for: "${keyword}" in year range: ${yearRange}`);
        
//         // Scrape article links
//         const csvFile = await scraper.scrapeAllPages(keyword, yearRange);
        
//         if (!csvFile) {
//             console.log('No results found. Exiting...');
//             await scraper.close();
//             return;
//         }

//         console.log(`\nArticle links saved to: ${csvFile}`);

//         // Extract emails if requested
//         if (extractEmails.toLowerCase() === 'yes' || extractEmails.toLowerCase() === 'y') {
//             console.log('\nExtracting author emails...');
//             await scraper.extractEmails(csvFile, keyword, yearRange);
//         }

//         console.log('\n✅ Scraping completed successfully!');
//     } catch (error) {
//         console.error('❌ Error in main execution:', error);
//     } finally {
//         console.log('\nClosing browser...');
//         await scraper.close();
//     }
// }

// // Export for use as module
// export default ScienceDirectScraper;

// // Run if executed directly
// const __filename = fileURLToPath(import.meta.url);
// const __dirname = path.dirname(__filename);

// // Check if this file is being run directly
// if (process.argv[1] === __filename) {
//     console.log('Starting ScienceDirect scraper...');
//     main().catch(console.error);
// }


import puppeteer from 'puppeteer-extra';
import StealthPlugin from 'puppeteer-extra-plugin-stealth';
import fs from 'fs/promises';
import fsSync from 'fs';
import path from 'path';
import { createObjectCsvWriter } from 'csv-writer';
import csv from 'csv-parser';
import { fileURLToPath } from 'url';
import readline from 'readline';
import os from 'os';

puppeteer.use(StealthPlugin());

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

export default ScienceDirectScraper;

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

if (process.argv[1] === __filename) {
    console.log('Starting ScienceDirect scraper...');
    main().catch(console.error);
}
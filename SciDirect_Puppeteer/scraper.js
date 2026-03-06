// var puppeteer = require('puppeteer-core');
// var fsSync = require('fs');
// var path = require('path');
// var csvWriter = require('csv-writer');
// var csv = require('csv-parser');
// var os = require('os');
// var readline = require('readline');

// var createObjectCsvWriter = csvWriter.createObjectCsvWriter;

// function ScienceDirectScraper() {
//     this.browser = null;
//     this.page = null;
//     this.logFile = null;
//     this.outputDir = 'output';
//     this.currentUserAgentIndex = 0;
//     this.userAgents = [
//         'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
//         'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
//         'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
//         'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
//         'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0'
//     ];
//     this.articleTypes = ['REV', 'FLA', 'DAT', 'CH'];
// }

// ScienceDirectScraper.prototype.delay = function(ms) {
//     return new Promise(function(resolve) {
//         setTimeout(resolve, ms);
//     });
// };

// ScienceDirectScraper.prototype.initializeLog = function(keywordDir) {
//     this.logFile = path.join(keywordDir, 'scraper_log.log');
//     if (fsSync.existsSync(this.logFile)) {
//         fsSync.unlinkSync(this.logFile);
//     }
//     fsSync.writeFileSync(this.logFile, 'Log initialized at ' + new Date().toISOString() + '\n');
//     console.log('Log file created at: ' + this.logFile);
// };

// ScienceDirectScraper.prototype.log = function(level, message) {
//     var timestamp = new Date().toISOString();
//     var logMessage = timestamp + ' - ' + level + ' - ' + message + '\n';
//     if (this.logFile) {
//         fsSync.appendFileSync(this.logFile, logMessage);
//     }
//     console.log(logMessage.trim());
// };

// ScienceDirectScraper.prototype.getNextUserAgent = function() {
//     var userAgent = this.userAgents[this.currentUserAgentIndex];
//     this.currentUserAgentIndex = (this.currentUserAgentIndex + 1) % this.userAgents.length;
//     return userAgent;
// };

// ScienceDirectScraper.prototype.findChromePath = function() {
//     var self = this;
//     var platform = os.platform();
//     var possiblePaths = [];

//     if (platform === 'win32') {
//         possiblePaths = [
//             'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
//             'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
//             path.join(os.homedir(), 'AppData\\Local\\Google\\Chrome\\Application\\chrome.exe'),
//             process.env.CHROME_PATH,
//             process.env.CHROME_BIN
//         ];
//     } else if (platform === 'darwin') {
//         possiblePaths = [
//             '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
//             path.join(os.homedir(), 'Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
//             process.env.CHROME_PATH,
//             process.env.CHROME_BIN
//         ];
//     } else if (platform === 'linux') {
//         possiblePaths = [
//             '/usr/bin/google-chrome',
//             '/usr/bin/google-chrome-stable',
//             '/usr/bin/chromium-browser',
//             '/usr/bin/chromium',
//             '/snap/bin/chromium',
//             process.env.CHROME_PATH,
//             process.env.CHROME_BIN
//         ];
//     }

//     for (var i = 0; i < possiblePaths.length; i++) {
//         var chromePath = possiblePaths[i];
//         if (chromePath && fsSync.existsSync(chromePath)) {
//             self.log('INFO', 'Found Chrome at: ' + chromePath);
//             return chromePath;
//         }
//     }

//     self.log('ERROR', 'Chrome not found! Please install Google Chrome.');
//     return null;
// };

// ScienceDirectScraper.prototype.handleCookiesAndPopups = async function() {
//     var self = this;
//     try {
//         self.log('INFO', 'Starting cookie and popup handling with 30 second delay...');
//         await self.delay(30000);

//         try {
//             var cookieButton = await self.page.waitForSelector('#onetrust-accept-btn-handler', { timeout: 5000 });
//             if (cookieButton) {
//                 await cookieButton.click();
//                 self.log('INFO', 'Accepted cookies');
//                 await self.delay(2000);
//             }
//         } catch (e) {
//             self.log('INFO', 'No cookie banner found or already accepted');
//         }
        
//         try {
//             var closeButton = await self.page.$('._pendo-close-guide');
//             if (closeButton) {
//                 await closeButton.click();
//                 self.log('INFO', 'Closed AI popup');
//                 await self.delay(1000);
//             }
//         } catch (e) {}

//         try {
//             var pendoCloseButton = await self.page.$('#pendo-close-guide-bfad995f');
//             if (pendoCloseButton) {
//                 await pendoCloseButton.click();
//                 self.log('INFO', 'Closed Science Direct AI popup');
//                 await self.delay(1000);
//             }
//         } catch (e) {}

//         try {
//             var instCloseButton = await self.page.$('#bdd-els-close');
//             if (instCloseButton) {
//                 await instCloseButton.click();
//                 self.log('INFO', 'Closed institution popup');
//                 await self.delay(1000);
//             }
//         } catch (e) {}
//     } catch (error) {
//         self.log('ERROR', 'Error handling cookies/popups: ' + error.message);
//     }
// };

// ScienceDirectScraper.prototype.checkAndRotateUserAgent = async function() {
//     var self = this;
//     try {
//         var pageContent = '';
//         try {
//             pageContent = await self.page.content();
//         } catch (e) {
//             pageContent = '';
//         }
        
//         var isBotPage = pageContent.indexOf('User Agent:') !== -1;
        
//         if (isBotPage) {
//             self.log('WARNING', 'BOT DETECTION PAGE DETECTED!');
//             self.log('WARNING', 'Closing browser and restarting with new User Agent...');
            
//             if (self.browser) {
//                 try {
//                     await self.browser.close();
//                     self.log('INFO', 'Browser closed successfully');
//                 } catch (e) {
//                     self.log('WARNING', 'Error closing browser: ' + e.message);
//                 }
//                 self.browser = null;
//                 self.page = null;
//             }
            
//             self.log('INFO', 'Waiting 5 seconds before restarting...');
//             await self.delay(5000);
            
//             self.log('INFO', 'Initializing new browser session...');
//             await self.initialize(false);
            
//             self.log('INFO', 'Loading homepage with new session...');
//             await self.page.goto('https://www.sciencedirect.com/', {
//                 waitUntil: 'networkidle2',
//                 timeout: 30000
//             });
            
//             await self.handleCookiesAndPopups();
            
//             self.log('INFO', 'Successfully rotated to new User Agent');
//             return true;
//         }
        
//         return false;
//     } catch (error) {
//         self.log('ERROR', 'Error checking User Agent: ' + error.message);
//         return false;
//     }
// };

// ScienceDirectScraper.prototype.initialize = async function(headless) {
//     var self = this;
//     headless = headless || false;
    
//     try {
//         var executablePath = self.findChromePath();

//         if (!executablePath) {
//             throw new Error('Chrome executable not found. Please install Google Chrome.');
//         }

//         var launchOptions = {
//             headless: headless ? 'new' : false,
//             executablePath: executablePath,
//             args: [
//                 '--no-sandbox',
//                 '--disable-setuid-sandbox',
//                 '--disable-dev-shm-usage',
//                 '--disable-accelerated-2d-canvas',
//                 '--disable-gpu',
//                 '--start-maximized',
//                 '--disable-blink-features=AutomationControlled',
//                 '--disable-infobars',
//                 '--disable-notifications',
//                 '--disable-popup-blocking'
//             ],
//             defaultViewport: null,
//             ignoreHTTPSErrors: true,
//             timeout: 60000
//         };

//         self.browser = await puppeteer.launch(launchOptions);
//         self.page = await self.browser.newPage();
        
//         var userAgent = self.getNextUserAgent();
//         await self.page.setUserAgent(userAgent);
//         self.log('INFO', 'Set User Agent: ' + userAgent);

//         // Use string-based evaluateOnNewDocument for pkg compatibility
//         await self.page.evaluateOnNewDocument('Object.defineProperty(navigator, "webdriver", { get: function() { return false; } });');

//         self.log('INFO', 'Browser initialized successfully');
//     } catch (error) {
//         self.log('ERROR', 'Failed to initialize browser: ' + error.message);
//         throw error;
//     }
// };

// ScienceDirectScraper.prototype.landFirstPage = async function() {
//     var self = this;
//     try {
//         await self.page.goto('https://www.sciencedirect.com/', {
//             waitUntil: 'networkidle2',
//             timeout: 30000
//         });
        
//         await self.checkAndRotateUserAgent();
//         self.log('INFO', 'Landed on ScienceDirect homepage');
//         await self.handleCookiesAndPopups();
        
//     } catch (error) {
//         self.log('ERROR', 'Failed to load homepage: ' + error.message);
//         throw error;
//     }
// };

// ScienceDirectScraper.prototype.extractPublicationTitles = async function(keywordInput, yearRange) {
//     var self = this;
//     try {
//         var query = keywordInput.replace(/ /g, '%20');
//         var url = 'https://www.sciencedirect.com/search?qs=' + query + '&date=' + yearRange + '&show=100';
        
//         await self.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
//         await self.delay(3000);

//         try {
//             var showMoreBtn = await self.page.waitForSelector('button[data-aa-button="srp-show-more-publicationTitles-facet"]', { timeout: 5000 });
//             if (showMoreBtn) {
//                 await showMoreBtn.click();
//                 self.log('INFO', 'Clicked show more for publication titles');
//                 await self.delay(2000);
//             }
//         } catch (e) {
//             self.log('WARNING', 'Could not find show more button for publication titles');
//         }

//         // STRING-BASED evaluate for pkg compatibility
//         var publicationTitles = await self.page.evaluate('(function() { var inputs = document.querySelectorAll("input[id^=\\"publicationTitles-\\"]"); var results = []; for (var i = 0; i < inputs.length; i++) { var id = inputs[i].getAttribute("id"); results.push(id.replace("publicationTitles-", "")); } return results; })()');

//         self.log('INFO', 'Found ' + publicationTitles.length + ' publication titles');
//         return publicationTitles;
//     } catch (error) {
//         self.log('ERROR', 'Failed to extract publication titles: ' + error.message);
//         return [];
//     }
// };

// ScienceDirectScraper.prototype.extractSubjectAreas = async function(keywordInput, yearRange) {
//     var self = this;
//     try {
//         var query = keywordInput.replace(/ /g, '%20');
//         var url = 'https://www.sciencedirect.com/search?qs=' + query + '&date=' + yearRange + '&show=100';
        
//         await self.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
        
//         var wasRotated = await self.checkAndRotateUserAgent();
//         if (wasRotated) {
//             await self.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
//         }
        
//         await self.delay(3000);

//         try {
//             var showMoreBtn = await self.page.waitForSelector('button[data-aa-button="srp-show-more-subjectAreas-facet"]', { timeout: 5000 });
//             if (showMoreBtn) {
//                 await showMoreBtn.click();
//                 self.log('INFO', 'Clicked show more for subject areas');
//                 await self.delay(2000);
//             }
//         } catch (e) {
//             self.log('WARNING', 'Could not find show more button for subject areas');
//         }

//         // STRING-BASED evaluate for pkg compatibility
//         var subjectAreas = await self.page.evaluate('(function() { var inputs = document.querySelectorAll("input[id^=\\"subjectAreas-\\"]"); var results = []; for (var i = 0; i < inputs.length; i++) { var id = inputs[i].getAttribute("id"); results.push(id.replace("subjectAreas-", "")); } return results; })()');

//         self.log('INFO', 'Found ' + subjectAreas.length + ' subject areas');
//         return subjectAreas;
//     } catch (error) {
//         self.log('ERROR', 'Failed to extract subject areas: ' + error.message);
//         return [];
//     }
// };

// ScienceDirectScraper.prototype.getTotalResults = async function(url, retries) {
//     var self = this;
//     retries = retries || 3;
    
//     for (var attempt = 1; attempt <= retries; attempt++) {
//         try {
//             await self.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
            
//             var wasRotated = await self.checkAndRotateUserAgent();
//             if (wasRotated) {
//                 await self.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
//             }
            
//             await self.delay(3000);

//             try {
//                 var closeButton = await self.page.$('#bdd-els-close');
//                 if (closeButton) {
//                     await closeButton.click();
//                     await self.delay(1000);
//                 }
//             } catch (e) {}

//             try {
//                 await self.page.waitForSelector('.search-body-results-text', { timeout: 10000 });
//             } catch (e) {}

//             // STRING-BASED evaluate for pkg compatibility
//             var totalResults = await self.page.evaluate('(function() { var el = document.querySelector(".search-body-results-text"); if (!el) { el = document.querySelector(".ResultsFound"); } if (!el) { return 0; } var text = el.textContent || ""; var match = text.match(/[\\d,]+/); if (match) { return parseInt(match[0].replace(/,/g, ""), 10) || 0; } return 0; })()');

//             self.log('INFO', 'Found ' + totalResults + ' results');
//             return totalResults;
//         } catch (error) {
//             self.log('ERROR', 'Failed to get total results (attempt ' + attempt + '/' + retries + '): ' + error.message);
            
//             if (attempt < retries) {
//                 self.log('INFO', 'Retrying after browser restart...');
//                 await self.restartBrowser();
//             } else {
//                 return 0;
//             }
//         }
//     }
//     return 0;
// };

// ScienceDirectScraper.prototype.restartBrowser = async function() {
//     var self = this;
//     try {
//         if (self.browser) {
//             await self.browser.close();
//             self.browser = null;
//             self.page = null;
//         }
        
//         await self.delay(5000);
//         await self.initialize(false);
        
//         await self.page.goto('https://www.sciencedirect.com/', {
//             waitUntil: 'networkidle2',
//             timeout: 60000
//         });
        
//         await self.handleCookiesAndPopups();
//     } catch (error) {
//         self.log('ERROR', 'Failed to restart browser: ' + error.message);
//         throw error;
//     }
// };

// ScienceDirectScraper.prototype.getArticleLinksFromPage = async function(url, retries) {
//     var self = this;
//     retries = retries || 3;
    
//     for (var attempt = 1; attempt <= retries; attempt++) {
//         try {
//             await self.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
            
//             var rotated = await self.checkAndRotateUserAgent();
//             if (rotated) {
//                 await self.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
//             }
            
//             await self.delay(2000);

//             try {
//                 var closeButton = await self.page.$('#bdd-els-close');
//                 if (closeButton) {
//                     await closeButton.click();
//                     await self.delay(1000);
//                 }
//             } catch (e) {}

//             await self.page.waitForSelector('#srp-results-list', { timeout: 10000 });
            
//             // STRING-BASED evaluate for pkg compatibility
//             var results = await self.page.evaluate('(function() { var linkElements = document.querySelectorAll("#srp-results-list .result-list-title-link"); var data = []; for (var i = 0; i < linkElements.length; i++) { data.push({ url: linkElements[i].href, title: (linkElements[i].textContent || "").trim() }); } return data; })()');

//             return results;
//         } catch (error) {
//             self.log('ERROR', 'Failed to get article links (attempt ' + attempt + '/' + retries + '): ' + error.message);
            
//             if (attempt < retries) {
//                 self.log('INFO', 'Retrying after browser restart...');
//                 await self.restartBrowser();
//             } else {
//                 return [];
//             }
//         }
//     }
//     return [];
// };

// ScienceDirectScraper.prototype.scrapeWithFacetFilters = async function(keywordInput, yearRange, keywordDir) {
//     var self = this;
//     var csvFile = path.join(keywordDir, 'articles_' + yearRange + '.csv');
//     var query = keywordInput.replace(/ /g, '%20');

//     if (fsSync.existsSync(csvFile)) {
//         fsSync.unlinkSync(csvFile);
//     }

//     var writer = createObjectCsvWriter({
//         path: csvFile,
//         header: [
//             { id: 'url', title: 'url' },
//             { id: 'title', title: 'Title' }
//         ],
//         append: false
//     });

//     await writer.writeRecords([]);

//     var seenUrls = {};

//     var writeResults = async function(results) {
//         var uniqueNew = [];
//         for (var i = 0; i < results.length; i++) {
//             if (!seenUrls[results[i].url]) {
//                 uniqueNew.push(results[i]);
//                 seenUrls[results[i].url] = true;
//             }
//         }
        
//         if (uniqueNew.length > 0) {
//             var appendWriter = createObjectCsvWriter({
//                 path: csvFile,
//                 header: [
//                     { id: 'url', title: 'url' },
//                     { id: 'title', title: 'Title' }
//                 ],
//                 append: true
//             });
//             await appendWriter.writeRecords(uniqueNew);
//             var count = Object.keys(seenUrls).length;
//             self.log('INFO', 'Wrote ' + uniqueNew.length + ' new articles (Total: ' + count + ')');
//         }
//     };

//     self.log('INFO', '=== Step 1: Getting total results ===');
//     var baseUrl = 'https://www.sciencedirect.com/search?qs=' + query + '&date=' + yearRange + '&show=100';
//     var totalResults = await self.getTotalResults(baseUrl);
//     self.log('INFO', 'Total results for "' + keywordInput + '": ' + totalResults);

//     if (totalResults > 0) {
//         self.log('INFO', '=== Step 2: Scraping pages ===');
//         var offset = 0;
//         var hasMore = true;
        
//         while (hasMore && offset <= 900) {
//             var pageUrl = baseUrl + '&offset=' + offset;
//             self.log('INFO', 'Scraping offset ' + offset);
            
//             var results = await self.getArticleLinksFromPage(pageUrl);
//             await writeResults(results);
            
//             if (results.length < 100 || offset >= 900) {
//                 hasMore = false;
//             } else {
//                 offset += 100;
//                 await self.delay(2000);
//             }
//         }
//     }

//     self.log('INFO', '=== Step 3: Scraping by Article Types ===');
//     for (var t = 0; t < self.articleTypes.length; t++) {
//         var articleType = self.articleTypes[t];
//         self.log('INFO', 'Processing type: ' + articleType);
        
//         var typeUrl = baseUrl + '&articleTypes=' + articleType + '&lastSelectedFacet=articleTypes';
//         var typeResults = await self.getTotalResults(typeUrl);
        
//         if (typeResults === 0) continue;

//         var typeOffset = 0;
//         var typeHasMore = true;
        
//         while (typeHasMore && typeOffset <= 900) {
//             var typePageUrl = typeUrl + '&offset=' + typeOffset;
//             var typePageResults = await self.getArticleLinksFromPage(typePageUrl);
//             await writeResults(typePageResults);
            
//             if (typePageResults.length < 100 || typeOffset >= 900) {
//                 typeHasMore = false;
//             } else {
//                 typeOffset += 100;
//                 await self.delay(2000);
//             }
//         }
//     }

//     self.log('INFO', '=== Step 4: Scraping by Publications ===');
//     var pubTitles = await self.extractPublicationTitles(keywordInput, yearRange);
//     var pubSlice = pubTitles.slice(0, 10);
    
//     for (var p = 0; p < pubSlice.length; p++) {
//         var pubTitle = pubSlice[p];
//         self.log('INFO', 'Processing publication: ' + pubTitle);
        
//         var pubUrl = baseUrl + '&publicationTitles=' + pubTitle + '&lastSelectedFacet=publicationTitles';
//         var pubResults = await self.getTotalResults(pubUrl);
        
//         if (pubResults === 0) continue;

//         var pubOffset = 0;
//         var pubHasMore = true;
        
//         while (pubHasMore && pubOffset <= 900) {
//             var pubPageUrl = pubUrl + '&offset=' + pubOffset;
//             var pubPageResults = await self.getArticleLinksFromPage(pubPageUrl);
//             await writeResults(pubPageResults);
            
//             if (pubPageResults.length < 100 || pubOffset >= 900) {
//                 pubHasMore = false;
//             } else {
//                 pubOffset += 100;
//                 await self.delay(2000);
//             }
//         }
//     }

//     self.log('INFO', '=== Step 5: Scraping by Subject Areas ===');
//     var subjects = await self.extractSubjectAreas(keywordInput, yearRange);
//     var subSlice = subjects.slice(0, 10);
    
//     for (var s = 0; s < subSlice.length; s++) {
//         var subject = subSlice[s];
//         self.log('INFO', 'Processing subject: ' + subject);
        
//         var subUrl = baseUrl + '&subjectAreas=' + subject + '&lastSelectedFacet=subjectAreas';
//         var subResults = await self.getTotalResults(subUrl);
        
//         if (subResults === 0) continue;

//         var subOffset = 0;
//         var subHasMore = true;
        
//         while (subHasMore && subOffset <= 900) {
//             var subPageUrl = subUrl + '&offset=' + subOffset;
//             var subPageResults = await self.getArticleLinksFromPage(subPageUrl);
//             await writeResults(subPageResults);
            
//             if (subPageResults.length < 100 || subOffset >= 900) {
//                 subHasMore = false;
//             } else {
//                 subOffset += 100;
//                 await self.delay(2000);
//             }
//         }
//     }

//     var finalCount = Object.keys(seenUrls).length;
//     self.log('INFO', 'COMPLETE! Total unique articles: ' + finalCount);
//     self.log('INFO', 'Saved to: ' + csvFile);
    
//     return csvFile;
// };

// ScienceDirectScraper.prototype.clickEnvelopes = async function(keywords, yearRange, url, title, retries) {
//     var self = this;
//     retries = retries || 3;
    
//     for (var attempt = 1; attempt <= retries; attempt++) {
//         try {
//             var results = [];
            
//             await self.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
            
//             var rotated = await self.checkAndRotateUserAgent();
//             if (rotated) {
//                 await self.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
//             }
            
//             await self.delay(2000);

//             try {
//                 var pendoBtn = await self.page.$('#pendo-close-guide-bfad995f');
//                 if (pendoBtn) await pendoBtn.click();
//             } catch (e) {}

//             try {
//                 var closeBtn = await self.page.$('#bdd-els-close');
//                 if (closeBtn) await closeBtn.click();
//             } catch (e) {}

//             await self.delay(1000);

//             try {
//                 await self.page.click('#show-more-btn');
//                 await self.delay(1000);
//             } catch (e) {}
            
//             var authorButtons = await self.page.$$('svg[title="Author email or social media contact details icon"]');
//             self.log('INFO', 'Found ' + authorButtons.length + ' author buttons');

//             if (authorButtons.length === 0) return results;

//             for (var i = 0; i < authorButtons.length; i++) {
//                 try {
//                     var buttons = await self.page.$$('svg[title="Author email or social media contact details icon"]');
//                     if (!buttons[i]) continue;
                    
//                     await buttons[i].click();
//                     await self.delay(2000);

//                     try {
//                         await self.page.waitForSelector('#side-panel-author', { timeout: 5000 });
//                     } catch (e) { continue; }

//                     // STRING-BASED evaluate for pkg compatibility
//                     var authorData = await self.page.evaluate('(function() { var emailEl = document.querySelector("#side-panel-author .e-address a"); var givenEl = document.querySelector("#side-panel-author .given-name"); var surnameEl = document.querySelector("#side-panel-author .surname"); return { email: emailEl ? emailEl.textContent.trim() : null, given: givenEl ? givenEl.textContent.trim() : "", surname: surnameEl ? surnameEl.textContent.trim() : "" }; })()');

//                     if (authorData.email) {
//                         var authorName = (authorData.given + ' ' + authorData.surname).trim();
//                         results.push({
//                             runDate: new Date().toISOString().split('T')[0],
//                             keywordInput: keywords,
//                             yearRange: yearRange,
//                             url: url,
//                             email: authorData.email,
//                             name: authorName
//                         });
//                         self.log('INFO', 'Got email: ' + authorData.email);
//                     }

//                     try {
//                         var closePanel = await self.page.$('#side-panel-author button[aria-label="Close"]');
//                         if (closePanel) await closePanel.click();
//                     } catch (e) {}
                    
//                     await self.delay(500);
//                 } catch (e) {
//                     self.log('WARNING', 'Error on author ' + (i+1) + ': ' + e.message);
//                 }
//             }

//             return results;
//         } catch (error) {
//             self.log('ERROR', 'clickEnvelopes error (attempt ' + attempt + '): ' + error.message);
//             if (attempt < retries) {
//                 await self.restartBrowser();
//             } else {
//                 return [];
//             }
//         }
//     }
//     return [];
// };

// ScienceDirectScraper.prototype.extractEmails = async function(csvFilePath, keywords, yearRange, keywordDir) {
//     var self = this;
//     var writeFilePath = path.join(keywordDir, 'emails_' + yearRange + '.csv');

//     if (fsSync.existsSync(writeFilePath)) {
//         fsSync.unlinkSync(writeFilePath);
//     }

//     var writer = createObjectCsvWriter({
//         path: writeFilePath,
//         header: [
//             { id: 'runDate', title: 'Run_Date' },
//             { id: 'keywordInput', title: 'Keyword_input' },
//             { id: 'yearRange', title: 'Year_Range' },
//             { id: 'url', title: 'URLs' },
//             { id: 'email', title: 'emails' },
//             { id: 'name', title: 'names' }
//         ],
//         append: false
//     });

//     await writer.writeRecords([]);

//     var count = 0;

//     return new Promise(function(resolve, reject) {
//         var rows = [];
//         fsSync.createReadStream(csvFilePath)
//             .pipe(csv())
//             .on('data', function(row) {
//                 rows.push(row);
//             })
//             .on('end', async function() {
//                 for (var r = 0; r < rows.length; r++) {
//                     var row = rows[r];
//                     try {
//                         if (!row.url || row.url === 'undefined') {
//                             self.log('WARNING', 'Skipping invalid URL at row ' + (count + 1));
//                             count++;
//                             continue;
//                         }

//                         count++;
//                         self.log('INFO', 'Processing article ' + count + '/' + rows.length + ': ' + row.url);
                        
//                         var results = await self.clickEnvelopes(keywords, yearRange, row.url, row.title);
                        
//                         if (results.length > 0) {
//                             var appendWriter = createObjectCsvWriter({
//                                 path: writeFilePath,
//                                 header: [
//                                     { id: 'runDate', title: 'Run_Date' },
//                                     { id: 'keywordInput', title: 'Keyword_input' },
//                                     { id: 'yearRange', title: 'Year_Range' },
//                                     { id: 'url', title: 'URLs' },
//                                     { id: 'email', title: 'emails' },
//                                     { id: 'name', title: 'names' }
//                                 ],
//                                 append: true
//                             });
//                             await appendWriter.writeRecords(results);
//                             self.log('INFO', 'Wrote ' + results.length + ' emails');
//                         }
                        
//                         await self.delay(1000);
//                     } catch (error) {
//                         self.log('ERROR', 'Error processing article: ' + error.message);
//                     }
//                 }

//                 self.log('INFO', 'Email extraction completed. Saved to ' + writeFilePath);
//                 resolve();
//             })
//             .on('error', function(err) {
//                 reject(err);
//             });
//     });
// };

// ScienceDirectScraper.prototype.close = async function() {
//     var self = this;
//     if (self.browser) {
//         await self.browser.close();
//         self.log('INFO', 'Browser closed');
//     }
// };

// function getUserInput(question) {
//     var rl = readline.createInterface({
//         input: process.stdin,
//         output: process.stdout
//     });

//     return new Promise(function(resolve) {
//         rl.question(question, function(answer) {
//             rl.close();
//             resolve(answer);
//         });
//     });
// }

// function validateYearRange(yearRange) {
//     var singleYearPattern = /^\d{4}$/;
//     var rangePattern = /^\d{4}-\d{4}$/;
    
//     if (singleYearPattern.test(yearRange)) {
//         return true;
//     }
    
//     if (rangePattern.test(yearRange)) {
//         var parts = yearRange.split('-');
//         var startYear = parseInt(parts[0], 10);
//         var endYear = parseInt(parts[1], 10);
//         return startYear <= endYear;
//     }
    
//     return false;
// }

// function sanitizeKeyword(keyword) {
//     return keyword.replace(/[<>:"/\\|?*]/g, '_').trim();
// }

// async function main() {
//     var scraper = new ScienceDirectScraper();
    
//     try {
//         console.log('\n=== ScienceDirect Scraper ===\n');
        
//         var keyword = await getUserInput('Enter search keyword (e.g., "Bioinformatics"): ');
//         if (!keyword.trim()) {
//             console.error('Error: Keyword cannot be empty');
//             process.exit(1);
//         }
        
//         var yearRange;
//         var isValidYear = false;
//         while (!isValidYear) {
//             yearRange = await getUserInput('Enter year or year range (e.g., "2018" or "2017-2025"): ');
//             if (validateYearRange(yearRange)) {
//                 isValidYear = true;
//             } else {
//                 console.log('Invalid year format. Please use YYYY or YYYY-YYYY format.');
//             }
//         }
        
//         var sanitizedKeyword = sanitizeKeyword(keyword);
//         var keywordDir = path.join('output', sanitizedKeyword);
        
//         if (!fsSync.existsSync('output')) {
//             fsSync.mkdirSync('output');
//             console.log('Created output directory');
//         }
        
//         if (!fsSync.existsSync(keywordDir)) {
//             fsSync.mkdirSync(keywordDir, { recursive: true });
//             console.log('Created directory: ' + keywordDir);
//         }
        
//         scraper.initializeLog(keywordDir);
        
//         var articlesCSVPath = path.join(keywordDir, 'articles_' + yearRange + '.csv');
//         var articlesExist = fsSync.existsSync(articlesCSVPath);
        
//         var extractNewLinks = true;
        
//         if (articlesExist) {
//             console.log('\nFound existing articles file: ' + articlesCSVPath);
//             var extractNewInput = await getUserInput('Extract new article links? (y/n): ');
//             extractNewLinks = extractNewInput.toLowerCase() === 'y' || extractNewInput.toLowerCase() === 'yes';
//         }
        
//         var csvFile = articlesCSVPath;
        
//         if (extractNewLinks || !articlesExist) {
//             console.log('\nInitializing browser...');
//             await scraper.initialize(false);
            
//             console.log('Loading homepage (30 second delay for cookies)...');
//             await scraper.landFirstPage();
            
//             console.log('\nSearching for: "' + keyword + '" in year range: ' + yearRange);
            
//             csvFile = await scraper.scrapeWithFacetFilters(keyword, yearRange, keywordDir);
            
//             console.log('\nArticle links extraction completed!');
//         } else {
//             console.log('\nUsing existing file.');
            
//             console.log('\nInitializing browser...');
//             await scraper.initialize(false);
            
//             console.log('Loading homepage (30 second delay for cookies)...');
//             await scraper.landFirstPage();
//         }
        
//         var extractEmailsInput = await getUserInput('\nExtract author emails? (y/n): ');
//         var doExtractEmails = extractEmailsInput.toLowerCase() === 'y' || extractEmailsInput.toLowerCase() === 'yes';
        
//         if (doExtractEmails) {
//             console.log('\nExtracting author emails...');
//             await scraper.extractEmails(csvFile, keyword, yearRange, keywordDir);
//             console.log('\nEmail extraction completed!');
//         }

//         console.log('\nAll operations completed!');
//         console.log('Output saved in: ' + keywordDir);
        
//     } catch (error) {
//         console.error('Error:', error);
//     } finally {
//         console.log('\nClosing browser...');
//         await scraper.close();
//     }
// }

// module.exports = ScienceDirectScraper;

// if (require.main === module) {
//     console.log('Starting ScienceDirect scraper...');
//     main().catch(console.error);
// }

var puppeteer = require('puppeteer-core');
var fsSync = require('fs');
var path = require('path');
var csvWriter = require('csv-writer');
var csv = require('csv-parser');
var os = require('os');
var readline = require('readline');

var createObjectCsvWriter = csvWriter.createObjectCsvWriter;

function ScienceDirectScraper() {
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
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0'
    ];
    this.articleTypes = ['REV', 'FLA', 'DAT', 'CH'];
}

ScienceDirectScraper.prototype.delay = function(ms) {
    return new Promise(function(resolve) {
        setTimeout(resolve, ms);
    });
};

ScienceDirectScraper.prototype.initializeLog = function(keywordDir) {
    this.logFile = path.join(keywordDir, 'scraper_log.log');
    if (fsSync.existsSync(this.logFile)) {
        fsSync.unlinkSync(this.logFile);
    }
    fsSync.writeFileSync(this.logFile, 'Log initialized at ' + new Date().toISOString() + '\n');
    console.log('Log file created at: ' + this.logFile);
};

ScienceDirectScraper.prototype.log = function(level, message) {
    var timestamp = new Date().toISOString();
    var logMessage = timestamp + ' - ' + level + ' - ' + message + '\n';
    if (this.logFile) {
        fsSync.appendFileSync(this.logFile, logMessage);
    }
    console.log(logMessage.trim());
};

ScienceDirectScraper.prototype.getNextUserAgent = function() {
    var userAgent = this.userAgents[this.currentUserAgentIndex];
    this.currentUserAgentIndex = (this.currentUserAgentIndex + 1) % this.userAgents.length;
    return userAgent;
};

ScienceDirectScraper.prototype.findChromePath = function() {
    var self = this;
    var platform = os.platform();
    var possiblePaths = [];

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

    for (var i = 0; i < possiblePaths.length; i++) {
        var chromePath = possiblePaths[i];
        if (chromePath && fsSync.existsSync(chromePath)) {
            self.log('INFO', 'Found Chrome at: ' + chromePath);
            return chromePath;
        }
    }

    self.log('ERROR', 'Chrome not found! Please install Google Chrome.');
    return null;
};

ScienceDirectScraper.prototype.handleCookiesAndPopups = async function() {
    var self = this;
    try {
        self.log('INFO', 'Starting cookie and popup handling with 30 second delay...');
        await self.delay(30000);

        try {
            var cookieButton = await self.page.waitForSelector('#onetrust-accept-btn-handler', { timeout: 5000 });
            if (cookieButton) {
                await cookieButton.click();
                self.log('INFO', 'Accepted cookies');
                await self.delay(2000);
            }
        } catch (e) {
            self.log('INFO', 'No cookie banner found or already accepted');
        }
        
        try {
            var closeButton = await self.page.$('._pendo-close-guide');
            if (closeButton) {
                await closeButton.click();
                self.log('INFO', 'Closed AI popup');
                await self.delay(1000);
            }
        } catch (e) {}

        try {
            var pendoCloseButton = await self.page.$('#pendo-close-guide-bfad995f');
            if (pendoCloseButton) {
                await pendoCloseButton.click();
                self.log('INFO', 'Closed Science Direct AI popup');
                await self.delay(1000);
            }
        } catch (e) {}

        try {
            var instCloseButton = await self.page.$('#bdd-els-close');
            if (instCloseButton) {
                await instCloseButton.click();
                self.log('INFO', 'Closed institution popup');
                await self.delay(1000);
            }
        } catch (e) {}
    } catch (error) {
        self.log('ERROR', 'Error handling cookies/popups: ' + error.message);
    }
};

ScienceDirectScraper.prototype.checkAndRotateUserAgent = async function() {
    var self = this;
    try {
        var pageContent = '';
        try {
            pageContent = await self.page.content();
        } catch (e) {
            pageContent = '';
        }
        
        var isBotPage = pageContent.indexOf('User Agent:') !== -1;
        
        if (isBotPage) {
            self.log('WARNING', 'BOT DETECTION PAGE DETECTED!');
            self.log('WARNING', 'Closing browser and restarting with new User Agent...');
            
            if (self.browser) {
                try {
                    await self.browser.close();
                    self.log('INFO', 'Browser closed successfully');
                } catch (e) {
                    self.log('WARNING', 'Error closing browser: ' + e.message);
                }
                self.browser = null;
                self.page = null;
            }
            
            self.log('INFO', 'Waiting 5 seconds before restarting...');
            await self.delay(5000);
            
            self.log('INFO', 'Initializing new browser session...');
            await self.initialize(false);
            
            self.log('INFO', 'Loading homepage with new session...');
            await self.page.goto('https://www.sciencedirect.com/', {
                waitUntil: 'networkidle2',
                timeout: 30000
            });
            
            await self.handleCookiesAndPopups();
            
            self.log('INFO', 'Successfully rotated to new User Agent');
            return true;
        }
        
        return false;
    } catch (error) {
        self.log('ERROR', 'Error checking User Agent: ' + error.message);
        return false;
    }
};

ScienceDirectScraper.prototype.initialize = async function(headless) {
    var self = this;
    headless = headless || false;
    
    try {
        var executablePath = self.findChromePath();

        if (!executablePath) {
            throw new Error('Chrome executable not found. Please install Google Chrome.');
        }

        var launchOptions = {
            headless: headless ? 'new' : false,
            executablePath: executablePath,
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
                '--disable-popup-blocking'
            ],
            defaultViewport: null,
            ignoreHTTPSErrors: true,
            timeout: 60000
        };

        self.browser = await puppeteer.launch(launchOptions);
        self.page = await self.browser.newPage();
        
        var userAgent = self.getNextUserAgent();
        await self.page.setUserAgent(userAgent);
        self.log('INFO', 'Set User Agent: ' + userAgent);

        await self.page.evaluateOnNewDocument('Object.defineProperty(navigator, "webdriver", { get: function() { return false; } });');

        self.log('INFO', 'Browser initialized successfully');
    } catch (error) {
        self.log('ERROR', 'Failed to initialize browser: ' + error.message);
        throw error;
    }
};

ScienceDirectScraper.prototype.landFirstPage = async function() {
    var self = this;
    try {
        await self.page.goto('https://www.sciencedirect.com/', {
            waitUntil: 'networkidle2',
            timeout: 30000
        });
        
        await self.checkAndRotateUserAgent();
        self.log('INFO', 'Landed on ScienceDirect homepage');
        await self.handleCookiesAndPopups();
        
    } catch (error) {
        self.log('ERROR', 'Failed to load homepage: ' + error.message);
        throw error;
    }
};

ScienceDirectScraper.prototype.extractPublicationTitles = async function(keywordInput, year) {
    var self = this;
    try {
        var query = keywordInput.replace(/ /g, '%20');
        var url = 'https://www.sciencedirect.com/search?qs=' + query + '&date=' + year + '&show=100';
        
        await self.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
        await self.delay(3000);

        try {
            var showMoreBtn = await self.page.waitForSelector('button[data-aa-button="srp-show-more-publicationTitles-facet"]', { timeout: 5000 });
            if (showMoreBtn) {
                await showMoreBtn.click();
                self.log('INFO', 'Clicked show more for publication titles');
                await self.delay(2000);
            }
        } catch (e) {
            self.log('WARNING', 'Could not find show more button for publication titles');
        }

        var publicationTitles = await self.page.evaluate('(function() { var inputs = document.querySelectorAll("input[id^=\\"publicationTitles-\\"]"); var results = []; for (var i = 0; i < inputs.length; i++) { var id = inputs[i].getAttribute("id"); results.push(id.replace("publicationTitles-", "")); } return results; })()');

        self.log('INFO', 'Found ' + publicationTitles.length + ' publication titles');
        return publicationTitles;
    } catch (error) {
        self.log('ERROR', 'Failed to extract publication titles: ' + error.message);
        return [];
    }
};

ScienceDirectScraper.prototype.extractSubjectAreas = async function(keywordInput, year) {
    var self = this;
    try {
        var query = keywordInput.replace(/ /g, '%20');
        var url = 'https://www.sciencedirect.com/search?qs=' + query + '&date=' + year + '&show=100';
        
        await self.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
        
        var wasRotated = await self.checkAndRotateUserAgent();
        if (wasRotated) {
            await self.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
        }
        
        await self.delay(3000);

        try {
            var showMoreBtn = await self.page.waitForSelector('button[data-aa-button="srp-show-more-subjectAreas-facet"]', { timeout: 5000 });
            if (showMoreBtn) {
                await showMoreBtn.click();
                self.log('INFO', 'Clicked show more for subject areas');
                await self.delay(2000);
            }
        } catch (e) {
            self.log('WARNING', 'Could not find show more button for subject areas');
        }

        var subjectAreas = await self.page.evaluate('(function() { var inputs = document.querySelectorAll("input[id^=\\"subjectAreas-\\"]"); var results = []; for (var i = 0; i < inputs.length; i++) { var id = inputs[i].getAttribute("id"); results.push(id.replace("subjectAreas-", "")); } return results; })()');

        self.log('INFO', 'Found ' + subjectAreas.length + ' subject areas');
        return subjectAreas;
    } catch (error) {
        self.log('ERROR', 'Failed to extract subject areas: ' + error.message);
        return [];
    }
};

ScienceDirectScraper.prototype.getTotalResults = async function(url, retries) {
    var self = this;
    retries = retries || 3;
    
    for (var attempt = 1; attempt <= retries; attempt++) {
        try {
            await self.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
            
            var wasRotated = await self.checkAndRotateUserAgent();
            if (wasRotated) {
                await self.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
            }
            
            await self.delay(3000);

            try {
                var closeButton = await self.page.$('#bdd-els-close');
                if (closeButton) {
                    await closeButton.click();
                    await self.delay(1000);
                }
            } catch (e) {}

            try {
                await self.page.waitForSelector('.search-body-results-text', { timeout: 10000 });
            } catch (e) {}

            var totalResults = await self.page.evaluate('(function() { var el = document.querySelector(".search-body-results-text"); if (!el) { el = document.querySelector(".ResultsFound"); } if (!el) { return 0; } var text = el.textContent || ""; var match = text.match(/[\\d,]+/); if (match) { return parseInt(match[0].replace(/,/g, ""), 10) || 0; } return 0; })()');

            self.log('INFO', 'Found ' + totalResults + ' results');
            return totalResults;
        } catch (error) {
            self.log('ERROR', 'Failed to get total results (attempt ' + attempt + '/' + retries + '): ' + error.message);
            
            if (attempt < retries) {
                self.log('INFO', 'Retrying after browser restart...');
                await self.restartBrowser();
            } else {
                return 0;
            }
        }
    }
    return 0;
};

ScienceDirectScraper.prototype.restartBrowser = async function() {
    var self = this;
    try {
        if (self.browser) {
            await self.browser.close();
            self.browser = null;
            self.page = null;
        }
        
        await self.delay(5000);
        await self.initialize(false);
        
        await self.page.goto('https://www.sciencedirect.com/', {
            waitUntil: 'networkidle2',
            timeout: 60000
        });
        
        await self.handleCookiesAndPopups();
    } catch (error) {
        self.log('ERROR', 'Failed to restart browser: ' + error.message);
        throw error;
    }
};

ScienceDirectScraper.prototype.getArticleLinksFromPage = async function(url, retries) {
    var self = this;
    retries = retries || 3;
    
    for (var attempt = 1; attempt <= retries; attempt++) {
        try {
            await self.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
            
            var rotated = await self.checkAndRotateUserAgent();
            if (rotated) {
                await self.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
            }
            
            await self.delay(2000);

            try {
                var closeButton = await self.page.$('#bdd-els-close');
                if (closeButton) {
                    await closeButton.click();
                    await self.delay(1000);
                }
            } catch (e) {}

            await self.page.waitForSelector('#srp-results-list', { timeout: 10000 });
            
            var results = await self.page.evaluate('(function() { var linkElements = document.querySelectorAll("#srp-results-list .result-list-title-link"); var data = []; for (var i = 0; i < linkElements.length; i++) { data.push({ url: linkElements[i].href, title: (linkElements[i].textContent || "").trim() }); } return data; })()');

            return results;
        } catch (error) {
            self.log('ERROR', 'Failed to get article links (attempt ' + attempt + '/' + retries + '): ' + error.message);
            
            if (attempt < retries) {
                self.log('INFO', 'Retrying after browser restart...');
                await self.restartBrowser();
            } else {
                return [];
            }
        }
    }
    return [];
};

ScienceDirectScraper.prototype.scrapeWithFacetFilters = async function(keywordInput, year, keywordDir) {
    var self = this;
    var fileName = sanitizeKeyword(keywordInput) + '-' + year + '_articles.csv';
    var csvFile = path.join(keywordDir, fileName);
    var query = keywordInput.replace(/ /g, '%20');

    if (fsSync.existsSync(csvFile)) {
        fsSync.unlinkSync(csvFile);
    }

    var writer = createObjectCsvWriter({
        path: csvFile,
        header: [
            { id: 'url', title: 'url' },
            { id: 'title', title: 'Title' }
        ],
        append: false
    });

    await writer.writeRecords([]);

    var seenUrls = {};

    var writeResults = async function(results) {
        var uniqueNew = [];
        for (var i = 0; i < results.length; i++) {
            if (!seenUrls[results[i].url]) {
                uniqueNew.push(results[i]);
                seenUrls[results[i].url] = true;
            }
        }
        
        if (uniqueNew.length > 0) {
            var appendWriter = createObjectCsvWriter({
                path: csvFile,
                header: [
                    { id: 'url', title: 'url' },
                    { id: 'title', title: 'Title' }
                ],
                append: true
            });
            await appendWriter.writeRecords(uniqueNew);
            var count = Object.keys(seenUrls).length;
            self.log('INFO', 'Wrote ' + uniqueNew.length + ' new articles (Total: ' + count + ')');
        }
    };

    self.log('INFO', '=== Step 1: Getting total results for year ' + year + ' ===');
    var baseUrl = 'https://www.sciencedirect.com/search?qs=' + query + '&date=' + year + '&show=100';
    var totalResults = await self.getTotalResults(baseUrl);
    self.log('INFO', 'Total results for "' + keywordInput + '" in ' + year + ': ' + totalResults);

    if (totalResults > 0) {
        self.log('INFO', '=== Step 2: Scraping pages ===');
        var offset = 0;
        var hasMore = true;
        
        while (hasMore && offset <= 900) {
            var pageUrl = baseUrl + '&offset=' + offset;
            self.log('INFO', 'Scraping offset ' + offset);
            
            var results = await self.getArticleLinksFromPage(pageUrl);
            await writeResults(results);
            
            if (results.length < 100 || offset >= 900) {
                hasMore = false;
            } else {
                offset += 100;
                await self.delay(2000);
            }
        }
    }

    self.log('INFO', '=== Step 3: Scraping by Article Types ===');
    for (var t = 0; t < self.articleTypes.length; t++) {
        var articleType = self.articleTypes[t];
        self.log('INFO', 'Processing type: ' + articleType);
        
        var typeUrl = baseUrl + '&articleTypes=' + articleType + '&lastSelectedFacet=articleTypes';
        var typeResults = await self.getTotalResults(typeUrl);
        
        if (typeResults === 0) continue;

        var typeOffset = 0;
        var typeHasMore = true;
        
        while (typeHasMore && typeOffset <= 900) {
            var typePageUrl = typeUrl + '&offset=' + typeOffset;
            var typePageResults = await self.getArticleLinksFromPage(typePageUrl);
            await writeResults(typePageResults);
            
            if (typePageResults.length < 100 || typeOffset >= 900) {
                typeHasMore = false;
            } else {
                typeOffset += 100;
                await self.delay(2000);
            }
        }
    }

    self.log('INFO', '=== Step 4: Scraping by Publications ===');
    var pubTitles = await self.extractPublicationTitles(keywordInput, year);
    var pubSlice = pubTitles.slice(0, 10);
    
    for (var p = 0; p < pubSlice.length; p++) {
        var pubTitle = pubSlice[p];
        self.log('INFO', 'Processing publication: ' + pubTitle);
        
        var pubUrl = baseUrl + '&publicationTitles=' + pubTitle + '&lastSelectedFacet=publicationTitles';
        var pubResults = await self.getTotalResults(pubUrl);
        
        if (pubResults === 0) continue;

        var pubOffset = 0;
        var pubHasMore = true;
        
        while (pubHasMore && pubOffset <= 900) {
            var pubPageUrl = pubUrl + '&offset=' + pubOffset;
            var pubPageResults = await self.getArticleLinksFromPage(pubPageUrl);
            await writeResults(pubPageResults);
            
            if (pubPageResults.length < 100 || pubOffset >= 900) {
                pubHasMore = false;
            } else {
                pubOffset += 100;
                await self.delay(2000);
            }
        }
    }

    self.log('INFO', '=== Step 5: Scraping by Subject Areas ===');
    var subjects = await self.extractSubjectAreas(keywordInput, year);
    var subSlice = subjects.slice(0, 10);
    
    for (var s = 0; s < subSlice.length; s++) {
        var subject = subSlice[s];
        self.log('INFO', 'Processing subject: ' + subject);
        
        var subUrl = baseUrl + '&subjectAreas=' + subject + '&lastSelectedFacet=subjectAreas';
        var subResults = await self.getTotalResults(subUrl);
        
        if (subResults === 0) continue;

        var subOffset = 0;
        var subHasMore = true;
        
        while (subHasMore && subOffset <= 900) {
            var subPageUrl = subUrl + '&offset=' + subOffset;
            var subPageResults = await self.getArticleLinksFromPage(subPageUrl);
            await writeResults(subPageResults);
            
            if (subPageResults.length < 100 || subOffset >= 900) {
                subHasMore = false;
            } else {
                subOffset += 100;
                await self.delay(2000);
            }
        }
    }

    var finalCount = Object.keys(seenUrls).length;
    self.log('INFO', 'COMPLETE! Total unique articles for ' + year + ': ' + finalCount);
    self.log('INFO', 'Saved to: ' + csvFile);
    
    return csvFile;
};

ScienceDirectScraper.prototype.clickEnvelopes = async function(keywords, year, url, title, retries) {
    var self = this;
    retries = retries || 3;
    
    for (var attempt = 1; attempt <= retries; attempt++) {
        try {
            var results = [];
            
            await self.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
            
            var rotated = await self.checkAndRotateUserAgent();
            if (rotated) {
                await self.page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
            }
            
            await self.delay(2000);

            try {
                var pendoBtn = await self.page.$('#pendo-close-guide-bfad995f');
                if (pendoBtn) await pendoBtn.click();
            } catch (e) {}

            try {
                var closeBtn = await self.page.$('#bdd-els-close');
                if (closeBtn) await closeBtn.click();
            } catch (e) {}

            await self.delay(1000);

            try {
                await self.page.click('#show-more-btn');
                await self.delay(1000);
            } catch (e) {}
            
            var authorButtons = await self.page.$$('svg[title="Author email or social media contact details icon"]');
            self.log('INFO', 'Found ' + authorButtons.length + ' author buttons');

            if (authorButtons.length === 0) return results;

            for (var i = 0; i < authorButtons.length; i++) {
                try {
                    var buttons = await self.page.$$('svg[title="Author email or social media contact details icon"]');
                    if (!buttons[i]) continue;
                    
                    await buttons[i].click();
                    await self.delay(2000);

                    try {
                        await self.page.waitForSelector('#side-panel-author', { timeout: 5000 });
                    } catch (e) { continue; }

                    var authorData = await self.page.evaluate('(function() { var emailEl = document.querySelector("#side-panel-author .e-address a"); var givenEl = document.querySelector("#side-panel-author .given-name"); var surnameEl = document.querySelector("#side-panel-author .surname"); return { email: emailEl ? emailEl.textContent.trim() : null, given: givenEl ? givenEl.textContent.trim() : "", surname: surnameEl ? surnameEl.textContent.trim() : "" }; })()');

                    if (authorData.email) {
                        var authorName = (authorData.given + ' ' + authorData.surname).trim();
                        results.push({
                            runDate: new Date().toISOString().split('T')[0],
                            keywordInput: keywords,
                            year: year,
                            url: url,
                            email: authorData.email,
                            name: authorName
                        });
                        self.log('INFO', 'Got email: ' + authorData.email);
                    }

                    try {
                        var closePanel = await self.page.$('#side-panel-author button[aria-label="Close"]');
                        if (closePanel) await closePanel.click();
                    } catch (e) {}
                    
                    await self.delay(500);
                } catch (e) {
                    self.log('WARNING', 'Error on author ' + (i+1) + ': ' + e.message);
                }
            }

            return results;
        } catch (error) {
            self.log('ERROR', 'clickEnvelopes error (attempt ' + attempt + '): ' + error.message);
            if (attempt < retries) {
                await self.restartBrowser();
            } else {
                return [];
            }
        }
    }
    return [];
};

ScienceDirectScraper.prototype.extractEmails = async function(csvFilePath, keywords, year, keywordDir) {
    var self = this;
    var fileName = sanitizeKeyword(keywords) + '-' + year + '_emails.csv';
    var writeFilePath = path.join(keywordDir, fileName);

    if (fsSync.existsSync(writeFilePath)) {
        fsSync.unlinkSync(writeFilePath);
    }

    var writer = createObjectCsvWriter({
        path: writeFilePath,
        header: [
            { id: 'runDate', title: 'Run_Date' },
            { id: 'keywordInput', title: 'Keyword_input' },
            { id: 'year', title: 'Year' },
            { id: 'url', title: 'URLs' },
            { id: 'email', title: 'emails' },
            { id: 'name', title: 'names' }
        ],
        append: false
    });

    await writer.writeRecords([]);

    var count = 0;

    return new Promise(function(resolve, reject) {
        var rows = [];
        fsSync.createReadStream(csvFilePath)
            .pipe(csv())
            .on('data', function(row) {
                rows.push(row);
            })
            .on('end', async function() {
                for (var r = 0; r < rows.length; r++) {
                    var row = rows[r];
                    try {
                        if (!row.url || row.url === 'undefined') {
                            self.log('WARNING', 'Skipping invalid URL at row ' + (count + 1));
                            count++;
                            continue;
                        }

                        count++;
                        self.log('INFO', 'Processing article ' + count + '/' + rows.length + ': ' + row.url);
                        
                        var results = await self.clickEnvelopes(keywords, year, row.url, row.title);
                        
                        if (results.length > 0) {
                            var appendWriter = createObjectCsvWriter({
                                path: writeFilePath,
                                header: [
                                    { id: 'runDate', title: 'Run_Date' },
                                    { id: 'keywordInput', title: 'Keyword_input' },
                                    { id: 'year', title: 'Year' },
                                    { id: 'url', title: 'URLs' },
                                    { id: 'email', title: 'emails' },
                                    { id: 'name', title: 'names' }
                                ],
                                append: true
                            });
                            await appendWriter.writeRecords(results);
                            self.log('INFO', 'Wrote ' + results.length + ' emails');
                        }
                        
                        await self.delay(1000);
                    } catch (error) {
                        self.log('ERROR', 'Error processing article: ' + error.message);
                    }
                }

                self.log('INFO', 'Email extraction completed. Saved to ' + writeFilePath);
                resolve();
            })
            .on('error', function(err) {
                reject(err);
            });
    });
};

ScienceDirectScraper.prototype.close = async function() {
    var self = this;
    if (self.browser) {
        await self.browser.close();
        self.log('INFO', 'Browser closed');
    }
};

function getUserInput(question) {
    var rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout
    });

    return new Promise(function(resolve) {
        rl.question(question, function(answer) {
            rl.close();
            resolve(answer);
        });
    });
}

function validateYearRange(yearRange) {
    var singleYearPattern = /^\d{4}$/;
    var rangePattern = /^\d{4}-\d{4}$/;
    
    if (singleYearPattern.test(yearRange)) {
        return true;
    }
    
    if (rangePattern.test(yearRange)) {
        var parts = yearRange.split('-');
        var startYear = parseInt(parts[0], 10);
        var endYear = parseInt(parts[1], 10);
        return startYear <= endYear;
    }
    
    return false;
}

function parseYearRange(yearRange) {
    var singleYearPattern = /^\d{4}$/;
    
    if (singleYearPattern.test(yearRange)) {
        var year = parseInt(yearRange, 10);
        return [year];
    }
    
    var parts = yearRange.split('-');
    var startYear = parseInt(parts[0], 10);
    var endYear = parseInt(parts[1], 10);
    
    var years = [];
    for (var y = startYear; y <= endYear; y++) {
        years.push(y);
    }
    
    return years;
}

function sanitizeKeyword(keyword) {
    return keyword.replace(/[<>:"/\\|?*]/g, '_').trim();
}

async function main() {
    var scraper = new ScienceDirectScraper();
    
    try {
        console.log('\n========================================');
        console.log('  ScienceDirect Scraper Ver 1.0');
        console.log('========================================\n');
        
        var keyword = await getUserInput('Enter search keyword (e.g., "Bioinformatics"): ');
        if (!keyword.trim()) {
            console.error('Error: Keyword cannot be empty');
            process.exit(1);
        }
        
        var yearRange;
        var isValidYear = false;
        while (!isValidYear) {
            yearRange = await getUserInput('Enter year or year range (e.g., "2018" or "2017-2025"): ');
            if (validateYearRange(yearRange)) {
                isValidYear = true;
            } else {
                console.log('Invalid year format. Please use YYYY or YYYY-YYYY format.');
            }
        }
        
        var years = parseYearRange(yearRange);
        console.log('\nWill process ' + years.length + ' year(s): ' + years.join(', '));
        
        var extractNewLinksInput = await getUserInput('\nExtract new article links? (y/n): ');
        var extractNewLinks = extractNewLinksInput.toLowerCase() === 'y' || extractNewLinksInput.toLowerCase() === 'yes';
        
        var sanitizedKeyword = sanitizeKeyword(keyword);
        var dirName = sanitizedKeyword + '-' + yearRange;
        var keywordDir = path.join('output', dirName);
        
        if (!fsSync.existsSync('output')) {
            fsSync.mkdirSync('output');
            console.log('Created output directory');
        }
        
        if (!fsSync.existsSync(keywordDir)) {
            fsSync.mkdirSync(keywordDir, { recursive: true });
            console.log('Created directory: ' + keywordDir);
        } else {
            console.log('Using directory: ' + keywordDir);
        }
        
        scraper.initializeLog(keywordDir);
        
        if (extractNewLinks) {
            console.log('\n=== EXTRACTING NEW ARTICLE LINKS ===\n');
            
            console.log('Initializing browser...');
            await scraper.initialize(false);
            
            console.log('Loading homepage (30 second delay for cookies)...');
            await scraper.landFirstPage();
            
            for (var i = 0; i < years.length; i++) {
                var year = years[i];
                console.log('\n========================================');
                console.log('Processing Year ' + (i + 1) + '/' + years.length + ': ' + year);
                console.log('========================================\n');
                
                console.log('Searching for: "' + keyword + '" in year: ' + year);
                
                var csvFile = await scraper.scrapeWithFacetFilters(keyword, year.toString(), keywordDir);
                
                console.log('\nArticle links for ' + year + ' extraction completed!');
                console.log('Saved to: ' + csvFile);
            }
            
            console.log('\n=== ALL ARTICLE LINKS EXTRACTED ===\n');
            
        } else {
            console.log('\n=== SKIPPING ARTICLE LINK EXTRACTION ===\n');
            console.log('Looking for existing article files...\n');
            
            var allFilesExist = true;
            for (var i = 0; i < years.length; i++) {
                var year = years[i];
                var fileName = sanitizedKeyword + '-' + year + '_articles.csv';
                var filePath = path.join(keywordDir, fileName);
                
                if (!fsSync.existsSync(filePath)) {
                    console.log('Missing: ' + fileName);
                    allFilesExist = false;
                } else {
                    console.log('Found: ' + fileName);
                }
            }
            
            if (!allFilesExist) {
                console.log('\n⚠️ Some article files are missing!');
                console.log('Starting article link extraction...\n');
                
                console.log('Initializing browser...');
                await scraper.initialize(false);
                
                console.log('Loading homepage (30 second delay for cookies)...');
                await scraper.landFirstPage();
                
                for (var i = 0; i < years.length; i++) {
                    var year = years[i];
                    var fileName = sanitizedKeyword + '-' + year + '_articles.csv';
                    var filePath = path.join(keywordDir, fileName);
                    
                    if (!fsSync.existsSync(filePath)) {
                        console.log('\n========================================');
                        console.log('Processing Year ' + (i + 1) + '/' + years.length + ': ' + year);
                        console.log('========================================\n');
                        
                        var csvFile = await scraper.scrapeWithFacetFilters(keyword, year.toString(), keywordDir);
                        console.log('Saved to: ' + csvFile);
                    }
                }
            } else {
                console.log('\n✅ All article files found!\n');
                
                console.log('Initializing browser for email extraction...');
                await scraper.initialize(false);
                
                console.log('Loading homepage (30 second delay for cookies)...');
                await scraper.landFirstPage();
            }
        }
        
        console.log('\n=== EXTRACTING AUTHOR EMAILS ===\n');
        
        for (var i = 0; i < years.length; i++) {
            var year = years[i];
            var articlesFileName = sanitizedKeyword + '-' + year + '_articles.csv';
            var articlesFilePath = path.join(keywordDir, articlesFileName);
            
            if (!fsSync.existsSync(articlesFilePath)) {
                console.log('⚠️ Skipping ' + year + ' - articles file not found');
                continue;
            }
            
            console.log('\n========================================');
            console.log('Extracting Emails for Year ' + (i + 1) + '/' + years.length + ': ' + year);
            console.log('========================================\n');
            
            await scraper.extractEmails(articlesFilePath, keyword, year.toString(), keywordDir);
            
            var emailsFileName = sanitizedKeyword + '-' + year + '_emails.csv';
            console.log('✅ Emails for ' + year + ' saved to: ' + emailsFileName);
        }
        
        console.log('\n========================================');
        console.log('  ALL OPERATIONS COMPLETED!');
        console.log('========================================');
        console.log('\nOutput saved in: ' + keywordDir);
        console.log('\nFiles created:');
        
        for (var i = 0; i < years.length; i++) {
            var year = years[i];
            console.log('  - ' + sanitizedKeyword + '-' + year + '_articles.csv');
            console.log('  - ' + sanitizedKeyword + '-' + year + '_emails.csv');
        }
        
        console.log('  - scraper_log.log');
        console.log('\n========================================\n');
        
    } catch (error) {
        console.error('\n❌ Error:', error.message);
        console.error('\nCheck the log file for details.');
    } finally {
        console.log('Closing browser...');
        await scraper.close();
        console.log('Done!\n');
    }
}

module.exports = ScienceDirectScraper;

if (require.main === module) {
    console.log('\nStarting ScienceDirect scraper...\n');
    main().catch(function(err) {
        console.error('Fatal error:', err);
        process.exit(1);
    });
}
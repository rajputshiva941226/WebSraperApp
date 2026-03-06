# Scraper Issues and Fixes - March 3, 2026

## Issues Reported

### 1. ✅ Emerald Scraper - Pagination Bug (FIXED)
**Problem:** Showing "81-4 of 4" and "441-4 of 4" - trying to access non-existent pages
**Root Cause:** Scraper calculated total_pages but didn't stop when pages had no results
**Fix Applied:** Added early termination when:
- "No results found" message appears
- No articles found on page
- No links extracted from page

**File:** `emerald_selenium.py` lines 252-318

---

### 2. ⚠️ BMJ Scraper - Not Starting
**Problem:** 
- Error: "Output file not found" 
- Searched locations show file path but file doesn't exist
- Scraper not creating output files

**Root Cause:** BMJ scraper exists and has proper error handling, but may be failing silently during execution

**Status:** Scraper code is active (lines 337-682 in `bmjjournal_selenium.py`)

**Recommended Actions:**
1. Check if BMJ scraper is actually running (check logs)
2. Verify ChromeDriver compatibility
3. Check if website structure changed
4. Add more verbose logging

---

### 3. ⚠️ MDPI Scraper - Chrome Version Mismatch
**Problem:** 
```
This version of ChromeDriver only supports Chrome version 146
Current browser version is 145.0.7632.117
```

**Root Cause:** `undetected_chromedriver` is downloading ChromeDriver v146 but user has Chrome v145 installed

**Current Code:** Uses `version_main=None` for auto-detection, but UC is still downloading wrong version

**Recommended Fix:** 
1. Manually detect Chrome version from Windows Registry
2. Pass exact version to `version_main` parameter
3. Clear ChromeDriver cache at `C:\Users\ragha\.wdm\drivers\chromedriver\`

**Manual Fix Required:**
```bash
# Delete cached ChromeDriver
rmdir /s "C:\Users\ragha\.wdm\drivers\chromedriver"

# Or delete the specific version folder
rmdir /s "C:\Users\ragha\.wdm\drivers\chromedriver\win64\145.0.7632.117"
```

---

### 4. ⚠️ Springer & Cambridge - Not Running
**Problem:** Both scrapers were working earlier but now failing

**Error from logs:**
```
Error: Message: session not created: cannot connect to chrome at 127.0.0.1:57062
This version of ChromeDriver only supports Chrome version 146
Current browser version is 145.0.7632.117
```

**Root Cause:** Same ChromeDriver version mismatch as MDPI

**Fix:** Same as MDPI - need to clear ChromeDriver cache

---

### 5. ❌ Error Messages Not Showing on Jobs Page
**Problem:** Failed jobs don't display error messages on UI

**Current Behavior:** 
- Job shows as "FAILED" status
- No error details visible to user
- User has to check logs manually

**Required Fix:** Update `jobs.html` to display `job.error` field in job cards

---

## Summary of Fixes Applied

### ✅ Completed
1. **Emerald Pagination** - Added early termination logic to stop when no results found
2. **Partial Results Handling** - System now extracts stats from partial CSV files on failure
3. **Download for Failed Jobs** - Can download partial results even when scraper fails

### ⚠️ Requires Manual Action
1. **Clear ChromeDriver Cache** - Delete `C:\Users\ragha\.wdm\drivers\chromedriver\` folder
2. **Restart Scrapers** - After clearing cache, restart the application

### 📋 Pending Implementation
1. **Error Display on UI** - Show error messages in job cards
2. **Chrome Version Detection** - Add registry-based version detection for MDPI
3. **BMJ Debugging** - Add more verbose logging to identify why it's not creating files

---

## Recommended Next Steps

### Immediate Actions (User)
1. **Stop the Flask server**
2. **Delete ChromeDriver cache:**
   ```powershell
   Remove-Item -Recurse -Force "C:\Users\ragha\.wdm\drivers\chromedriver"
   ```
3. **Restart the Flask server**
4. **Test scrapers again**

### Code Improvements Needed
1. Add error message display to jobs page UI
2. Implement Chrome version detection from registry
3. Add better logging for BMJ scraper
4. Add ChromeDriver cache cleanup on startup

---

## Files Modified

1. `emerald_selenium.py` - Fixed pagination logic
2. `app.py` - Added partial results extraction on failure
3. `jobs.html` - Added download buttons for failed jobs with partial results
4. `scraper.html` - Fixed form redirect and removed delay

---

## Testing Checklist

- [ ] Emerald scraper stops at correct page count
- [ ] BMJ scraper creates output files
- [ ] MDPI scraper uses correct Chrome version
- [ ] Springer scraper works after cache clear
- [ ] Cambridge scraper works after cache clear
- [ ] Error messages visible on jobs page
- [ ] Partial results downloadable for failed jobs

---

*Last Updated: March 3, 2026 7:20 PM IST*

# Scraper Issues - Manual Fixes Required

## ✅ FIXED: ChromeDriver Cache Cleared
The ChromeDriver cache has been cleared. On next run, it will download the correct version (145) instead of 146.

---

## 🔴 Issue 1: BMJ Scraper - Integer Parsing Error

**Error:** `invalid literal for int() with base 10: 'No'`

**Location:** `bmjjournal_selenium.py` line 471-472

**Current Code:**
```python
total_results_text = stats_element.text.split()[0].replace(",","").strip()
total_results = int(total_results_text)
```

**Fix:** Replace lines 471-472 with:
```python
stats_text = stats_element.text.strip()

# Check for "No results" case
if "No results" in stats_text or "0 results" in stats_text:
    self.logger.info("No results found for this search")
    return 0

total_results_text = stats_text.split()[0].replace(",","").strip()

# Validate it's a digit before parsing
if not total_results_text.isdigit():
    self.logger.warning(f"Could not parse total results from: {stats_text}")
    return 0

total_results = int(total_results_text)
```

---

## 🔴 Issue 2: Springer/Cambridge - Browser Closing Prematurely

**Error:** `no such window: target window already closed`

**Root Cause:** Browser is closing during initialization or being killed by anti-bot detection

**Fix Options:**

### Option A: Add headless mode detection and retry
In `sprngr_selenium.py` and `cambridge_scraper.py`, update driver initialization:

```python
# Add delay after driver init
time.sleep(2)

# Check if window is still alive
try:
    self.driver.current_url
except:
    # Reinitialize if window closed
    self.driver = uc.Chrome(options=chrome_options)
```

### Option B: Disable headless mode temporarily
Remove or comment out:
```python
chrome_options.add_argument('--headless')
```

---

## 🔴 Issue 3: Emerald - False Positive Results

**Error:** Shows 2,988,917 results, then "No results found" on page 1

**Location:** `emerald_selenium.py`

**Issue:** The total results counter includes ALL articles, not filtered by date range

**Current Detection:**
The scraper correctly detects "No results found" on page 1 and stops.

**Fix:** Add date validation or improve result detection logic:

```python
# After getting total results, verify first page has actual results
if total_pages > 0:
    # Navigate to page 1
    self.driver.get(f"{base_url}&page=1")
    time.sleep(2)
    
    # Check for "No results found" message
    no_results_text = ["No results found", "0 results", "no articles match"]
    page_content = self.driver.page_source.lower()
    
    if any(text.lower() in page_content for text in no_results_text):
        self.logger.warning("Total results shown but no actual results on page 1")
        return []
```

---

## 🔴 Issue 4: MDPI - ChromeDriver Version Mismatch

**Status:** Should be fixed by clearing cache

**If issue persists:** The MDPI scraper is completely commented out in `mdpi_app.py`. 

**Action Required:**
1. Uncomment the MdpiScrape class (lines 36-687)
2. Update to use latest Chrome detection like other scrapers
3. Test with a simple search

---

## 🔴 Issue 5: General ChromeDriver Version Detection

**Problem:** Auto-detection downloading ChromeDriver 146 for Chrome 145

**Permanent Fix:** Force version detection in all scrapers

Add to each scraper's initialization:

```python
import subprocess
import re

def get_chrome_version():
    """Detect installed Chrome version on Windows"""
    try:
        output = subprocess.check_output(
            r'reg query "HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon" /v version',
            shell=True
        ).decode('utf-8')
        version = re.search(r'(\d+\.\d+\.\d+\.\d+)', output).group(1)
        major_version = version.split('.')[0]
        return int(major_version)
    except:
        return None

# In driver initialization:
chrome_version = get_chrome_version()
if chrome_version:
    driver = uc.Chrome(options=options, version_main=chrome_version)
else:
    driver = uc.Chrome(options=options)
```

---

## 📋 Quick Fix Checklist

1. ✅ **Clear ChromeDriver cache** - DONE
2. ⬜ **Fix BMJ integer parsing** - Edit bmjjournal_selenium.py line 471-472
3. ⬜ **Add retry logic to Springer/Cambridge** - Add window check after init
4. ⬜ **Improve Emerald result validation** - Verify page 1 has results
5. ⬜ **Uncomment MDPI scraper** - Restore functionality in mdpi_app.py
6. ⬜ **Add Chrome version detection** - Implement in all scrapers

---

## Testing After Fixes

Run this test search:
- **Keyword:** cancer gene therapy (fix typo from "theraphy")
- **Date Range:** 2021-01-01 to 2021-03-31
- **Expected:** Should find some results in most journals

---

*Last Updated: 2026-03-03 23:18 IST*

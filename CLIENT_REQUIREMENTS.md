# Client Requirements - Academic Author Email Extraction Tool

**Client:** Satya Prabhu - Precision Business Insights (PBI)  
**Project Duration:** 6 weeks (1-2 months)  
**Total Budget:** ₹37,000  
**Date:** January 23, 2026

---

## Core Requirements

### 1. User Types & Access Control

#### Internal Users
- **Required Fields:**
  - Keyword (mandatory)
  - Conference Name (mandatory)
- **Special Privileges:**
  - Can upload master data for conferences
  - Can add scraped results to master database
  - Access to unique records based on email

#### External Users
- **Required Fields:**
  - Keyword only (mandatory)
- **Restrictions:**
  - Cannot access master database
  - Cannot upload conference data

#### Admin Users
- **Exclusive Access:**
  - Only admin can download master data
  - Full system access and control

---

### 2. Output & Results Management

#### CSV Generation
- ✅ **IMPLEMENTED:** Results generated in CSV format
- ✅ **IMPLEMENTED:** Unique records based on email addresses
- ⚠️ **PARTIAL:** Search history saved (currently in job_history, needs 7-day retention)

#### Search History
- **Requirement:** Save search history for 7 days
- **Current Status:** Job history exists but no automatic cleanup
- **TODO:** Implement 7-day auto-cleanup of old searches

#### Summary Report
- **Requirement:** After scraping completion, provide summary showing:
  - How many results scraped from each scraper
  - Per-keyword breakdown
- ✅ **IMPLEMENTED:** Basic stats shown in job cards
- **TODO:** Create comprehensive summary report view

---

### 3. Credit-Based System

**Requirement:** Deploy credit system for downloaded records

**Current Status:** ❌ NOT IMPLEMENTED

**TODO:**
- Implement user credit/token system
- Track downloads per user
- Deduct credits on download
- Show remaining credits to users
- Admin panel to manage user credits

---

### 4. Master Database System

#### Purpose
- Store all scraped author names and emails
- Maintain unique records based on email
- Conference-specific data organization

#### Features Required
- **Upload:** Internal users can upload conference master data
- **Append:** Scraped results automatically added to master DB
- **Uniqueness:** Email-based deduplication
- **Security:** Only admin can download master data
- **Access Control:** Strict permissions enforcement

**Current Status:** ❌ NOT IMPLEMENTED

**TODO:**
- Design master database schema
- Implement upload functionality
- Create auto-append mechanism
- Build admin download interface
- Add permission checks

---

### 5. User Licensing System

**Requirement:** User access based on license type

**License Types:**
- **Single License:** Runs on one PC only
- **Multi-License:** (To be defined)

**Current Status:** ❌ NOT IMPLEMENTED

**TODO:**
- Implement machine ID/fingerprinting
- License validation system
- User authentication
- License management panel

---

### 6. AWS Deployment

**Requirement:** Tool deployment on AWS

**Current Status:** ⚠️ PENDING CLIENT AWS ACCESS

**TODO:**
- Receive AWS credentials from client
- Set up EC2/ECS instance
- Configure database (RDS/DynamoDB)
- Set up S3 for file storage
- Configure security groups
- Set up domain and SSL
- Implement backup strategy

---

## Scrapers to Implement

### Currently Implemented (14/15)
1. ✅ EuropePMC
2. ✅ PubMed NCBI
3. ✅ Springer
4. ✅ Cambridge
5. ✅ Oxford
6. ✅ Lippincott
7. ✅ SAGE Journals
8. ✅ Emerald Insight
9. ✅ BMJ Journal
10. ✅ Nature
11. ✅ MDPI
12. ⚠️ PubMed (duplicate of #2?)
13. ❌ ScienceDirect (NOT IMPLEMENTED)
14. ❌ Taylor & Francis (NOT IMPLEMENTED)
15. ❌ Wiley (NOT IMPLEMENTED)

### TODO: Implement Missing Scrapers
- **ScienceDirect** (Elsevier)
- **Taylor & Francis**
- **Wiley Online Library**

---

## Recently Implemented Features

### ✅ Partial Results Handling (Just Completed)
- Scrapers that fail due to network errors now:
  - Check for any CSV files written before failure
  - Calculate stats (emails, authors, links) from partial data
  - Display partial results count in error message
  - Enable CSV/XLSX download for partial results
  - Show "⚠️ Partial Results" indicator on failed jobs

### ✅ Download Enhancements
- Both CSV and XLSX download options
- XLSX includes statistics sheet with:
  - Total records
  - Unique emails, authors, URLs
  - Scraper info, keyword, date range
  - Completion timestamp

### ✅ Form & Navigation Fixes
- Immediate redirect to jobs page after submission
- Fixed infinite polling loop on jobs page
- Proper interval cleanup when jobs complete

---

## Priority Implementation Roadmap

### Phase 1: Core Functionality (Current)
- ✅ Basic scraping for 12+ journals
- ✅ CSV/XLSX output
- ✅ Job management and progress tracking
- ✅ Partial results handling

### Phase 2: User Management (Next)
1. User authentication system
2. Role-based access (Admin, Internal, External)
3. License validation
4. Credit/token system

### Phase 3: Master Database
1. Database schema design
2. Conference master data upload
3. Auto-append scraped results
4. Admin-only download
5. Deduplication logic

### Phase 4: Missing Scrapers
1. ScienceDirect implementation
2. Taylor & Francis implementation
3. Wiley implementation

### Phase 5: AWS Deployment
1. Infrastructure setup
2. Database migration
3. File storage configuration
4. Security hardening
5. Production deployment

---

## Technical Debt & Improvements Needed

### Current Issues
1. **Search History Retention:** No 7-day auto-cleanup
2. **No Authentication:** Open access to all features
3. **No Credit System:** Unlimited downloads
4. **No Master DB:** Results not persisted long-term
5. **No License Validation:** Can run on any machine
6. **ChromeDriver Version Issues:** Still seeing version 146 errors occasionally

### Performance Optimizations
- Implement result caching
- Add database indexing
- Optimize CSV parsing for large files
- Add pagination for job history

### Security Enhancements
- Add user authentication
- Implement API rate limiting
- Add input validation and sanitization
- Secure file upload/download
- Add audit logging

---

## Notes from Client Call

1. **Conference Name Field:** Mandatory for internal users, helps organize data by conference
2. **Unique Records:** All deduplication based on email addresses
3. **7-Day History:** Automatic cleanup of old search records
4. **Per-Scraper Summary:** Show breakdown of results by each journal scraper
5. **Master Data Security:** Critical that only admin can download master database
6. **AWS Access:** Client will provide credentials for deployment

---

## Contact Information

**Client Contact:** Satya Prabhu  
**Email:** sathya@precisionbusinessinsights.com  
**Organization:** Precision Business Insights (PBI)  
**CC:** Kalyan

---

*Last Updated: March 3, 2026*

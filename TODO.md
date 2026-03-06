# TODO: Fix Jobs Stats - Scraper Logs and Stats Display

## Tasks:
- [ ] 1. Update scraper_adapter.py to pass current_url and links_count to callback
- [ ] 2. Add log capture mechanism in scraper_adapter.py
- [ ] 3. Update app.py callback to receive and store logs
- [ ] 4. Ensure links_count is properly stored when job completes
- [ ] 5. Expose logs through the API endpoint
- [ ] 6. Update templates/jobs.html to display scraper logs
- [ ] 7. Verify links count is displayed properly

## Implementation Order:
1. scraper_adapter.py - Add progress parameters and log capture
2. app.py - Update callback and API to handle logs
3. templates/jobs.html - Add log display section

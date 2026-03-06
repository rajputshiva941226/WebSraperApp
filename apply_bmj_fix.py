"""
Script to fix BMJ scraper integer parsing error
"""

import re

# Read the file
with open('bmjjournal_selenium.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the problematic section
old_pattern = r'            total_results_text = stats_element\.text\.split\(\)\[0\]\.replace\(",",""\)\.strip\(\)\n            total_results = int\(total_results_text\)'

new_code = '''            stats_text = stats_element.text.strip()
            
            # Check for "No results" case
            if "No results" in stats_text or "0 results" in stats_text:
                self.logger.info("No results found for this search")
                return 0
            
            total_results_text = stats_text.split()[0].replace(",","").strip()
            
            # Validate it's a digit before parsing
            if not total_results_text.isdigit():
                self.logger.warning(f"Could not parse total results from: {stats_text}")
                return 0
            
            total_results = int(total_results_text)'''

# Apply the replacement
content_fixed = re.sub(old_pattern, new_code, content)

# Check if replacement was successful
if content_fixed != content:
    with open('bmjjournal_selenium.py', 'w', encoding='utf-8') as f:
        f.write(content_fixed)
    print("✅ BMJ scraper fixed successfully!")
else:
    print("⚠️ Pattern not found - manual fix required")
    print("\nSearching for line...")
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'total_results_text = stats_element.text.split()' in line:
            print(f"Found at line {i+1}: {line}")

"""
Fix Cambridge browser closing issue
"""

with open('cambridge_scraper.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the correct section for Cambridge
old_section = """        self.wait = WebDriverWait(self.driver, 60)
        self.directory = sanitize_filename(keyword)"""

new_section = """        self.wait = WebDriverWait(self.driver, 60)
        
        # Verify window is still open after initialization
        time.sleep(2)
        try:
            _ = self.driver.current_url
        except:
            print("Window closed during init, reinitializing...")
            self.driver = uc.Chrome(
                options=self.options,
                driver_executable_path=driver_path,
                version_main=None,
                use_subprocess=False
            )
            self.wait = WebDriverWait(self.driver, 60)
        
        self.directory = sanitize_filename(keyword)"""

if old_section in content:
    content = content.replace(old_section, new_section)
    with open('cambridge_scraper.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("✅ Cambridge scraper fixed!")
else:
    print("⚠️ Pattern not found, trying alternative...")
    # Show what we found
    if "self.wait = WebDriverWait(self.driver, 60)" in content:
        print("Found WebDriverWait line")
    if "self.directory = sanitize_filename(keyword)" in content:
        print("Found directory line")

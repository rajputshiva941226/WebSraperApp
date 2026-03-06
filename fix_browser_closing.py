"""
Fix Springer and Cambridge browser closing issue by adding window validation
"""

def fix_springer():
    with open('sprngr_selenium.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find the section after driver initialization
    old_section = """        self.wait = WebDriverWait(self.driver, 30)
        
        self.directory = keyword.replace(" ","-")"""
    
    new_section = """        self.wait = WebDriverWait(self.driver, 30)
        
        # Verify window is still open after initialization
        time.sleep(2)
        try:
            _ = self.driver.current_url
        except:
            self.logger.warning("Window closed during init, reinitializing...")
            self.driver = uc.Chrome(
                options=self.options,
                driver_executable_path=driver_path,
                version_main=None,
                use_subprocess=False
            )
            self.wait = WebDriverWait(self.driver, 30)
        
        self.directory = keyword.replace(" ","-")"""
    
    if old_section in content:
        content = content.replace(old_section, new_section)
        with open('sprngr_selenium.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print("✅ Springer scraper fixed!")
        return True
    else:
        print("⚠️ Springer pattern not found")
        return False

def fix_cambridge():
    with open('cambridge_scraper.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find the section after driver initialization
    old_section = """        self.wait = WebDriverWait(self.driver, 30)
        
        self.directory = keyword.replace(" ","-")"""
    
    new_section = """        self.wait = WebDriverWait(self.driver, 30)
        
        # Verify window is still open after initialization
        time.sleep(2)
        try:
            _ = self.driver.current_url
        except:
            if hasattr(self, 'logger'):
                self.logger.warning("Window closed during init, reinitializing...")
            self.driver = uc.Chrome(
                options=self.options,
                driver_executable_path=driver_path,
                version_main=None,
                use_subprocess=False
            )
            self.wait = WebDriverWait(self.driver, 30)
        
        self.directory = keyword.replace(" ","-")"""
    
    if old_section in content:
        content = content.replace(old_section, new_section)
        with open('cambridge_scraper.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print("✅ Cambridge scraper fixed!")
        return True
    else:
        print("⚠️ Cambridge pattern not found")
        return False

if __name__ == "__main__":
    springer_ok = fix_springer()
    cambridge_ok = fix_cambridge()
    
    if springer_ok and cambridge_ok:
        print("\n✅ All browser closing fixes applied successfully!")
    else:
        print("\n⚠️ Some fixes could not be applied - check patterns manually")

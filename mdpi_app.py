# from selenium  import webdriver
# import pandas as pd
# import selenium.webdriver.support.expected_conditions as EC
# 
# 
# 
# import undetected_chromedriver as uc
# import os, time, subprocess, random

# ### Function to use Express VPN for changing IP address to avoid bot detection ####
# ### I've commented this function call below as some users may not use Express VPN
# def ChangeVPN():
#     countries = ["Georgia","Serbia","Moldova",'"North Macedonia"',"Jersey","Monaco","Slovakia",'Lebanon','Argentina',
#                     "Slovenia","Croatia","Albania","Cyprus","Liechtenstein","Malta","Ukraine",'Ghana','Chile','Colombia',
#                     "Belarus","Bulgaria","Hungary","Luxembourg","Montenegro","Andorra",'Morocco','Honduras','Guatemala',
#                     '"Czech Republic"',"Estonia","Latvia","Lithuania","Poland","Armenia","Austria",'Cuba','Panama',
#                     "Portugal","Greece","Finland","Belgium","Denmark","Norway","Iceland","Ireland",'Bermuda','Mexico',
#                     "Spain","Romania","Italy","Sweden","Turkey","Singapore",'Kenya','Israel','"South Africa"','Canada',
#                     "Australia",'"South Korea - 2"',"Malaysia","Pakistan",'"Sri Lanka"',"Kazakhstan",'Bahamas','Brazil',
#                     "Thailand","Indonesia",'"New Zealand"',"Cambodia","Vietnam","Macau",'Jamaica',
#                     "Mongolia","Laos","Bangladesh","Uzbekistan","Myanmar","Nepal","Brunei","Bhutan",'Venezuela',
#                     '"United Kingdom"', '"United States"',"Japan", "Germay", '"Hong Kong"', "Netherlands",'Bolivia',
#                     "Switzerland","Algeria","France","Egypt"] 
#     choice = random.choice(countries)
#     print(f"Selected Country is {choice}")
#     os.environ["ExpressVPN"] = os.pathsep + r"C:\Program Files (x86)\ExpressVPN\services"
    
#     process = subprocess.Popen(["powershell","ExpressVPN.CLI.exe", "disconnect"], shell=True)
#     result = process.communicate()[0]
#     print(result)
#     process = subprocess.Popen(["powershell","ExpressVPN.CLI.exe", "connect",
#                         f"{str(choice)}"],shell=True)
#     result = process.communicate()[0]
#     print(result)    

# class MdpiScrape(uc.Chrome):
    
#     def __init__(self,
#                 keep_alive=True, keyword = ''):
        
#         data_dir = keyword.replace(' ','_')
        
#         if not os.path.exists(os.getcwd()+'\\' +data_dir):
             
#             os.mkdir(data_dir)
#         chrome_options = uc.ChromeOptions()
#         prefs = {"download.default_directory" : os.getcwd()+'\\' +data_dir}
#         chrome_options.add_experimental_option("prefs",prefs)
#         chrome_options.add_argument("--disable-lazy-loading")
#         chrome_options.add_argument("--remote-allow-origins=*")
#         chrome_options.add_argument("--disable-print-preview")
        
#         chrome_options.add_argument("--disable-stack-profiler")
#         chrome_options.add_argument("--disable-background-networking")
        
#         chrome_options.add_argument("--no-sandbox")
#         chrome_options.add_argument("excludeSwitches=enable-automation")
#         chrome_options.add_argument("--disable-infobars")
#         chrome_options.add_argument("--disable-browser-side-navigation")
#         chrome_options.add_argument("--disable-notifications")
#         chrome_options.add_argument("--disable-blink-features=AutomationControlled")
#         chrome_options.add_argument("--disable-popup-blocking")
        
#         script_dir = os.path.dirname(os.path.abspath(__file__))
#         print(f"Current Working Dir: {script_dir}")
#         #chromeProfile = "\Includes\Data_files\data\Chrome_profile"
#         ## Add your chrome executable location as browser_path ##
#         #browser_path = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
#         #print(f"Browser Executable Path is : {os.path.join(script_dir,browser_path)}")
#         super(MdpiScrape, self).__init__(options=chrome_options)
#                                             #browser_executable_path=browser_path,
#                                             #suppress_welcome=True,debug=True,keep_alive=True,
#                                             #user_multi_procs=False)#user_data_dir= os.getcwd()+chromeProfile), version_main=121, 
#         self.keep_alive = keep_alive
        
#         self.maximize_window()
        
        
#     def __exit__(self,exc_type , exc_val, exc_to):
#         if not self.keep_alive:
#             print(f" Check for processes still running ? {self.service.assert_process_still_running()}")
#             print(f"Service.process.pid for chrome bot is : {self.service.process.pid}")
#             self.stop_client()
#             self.service._terminate_process()
#             #subprocess.run(['kill',f'{self.service.process.pid}'],shell=True)
            
#             self.quit()
        
#     def land_first_page(self):
#         #self.execute_script("window.open('');")
#         #self.switch_to.window(self.window_handles[0])
#         self.get('https://www.mdpi.com/user/login/') 
        
#         username = self.find_element(By.ID, 'username')
#         username.send_keys("pritham.pgc@gmail.com")
#         password = self.find_element(By.ID, 'password')
#         password.send_keys('PgC@500072')
        
#         submit = self.find_element(By.XPATH, '//input[@class="button submit-btn"]')
#         submit.click()
        
        
#     ## Function to get total number of result pages for your serch query ##   
#     def extractPages(self, st_yr, end_yr,keyword):
                  
#         self.get(f'https://www.mdpi.com/search?sort=pubdate&page_count=200&year_from={st_yr}&year_to={end_yr}&q={keyword}&view=compact') 
#         #WebDriverWait(self, 20).until(EC.element_to_be_clickable((By.ID,'CybotCookiebotDialogBodyLevelButtonLevelOptinAllowallSelection'))).click()
#         # accept_button = WebDriverWait(self, 10).until(EC.element_to_be_clickable((By.ID, "accept")))
#         # accept_button.click()
#         pages = self.find_element(By.XPATH, '//div[@class="columns large-6 medium-6 small-12"]')
#         print(pages.text)
#         total_pages = int(pages.text.split('of')[1].replace('.','').strip())
        
#         print(f'total pages ==> {total_pages}')
#         return total_pages
    
#     ## Function to download data in tabular format from links of articles ##
#     def extractEmails(self, page_no,start_yr, end_yr, keyword):
        
#             try:   
#                 self.get(f'https://www.mdpi.com/search?sort=pubdate&page_no={str(page_no+1)}&page_count=200&year_from={start_yr}&year_to={end_yr}&q={keyword}&view=compact')
#                 WebDriverWait(self, 60).until(EC.element_to_be_clickable((By.XPATH, '//a[@class="export-options-show export-element export-expanded"]'))).click()
#                 time.sleep(5)
#                 print('@'*10)
#                 #print(show_export.text)
#                 #show_export.click()
#                 checkbox = self.find_element(By.ID, 'selectUnselectAll')
#                 checkbox.click()
#                 self.find_element(By.XPATH, '//div[@class="listing-export"]').click()
#                 self.find_element(By.XPATH, '//div[@class="chosen-drop"]/ul/li[contains(text(), "Tab-delimited")]').click()
#                 time.sleep(5)
#                 self.find_element(By.ID, 'articleBrowserExport_top').click()
#             except Exception as e:
#                 print(f'Exception occurred while downloading file: ==> {str(e)}')
#                 ## ChangeVPN()
#                 ## uncomment above line if you use Express VPN
#                 curr_page = page_no
                    
#                 time.sleep(10)
                    
#                 self.refresh()
#                 pass
                    
                   
# ##########################################################################

# if __name__ == '__main__':
#     keyword_input = input('Enter any Keyword: ')
#     start_year = input('Enter Start Year (e.g., 2017): ')
#     end_year = input('Enter End Year (e.g., 2024): ')

#     #ChangeVPN()
#     with MdpiScrape(keyword=keyword_input) as bot:
#         bot.land_first_page()
#         pages_number = bot.extractPages(st_yr=start_year,end_yr=end_year,keyword=keyword_input)
#         for i in range(pages_number):
#             print(i)
#             bot.extractEmails(page_no=i,start_yr=start_year,end_yr=end_year,keyword=keyword_input)
#         time.sleep(10)
#         os.system(r'.\\kill.bat ' + str(bot.browser_pid))
                    
#         ########################################
#         ######## Parse downloaded files ########
#         ########################################
#     files_in_cwd = os.listdir(os.getcwd()+ '\\'+ keyword_input.replace(' ','_'))
#     txt_files = [keyword_input.replace(' ','_')+'\\'+file for file in files_in_cwd if '.txt' in file]
#     print('&&&&&&&&&&&&&')
#     print(txt_files)
#     input_files = keyword_input.replace(" ","_")+"\\" + '*.txt'
#     out_file = keyword_input.replace(" ","_")+"\\" + keyword_input.replace(" ","_")+"_results.txt"
#     copy_process = subprocess.Popen(['powershell', 'Get-Content', input_files, '| Set-Content', out_file], shell=True)
#     result = copy_process.communicate()[0]
#     print(result)
#     df = pd.read_csv(out_file, sep = '\t',skip_blank_lines=True, skipinitialspace=True)
#     df.rename(columns = {'AUTHOR':'names', 'EMAIL ':'emails'}, inplace = True)
#     print(df)
#     df2 = df[['names', 'emails']].copy(deep=True)
    
#     del df
#     df2['names'].mask(df2['names'].str.contains(';') == True, other = df2['names'].str.split(';'), inplace = True)
#     df2['emails'].mask(df2['emails'].str.contains(';') == True, other = df2['emails'].str.split(';'), inplace = True)

#     #df2=df2.set_index(['names', 'emails']).apply(pd.Series.explode).reset_index()
#     df2['len_names'] = df2['names'].str.len()
#     df2['len_mails'] = df2['emails'].str.len()
#     df3 = df2[df2['len_names'] == df2['len_mails']].copy(deep=True)
#     df3 = df3.explode(['names','emails'])
#     df3.reset_index(drop = True)
#     df3['names']=df3['names'].str.strip()
#     df3['emails']=df3['emails'].str.strip()
#     df3[['Last_Name','First_Name']] = df3['names'].str.split(',',n=1, expand = True)

#     df3['First_Name'] = df3['First_Name'].str.strip()
#     df3['Last_Name'] = df3['Last_Name'].str.strip()
#     df3['Names'] = df3['First_Name'] + " " + df3['Last_Name']
    
#     #for file in txt_files:
#     df4 = df3.loc[:,['emails', 'Names']].copy(deep=True)
#     df5 = df4[df4['emails'] != ''].copy(deep=True)
#     df6 = df5.drop_duplicates('emails')
#     df6.to_csv(out_file.replace('.txt', '')+'.csv', encoding = 'utf-8', index = False)
#     del df3, df2, df4, df5 , df6 
    
#     print('Results are successfully Saved....')
       

##########################################################################################
### New Version with Python 3.15 on date 9 Nov 2025
###########################################################################################
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
import selenium.webdriver.support.expected_conditions as EC
import pandas as pd

import undetected_chromedriver as uc
import os, time, subprocess, random

### Function to use Express VPN for changing IP address to avoid bot detection ####
### I've commented this function call below as some users may not use Express VPN
def ChangeVPN():
    countries = ["Georgia","Serbia","Moldova",'"North Macedonia"',"Jersey","Monaco","Slovakia",'Lebanon','Argentina',
                    "Slovenia","Croatia","Albania","Cyprus","Liechtenstein","Malta","Ukraine",'Ghana','Chile','Colombia',
                    "Belarus","Bulgaria","Hungary","Luxembourg","Montenegro","Andorra",'Morocco','Honduras','Guatemala',
                    '"Czech Republic"',"Estonia","Latvia","Lithuania","Poland","Armenia","Austria",'Cuba','Panama',
                    "Portugal","Greece","Finland","Belgium","Denmark","Norway","Iceland","Ireland",'Bermuda','Mexico',
                    "Spain","Romania","Italy","Sweden","Turkey","Singapore",'Kenya','Israel','"South Africa"','Canada',
                    "Australia",'"South Korea - 2"',"Malaysia","Pakistan",'"Sri Lanka"',"Kazakhstan",'Bahamas','Brazil',
                    "Thailand","Indonesia",'"New Zealand"',"Cambodia","Vietnam","Macau",'Jamaica',
                    "Mongolia","Laos","Bangladesh","Uzbekistan","Myanmar","Nepal","Brunei","Bhutan",'Venezuela',
                    '"United Kingdom"', '"United States"',"Japan", "Germay", '"Hong Kong"', "Netherlands",'Bolivia',
                    "Switzerland","Algeria","France","Egypt"] 
    choice = random.choice(countries)
    print(f"Selected Country is {choice}")
    os.environ["ExpressVPN"] = os.pathsep + r"C:\Program Files (x86)\ExpressVPN\services"
    
    process = subprocess.Popen(["powershell","ExpressVPN.CLI.exe", "disconnect"], shell=True)
    result = process.communicate()[0]
    print(result)
    process = subprocess.Popen(["powershell","ExpressVPN.CLI.exe", "connect",
                        f"{str(choice)}"],shell=True)
    result = process.communicate()[0]
    print(result)    

class MdpiScrape(uc.Chrome):
    
    def __init__(self,
                keep_alive=True, keyword = ''):
        
        data_dir = keyword.replace(' ','_')
        
        if not os.path.exists(os.path.join(os.getcwd(), data_dir)):
            os.makedirs(data_dir, exist_ok=True)
        
        chrome_options = uc.ChromeOptions()
        prefs = {
            "download.default_directory": os.path.join(os.getcwd(), data_dir),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": False,
            "plugins.always_open_pdf_externally": True
        }
        chrome_options.add_experimental_option("prefs", prefs)
        chrome_options.add_argument("--disable-lazy-loading")
        chrome_options.add_argument("--remote-allow-origins=*")
        chrome_options.add_argument("--disable-print-preview")
        chrome_options.add_argument("--disable-stack-profiler")
        chrome_options.add_argument("--disable-background-networking")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("excludeSwitches=enable-automation")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-browser-side-navigation")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        # Run in headless mode for server environments
        chrome_options.add_argument("--headless=new")
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        print(f"Current Working Dir: {script_dir}")
        
        # Force undetected_chromedriver to detect Chrome version instead of using cached driver
        try:
            super(MdpiScrape, self).__init__(
                options=chrome_options, 
                version_main=None,  # Auto-detect installed Chrome version
                use_subprocess=False,
                driver_executable_path=None  # Don't use cached path, force detection
            )
        except Exception as e:
            print(f"Error initializing Chrome with auto-detection: {e}")
            # Fallback: create fresh ChromeOptions to avoid reuse error
            fallback_options = uc.ChromeOptions()
            fallback_prefs = {
                "download.default_directory": os.path.join(os.getcwd(), data_dir),
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": False,
                "plugins.always_open_pdf_externally": True
            }
            fallback_options.add_experimental_option("prefs", fallback_prefs)
            fallback_options.add_argument("--disable-lazy-loading")
            fallback_options.add_argument("--remote-allow-origins=*")
            fallback_options.add_argument("--no-sandbox")
            fallback_options.add_argument("--disable-gpu")
            fallback_options.add_argument("--disable-dev-shm-usage")
            super(MdpiScrape, self).__init__(options=fallback_options, use_subprocess=False)
        
        self.keep_alive = keep_alive
        self.maximize_window()
        
    def __exit__(self, exc_type, exc_val, exc_to):
        if not self.keep_alive:
            print(f"Check for processes still running ? {self.service.assert_process_still_running()}")
            print(f"Service.process.pid for chrome bot is : {self.service.process.pid}")
            self.stop_client()
            self.service._terminate_process()
            self.quit()
    
    def handle_cookie_consent(self):
        """Handle cookie consent dialog if it appears"""
        try:
            # First check if the dialog container exists
            dialog = WebDriverWait(self, 5).until(
                EC.presence_of_element_located((By.ID, "usercentrics-cmp-ui"))
            )
            print("Cookie consent dialog detected")
            
            # Try to click Accept All button using JavaScript directly
            accept_clicked = self.execute_script("""
                try {
                    // Try to find and click the accept button
                    var acceptBtn = document.querySelector('button[data-action="consent"][data-action-type="accept"]') ||
                                   document.querySelector('button.uc-accept-button') ||
                                   document.getElementById('accept') ||
                                   document.querySelector('button[id="accept"]');
                    
                    if (acceptBtn) {
                        acceptBtn.click();
                        return true;
                    }
                    return false;
                } catch(e) {
                    return false;
                }
            """)

            if accept_clicked:
                print("Cookie consent accepted via JavaScript")
                time.sleep(3)
                return True
            else:
                print("Could not find accept button, removing dialog")
                # Remove the dialog entirely
                self.execute_script("""
                    var dialog = document.getElementById('usercentrics-cmp-ui');
                    if (dialog) {
                        dialog.style.display = 'none';
                        dialog.remove();
                    }
                    var overlay = document.querySelector('[data-nosnippet]');
                    if (overlay) {
                        overlay.style.display = 'none';
                        overlay.remove();
                    }
                """)
                time.sleep(2)
                return True
            
        except Exception as e:
            # No dialog present - this is fine
            return False
    
    def land_first_page(self):
        self.get('https://www.mdpi.com/user/login/') 
        
        # Handle cookie consent first
        self.handle_cookie_consent()
        
        username = self.find_element(By.ID, 'username')
        username.send_keys("pritham.pgc@gmail.com")
        password = self.find_element(By.ID, 'password')
        password.send_keys('PgC@500072')
        
        submit = self.find_element(By.XPATH, '//input[@class="button submit-btn"]')
        submit.click()
        time.sleep(3)
        
    ## Function to get total number of result pages for your search query ##   
    def extractPages(self, st_yr, end_yr, keyword):
        self.get(f'https://www.mdpi.com/search?sort=pubdate&page_count=200&year_from={st_yr}&year_to={end_yr}&q={keyword}&view=compact') 
        
        # Handle cookie consent if it appears on search page
        self.handle_cookie_consent()
        
        # Wait for the page to load
        pages = WebDriverWait(self, 20).until(
            EC.presence_of_element_located((By.XPATH, '//div[@class="columns large-6 medium-6 small-12"]'))
        )
        print(pages.text)
        total_pages = int(pages.text.split('of')[1].replace('.','').strip())
        
        print(f'total pages ==> {total_pages}')
        return total_pages
    
    ## Function to download data in tabular format from links of articles ##
    def extractEmails(self, page_no, start_yr, end_yr, keyword):
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:   
                print(f"\nAttempt {retry_count + 1} for page {page_no + 1}")
                self.get(f'https://www.mdpi.com/search?sort=pubdate&page_no={str(page_no+1)}&page_count=200&year_from={start_yr}&year_to={end_yr}&q={keyword}&view=compact')
                
                # Handle cookie consent if it appears - CRITICAL for this page
                self.handle_cookie_consent()
                
                # Wait for page to fully load
                time.sleep(3)
                
                # Check if "Show export options" is visible and click it
                try:
                    show_export = WebDriverWait(self, 10).until(
                        EC.element_to_be_clickable((By.XPATH, '//a[contains(@class, "export-options-show")]'))
                    )
                    print("Found 'Show export options' button")
                    show_export.click()
                    print("Clicked 'Show export options'")
                    time.sleep(2)
                except Exception as e:
                    print(f"Could not find/click 'Show export options': {str(e)}")
                
                print('@'*10)
                
                # Select all checkbox - use regular click
                print("Looking for 'Select all' checkbox...")
                checkbox = WebDriverWait(self, 10).until(
                    EC.element_to_be_clickable((By.ID, 'selectUnselectAll'))
                )
                print("Found checkbox, clicking...")
                checkbox.click()
                print("Checkbox clicked")
                time.sleep(2)
                
                # Click listing export dropdown - use regular click like before
                print("Looking for format dropdown...")
                listing_export = WebDriverWait(self, 10).until(
                    EC.element_to_be_clickable((By.XPATH, '//div[@class="listing-export"]'))
                )
                print("Found dropdown, clicking...")
                listing_export.click()
                print("Dropdown clicked")
                time.sleep(3)
                
                # Select Tab-delimited format - use regular click
                print("Looking for 'Tab-delimited' option...")
                tab_delimited = WebDriverWait(self, 10).until(
                    EC.element_to_be_clickable((By.XPATH, '//div[@class="chosen-drop"]/ul/li[contains(text(), "Tab-delimited")]'))
                )
                print("Found 'Tab-delimited' option, clicking...")
                tab_delimited.click()
                print("Tab-delimited selected")
                time.sleep(3)
                
                # Click final export button - use regular click
                print("Looking for final Export button...")
                final_export = WebDriverWait(self, 10).until(
                    EC.element_to_be_clickable((By.ID, 'articleBrowserExport_top'))
                )
                print("Found Export button, clicking...")
                final_export.click()
                print("Export button clicked")
                
                # Wait for download to complete
                print("Waiting for download...")
                time.sleep(6)
                print(f"✓ Page {page_no+1} downloaded successfully")
                return  # Success, exit the retry loop
                
            except Exception as e:
                retry_count += 1
                print(f'✗ Exception on page {page_no+1}, attempt {retry_count}: {str(e)}')
                
                if retry_count < max_retries:
                    print(f"Retrying in 5 seconds...")
                    time.sleep(5)
                    self.refresh()
                else:
                    print(f"Failed to download page {page_no+1} after {max_retries} attempts")
                    ## ChangeVPN()
                    ## uncomment above line if you use Express VPN
                   
##########################################################################

if __name__ == '__main__':
    keyword_input = input('Enter any Keyword: ')
    start_year = input('Enter Start Year (e.g., 2017): ')
    end_year = input('Enter End Year (e.g., 2024): ')

    #ChangeVPN()
    with MdpiScrape(keyword=keyword_input) as bot:
        bot.land_first_page()
        pages_number = bot.extractPages(st_yr=start_year, end_yr=end_year, keyword=keyword_input)
        
        for i in range(pages_number):
            print(f"Processing page {i+1} of {pages_number}")
            bot.extractEmails(page_no=i, start_yr=start_year, end_yr=end_year, keyword=keyword_input)
            
        time.sleep(10)
        os.system(r'.\\kill.bat ' + str(bot.browser_pid))
                    
        ########################################
        ######## Parse downloaded files ########
        ########################################
    print("\n" + "="*50)
    print("Processing downloaded files...")
    print("="*50 + "\n")
    
    data_dir = keyword_input.replace(' ', '_')
    data_dir_path = os.path.join(os.getcwd(), data_dir)
    files_in_cwd = os.listdir(data_dir_path)
    txt_files = [os.path.join(data_dir_path, f) for f in files_in_cwd if f.endswith('.txt')]
    
    if not txt_files:
        print("No text files found to process")
        exit()
    
    out_file = os.path.join(data_dir_path, data_dir + "_results.txt")
    
    # Combine all text files using Python (cross-platform)
    with open(out_file, 'w', encoding='utf-8') as outf:
        for txt_file in txt_files:
            try:
                with open(txt_file, 'r', encoding='utf-8', errors='replace') as inf:
                    outf.write(inf.read())
            except Exception:
                pass
            
    # Process the combined file
    df = pd.read_csv(out_file, sep='\t', skip_blank_lines=True, skipinitialspace=True)
    df.rename(columns={'AUTHOR':'names', 'EMAIL ':'emails'}, inplace=True)
    
    df2 = df[['names', 'emails']].copy(deep=True)
    del df
    
    # Split multiple authors/emails
    df2['names'].mask(df2['names'].str.contains(';') == True, other=df2['names'].str.split(';'), inplace=True)
    df2['emails'].mask(df2['emails'].str.contains(';') == True, other=df2['emails'].str.split(';'), inplace=True)

    # Check length matching
    df2['len_names'] = df2['names'].str.len()
    df2['len_mails'] = df2['emails'].str.len()
    df3 = df2[df2['len_names'] == df2['len_mails']].copy(deep=True)
    df3 = df3.explode(['names','emails'])
    df3.reset_index(drop=True, inplace=True)
    
    # Clean and format names
    df3['names'] = df3['names'].str.strip()
    df3['emails'] = df3['emails'].str.strip()
    df3[['Last_Name','First_Name']] = df3['names'].str.split(',', n=1, expand=True)

    df3['First_Name'] = df3['First_Name'].str.strip()
    df3['Last_Name'] = df3['Last_Name'].str.strip()
    df3['Names'] = df3['First_Name'] + " " + df3['Last_Name']
    
    # Final cleanup
    df4 = df3.loc[:,['emails', 'Names']].copy(deep=True)
    df5 = df4[df4['emails'] != ''].copy(deep=True)
    df6 = df5.drop_duplicates('emails')
    
    output_csv = out_file.replace('.txt', '') + '.csv'
    df6.to_csv(output_csv, encoding='utf-8', index=False)
    
    del df3, df2, df4, df5, df6
    
    print(f"\n{'='*50}")
    print(f"Results successfully saved to: {output_csv}")
    
    print(f"{'='*50}\n")


##########################################################################################
### Wrapper class for integration with scraper_adapter
##########################################################################################

class MdpiScraperAdapter:
    """Adapter class to make MdpiScrape compatible with the unified scraper interface"""
    
    def __init__(self, keyword, start_year, end_year, driver_path=None):
        """
        Initialize MDPI scraper with standard interface
        
        Args:
            keyword: Search keyword
            start_year: Start year in MM/DD/YYYY format
            end_year: End year in MM/DD/YYYY format
            driver_path: Not used for MDPI (uses undetected_chromedriver)
        """
        self.keyword = keyword
        # Extract year from date format MM/DD/YYYY
        self.start_year = start_year.split('/')[-1] if '/' in start_year else start_year
        self.end_year = end_year.split('/')[-1] if '/' in end_year else end_year
        self.driver_path = driver_path
        self.output_file = None
        
    def run(self):
        """Run the MDPI scraper and return output file path"""
        try:
            with MdpiScrape(keyword=self.keyword) as bot:
                bot.land_first_page()
                pages_number = bot.extractPages(
                    st_yr=self.start_year, 
                    end_yr=self.end_year, 
                    keyword=self.keyword
                )
                
                for i in range(pages_number):
                    print(f"Processing page {i+1} of {pages_number}")
                    bot.extractEmails(
                        page_no=i, 
                        start_yr=self.start_year, 
                        end_yr=self.end_year, 
                        keyword=self.keyword
                    )
                
                time.sleep(5)
            
            # Process downloaded files
            data_dir = self.keyword.replace(' ', '_')
            data_dir_path = os.path.join(os.getcwd(), data_dir)
            files_in_cwd = os.listdir(data_dir_path)
            txt_files = [os.path.join(data_dir_path, f) for f in files_in_cwd if f.endswith('.txt')]
            
            if not txt_files:
                print("No text files found to process")
                return None
            
            out_file = os.path.join(data_dir_path, data_dir + "_results.txt")
            
            # Combine all text files using Python (cross-platform)
            with open(out_file, 'w', encoding='utf-8') as outf:
                for txt_file in txt_files:
                    try:
                        with open(txt_file, 'r', encoding='utf-8', errors='replace') as inf:
                            outf.write(inf.read())
                    except Exception:
                        pass
            
            # Process the combined file
            df = pd.read_csv(out_file, sep='\t', skip_blank_lines=True, skipinitialspace=True)
            df.rename(columns={'AUTHOR':'names', 'EMAIL ':'emails'}, inplace=True)
            
            df2 = df[['names', 'emails']].copy(deep=True)
            del df
            
            # Split multiple authors/emails
            df2['names'].mask(df2['names'].str.contains(';') == True, other=df2['names'].str.split(';'), inplace=True)
            df2['emails'].mask(df2['emails'].str.contains(';') == True, other=df2['emails'].str.split(';'), inplace=True)
            
            # Check length matching
            df2['len_names'] = df2['names'].str.len()
            df2['len_mails'] = df2['emails'].str.len()
            df3 = df2[df2['len_names'] == df2['len_mails']].copy(deep=True)
            df3 = df3.explode(['names','emails'])
            df3.reset_index(drop=True, inplace=True)
            
            # Clean and format names
            df3['names'] = df3['names'].str.strip()
            df3['emails'] = df3['emails'].str.strip()
            df3[['Last_Name','First_Name']] = df3['names'].str.split(',', n=1, expand=True)
            
            df3['First_Name'] = df3['First_Name'].str.strip()
            df3['Last_Name'] = df3['Last_Name'].str.strip()
            df3['Names'] = df3['First_Name'] + " " + df3['Last_Name']
            
            # Final cleanup
            df4 = df3.loc[:,['emails', 'Names']].copy(deep=True)
            df5 = df4[df4['emails'] != ''].copy(deep=True)
            df6 = df5.drop_duplicates('emails')
            
            output_csv = out_file.replace('.txt', '') + '.csv'
            df6.to_csv(output_csv, encoding='utf-8', index=False)
            
            del df3, df2, df4, df5, df6
            
            self.output_file = output_csv
            print(f"Results saved to: {output_csv}")
            return output_csv
            
        except Exception as e:
            print(f"Error in MDPI scraper: {str(e)}")
            raise
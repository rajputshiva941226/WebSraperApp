import sys, os, time,shutil
from PMC_New_Edit.spiders.pmc_crawler import PmcCrawlerSpider

#from PMC_New_Edit.selenium_driver.selenium_part import NCBI_Crawler
#from ..selenium_driver.selenium_part import NCBI_Crawler
from PMC_New_Edit.selenium_driver.pmc_ncbi_new import NCBIPMC
from datetime import datetime, timedelta
import glob
from scrapy.utils.project import get_project_settings
from scrapy.utils.log import configure_logging
sys.path.append(os.getcwd())
print(f"current working directory is :: {os.getcwd()}")
import subprocess
import pandas as pd
import logging, random

def ChangeVPN():
        countries = ["Georgia","Serbia","Moldova","'North Macedonia'","Jersey","Monaco","Slovakia",
                     "Slovenia","Croatia","Albania","Cyprus","Liechtenstein","Malta","Ukraine",
                     "Belarus","Bulgaria","Hungary","Luxembourg","Montenegro","Andorra",
                     "'Czech Republic'","Estonia","Latvia","Lithuania","Poland","Armenia","Austria",
                     "Portugal","Greece","Finland","Belgium","Denmark","Norway","Iceland","Ireland",
                     "Spain","Romania","Italy","Sweden","Turkey","Singapore","Japan",
                     "Australia","'South Korea - 2'","Malaysia","Pakistan","'Sri Lanka'","Kazakhstan",
                     "Thailand","Indonesia","'New Zealand'","Taiwan - 3","Cambodia","Vietnam","Macau",
                     "Mongolia","Laos","Bangladesh","Uzbekistan","Myanmar","Nepal","Brunei","Bhutan",
                     "'United Kingdom'", "'United States'","Japan", "Germay", "'Hong Kong'", "Netherlands",
                     "Switzerland","Algeria","France","Egypt"] 
        choice = random.choice(countries)
        print(f"Selected Country is {choice}")
        #os.environ["ExpressVPN"] = os.pathsep + r"C:\Program Files (x86)\ExpressVPN\services"
        
        process = subprocess.Popen(["powershell","ExpressVPN.CLI.exe", "disconnect"], shell=True)
        result = process.communicate()[0]
        print(result)
        process = subprocess.Popen(["powershell","ExpressVPN.CLI.exe", "connect",
                            f"{str(choice)}"],shell=True)
        result = process.communicate()[0]
        print(result)    
def run_spider(filename):
    try:
        import scrapy
        import asyncio
        os.environ.setdefault('SCRAPY_SETTINGS_MODULE', 'settings')
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        from twisted.internet import asyncioreactor
        scrapy.utils.reactor.install_reactor('twisted.internet.asyncioreactor.AsyncioSelectorReactor')
        print("$$**"*5)
        is_asyncio_reactor_installed = scrapy.utils.reactor.is_asyncio_reactor_installed()
        
        print(f"Is asyncio reactor installed: {is_asyncio_reactor_installed}")
        from twisted.internet import reactor, defer
        from scrapy.crawler import CrawlerProcess

        #from ncbi_pmc.spiders.main_extractn import NCBI_pmc_extract
        
        strout = filename + "_results.csv"
        custom_args = {
            "FEEDS": {
                f"{strout}": {"format": "csv"},
            },
        }
        settings = dict(get_project_settings(), **custom_args)
        configure_logging(settings)
        #f = open("db-1.txt", "r")
        #a = f.readlines()
        #b = random.choice(a).strip('\n')
        
        
        runner = CrawlerProcess(settings=settings)
        @defer.inlineCallbacks
        def crawl():
            # Create the process with custom settings
            yield runner.crawl(PmcCrawlerSpider, filename=filename)
            #yield runner.crawl(MySpider2)
            print(f" Runner.spider_loader printing ... : {runner.spider_loader}")
            #d.addCallback(lambda _: runner.stop())
            runner.stop()
            
            print(f" Runner.crawler printing .... : {runner.crawlers}")
        crawl()
        runner.start(stop_after_crawl=True,install_signal_handlers=True)
        if "twisted.internet.reactor" in sys.modules:
            del sys.modules["twisted.internet.reactor"]
        else: 
            print("twisted.internet.reactor modules not Found in Sys")
        
        print("Rextor is Stopped!")
    except Exception as e:
        print(f"Exception Error occurred : {str(e)}")
        
def get_executable_directory():
    """
    Get the directory where the executable (.exe) is located.
    Works for both PyInstaller executable and regular Python script.
    """
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller executable
        return os.path.dirname(sys.executable)
    else:
        # Running as Python script
        return os.path.dirname(os.path.abspath(__file__))



if __name__ == "__main__":        
    # filename = input("For Saving Data to a file, Enter Filename: ")
    # Keyword_input = input("Enter the Keyword: ")
    # s_year = input("Enter the start year: ")
    # s_month = input("Enter the start month: ")
    # s_day = input("Enter the start day: ")
    # e_year = input("Enter the end year: ")
    # e_month = input("Enter the end month: ")
    # e_day = input("Enter the end day: ")
    
    # init_page = input("From which page no. you want to scrape? ")
    # dates_range = [s_year,s_month,s_day,e_year,e_month,e_day]
    # print(dates_range)
    # start_list = []
    # #page_no = 0
    # with NCBI_Crawler() as bot:
    #     bot.start_browser(Keyword_input,s_year,s_month,s_day,e_year,e_month,e_day)
    #     print(f"Session ID for Bot chrom ==> {bot.browser_pid}")
    #     ranges_list = bot.Page_Ranges()
    #     print(ranges_list)
    #     if init_page != 0:
    #         print(f"User want to start from {init_page}th page. ")
    #         start_list = [i for i in ranges_list if int(init_page) < i]
    #         start_list.append(int(init_page))
    #         start_list.sort()
            
    #     else : 
    #         start_list = ranges_list
        
    #     print(f" Check for processes still running ? {bot.service.assert_process_still_running()}")
    #     print(f"Service.process.pid for chrome bot is : {bot.service.process.pid}")
    #     #subprocess.run(['kill',f'{bot.service.process.pid}'],shell=True)
    #     os.system(r'.\kill.bat ' + str(bot.browser_pid))
    #     time.sleep(3)
        
    #     bot.quit()
    # lim4loop = 50
    # if init_page != 0 and start_list[0] != 0:
    #     lim4loop  = start_list[1] - start_list[0]   
    # print(f" While loop will run until i  = {lim4loop}") 
    # for page in start_list:
    #         logging.getLogger("selenium.webdriver.remote.remote_connection").propagate = False
    #         logging.getLogger("urllib3.connectionpool").propagate = False
    #         with NCBI_Crawler() as bot:
    #             bot.start_browser(Keyword_input,s_year,s_month,s_day,e_year,e_month,e_day)
                
    #             print(f"Session ID for Bot chrom ==> {bot.browser_pid}")
    #             bot.implicitly_wait(5)
    #             bot.getArticleLinks(page,filename,lim4loop)
                
    #             os.system(r'.\kill.bat ' + str(bot.browser_pid))
    #             #subprocess.run(['kill',f'{bot.service.process.pid}'],shell=True)
    #             time.sleep(3)
    #             bot.quit()
    #         ChangeVPN()
    #         url_files  = f"{filename}" + f"_{str(page)}_urls.txt"
    #         url_out_file = f"{filename}" + f"_{str(page)}_urls.csv"
    #         df = pd.read_csv(url_files,header=None)
    #         df.drop_duplicates(inplace=True)
    #         df.to_csv(url_out_file,lineterminator="\n" ,sep=",", header=None, index=False)
    #         os.remove(url_files)
           
    #         run_spider(filename,page)
    #         ChangeVPN()
    #         time.sleep(20)
            
    
    keyword = input("Enter search keyword: ")

    # Take user input
    start_date_str = input("Enter start date (dd/mm/yyyy): ")
    end_date_str = input("Enter end date (dd/mm/yyyy): ")

    # Convert to datetime objects
    start_date = datetime.strptime(start_date_str, "%d/%m/%Y")
    end_date = datetime.strptime(end_date_str, "%d/%m/%Y")

    # Generate weekly ranges
    current = start_date
    ranges = []
    query = keyword.replace(" ", "_")
    # download_dir = os.path.join(os.getcwd(), query)
    # os.makedirs(download_dir, exist_ok=True)
    exe_directory = get_executable_directory()
    download_dir = os.path.join(exe_directory, query)
    os.makedirs(download_dir, exist_ok=True)
    
    print(f"Executable directory: {exe_directory}")
    print(f"Download directory: {download_dir}")

    while current <= end_date:
        week_end = current + timedelta(days=6)  # 7-day window
        if week_end > end_date:
            week_end = end_date
        
        # Extract components as integers, then convert to str (no leading zeros)
        start_year, start_month, start_day = str(current.year), str(current.month), str(current.day)
        end_year, end_month, end_day = str(week_end.year), str(week_end.month), str(week_end.day)

        ranges.append({
            "start_year": start_year,
            "start_month": start_month,
            "start_day": start_day,
            "end_year": end_year,
            "end_month": end_month,
            "end_day": end_day
        })

        current = week_end + timedelta(days=1)

    # # Print result
    # for r in ranges:
    #     print(r)
    #     #desired_name = query.replace(" ", "_") + f'{r["start_year"]}-{r["start_month"]}-{r["start_day"]}-{r["end_year"]}-{r["end_month"]}-{r["end_day"]}.txt'
    #     desired_name = query.replace(" ", "_") + "_urls.csv"
    #     with NCBIPMC() as pmc:
    #         pmc.search_articles(keyword, r["start_year"], r["start_month"], r["start_day"], r["end_year"], r["end_month"], r["end_day"])
    #     latest_file = max(glob.glob(os.path.join(os.getcwd(),"*")), key=os.path.getctime)
    #     new_path = os.path.join(download_dir, desired_name)
    #     if os.path.exists(new_path):
    #         os.remove(new_path)  # delete the existing file
    #     shutil.move(latest_file, new_path)
        
    #     print(f"Moved file to {new_path}")
    #     run_spider(new_path,0)
    #     #ChangeVPN()
    #     time.sleep(20)
        
    desired_name = query.replace(" ", "_") + "_urls.csv"
    for i, r in enumerate(ranges, 1):
        print(f"Processing range {i}/{len(ranges)}: {r}")
        
        max_retries = 3
        retry_count = 0
        success = False
        
        while retry_count < max_retries and not success:
            try:
                # Create a new browser session for each attempt
                with NCBIPMC() as pmc:
                    print(f"Attempt {retry_count + 1}: Starting browser session...")
                    pmc.search_articles(keyword, r["start_year"], r["start_month"], r["start_day"], r["end_year"], r["end_month"], r["end_day"])
                    print("Search completed successfully, browser session closed")
                    #pmc.quit()
                # Handle file operations
                
                latest_file = max(glob.glob(os.path.join(exe_directory,"*")), key=os.path.getctime)
                new_path = os.path.join(download_dir, desired_name)
                if os.path.exists(new_path):
                    os.remove(new_path)  # delete the existing file
                shutil.move(latest_file, new_path)
                
                print(f"Moved file to {new_path}")
                run_spider(new_path)
                success = True
                
            except Exception as e:
                retry_count += 1
                print(f"Error occurred (attempt {retry_count}/{max_retries}): {str(e)}")
                if retry_count < max_retries:
                    print(f"Retrying in 10 seconds...")
                    time.sleep(10)
                else:
                    print(f"Failed to process range {r} after {max_retries} attempts. Skipping...")
        
        if success:
            ChangeVPN()
            time.sleep(20)
        else:
            print(f"Skipping to next range due to persistent errors...")

    data_frame = pd.read_csv(os.path.join(download_dir, f"{desired_name}_results.csv"))
    data_frame.drop_duplicates(inplace=True)
    df_cleaned = data_frame.dropna(subset=['email'])
    df_filtered = df_cleaned[df_cleaned['total_authors_found'] != 0]
    # Define domains/keywords to filter out
    blocked_domains = ['reprint', 'journal', 'plos.org']

    # Build regex pattern
    pattern = '|'.join(blocked_domains)
    df_final = df_filtered[~df_filtered['email'].str.contains(pattern,case=False, na=False)]
    df_final.to_csv(os.path.join(download_dir, f"{query.replace(" ", "_")}_results_deduplicated.csv"), lineterminator="\n", sep=",", index=False)
    print(f"Deduplicated results saved to {os.path.join(download_dir, f'{query.replace(" ", "_")}_results_deduplicated.csv')}")


    
    
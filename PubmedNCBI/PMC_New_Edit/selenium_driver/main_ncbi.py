from selenium_part import NCBI_Crawler
import multiprocessing

def startWebChrome(start_page, Keyword_input,s_year,s_month,s_day,e_year,e_month,e_day):
        with NCBI_Crawler() as bot:
            bot.start_browser(Keyword_input,s_year,s_month,s_day,e_year,e_month,e_day)
            #bot.sign_in(username=user[0], pswrd=user[1])
            bot.implicitly_wait(5)
            bot.getArticleLinks(start_page,Keyword_input)
	
            bot.close()
def Parallel_Selenium():
    #items = pages_range  # List of items to process
        #additional_param = ...  # Additional parameter to pass
        num_threads = multiprocessing.cpu_count()
        # Create a multiprocessing pool
        
        print(f"Number of Processors : {num_threads}")
        if num_threads <= 2 or len(ranges_list) == 1:
            
            pool = multiprocessing.Pool(processes= 1)
            print(pool)
        elif num_threads > 4:
            pool = multiprocessing.Pool(processes=3)
            print(pool)
        else:
            pool = multiprocessing.Pool(processes=num_threads - 2)
            print(pool)
        
        # Parallelize the function execution over the list
        try:
            results = [pool.apply_async(startWebChrome, args=(item,Keyword_input,s_year,s_month,s_day,e_year,e_month,e_day)) for item in ranges_list]
        
        # Get the results
            output = [result.get() for result in results]
        
        # Close the pool
            pool.close()
            pool.join()
        except Exception as e:
            print(f"Error : {str(e)}")
        #bot.Parallel_Selenium(ranges_list,filename=Keyword_input,dates_range=dates_range)
        

if __name__ == "__main__":
    
    multiprocessing.freeze_support()
    with NCBI_Crawler() as bot:
        Keyword_input = input("Enter the Keyword")
        s_year = input("Enter the start year: ")
        s_month = input("Enter the start month: ")
        s_day = input("Enter the start day: ")
        e_year = input("Enter the end year: ")
        e_month = input("Enter the end month: ")
        e_day = input("Enter the end day: ")
        #s_year = input("Enter the start year: ")
        dates_range = [s_year,s_month,s_day,e_year,e_month,e_day]
        print(dates_range)
        bot.start_browser(Keyword_input,s_year,s_month,s_day,e_year,e_month,e_day)
        ranges_list = bot.Page_Ranges()
        print(ranges_list)
        bot.close()
        startWebChrome(ranges_list[0],Keyword_input,s_year,s_month,s_day,e_year,e_month,e_day)
        #Parallel_Selenium()
        
        
        
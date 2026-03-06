"""
Reset Application - Delete all results and clear stats
"""

import os
import glob
import shutil

def reset_application():
    """Delete all result files and provide reset instructions"""
    
    results_folder = "results"
    deleted_count = 0
    
    print("=" * 70)
    print("APPLICATION RESET - Deleting all results and stats")
    print("=" * 70)
    
    # Delete all CSV and XLSX files in results folder
    if os.path.exists(results_folder):
        result_files = glob.glob(os.path.join(results_folder, "*.csv")) + \
                      glob.glob(os.path.join(results_folder, "*.xlsx"))
        
        if result_files:
            print(f"\nFound {len(result_files)} result files to delete...")
            
            for file_path in result_files:
                try:
                    os.remove(file_path)
                    deleted_count += 1
                    print(f"  ✓ Deleted: {os.path.basename(file_path)}")
                except Exception as e:
                    print(f"  ✗ Failed to delete {os.path.basename(file_path)}: {e}")
            
            print(f"\n✅ Deleted {deleted_count} result files")
        else:
            print("\n✓ Results folder is already empty")
    else:
        print(f"\n⚠️ Results folder '{results_folder}' not found")
    
    # Delete log files (optional)
    logs_folder = "logs"
    if os.path.exists(logs_folder):
        log_files = glob.glob(os.path.join(logs_folder, "*.log"))
        if log_files:
            response = input(f"\nFound {len(log_files)} log files. Delete them too? (y/n): ").lower()
            if response == 'y':
                for log_file in log_files:
                    try:
                        os.remove(log_file)
                        print(f"  ✓ Deleted: {os.path.basename(log_file)}")
                    except:
                        pass
                print("✅ Log files deleted")
    
    print("\n" + "=" * 70)
    print("RESET INSTRUCTIONS")
    print("=" * 70)
    print("""
To complete the reset and clear in-memory stats:

1. Stop the Flask server:
   - Press Ctrl+C in the terminal running app.py

2. Restart the Flask server:
   - Run: py app.py

3. All stats will be reset to zero:
   - Total jobs: 0
   - Successful jobs: 0
   - Failed jobs: 0
   - Total authors: 0
   - Total emails: 0

4. The dashboard and jobs page will show empty/reset data

✅ Application is ready for a fresh start!
""")
    print("=" * 70)

if __name__ == "__main__":
    reset_application()

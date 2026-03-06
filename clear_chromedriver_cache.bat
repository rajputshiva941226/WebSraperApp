@echo off
echo ========================================
echo ChromeDriver Cache Cleanup Script
echo ========================================
echo.

set CACHE_DIR=C:\Users\%USERNAME%\.wdm\drivers\chromedriver

if exist "%CACHE_DIR%" (
    echo Found ChromeDriver cache at: %CACHE_DIR%
    echo.
    echo Deleting cache...
    rmdir /s /q "%CACHE_DIR%"
    
    if exist "%CACHE_DIR%" (
        echo ERROR: Failed to delete cache directory
        echo Please run this script as Administrator
    ) else (
        echo SUCCESS: ChromeDriver cache cleared!
        echo.
        echo Next steps:
        echo 1. Restart your Flask application
        echo 2. ChromeDriver will download the correct version on next run
    )
) else (
    echo ChromeDriver cache not found at: %CACHE_DIR%
    echo Cache may already be cleared or located elsewhere
)

echo.
echo ========================================
pause

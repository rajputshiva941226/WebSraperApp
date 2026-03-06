@echo off
echo ======================================
echo Journal Scraper - Quick Start Script
echo ======================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo X Python is not installed. Please install Python 3.8 or higher.
    pause
    exit /b 1
)

echo [OK] Python found

REM Create virtual environment
echo.
echo Creating virtual environment...
python -m venv venv

REM Activate virtual environment
call venv\Scripts\activate.bat

echo [OK] Virtual environment activated

REM Install dependencies
echo.
echo Installing dependencies...
pip install -r requirements.txt

if errorlevel 1 (
    echo X Failed to install dependencies
    pause
    exit /b 1
)

echo [OK] Dependencies installed

REM Create results directory
if not exist "results" mkdir results
echo [OK] Results directory created

REM Start the server
echo.
echo ======================================
echo Starting the web server...
echo ======================================
echo.
echo Access the application at: http://localhost:5000
echo Press Ctrl+C to stop the server
echo.

python web_server.py

pause

@echo off
REM ============================================================
REM  Build a standalone Windows .exe for Money Trail Report Generator
REM  Run this ON WINDOWS from the project root folder:
REM      build_windows.bat
REM ============================================================

echo Creating virtual environment (if not already present)...
if not exist venv (
    python -m venv venv
)

call venv\Scripts\activate.bat

echo Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt

echo Building executable with PyInstaller...
pyinstaller --noconfirm --clean --onefile --windowed ^
    --name "MoneyTrailReportGenerator" ^
    --add-data "core\templates;core\templates" ^
    main.py

echo.
echo ============================================================
echo  Build complete. Find the app at:
echo    dist\MoneyTrailReportGenerator.exe
echo ============================================================
pause

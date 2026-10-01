@echo off
cd /d "%~dp0"
echo Installing dependencies...
python -m pip install -r requirements.txt -r requirements-build.txt
if errorlevel 1 goto err
echo Building EXE...
python -m PyInstaller --noconfirm --clean --onefile --windowed --name SKYHELPER --paths . --collect-submodules gspread --collect-submodules google.auth --collect-submodules google.oauth2 run_tracker.py
if errorlevel 1 goto err
echo.
echo Done: dist\SKYHELPER.exe
pause
exit /b 0
:err
echo.
echo BUILD FAILED. Check the messages above.
pause
exit /b 1

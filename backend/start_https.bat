@echo off
REM Start XBRL Budget Backend with HTTPS
REM URL: https://kpsfinanciallab.w3pro.it:8001

cd /d "%~dp0"

REM Activate virtual environment
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo Virtual environment not found. Creating...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
)

REM Set SSL certificate paths (relative to project root)
set SSL_KEYFILE=%~dp0..\ssl\star_w3pro_it.key
set SSL_CERTFILE=%~dp0..\ssl\star_w3pro_it.crt
set PORT=8001

echo.
echo Starting XBRL Budget API with HTTPS...
echo URL: https://kpsfinanciallab.w3pro.it:8001
echo Docs: https://kpsfinanciallab.w3pro.it:8001/docs
echo.

python -m app.main

pause

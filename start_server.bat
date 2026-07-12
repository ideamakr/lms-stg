@echo off
:: Move to the root directory
cd /d "C:\leave-system\leave-system\leave-system"

:: Ensure any existing python process on this port is cleared 
taskkill /F /IM python.exe /T >nul 2>&1

:: Run uvicorn on port 8081 and save logs
echo Starting Leave System on port 8081...
echo Check C:\leave-system\server_log.txt for live logs.
python -m uvicorn app.main:app --host 0.0.0.0 --port 8081 > "C:\leave-system\server_log.txt" 2>&1

pause
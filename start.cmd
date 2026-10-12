@echo off
setlocal DisableDelayedExpansion
title Server Monitor
pushd "%~dp0" >nul 2>&1
if errorlevel 1 goto path_error

set "MONITOR_POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if exist "%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershell.exe" set "MONITOR_POWERSHELL=%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%MONITOR_POWERSHELL%" goto powershell_error

"%MONITOR_POWERSHELL%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
set "MONITOR_EXIT=%ERRORLEVEL%"
popd
if "%MONITOR_EXIT%"=="0" exit /b 0
echo(
echo Server Monitor stopped with exit code %MONITOR_EXIT%.
echo Read the error above. Troubleshooting is in README.md.
pause
exit /b %MONITOR_EXIT%

:powershell_error
echo Windows PowerShell 5.1 was not found.
echo Run on Windows 10 or 11, or use Python 3.11+ to run server.py.
popd
pause
exit /b 1

:path_error
echo Cannot open the application folder.
echo Extract the entire ZIP to a writable local folder, then run start.cmd again.
pause
exit /b 1

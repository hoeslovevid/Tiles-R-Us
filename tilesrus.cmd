@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0TilesRUs.exe" (
  "%~dp0TilesRUs.exe" %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
  python -m tile_reader %*
  exit /b %ERRORLEVEL%
)

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -m tile_reader %*
  exit /b %ERRORLEVEL%
)

echo Python 3.11+ (with tcl/tk) was not found, and TilesRUs.exe is not in this folder.
exit /b 1

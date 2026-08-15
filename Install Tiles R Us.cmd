@echo off
setlocal
cd /d "%~dp0"
title Tiles R Us installer
echo.
echo  Tiles R Us
echo  Downloading and opening the installer wizard...
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-setup.ps1" %*
if errorlevel 1 (
  echo.
  echo Install did not finish successfully.
  pause
)

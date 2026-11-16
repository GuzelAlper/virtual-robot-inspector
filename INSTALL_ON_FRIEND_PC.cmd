@echo off
setlocal
title Unitree Go2 Inspector - Installation

wsl.exe -d Ubuntu-24.04 -- true >nul 2>&1
if errorlevel 1 (
  echo Ubuntu-24.04 is not installed in WSL.
  echo Open PowerShell as Administrator and run:
  echo   wsl --install -d Ubuntu-24.04
  echo Restart Windows if requested, create the Ubuntu user, then run this file again.
  pause
  exit /b 1
)

for /f "usebackq delims=" %%P in (`wsl.exe -d Ubuntu-24.04 -- wslpath -a "%~dp0"`) do set "REPO_WSL=%%P"
if not defined REPO_WSL (
  echo Could not convert the repository path for WSL.
  pause
  exit /b 1
)

echo Repository in WSL: %REPO_WSL%
wsl.exe -d Ubuntu-24.04 -- bash -lc "cd \"%REPO_WSL%\" && bash deployment/factory_integration/install.sh"
if errorlevel 1 (
  echo.
  echo Installation failed. Copy the last error and send it to Alper.
  pause
  exit /b 1
)

copy /Y "%~dp0START_SIMULATION.cmd" "%USERPROFILE%\Desktop\START_ROBOT_INSPECTOR.cmd" >nul
copy /Y "%~dp0START_CUSTOM_FACTORY.cmd" "%USERPROFILE%\Desktop\START_CUSTOM_FACTORY.cmd" >nul
copy /Y "%~dp0STOP_SIMULATION.cmd" "%USERPROFILE%\Desktop\STOP_ROBOT_INSPECTOR.cmd" >nul

echo.
echo Installation completed.
echo Start and stop command files were copied to the Desktop.
pause

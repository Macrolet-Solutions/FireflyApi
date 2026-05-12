@echo off
setlocal

REM Firefly API Windows service install / control helper.
REM This batch file ships next to the bundled firefly_api_service.exe
REM in dist\FireflyApi\ — run it from there on the target machine.

set "SERVICE_NAME=MacroletFireflyApi"
set "EXE_PATH=%~dp0firefly_api_service.exe"

if not exist "%EXE_PATH%" (
    echo ERROR: Could not find firefly_api_service.exe in %~dp0
    echo Run packaging\windows\build.bat first, then ship the dist\FireflyApi\ folder.
    exit /b 1
)

REM Every action below requires elevation (sc config, service install,
REM net start/stop). Bail early with a friendly message otherwise.
net session >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: This script must be run from an elevated Administrator prompt.
    exit /b 1
)

if "%~1"=="" goto :usage
if /I "%~1"=="install"   goto :install
if /I "%~1"=="uninstall" goto :uninstall
if /I "%~1"=="start"     goto :start
if /I "%~1"=="stop"      goto :stop
if /I "%~1"=="restart"   goto :restart
if /I "%~1"=="status"    goto :status
goto :usage

:install
echo Installing %SERVICE_NAME% ...
"%EXE_PATH%" install
sc config %SERVICE_NAME% start= auto
sc failure %SERVICE_NAME% reset= 86400 actions= restart/30000/restart/30000/restart/60000
echo.
echo Service installed and configured for automatic start.
echo Start it now with:  deploy.bat start
goto :eof

:uninstall
net stop %SERVICE_NAME% >nul 2>&1
"%EXE_PATH%" remove
echo Service removed.
goto :eof

:start
net start %SERVICE_NAME%
goto :eof

:stop
net stop %SERVICE_NAME%
goto :eof

:restart
net stop %SERVICE_NAME% >nul 2>&1
timeout /t 3 /nobreak >nul
net start %SERVICE_NAME%
goto :eof

:status
sc query %SERVICE_NAME%
goto :eof

:usage
echo Usage: deploy.bat [install ^| uninstall ^| start ^| stop ^| restart ^| status]
echo.
echo Workflow:
echo   1. Edit .\config\firefly-appsettings.json (copy from .example.json).
echo   2. deploy.bat install
echo   3. deploy.bat start
echo.
echo To change the config path, set FIREFLY_HOST or FIREFLY_PORT in the
echo service environment, or place the JSON file at the working directory's
echo default path ./config/firefly-appsettings.json.
goto :eof

@echo off
setlocal

REM Firefly API Windows service install / control helper.
REM This batch file ships next to the bundled firefly_api_service.exe
REM in dist\FireflyApi\ — run it from there on the target machine.

set "SERVICE_NAME=MacroletFireflyApi"
set "SERVICE_DISPLAY_NAME=Macrolet Firefly API"
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
set "ACTION=%~1"
shift

:parse_args
if "%~1"=="" goto :dispatch
if /I "%~1"=="--service-name" (
    if "%~2"=="" goto :missing_arg
    set "SERVICE_NAME=%~2"
    shift
    shift
    goto :parse_args
)
if /I "%~1"=="--name" (
    if "%~2"=="" goto :missing_arg
    set "SERVICE_NAME=%~2"
    shift
    shift
    goto :parse_args
)
if /I "%~1"=="--display-name" (
    if "%~2"=="" goto :missing_arg
    set "SERVICE_DISPLAY_NAME=%~2"
    shift
    shift
    goto :parse_args
)
echo ERROR: Unknown option: %~1
echo.
goto :usage

:dispatch
if /I "%ACTION%"=="install"   goto :install
if /I "%ACTION%"=="uninstall" goto :uninstall
if /I "%ACTION%"=="start"     goto :start
if /I "%ACTION%"=="stop"      goto :stop
if /I "%ACTION%"=="restart"   goto :restart
if /I "%ACTION%"=="status"    goto :status
goto :usage

:install
echo Installing %SERVICE_NAME% ...
"%EXE_PATH%" --service-name "%SERVICE_NAME%" --service-display-name "%SERVICE_DISPLAY_NAME%" install
sc config "%SERVICE_NAME%" start= auto
sc failure "%SERVICE_NAME%" reset= 86400 actions= restart/30000/restart/30000/restart/60000
echo.
echo Service installed and configured for automatic start.
echo Start it now with:  deploy.bat start --service-name "%SERVICE_NAME%"
goto :eof

:uninstall
net stop "%SERVICE_NAME%" >nul 2>&1
"%EXE_PATH%" --service-name "%SERVICE_NAME%" remove
echo Service removed.
goto :eof

:start
net start "%SERVICE_NAME%"
goto :eof

:stop
net stop "%SERVICE_NAME%"
goto :eof

:restart
net stop "%SERVICE_NAME%" >nul 2>&1
timeout /t 3 /nobreak >nul
net start "%SERVICE_NAME%"
goto :eof

:status
sc query "%SERVICE_NAME%"
goto :eof

:missing_arg
echo ERROR: %~1 requires a value.
echo.
goto :usage

:usage
echo Usage: deploy.bat [install ^| uninstall ^| start ^| stop ^| restart ^| status] [options]
echo.
echo Options:
echo   --service-name NAME       Windows service name. Default: MacroletFireflyApi
echo   --name NAME               Alias for --service-name.
echo   --display-name NAME       Windows display name used during install.
echo.
echo Workflow:
echo   1. Edit .\config\firefly-appsettings.json (copy from .example.json).
echo   2. deploy.bat install --service-name MacroletFireflyApi --display-name "Macrolet Firefly API"
echo   3. deploy.bat start --service-name MacroletFireflyApi
echo.
echo Bind host and port are read from .\config\firefly-appsettings.json
echo under server.host and server.port.
goto :eof

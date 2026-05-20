@echo off
setlocal

set "REPO_ROOT=%~dp0"
set "FRONTEND_DIR=%REPO_ROOT%frontend"
set "FRONTEND_PORT=%FIREFLY_FRONTEND_PORT%"
set "CONFIG_PATH=%REPO_ROOT%config\firefly-appsettings.json"

if "%FRONTEND_PORT%"=="" set "FRONTEND_PORT=5173"

if "%FIREFLY_BACKEND_URL%"=="" (
    if exist "%CONFIG_PATH%" (
        for /f "usebackq delims=" %%U in (`python -c "import json, pathlib; data=json.loads(pathlib.Path(r'%CONFIG_PATH%').read_text(encoding='utf-8')); server=data.get('server', {}); host=server.get('host', '0.0.0.0'); port=server.get('port', 8000); display='127.0.0.1' if host in ('0.0.0.0', '::') else host; print(f'http://{display}:{port}')"`) do set "FIREFLY_BACKEND_URL=%%U"
    )
    if "%FIREFLY_BACKEND_URL%"=="" (
        set "FIREFLY_BACKEND_URL=http://127.0.0.1:8000"
    )
)

if not exist "%FRONTEND_DIR%\package.json" (
    echo Frontend package not found: %FRONTEND_DIR%\package.json
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo npm was not found on PATH. Install Node.js, then run this script again.
    exit /b 1
)

pushd "%FRONTEND_DIR%" >nul || exit /b 1

if not exist "node_modules" (
    echo Installing frontend dependencies...
    call npm install
    if errorlevel 1 (
        popd >nul
        exit /b 1
    )
)

echo Running Firefly frontend dev server
echo   Frontend: http://127.0.0.1:%FRONTEND_PORT%
echo   Backend proxy: %FIREFLY_BACKEND_URL%
echo.

call npm run dev -- --host 127.0.0.1 --port %FRONTEND_PORT%
set "EXIT_CODE=%ERRORLEVEL%"

popd >nul
exit /b %EXIT_CODE%
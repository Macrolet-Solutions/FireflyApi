@echo off
setlocal

set "REPO_ROOT=%~dp0"
set "HOST=%FIREFLY_HOST%"
set "PORT=%FIREFLY_PORT%"

if "%HOST%"=="" set "HOST=127.0.0.1"
if "%PORT%"=="" set "PORT=8000"

pushd "%REPO_ROOT%" >nul || exit /b 1

if exist "%REPO_ROOT%backend\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%REPO_ROOT%backend\.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

if "%~1"=="" (
    if exist "config\firefly-appsettings.json" (
        set "CONFIG_PATH=config\firefly-appsettings.json"
    ) else if exist "dist\FireflyApi\config\firefly-appsettings.json" (
        set "CONFIG_PATH=dist\FireflyApi\config\firefly-appsettings.json"
    ) else (
        echo No config file found.
        echo Expected config\firefly-appsettings.json or dist\FireflyApi\config\firefly-appsettings.json.
        echo You can also pass a config path: run_backend.bat path\to\firefly-appsettings.json
        popd >nul
        exit /b 2
    )
) else (
    set "CONFIG_PATH=%~1"
)

if not exist "%CONFIG_PATH%" (
    echo Config file not found: %CONFIG_PATH%
    popd >nul
    exit /b 2
)

for %%I in ("%CONFIG_PATH%") do set "CONFIG_ABS=%%~fI"
for %%I in ("%CONFIG_ABS%") do set "CONFIG_DIR=%%~dpI"
for %%I in ("%CONFIG_DIR%..") do set "CONFIG_BASE=%%~fI"

set "GENERATED_CONFIG=%TEMP%\firefly-run-backend-appsettings.json"
set "RUN_BACKEND_REPO_ROOT=%REPO_ROOT%"
set "RUN_BACKEND_CONFIG_ABS=%CONFIG_ABS%"
set "RUN_BACKEND_CONFIG_BASE=%CONFIG_BASE%"
set "RUN_BACKEND_GENERATED_CONFIG=%GENERATED_CONFIG%"
"%PYTHON_EXE%" -c "import json, os, pathlib; repo=pathlib.Path(os.environ['RUN_BACKEND_REPO_ROOT']).resolve(); src=pathlib.Path(os.environ['RUN_BACKEND_CONFIG_ABS']).resolve(); base=pathlib.Path(os.environ['RUN_BACKEND_CONFIG_BASE']).resolve(); out=pathlib.Path(os.environ['RUN_BACKEND_GENERATED_CONFIG']).resolve(); data=json.loads(src.read_text(encoding='utf-8')); fp=data.setdefault('frontend', {}).get('staticFilesPath', './frontend/dist'); p=pathlib.Path(fp); candidates=[p if p.is_absolute() else base / p, base / '_internal' / 'frontend' / 'dist', repo / 'build' / 'frontend', repo / 'frontend' / 'dist']; frontend=next((c for c in candidates if (c / 'index.html').is_file()), candidates[0]); data.setdefault('frontend', {})['staticFilesPath']=str(frontend); out.write_text(json.dumps(data, indent=4) + '\n', encoding='utf-8')" >nul
if errorlevel 1 (
    echo Failed to prepare temporary backend config from: %CONFIG_ABS%
    popd >nul
    exit /b 1
)

set "PYTHONPATH=%REPO_ROOT%backend;%PYTHONPATH%"

echo Running Firefly API backend from source
echo   Source config: %CONFIG_ABS%
echo   Runtime config: %GENERATED_CONFIG%
echo   Working directory: %CONFIG_BASE%
echo   URL: http://%HOST%:%PORT%
echo.

pushd "%CONFIG_BASE%" >nul || exit /b 1
"%PYTHON_EXE%" -m firefly_api --config "%GENERATED_CONFIG%" --host "%HOST%" --port "%PORT%"
set "EXIT_CODE=%ERRORLEVEL%"
popd >nul
popd >nul

exit /b %EXIT_CODE%
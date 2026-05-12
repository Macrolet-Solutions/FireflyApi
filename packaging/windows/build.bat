@echo off
setlocal

REM Build the Firefly API Windows service bundle.
REM
REM Output: dist\FireflyApi\firefly_api_service.exe + supporting files.
REM
REM Pre-requisites:
REM   * Python 3.12+ on PATH (or a .venv at repository root).
REM   * Node 18+ on PATH (for the frontend build).
REM
REM Run from any directory; the script re-anchors on the repository root.

pushd "%~dp0..\.."

echo ========================================
echo  Building Firefly API service bundle
echo ========================================

REM ---- 1. Build the frontend bundle into build\frontend\ ----------------

set "FRONTEND_BUILD_DIR=build\frontend"
if exist "%FRONTEND_BUILD_DIR%" rmdir /S /Q "%FRONTEND_BUILD_DIR%"

if not exist "frontend\package.json" (
    popd
    echo ERROR: frontend\package.json not found.
    exit /b 1
)

echo.
echo Building frontend ...
pushd frontend
if exist package-lock.json (
    call npm ci
) else (
    call npm install
)
if errorlevel 1 (
    popd
    popd
    echo ERROR: Frontend dependency install failed.
    exit /b 1
)
call npm run build
if errorlevel 1 (
    popd
    popd
    echo ERROR: Frontend build failed.
    exit /b 1
)
popd

xcopy /E /I /Y "frontend\dist" "%FRONTEND_BUILD_DIR%" >nul
if not exist "%FRONTEND_BUILD_DIR%\index.html" (
    popd
    echo ERROR: Frontend output is missing index.html.
    exit /b 1
)

REM ---- 2. Resolve the Python interpreter -------------------------------

set "PYTHON_EXE=%CD%\backend\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

REM ---- 3. Install build-time requirements ------------------------------

echo.
echo Installing Windows packaging requirements ...
"%PYTHON_EXE%" -m pip install -r backend\requirements-windows.txt
if errorlevel 1 (
    popd
    echo ERROR: Could not install build requirements.
    exit /b 1
)

REM Ensure firefly_api is importable by PyInstaller even when the venv
REM is fresh (matches the dev workflow's editable install).
"%PYTHON_EXE%" -m pip install -e backend >nul 2>&1

REM ---- 4. Run PyInstaller ----------------------------------------------

echo.
echo Running PyInstaller ...
"%PYTHON_EXE%" -m PyInstaller --noconfirm packaging\pyinstaller\firefly_api_service.spec
if errorlevel 1 (
    popd
    echo ERROR: PyInstaller build failed.
    exit /b 1
)

REM ---- 5. Stage deployment artefacts next to the exe -------------------

set "BUNDLE_DIR=dist\FireflyApi"
copy /Y packaging\windows\deploy.bat "%BUNDLE_DIR%\deploy.bat" >nul

if not exist "%BUNDLE_DIR%\config" mkdir "%BUNDLE_DIR%\config"
copy /Y config\firefly-appsettings.example.json "%BUNDLE_DIR%\config\firefly-appsettings.example.json" >nul

echo.
echo ========================================
echo  Build complete
echo ========================================
echo Bundle: %CD%\%BUNDLE_DIR%\
echo.
echo Next steps:
echo   1. Copy %BUNDLE_DIR%\ to the target machine.
echo   2. Copy config\firefly-appsettings.example.json -^> config\firefly-appsettings.json and edit it.
echo   3. From an elevated prompt, run:  deploy.bat install
echo                                     deploy.bat start
echo.

popd

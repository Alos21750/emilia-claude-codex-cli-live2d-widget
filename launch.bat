@echo off
chcp 65001 >nul
setlocal

set "ROOT=%~dp0"
cd /d "%ROOT%"

echo Emilia Live2D Widget launcher
echo.

set "MISSING=0"

if not exist "%ROOT%frontend\node_modules\" (
  echo [missing] frontend\node_modules
  echo Run:
  echo   cd frontend
  echo   npm install
  echo.
  set "MISSING=1"
)

if not exist "%ROOT%server\.venv\Scripts\python.exe" (
  echo [missing] server\.venv\Scripts\python.exe
  echo Run:
  echo   cd server
  echo   uv venv
  echo   uv sync
  echo.
  set "MISSING=1"
)

if not exist "%ROOT%frontend\public\assets\models\rezero\" (
  echo [missing] frontend\public\assets\models\rezero
  echo Run:
  echo   cd frontend
  echo   pwsh .\scripts\setup-emilia-models.ps1 -Source "^<path to ReZero LiM Live2D Characters\Live2D Characters^>"
  echo.
  set "MISSING=1"
)

if "%MISSING%"=="1" (
  echo Setup is incomplete. Fix the missing items above, then run launch.bat again.
  echo.
  pause
  exit /b 1
)

echo Starting backend on http://127.0.0.1:8000 ...
start "Emilia Widget Backend" cmd /k "cd /d ""%ROOT%server"" && ""%ROOT%server\.venv\Scripts\python.exe"" main.py"

timeout /t 2 /nobreak >nul

echo Starting Vite dev server on http://127.0.0.1:5173 ...
start "Emilia Widget Vite" cmd /k "cd /d ""%ROOT%frontend"" && npm run dev"

timeout /t 3 /nobreak >nul

echo Starting Electron widget. Close the widget window to return here.
echo.
cd /d "%ROOT%frontend"
npm run electron:dev
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo Electron has closed. Close the Backend and Vite command windows when you are done.
echo.
pause
exit /b %EXIT_CODE%

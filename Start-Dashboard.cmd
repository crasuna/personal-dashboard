@echo off
setlocal
cd /d "%~dp0"
py -3 -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>&1
if not errorlevel 1 (
  py -3 launch.py
  if errorlevel 1 pause
  exit /b
)
python -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>&1
if not errorlevel 1 (
  python launch.py
  if errorlevel 1 pause
  exit /b
)
echo Python 3.10 or newer was not found.
echo Install Python from https://www.python.org/downloads/windows/
echo During installation, enable the Python launcher or add Python to PATH.
pause
exit /b 1

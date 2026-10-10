@echo off
REM Double-click this file to build and open the SafeWindow demo app.
cd /d "%~dp0"
set SAFEWINDOW_DATA_DIR=data_demo
set PYTHONIOENCODING=utf-8

if not exist ".venv\Scripts\python.exe" (
    echo Setting up Python environment for the first time, please wait...
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements-pipeline.txt
    .venv\Scripts\python.exe -m pip install -e .
)

echo Building and validating the demo package...
.venv\Scripts\python.exe scripts\build_demo.py --keep data_demo

if errorlevel 1 (
    echo Demo build failed. Check the output above.
    pause
    exit /b 1
)

echo.
echo Opening SafeWindow at http://localhost:8501  (close this window to stop)
.venv\Scripts\python.exe -m streamlit run app\streamlit_app.py
pause

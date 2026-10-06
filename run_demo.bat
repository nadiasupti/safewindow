@echo off
REM Double-click this file to open the SafeWindow demo app in your browser.
cd /d "%~dp0"
set SAFEWINDOW_DATA_DIR=data_demo
set PYTHONIOENCODING=utf-8

if not exist ".venv\Scripts\python.exe" (
    echo Setting up Python environment for the first time, please wait...
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements-pipeline.txt
    .venv\Scripts\python.exe -m pip install -e .
)

if not exist "data_demo\app\meta.json" (
    echo Building demo data...
    .venv\Scripts\python.exe scripts\make_demo_data.py
    .venv\Scripts\python.exe scripts\run_engine.py
)

echo.
echo Opening SafeWindow at http://localhost:8501  (close this window to stop)
.venv\Scripts\python.exe -m streamlit run app\streamlit_app.py
pause

@echo off
rem Design Conveyor: local web UI. First run creates .venv and installs dependencies.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Creating .venv ...
  python -m venv .venv || exit /b 1
  .venv\Scripts\python -m pip install -r requirements.txt fastapi uvicorn python-multipart resvg-py || exit /b 1
)
set PYTHONUTF8=1
set OPENBLAS_NUM_THREADS=1
set OMP_NUM_THREADS=1
start "" http://localhost:8765
.venv\Scripts\python -X utf8 -m uvicorn server:app --app-dir app --host 127.0.0.1 --port 8765

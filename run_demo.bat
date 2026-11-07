@echo off
rem Live localhost demo: double-click; the browser opens http://localhost:8501. Close this window to stop.
rem Uses _ext\jdk and _ext\hadoop when present, otherwise the JAVA_HOME / HADOOP_HOME already set on this machine.
cd /d "%~dp0"
if exist "%~dp0_ext\jdk\jdk-11.0.32.1+1\bin\java.exe" set "JAVA_HOME=%~dp0_ext\jdk\jdk-11.0.32.1+1"
if exist "%~dp0_ext\hadoop\bin\winutils.exe" set "HADOOP_HOME=%~dp0_ext\hadoop"
if not defined JAVA_HOME (
  echo JAVA_HOME is not set and _ext\jdk is missing. Install Java 11 or 17, see README "Live demo".
  pause
  exit /b 1
)
if not defined HADOOP_HOME (
  echo HADOOP_HOME is not set and _ext\hadoop\bin\winutils.exe is missing, see README "Live demo".
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo .venv is missing. Run: python -m venv .venv  and  .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)
set "PATH=%JAVA_HOME%\bin;%HADOOP_HOME%\bin;%PATH%"
set "PYSPARK_PYTHON=%~dp0.venv\Scripts\python.exe"
set "PYTHONUTF8=1"
echo Starting demo at http://localhost:8501  (close this window to stop)
start "" cmd /c "timeout /t 6 /nobreak >nul & start http://localhost:8501"
".venv\Scripts\python.exe" -m streamlit run demo\app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false
pause

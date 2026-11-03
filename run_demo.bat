@echo off
rem Live localhost demo: double-click; the browser opens http://localhost:8501. Close this window to stop.
cd /d "%~dp0"
set "JAVA_HOME=%~dp0_ext\jdk\jdk-11.0.32.1+1"
set "HADOOP_HOME=%~dp0_ext\hadoop"
set "PATH=%JAVA_HOME%\bin;%HADOOP_HOME%\bin;%PATH%"
set "PYSPARK_PYTHON=%~dp0.venv\Scripts\python.exe"
set "PYTHONUTF8=1"
echo Starting demo at http://localhost:8501  (close this window to stop)
start "" cmd /c "timeout /t 6 /nobreak >nul & start http://localhost:8501"
".venv\Scripts\python.exe" -m streamlit run demo\app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false
pause

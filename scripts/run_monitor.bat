@echo off
REM Wrapper invocado pelo Windows Task Scheduler para rodar o Monitor Diario.
REM - Resolve o diretorio do repo relativo a este script (pai de scripts\).
REM - Usa .venv\Scripts\python.exe se existir; senao "python" do PATH.
REM - Stdout/stderr vao pra logs\scheduler_run.log (rotacao a cargo do Python).

setlocal
set SCRIPT_DIR=%~dp0
set REPO_ROOT=%SCRIPT_DIR%..

pushd "%REPO_ROOT%"
if not exist logs mkdir logs

set PYEXE=%REPO_ROOT%\.venv\Scripts\python.exe
if not exist "%PYEXE%" set PYEXE=python

echo [%date% %time%] starting monitor-diario run >> logs\scheduler_run.log
"%PYEXE%" -m scheduler.runner >> logs\scheduler_run.log 2>&1
set RC=%ERRORLEVEL%
echo [%date% %time%] finished rc=%RC% >> logs\scheduler_run.log
echo. >> logs\scheduler_run.log

popd
endlocal & exit /b %RC%

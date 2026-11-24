@echo off
setlocal DisableDelayedExpansion
if not exist "%~dp0registry_companion_launcher.py" goto incomplete
py -3 -I -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if not errorlevel 1 goto use_py
python -I -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if not errorlevel 1 goto use_python
echo Install Python 3.11 or later for your user, enable py or python on PATH, then reopen this launcher. 1>&2
goto failed
:incomplete
echo Extract all files from registry-companion-kit.zip into the same folder. 1>&2
:failed
pause
exit /b 2
:use_py
py -3 -I "%~dp0registry_companion_launcher.py" "%~f0" %*
exit /b %errorlevel%
:use_python
python -I "%~dp0registry_companion_launcher.py" "%~f0" %*
exit /b %errorlevel%

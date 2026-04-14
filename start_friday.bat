@echo off
REM FRIDAY launcher — activates the venv and runs friday_start.
REM Invoked at Windows login via a shortcut in the Startup folder.

cd /d "%~dp0"
call .venv\Scripts\activate.bat
friday_start

@echo off
rem Abre o Legendas no navegador (versao de desenvolvimento, antes do instalador).
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" -m app
) else (
  start "" pythonw -m app
)

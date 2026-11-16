@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" main.py >> scraper.log 2>&1

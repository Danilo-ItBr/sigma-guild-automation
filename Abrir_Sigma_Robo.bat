@echo off
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="%~dp0chrome_profile" --remote-debugging-port=9222 --remote-allow-origins=* --app="https://poke.sigmaproject.online/play"

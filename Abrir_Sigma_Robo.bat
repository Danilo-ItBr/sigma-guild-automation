@echo off
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="%~dp0chrome_profile" --remote-debugging-port=9222 --remote-allow-origins=* --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding --app="https://poke.sigmaproject.online/play"

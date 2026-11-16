@echo off
title WhatsApp Login - Robô Sigma
cd /d "%~dp0"
echo ============================================================
echo Abrindo WhatsApp Web...
echo ============================================================
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="%~dp0whatsapp_profile" --no-first-run --no-default-browser-check "https://web.whatsapp.com"
echo.
echo ============================================================
echo 1. Se aparecer mensagem do Chrome, clique em "Continuar sem uma conta"
echo 2. Na tela do WhatsApp Web, aponte a camera (Conectar Aparelho)
echo 3. Assim que carregar suas conversas, pode fechar a janela do Chrome.
echo ============================================================
pause

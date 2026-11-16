@echo off
title Executar Robo Sigma - Manual
cd /d "%~dp0"
echo ============================================================
echo   EXECUTANDO ROBO SIGMA MANUALMENTE
echo   Coleta de Membros + Doacoes + Consolidacao + WhatsApp
echo ============================================================
echo.
".venv\Scripts\python.exe" main.py
echo.
echo ============================================================
echo Processo concluido! Pressione qualquer tecla para fechar.
echo ============================================================
pause

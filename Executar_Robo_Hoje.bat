@echo off
title Executar Robo Sigma - Coleta Ate Hoje (Tempo Real)
cd /d "%~dp0"
echo ============================================================
echo   EXECUTANDO ROBO SIGMA - COLETA ATE HOJE
echo   Membros + Doacoes (Ontem e Hoje) + Consolidacao + WhatsApp
echo ============================================================
echo.
".venv\Scripts\python.exe" main_hoje.py
echo.
echo ============================================================
echo Processo concluido! Pressione qualquer tecla para fechar.
echo ============================================================
pause

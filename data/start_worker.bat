@echo off
title Tradezer - lokalni LLM worker (Qwen)
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set LLM_MODEL=qwen2.5-coder-7b-instruct
set LLM_BASE_URL=http://localhost:1234/v1
echo Spoustim worker (watch rezim) - hlidani feedu + klasifikace pres Qwen...
echo Okno nechej otevrene. Ukoncis ho zavrenim nebo Ctrl+C.
echo.
py local_predictor.py --watch 45
pause

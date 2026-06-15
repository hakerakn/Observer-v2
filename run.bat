@echo off
title Jobs Tracker
chcp 65001 > nul

:: Navigate to the script's directory
cd /d "%~dp0"

echo [1/3] Проверка и инсталиране на необходимите Python библиотеки...
python -m pip install flask beautifulsoup4 lxml --quiet

echo [2/3] Отваряне на уеб приложението в браузъра...
:: Give the Flask server 2 seconds to start before opening the browser
timeout /t 2 /nobreak > nul
start firefox "http://127.0.0.1:5001"

echo [3/3] Стартиране на сървъра...
echo -------------------------------------------------------------------
echo За да спрете сървъра, затворете този прозорец или натиснете CTRL+C.
echo -------------------------------------------------------------------
python app.py
pause

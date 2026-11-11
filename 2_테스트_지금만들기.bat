@echo off
chcp 65001 >nul
cd /d %~dp0
echo Making 1 test post (not posted to Instagram). Takes 5-15 min.
python pc\run.py --slot now --test
echo.
pause

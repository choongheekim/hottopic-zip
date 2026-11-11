@echo off
chcp 65001 >nul
cd /d %~dp0
python pc\run.py --slot %1

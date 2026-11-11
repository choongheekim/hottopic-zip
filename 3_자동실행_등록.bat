@echo off
chcp 65001 >nul
cd /d %~dp0
echo Scheduling daily runs at 07:20 / 11:50 / 17:50 / 20:50.
schtasks /Create /F /TN "HotTopic_0800" /SC DAILY /ST 07:20 /TR "\"%~dp0run_slot.bat\" 08:00"
schtasks /Create /F /TN "HotTopic_1230" /SC DAILY /ST 11:50 /TR "\"%~dp0run_slot.bat\" 12:30"
schtasks /Create /F /TN "HotTopic_1830" /SC DAILY /ST 17:50 /TR "\"%~dp0run_slot.bat\" 18:30"
schtasks /Create /F /TN "HotTopic_2130" /SC DAILY /ST 20:50 /TR "\"%~dp0run_slot.bat\" 21:30"
echo.
echo Done. 4 tasks named HotTopic_ were added to Task Scheduler.
pause

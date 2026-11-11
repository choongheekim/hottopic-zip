@echo off
chcp 65001 >nul
for %%s in (0800 1230 1830 2130) do schtasks /Delete /F /TN "HotTopic_%%s"
echo All scheduled runs removed.
pause

@echo off
chcp 65001 >nul
cd /d %~dp0
echo [1/3] Installing Python packages
python -m pip install -r requirements.txt
echo.
echo [2/3] Checking Claude Code
where claude
claude --version
echo.
echo [3/3] Checking GitHub connection
if not exist config.txt (
  echo config.txt not found. Copy config_example.txt to config.txt and fill GITHUB_TOKEN.
) else (
  python -c "import sys,os;sys.path.insert(0,'.');from pc.run import load_config;load_config();from pc import ghup;print('GitHub OK:',ghup.check())"
)
echo.
pause

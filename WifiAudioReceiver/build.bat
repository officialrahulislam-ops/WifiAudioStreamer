@echo off
setlocal
cd /d "%~dp0"
if not exist .venv py -3 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt || exit /b 1
python assets\make_icon.py || exit /b 1
pyinstaller --noconfirm --clean --onefile --windowed --name WifiAudioReceiver --icon assets\icon.ico --collect-all av --collect-all sounddevice --collect-all _sounddevice_data main.py || exit /b 1
echo.
echo Built: %~dp0dist\WifiAudioReceiver.exe

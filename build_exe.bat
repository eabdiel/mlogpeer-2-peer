@echo off
setlocal
python -m pip install -r requirements.txt
python -m pip install pyinstaller
pyinstaller --clean --noconfirm --name Mlog --onefile -m mlog.main
echo.
echo Built dist\Mlog.exe
endlocal

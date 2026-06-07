@echo off

pip install pyinstaller

pyinstaller ^
  --onefile ^
  --windowed ^
  --clean ^
  --noupx ^
  --name "Address Jigger" ^
  "abu's address jigger.py"

echo.
echo Build complete.
echo EXE located in:
echo dist\Address Jigger.exe

pause

@echo off
:: =============================
:: Build script for Garbage Collector
:: =============================

set ENTRY=main.py

set EXE_NAME=GarbageCollector.exe

:: Icon file
set ICON=trash-logo.ico

:: Cleanup previous builds
echo Cleaning previous builds...
rmdir /s /q build
rmdir /s /q dist
del /q "%EXE_NAME%"

:: Build with PyInstaller
echo Building executable...
pyinstaller --clean --onefile --noconsole --icon="%ICON%" --name "%EXE_NAME%" "%ENTRY%"

:: Cleanup spec file and temporary folders
del /q "%ENTRY:.py=.spec%"
del /q "%EXE_NAME:.py=.spec%"
rmdir /s /q build

echo Build finished. Executable is in the 'dist' folder.
pause

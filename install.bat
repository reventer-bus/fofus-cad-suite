@echo off
title FOFUS CAD Suite installer
where py >nul 2>nul && (py install.py & goto done)
where python >nul 2>nul && (python install.py & goto done)
echo Python 3 not found. Install it from https://www.python.org/downloads/
echo (tick "Add python.exe to PATH" during install), then re-run this file.
pause
:done
echo.
pause
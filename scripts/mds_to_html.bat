@echo off

python scripts\mds_to_html.py
if ERRORLEVEL 1 exit /b %ERRORLEVEL%
copy scripts\main.* build
if ERRORLEVEL 1 exit /b %ERRORLEVEL%
xcopy scripts\images build\images /S /I
if ERRORLEVEL 1 exit /b %ERRORLEVEL%

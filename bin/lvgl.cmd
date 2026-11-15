@echo off
setlocal
rem Unified skill entry. Python 3.9+ must be on PATH; the package does not
rem bundle a runtime.
set "LVGL_AI_ROOT=%~dp0.."
set "LVGL_AI_PY="
where python >nul 2>nul
if not errorlevel 1 set "LVGL_AI_PY=python"
if not defined LVGL_AI_PY (
  where py >nul 2>nul
  if not errorlevel 1 set "LVGL_AI_PY=py -3"
)
if not defined LVGL_AI_PY (
  echo [lvgl] Python 3.9+ was not found on PATH. 1>&2
  exit /b 2
)
%LVGL_AI_PY% -I -B "%LVGL_AI_ROOT%\core\tools\lvgl.py" %*
exit /b %ERRORLEVEL%

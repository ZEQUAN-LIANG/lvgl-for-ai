@echo off
setlocal
rem Unified skill entry. The package may later ship an embedded Python under
rem runtime\python; until then fall back to python on PATH.
set "LVGL_AI_ROOT=%~dp0.."
if exist "%LVGL_AI_ROOT%\runtime\python\python.exe" (
  set "LVGL_AI_PY=%LVGL_AI_ROOT%\runtime\python\python.exe"
) else (
  set "LVGL_AI_PY=python"
)
"%LVGL_AI_PY%" -I -B "%LVGL_AI_ROOT%\core\tools\lvgl.py" %*
exit /b %ERRORLEVEL%

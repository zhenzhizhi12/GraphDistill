@echo off
setlocal enabledelayedexpansion

REM Install CangjieTreeSitter Python binding (tree_sitter_cangjie) on Windows.
REM This script:
REM  1) uses vswhere.exe to find the latest VS Build Tools with C++ toolchain
REM  2) calls VsDevCmd.bat to load cl.exe environment
REM  3) runs pip install on bindings/python
REM
REM Repository: https://github.com/SunriseSummer/CangjieTreeSitter.git

set "VSWHERE=C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" (
  echo [ERROR] vswhere.exe not found: "%VSWHERE%"
  exit /b 1
)

for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do (
  set "VSINST=%%i"
)

if not defined VSINST (
  echo [ERROR] VS installationPath not found via vswhere.
  exit /b 1
)

set "VSDEVCMD=%VSINST%\Common7\Tools\VsDevCmd.bat"
if not exist "%VSDEVCMD%" (
  echo [ERROR] VsDevCmd.bat not found: "%VSDEVCMD%"
  exit /b 1
)

call "%VSDEVCMD%" -no_logo -arch=amd64

where cl.exe >nul 2>nul
if errorlevel 1 (
  echo [ERROR] cl.exe not found after VsDevCmd.bat. Please ensure MSVC Build Tools are installed.
  exit /b 1
)

set "BINDING_DIR=%~dp0..\temp_repos\CangjieTreeSitter\bindings\python"
if not exist "%BINDING_DIR%\pyproject.toml" (
  echo [ERROR] binding directory not found or invalid: "%BINDING_DIR%"
  exit /b 1
)

echo [INFO] Installing CangjieTreeSitter Python binding from: "%BINDING_DIR%"
pip install --upgrade "%BINDING_DIR%"
exit /b %errorlevel%


@echo off
rem Builds FujinEffects.dll (32-bit: it runs in FF8_EN.exe), the host of the effects Fujin writes
rem (fxhost.cpp). Needs the Visual Studio C++ build tools (found with vswhere, as the recorder's
rem build.bat) and FFNx's effect sources (ExternalTools\FFNx\fx, from the updater's FFNxEffects).
setlocal EnableDelayedExpansion
cd /d %~dp0
where cl >nul 2>nul
if not errorlevel 1 goto build
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if exist "%VSWHERE%" for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do (
  if exist "%%i\VC\Auxiliary\Build\vcvarsall.bat" call "%%i\VC\Auxiliary\Build\vcvarsall.bat" x86 >nul
)
where cl >nul 2>nul
if not errorlevel 1 goto build
for %%v in (2022 2019) do for %%e in (Community Professional Enterprise BuildTools) do (
  if exist "C:\Program Files\Microsoft Visual Studio\%%v\%%e\VC\Auxiliary\Build\vcvarsall.bat" call "C:\Program Files\Microsoft Visual Studio\%%v\%%e\VC\Auxiliary\Build\vcvarsall.bat" x86 >nul
  if exist "C:\Program Files (x86)\Microsoft Visual Studio\%%v\%%e\VC\Auxiliary\Build\vcvarsall.bat" call "C:\Program Files (x86)\Microsoft Visual Studio\%%v\%%e\VC\Auxiliary\Build\vcvarsall.bat" x86 >nul
)
where cl >nul 2>nul
if not errorlevel 1 goto build
echo no Visual Studio C++ build tools found (cl.exe)
exit /b 9009
:build
set "FX=%~dp0..\..\ExternalTools\FFNx\fx"
if exist "%FX%\fx_layouts.h" goto compile
echo FFNx's effect sources are missing (ExternalTools\FFNx\fx: the updater's FFNxEffects)
exit /b 3
:compile
if not exist obj mkdir obj
cl /nologo /std:c++20 /EHa /W3 /O1 /MT /LD /bigobj /DNOMINMAX /D_CRT_SECURE_NO_WARNINGS /I"%FX%" fxhost.cpp /Foobj\ /FeFujinEffects.dll /link /LARGEADDRESSAWARE
set E=%ERRORLEVEL%
echo build FujinEffects.dll exit %E%
exit /b %E%

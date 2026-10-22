@echo off
rem Builds fxrecorder.exe (32-bit: it runs FF8_EN.exe's code in its own process).
rem Needs the Visual Studio C++ build tools. The image is based at 0x10000000 so 0x400000 stays
rem free for the game exe.
setlocal
cd /d %~dp0
where cl >nul 2>nul
if errorlevel 1 (
  for %%v in (2022 2019) do for %%e in (Community Professional Enterprise BuildTools) do (
    if exist "C:\Program Files\Microsoft Visual Studio\%%v\%%e\VC\Auxiliary\Build\vcvarsall.bat" call "C:\Program Files\Microsoft Visual Studio\%%v\%%e\VC\Auxiliary\Build\vcvarsall.bat" x86 >nul
    if exist "C:\Program Files (x86)\Microsoft Visual Studio\%%v\%%e\VC\Auxiliary\Build\vcvarsall.bat" call "C:\Program Files (x86)\Microsoft Visual Studio\%%v\%%e\VC\Auxiliary\Build\vcvarsall.bat" x86 >nul
  )
)
if not exist obj mkdir obj
cl /nologo /std:c++17 /EHa /W3 /O1 /MT /DNOMINMAX /D_CRT_SECURE_NO_WARNINGS fxrecorder.cpp /Foobj\ /Fefxrecorder.exe /link /BASE:0x10000000 /DYNAMICBASE:NO /FIXED /LARGEADDRESSAWARE
set E=%ERRORLEVEL%
echo build fxrecorder.exe exit %E%
exit /b %E%

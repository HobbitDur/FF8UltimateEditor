@echo off
rem Builds fxrecorder.exe (32-bit: it runs FF8_EN.exe's code in its own process).
rem Needs the Visual Studio C++ build tools (any version: found with vswhere). The image is based
rem at 0x10000000 so 0x400000 stays free for the game exe. FF8UltimateEditor runs this by itself
rem when started from source (Fujin/recorderbuild.py); the release ships the exe its CI builds.
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
if not exist obj mkdir obj
rem Effect lab: with FFNx's effect sources (ExternalTools\FFNx\fx, from the updater), the effect
rem ports that have parameters are built in (native=1, params=, schema=): every module naming
rem FX_LAB_MODULE (older sources: Cure)
set "FX=%~dp0..\..\ExternalTools\FFNx\fx"
set LAB=
if not exist "%FX%\fx_params.h" goto compile
rem (the modules listed in a response file: more of them than a command line holds)
set "RSP=obj\lab.rsp"
if exist "%RSP%" del "%RSP%"
for /f "delims=" %%f in ('findstr /m /c:"FX_LAB_MODULE(register" "%FX%\mag*.cpp" 2^>nul') do echo "%%f">>"%RSP%"
if not exist "%RSP%" echo "%FX%\mag001_cure.cpp">"%RSP%"
set ACT=
set ACTORS=
set GFC=
set EDEN=
set BROTHERS=
set BAHAMUT=
set LEV=
for /f "usebackq delims=" %%f in ("%RSP%") do (
  findstr /m /c:"act_engine.h" %%f >nul 2>nul && set ACT=1
  findstr /m /c:"fx_actors.h" %%f >nul 2>nul && set ACTORS=1
  findstr /m /c:"gfc_engine.h" %%f >nul 2>nul && set GFC=1
  findstr /m /c:"apply_eden_" %%f >nul 2>nul && set EDEN=1
  findstr /m /c:"apply_brothers" %%f >nul 2>nul && set BROTHERS=1
  findstr /m /c:"apply_bahamut" %%f >nul 2>nul && set BAHAMUT=1
  findstr /m /c:"apply_lev_" %%f >nul 2>nul && set LEV=1
)
rem a cinematic clone borrowing Eden's draw handlers (Hell's Judgement, the final form's death: apply_eden_*) needs Eden's module
if defined EDEN if exist "%FX%\mag_eden.cpp" echo "%FX%\mag_eden.cpp">>"%RSP%"
rem (a cinematic clone borrowing the Brothers' handlers: Water's apply_brothers)
if defined BROTHERS if exist "%FX%\mag_brothers.cpp" findstr /m /c:"mag_brothers.cpp" "%RSP%" >nul 2>nul || echo "%FX%\mag_brothers.cpp">>"%RSP%"
rem (a cinematic clone borrowing Bahamut's: apply_bahamut)
if defined BAHAMUT if exist "%FX%\mag_bahamut.cpp" findstr /m /c:"mag_bahamut.cpp" "%RSP%" >nul 2>nul || echo "%FX%\mag_bahamut.cpp">>"%RSP%"
rem (a cinematic clone borrowing Leviathan's: Earthquake's apply_lev_a)
if defined LEV if exist "%FX%\mag_leviathan.cpp" findstr /m /c:"mag_leviathan.cpp" "%RSP%" >nul 2>nul || echo "%FX%\mag_leviathan.cpp">>"%RSP%"
rem the modules built on the actor engine (act_engine.h) need it and its actor system compiled in
if defined ACT if exist "%FX%\act_engine.cpp" echo "%FX%\act_engine.cpp">>"%RSP%"
if defined ACTORS if exist "%FX%\fx_actors.cpp" echo "%FX%\fx_actors.cpp">>"%RSP%"
rem the modules built on the GF cinematic engine (gfc_engine.h) need it compiled in
if defined GFC if exist "%FX%\gfc_engine.cpp" echo "%FX%\gfc_engine.cpp">>"%RSP%"
set LAB=/DFF8_FX_LAB /I"%FX%" @"%RSP%"
:compile
cl /nologo /std:c++20 /EHa /W3 /O1 /MT /DNOMINMAX /D_CRT_SECURE_NO_WARNINGS fxrecorder.cpp %LAB% /Foobj\ /Fefxrecorder.exe /link /BASE:0x10000000 /DYNAMICBASE:NO /FIXED /LARGEADDRESSAWARE
set E=%ERRORLEVEL%
echo build fxrecorder.exe exit %E%
rem the game's host of Fujin's effects (Tools\fxhost: FujinEffects.dll), from the same sources
if "%E%"=="0" if not "%LAB%"=="" call "%~dp0..\fxhost\build.bat"
exit /b %E%

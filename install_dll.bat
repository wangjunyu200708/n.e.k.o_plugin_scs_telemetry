@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

echo ========================================
echo   SCS SDK Plugin - DLL Installer
echo ========================================
echo.

:: -- 1. Check system arch --
if "%PROCESSOR_ARCHITECTURE%"=="AMD64" (
    set "ARCH=Win64"
    set "GAME_ARCH=win_x64"
    echo [OK] System: 64-bit
) else if "%PROCESSOR_ARCHITECTURE%"=="x86" (
    set "ARCH=Win32"
    set "GAME_ARCH=win_x86"
    echo [OK] System: 32-bit
) else (
    echo [ERR] Unknown arch: %PROCESSOR_ARCHITECTURE%
    pause
    exit /b 1
)
echo.

:: -- 2. DLL source dir --
set "SCRIPT_DIR=%~dp0"
set "DLL_SRC=%SCRIPT_DIR%dlls\%ARCH%"

if not exist "%DLL_SRC%" (
    echo [ERR] DLL source dir not found: %DLL_SRC%
    pause
    exit /b 1
)

set "DLL_COUNT=0"
for %%f in ("%DLL_SRC%\*.dll") do set /a DLL_COUNT+=1

if !DLL_COUNT!==0 (
    echo [ERR] No DLL files found in: %DLL_SRC%
    echo        Please put compiled DLLs there first.
    pause
    exit /b 1
)

echo [OK] DLL source: %DLL_SRC%
echo      Found !DLL_COUNT! DLL file(s)
echo.

:: -- 3. Search game install dir --
echo [*] Searching for game installation...
echo.

set "GAME_ROOT="

:: 3a. Check common Steam paths for ETS2
call :CheckGameDir "C:\Program Files (x86)\Steam\steamapps\common" "Euro Truck Simulator 2"
call :CheckGameDir "D:\SteamLibrary\steamapps\common" "Euro Truck Simulator 2"
call :CheckGameDir "D:\Steam\steamapps\common" "Euro Truck Simulator 2"
call :CheckGameDir "E:\SteamLibrary\steamapps\common" "Euro Truck Simulator 2"
call :CheckGameDir "E:\Steam\steamapps\common" "Euro Truck Simulator 2"
call :CheckGameDir "F:\SteamLibrary\steamapps\common" "Euro Truck Simulator 2"
call :CheckGameDir "F:\Steam\steamapps\common" "Euro Truck Simulator 2"
call :CheckGameDir "G:\SteamLibrary\steamapps\common" "Euro Truck Simulator 2"

:: 3b. Parse libraryfolders.vdf for extra Steam libraries
if not defined GAME_ROOT (
    call :ScanSteamLibs "C:\Program Files (x86)\Steam\steamapps\libraryfolders.vdf"
    call :ScanSteamLibs "D:\Steam\steamapps\libraryfolders.vdf"
    call :ScanSteamLibs "E:\Steam\steamapps\libraryfolders.vdf"
)

:: 3c. Try ATS if ETS2 not found
if not defined GAME_ROOT (
    call :CheckGameDir "C:\Program Files (x86)\Steam\steamapps\common" "American Truck Simulator"
    call :CheckGameDir "D:\SteamLibrary\steamapps\common" "American Truck Simulator"
    call :CheckGameDir "D:\Steam\steamapps\common" "American Truck Simulator"
    call :CheckGameDir "E:\SteamLibrary\steamapps\common" "American Truck Simulator"
    call :CheckGameDir "E:\Steam\steamapps\common" "American Truck Simulator"
    call :CheckGameDir "F:\SteamLibrary\steamapps\common" "American Truck Simulator"
    call :CheckGameDir "F:\Steam\steamapps\common" "American Truck Simulator"
    call :CheckGameDir "G:\SteamLibrary\steamapps\common" "American Truck Simulator"
)

:: 3d. Manual input
if not defined GAME_ROOT (
    echo.
    echo [!] Could not auto-detect game directory.
    echo.
    set /p "GAME_ROOT=Enter game root path (e.g. D:\SteamLibrary\steamapps\common\Euro Truck Simulator 2): "
    if not defined GAME_ROOT (
        echo [ERR] No path entered. Exiting.
        pause
        exit /b 1
    )
    set "GAME_ROOT=!GAME_ROOT:"=!"
)

echo.
echo [OK] Game root: %GAME_ROOT%
echo.

:: -- 4. Validate game dir --
if not exist "%GAME_ROOT%" (
    echo [ERR] Directory does not exist: %GAME_ROOT%
    pause
    exit /b 1
)

:: -- 5. Build target path and install --
set "PLUGIN_DIR=%GAME_ROOT%\bin\%GAME_ARCH%\plugins"

echo [OK] Target: %PLUGIN_DIR%
echo.

if not exist "%PLUGIN_DIR%" (
    echo [*] Creating plugins directory...
    mkdir "%PLUGIN_DIR%"
    if errorlevel 1 (
        echo [ERR] Failed to create directory. Try running as Administrator.
        pause
        exit /b 1
    )
    echo [OK] Directory created.
) else (
    echo [OK] Plugins directory already exists.
)
echo.

:: Copy DLLs
echo [*] Copying DLL files...
echo.
set "COPY_COUNT=0"
for %%f in ("%DLL_SRC%\*.dll") do (
    copy /Y "%%f" "%PLUGIN_DIR%\" >nul 2>&1
    if errorlevel 1 (
        echo      [FAIL] %%~nxf
    ) else (
        echo      [OK] %%~nxf -^> %PLUGIN_DIR%
        set /a COPY_COUNT+=1
    )
)

echo.
set "RESULT_COUNT=!COPY_COUNT!"
if "%RESULT_COUNT%"=="0" goto :install_failed
echo ========================================
echo   Done! Copied %RESULT_COUNT% DLL file(s)
echo ========================================
echo.
echo   Target: %PLUGIN_DIR%
echo.
echo   Note: Game will show an SDK activation prompt
echo   on startup - click OK to confirm.
goto :install_end

:install_failed
echo ========================================
echo   Failed - no files were copied
echo ========================================

:install_end

echo.
pause
exit /b 0


:: ============ Subroutines ============

:CheckGameDir
if not defined GAME_ROOT (
    set "CHECK_BASE=%~1"
    set "CHECK_GAME=%~2"
    if exist "!CHECK_BASE!\!CHECK_GAME!" (
        set "GAME_ROOT=!CHECK_BASE!\!CHECK_GAME!"
        echo      [OK] Found: !CHECK_BASE!\!CHECK_GAME!
    )
)
exit /b

:ScanSteamLibs
set "VDF_FILE=%~1"
if not defined GAME_ROOT (
    if exist "%VDF_FILE%" (
        for /f "usebackq tokens=1,* delims=" %%a in ("%VDF_FILE%") do (
            if not defined GAME_ROOT (
                echo %%a | findstr /i /c:"path" >nul 2>&1
                if not errorlevel 1 (
                    for /f "tokens=2 delims=\"" %%p in ("%%a") do (
                        if not defined GAME_ROOT (
                            if exist "%%p\steamapps\common\Euro Truck Simulator 2" (
                                set "GAME_ROOT=%%p\steamapps\common\Euro Truck Simulator 2"
                                echo      [OK] Found via Steam lib: %%p\steamapps\common\Euro Truck Simulator 2
                            )
                        )
                    )
                )
            )
        )
    )
)
exit /b

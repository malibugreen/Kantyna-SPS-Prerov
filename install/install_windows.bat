@echo off
chcp 65001 >nul
title Instalace knihoven pro kantýnu

echo ========================================================
echo   Instalace potřebných knihoven pro systém kantýny
echo ========================================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    where py >nul 2>nul
    if %ERRORLEVEL% NEQ 0 (
        echo [CHYBA] Python nebyl v systému nalezen!
        echo Ujistěte se, že máte nainstalovaný Python a při instalaci
        echo jste zaškrtli volbu "Add Python to PATH".
        echo.
        pause
        exit /b 1
    ) else (
        set PY_CMD=py
    )
) else (
    set PY_CMD=python
)

echo Detekován příkaz: %PY_CMD%
echo.
echo Aktualizace pip...
%PY_CMD% -m pip install --upgrade pip

echo.
echo Instalace požadovaných balíčků:
echo  - customtkinter (moderní grafické rozhraní)
echo  - Pillow (zpracování fotek a ikon)
echo  - requests (komunikace s Firebase databází)
echo  - certifi (SSL certifikáty)
echo  - urllib3 (síťová vrstva)
echo.

%PY_CMD% -m pip install -r "%~dp0requirements.txt"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================================
    echo   [HOTOVO] Všechny knihovny byly úspěšně nainstalovány!
    echo ========================================================
) else (
    echo.
    echo ========================================================
    echo   [VAROVÁNÍ] Při instalaci došlo k chybě.
    echo   Zkontrolujte připojení k internetu a zkuste to znovu.
    echo ========================================================
)

echo.
echo Klikněte jakékoliv tlačítko pro dokončení...
pause >nul

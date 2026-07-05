@echo off
title Cross Monitor
cd /d "%~dp0"

rem ── Verificar que los archivos necesarios esten en esta carpeta ──
if not exist "server.py" (
    echo [ERROR] No se encuentra server.py en esta carpeta.
    echo Coloca CrossMonitor.bat, server.py y cross_monitor_v3.html juntos.
    pause
    exit /b 1
)
if not exist "cross_monitor_v3.html" (
    echo [ERROR] No se encuentra cross_monitor_v3.html en esta carpeta.
    echo Coloca CrossMonitor.bat, server.py y cross_monitor_v3.html juntos.
    pause
    exit /b 1
)

rem ── Buscar Python (py launcher o python) ──
where py >nul 2>nul
if %errorlevel%==0 (
    set "PYCMD=py"
    goto :run
)
where python >nul 2>nul
if %errorlevel%==0 (
    set "PYCMD=python"
    goto :run
)

echo [ERROR] Python no esta instalado.
echo.
echo Instalalo desde Microsoft Store buscando "Python 3.12"
echo o desde https://www.python.org/downloads/
echo Luego vuelve a hacer doble clic en este archivo.
pause
exit /b 1

:run
echo ============================================
echo   CROSS MONITOR - Golden / Death Cross
echo ============================================
echo.
echo Iniciando servidor... el navegador se abrira solo.
echo NO CIERRES esta ventana mientras uses el monitor.
echo Para detener: cierra esta ventana o presiona Ctrl+C.
echo.
%PYCMD% server.py
pause

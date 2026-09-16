@echo off
setlocal EnableDelayedExpansion
title Cross Monitor
cd /d "%~dp0"

rem ── Entorno Python dedicado (se crea solo la primera vez) ──
set VENV_DIR=%~dp0.venv314
set VENV_PY=%VENV_DIR%\Scripts\python.exe
set SETUP_OK=%VENV_DIR%\.setup_ok

if not exist "!SETUP_OK!" (
    echo Preparando el entorno por primera vez, un momento...
    where py >nul 2>nul
    if !errorlevel!==0 (
        set PYCMD=py
    ) else (
        where python >nul 2>nul
        if !errorlevel!==0 (
            set PYCMD=python
        ) else (
            echo [ERROR] No se encontro Python instalado.
            echo Instalalo desde https://www.python.org/downloads/ y vuelve a abrir este icono.
            pause
            exit /b 1
        )
    )
    if not exist "!VENV_PY!" !PYCMD! -m venv "!VENV_DIR!"
    "!VENV_PY!" -m pip install --upgrade pip -q
    "!VENV_PY!" -m pip install -r backend\requirements.txt -q
    if errorlevel 1 (
        rem Las versiones fijadas en requirements.txt pueden no tener wheel
        rem precompilado para un Python muy nuevo ^(ej. pydantic-core en 3.14^).
        rem Reintenta sin fijar version, igual que en desarrollo.
        echo Reintentando con versiones mas recientes...
        "!VENV_PY!" -m pip install --upgrade fastapi "uvicorn[standard]" pydantic pydantic-settings apscheduler yfinance pywebpush httpx pytest -q
        if errorlevel 1 (
            echo [ERROR] No se pudieron instalar las dependencias.
            pause
            exit /b 1
        )
    )
    echo ok > "!SETUP_OK!"
)

echo ============================================
echo   CROSS MONITOR - Golden / Death Cross
echo ============================================
echo.
echo Iniciando el servidor... el navegador se abrira solo.
echo NO CIERRES esta ventana mientras uses la app.
echo Para detener: cierra esta ventana o presiona Ctrl+C.
echo.
"%VENV_PY%" scripts\run_local.py
pause

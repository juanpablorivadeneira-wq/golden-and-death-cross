@echo off
setlocal EnableDelayedExpansion
title Detener Cross Monitor
echo Buscando Cross Monitor (puertos 8000 y 8080)...
set FOUND=0
for %%P in (8000 8080) do (
    for /f "tokens=5" %%Q in ('netstat -ano ^| findstr ":%%P " ^| findstr "LISTENING"') do (
        echo Deteniendo proceso %%Q ^(puerto %%P^)...
        taskkill /PID %%Q /F >nul 2>nul
        set FOUND=1
    )
)
if "!FOUND!"=="0" (
    echo Cross Monitor no esta corriendo.
) else (
    echo Cross Monitor detenido.
)
ping -n 3 127.0.0.1 >nul

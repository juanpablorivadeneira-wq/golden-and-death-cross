@echo off
setlocal
 title Cross Monitor - Radar diario
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "CROSS_PY=.venv\Scripts\python.exe"
) else (
  echo Falta el entorno de la aplicacion.
  echo Preparalo con Python 3.12 e instala backend\requirements.txt.
  pause
  exit /b 1
)
echo Cross Monitor - acceso local sin token
echo Revision diaria a las 17:00 de Nueva York. No consume tokens de IA.
echo Mantener esta ventana abierta para recibir alertas.
"%CROSS_PY%" -B scripts\run_local.py
pause

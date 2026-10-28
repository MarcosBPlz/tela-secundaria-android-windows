@echo off
cd /d "%~dp0"
set "PYTHON="
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" set "PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not defined PYTHON (
  where py >nul 2>nul
  if not errorlevel 1 set "PYTHON=py -3"
)
if not defined PYTHON (
  where python >nul 2>nul
  if not errorlevel 1 set "PYTHON=python"
)
if not defined PYTHON (
  where python3 >nul 2>nul
  if not errorlevel 1 set "PYTHON=python3"
)
if not defined PYTHON (
  echo Python nao foi encontrado neste computador.
  echo Instale Python 3.11 ou superior e tente novamente.
  pause
  exit /b 1
)
if not exist "packages\winrt\windows\media\control" (
  echo Preparando a integracao de audio do Windows na primeira inicializacao...
  %PYTHON% -m pip install --disable-pip-version-check --target "%~dp0packages" -r requirements.txt
  if errorlevel 1 (
    echo Nao foi possivel instalar a integracao de audio. Verifique a conexao e tente novamente.
    pause
    exit /b 1
  )
)
set "PYTHONPATH=%~dp0packages;%PYTHONPATH%"
%PYTHON% server.py
if errorlevel 1 (
  echo.
  echo O painel nao conseguiu iniciar. Veja a mensagem de erro acima.
  pause
)

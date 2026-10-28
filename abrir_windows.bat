@echo off
setlocal
cd /d "%~dp0"

rem Se o Tela Tablet ja estiver rodando (icone na bandeja), so abre o painel.
curl.exe -fsS --max-time 1 http://127.0.0.1:47811/api/status >nul 2>nul
if not errorlevel 1 goto openapp

rem ---- Encontra o Python (com e sem janela)
set "PY="
set "PYW="
set "CODEX=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python"
if exist "%CODEX%\python.exe" set "PY=%CODEX%\python.exe"
if exist "%CODEX%\pythonw.exe" set "PYW=%CODEX%\pythonw.exe"
if not defined PY for /f "delims=" %%i in ('where python 2^>nul') do if not defined PY set "PY=%%i"
if not defined PYW for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%i"
if not defined PYW if defined PY (
  for %%d in ("%PY%") do if exist "%%~dpdpythonw.exe" set "PYW=%%~dpdpythonw.exe"
)
set "USE_PYLAUNCHER="
if not defined PYW (
  where pyw >nul 2>nul
  if not errorlevel 1 set "USE_PYLAUNCHER=1"
)
if not defined PYW if not defined USE_PYLAUNCHER (
  echo Python nao foi encontrado neste computador.
  echo Instale Python 3.11 ou superior e tente novamente.
  pause
  exit /b 1
)

rem ---- Primeira vez: instala a integracao de musica do Windows
if not exist "packages\winrt\windows\media\control" (
  echo Preparando a integracao de audio do Windows na primeira inicializacao...
  if defined PY ( "%PY%" -m pip install --disable-pip-version-check --target "%~dp0packages" -r requirements.txt ) else ( py -3 -m pip install --disable-pip-version-check --target "%~dp0packages" -r requirements.txt )
)

rem ---- Inicia escondido, so com o icone perto do relogio (o proprio icone abre o painel)
set "TABLET_PANEL_PORT=47811"
if defined PYW (
  start "" "%PYW%" "%~dp0tray.py"
) else (
  start "" pyw -3 "%~dp0tray.py"
)
exit /b 0

:openapp
if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" (
  start "" "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" --app=http://127.0.0.1:47811
) else if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" (
  start "" "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" --app=http://127.0.0.1:47811
) else (
  start "" http://127.0.0.1:47811
)
exit /b 0

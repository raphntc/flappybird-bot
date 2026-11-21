@echo off
setlocal
title Flappy Bot
cd /d "%~dp0"

rem ---------------------------------------------------------------- python
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo [!] Python nao encontrado.
    echo     Instale em https://www.python.org/downloads/ e marque
    echo     "Add python.exe to PATH" durante a instalacao.
    echo.
    pause
    exit /b 1
)

rem ---------------------------------------------------------------- padroes
set "CFG=flappy_config.json"
set "ACTION=click"
set "DEBUG=nao"

rem confere as bibliotecas uma vez ao abrir
%PY% -c "import cv2, numpy, mss, pyautogui, pynput" >nul 2>&1
if errorlevel 1 (
    cls
    echo [!] Faltam bibliotecas do bot.
    choice /c SN /n /m "Instalar agora? [S/N] "
    if not errorlevel 2 call :install
)

rem ---------------------------------------------------------------- menu
:menu
cls
if exist "%CFG%" (set "STATUS=calibrado") else (set "STATUS=NAO calibrado - use a opcao 2")
if "%ACTION%"=="click" (set "ACTION_TXT=clique do mouse") else (set "ACTION_TXT=tecla espaco")
echo ==================================================
echo                    FLAPPY BOT
echo ==================================================
echo   Config : %CFG% (%STATUS%)
echo   Pulo   : %ACTION_TXT%
echo   Debug  : %DEBUG%
echo --------------------------------------------------
echo   1) Iniciar bot
echo   2) Calibrar (outro jogo, janela movida...)
echo   3) Alternar pulo (clique / espaco)
echo   4) Alternar janela de debug
echo   5) Trocar arquivo de config
echo   6) Instalar / atualizar bibliotecas
echo   7) Ajuda
echo   0) Sair
echo ==================================================
choice /c 12345670 /n /m "Escolha uma opcao: "
if errorlevel 8 goto :eof
if errorlevel 7 goto help
if errorlevel 6 goto install_menu
if errorlevel 5 goto config
if errorlevel 4 goto toggle_debug
if errorlevel 3 goto toggle_action
if errorlevel 2 goto calibrate
goto start

rem ---------------------------------------------------------------- acoes
:start
set "ARGS=--config "%CFG%" --action %ACTION%"
if "%DEBUG%"=="sim" set "ARGS=%ARGS% --debug"
cls
echo [*] Clique no jogo, comece a partida e aperte F8 para ligar o bot.
echo     F8 liga/pausa  -  ESC sai  -  mouse no canto superior esquerdo para tudo
echo.
%PY% flappy_bot.py %ARGS%
goto after_run

:calibrate
set "ARGS=--calibrate --config "%CFG%" --action %ACTION%"
if "%DEBUG%"=="sim" set "ARGS=%ARGS% --debug"
cls
%PY% flappy_bot.py %ARGS%
goto after_run

:after_run
echo.
echo [*] O bot terminou. Voltando ao menu.
pause
goto menu

:toggle_action
if "%ACTION%"=="click" (set "ACTION=space") else (set "ACTION=click")
goto menu

:toggle_debug
if "%DEBUG%"=="nao" (set "DEBUG=sim") else (set "DEBUG=nao")
goto menu

:config
cls
echo Arquivos de config nesta pasta:
dir /b *.json 2>nul || echo   (nenhum)
echo.
echo Digite o nome do arquivo (pode ser novo, ex.: site2.json).
set "NEW="
set /p "NEW=ENTER mantem %CFG%: "
if defined NEW set "CFG=%NEW%"
goto menu

:install_menu
cls
call :install
pause
goto menu

:help
cls
echo COMO USAR
echo.
echo  1. Abra o jogo e deixe o passaro e um cano na tela.
echo  2. Opcao 2 (Calibrar): com o jogo em foco aperte F9, arraste um
echo     retangulo do topo do jogo ate LOGO ACIMA do chao e confirme.
echo     Na conferencia: ENTER aceita, M marca com o mouse, R recaptura.
echo  3. Opcao 1 (Iniciar): clique no jogo, comece a partida e aperte F8.
echo.
echo  - Mudou a janela do jogo de lugar ou de tamanho? Calibre de novo.
echo  - Um config por jogo: use a opcao 5 (ex.: site1.json, site2.json).
echo  - Jogo nao aceita clique? Troque o pulo para espaco (opcao 3).
echo  - A janela de debug mostra o que o bot ve (deixa o bot mais lento).
echo.
echo  Mais detalhes no README.md.
echo.
pause
goto menu

rem ---------------------------------------------------------------- subrotinas
:install
echo [*] Instalando bibliotecas...
%PY% -m pip install --upgrade -r requirements.txt
if errorlevel 1 (
    echo [!] Falhou. Confira sua internet e tente de novo.
) else (
    echo [ok] Bibliotecas instaladas.
)
exit /b

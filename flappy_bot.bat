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
if exist "%CFG%" (set "STATUS=calibrado") else (set "STATUS=sem calibracao - o bot acha o jogo sozinho")
if "%ACTION%"=="click" (set "ACTION_TXT=clique do mouse") else (set "ACTION_TXT=tecla espaco")
echo ==================================================
echo                    FLAPPY BOT
echo ==================================================
echo   Config : %CFG% (%STATUS%)
echo   Pulo   : %ACTION_TXT%
echo   Debug  : %DEBUG%
echo --------------------------------------------------
echo   1) Iniciar bot (acha o jogo sozinho)
echo   2) Procurar o jogo de novo (ignora a calibracao salva)
echo   3) Calibrar manualmente (F9/ENTER + marcar a area)
echo   4) Alternar pulo (clique / espaco)
echo   5) Alternar janela de debug
echo   6) Trocar arquivo de config
echo   7) Instalar / atualizar bibliotecas
echo   8) Ajuda
echo   0) Sair
echo ==================================================
choice /c 123456780 /n /m "Escolha uma opcao: "
if errorlevel 9 goto :eof
if errorlevel 8 goto help
if errorlevel 7 goto install_menu
if errorlevel 6 goto config
if errorlevel 5 goto toggle_debug
if errorlevel 4 goto toggle_action
if errorlevel 3 goto calibrate
if errorlevel 2 goto research
goto start

rem ---------------------------------------------------------------- acoes
:start
set "ARGS=--config "%CFG%" --action %ACTION%"
goto launch

:research
set "ARGS=--recalibrate --config "%CFG%" --action %ACTION%"
goto launch

:launch
if "%DEBUG%"=="sim" set "ARGS=%ARGS% --debug"
cls
echo [*] Abra o jogo, deixe a janela visivel e comece a partida.
echo     O bot acha o jogo sozinho e liga depois de contar 3 s.
echo     F8 pausa/liga  -  ESC sai  -  mouse no canto superior esquerdo para tudo
echo     Sem F8? ENTER aqui no terminal pausa/liga e Q sai.
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
echo  1. Abra o jogo (navegador, emulador ou celular no scrcpy) e deixe
echo     a janela visivel, sem nada por cima.
echo  2. Opcao 1: o bot procura o jogo em todas as janelas abertas.
echo  3. Comece a partida. Quando os canos aparecem ANDANDO, ele reconhece
echo     o jogo em menos de 1 s, salva a calibracao e assume sozinho.
echo.
echo  - Mudou a janela de lugar? Ele percebe (8 s sem ver o passaro) e
echo    procura o jogo de novo sozinho. Ou use a opcao 2.
echo  - Nao achou de jeito nenhum? Use a calibracao manual (opcao 3):
echo    F9 ou ENTER captura, arraste do topo do jogo ate LOGO ACIMA do
echo    chao. Na conferencia: ENTER aceita, M marca com o mouse.
echo  - F8 nao funciona? ENTER aqui no terminal pausa/liga, Q sai.
echo  - Celular com scrcpy: use pulo por clique (vira toque no celular).
echo  - Um config por jogo: use a opcao 6 (ex.: site1.json, site2.json).
echo  - Jogo nao aceita clique? Troque o pulo para espaco (opcao 4).
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

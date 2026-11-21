# flappybird bot

Bot de Flappy Bird que joga **olhando a tela**, por visão computacional. Ele não lê nem altera o código do jogo, então funciona em qualquer versão que apareça no monitor: site, emulador, celular espelhado etc.

A cada quadro ele captura a área do jogo, acha o pássaro e os canos pela cor, prevê para onde o pássaro vai e decide se deve pular (clique ou espaço).

## Requisitos

- Python 3.8+
- Bibliotecas:

```bash
pip install -r requirements.txt
```

Se faltar alguma, o próprio script avisa e mostra o comando `pip install` pronto.

## Windows: menu interativo

Dê dois cliques em **`flappy_bot.bat`**. Ele acha o Python, oferece instalar as bibliotecas que faltarem e abre um menu:

```
  1) Iniciar bot
  2) Calibrar (outro jogo, janela movida...)
  3) Alternar pulo (clique / espaco)
  4) Alternar janela de debug
  5) Trocar arquivo de config
  6) Instalar / atualizar bibliotecas
  7) Ajuda
  0) Sair
```

O topo do menu mostra qual config está em uso, se ele já foi calibrado, o modo de pulo e o debug. Quando o bot termina, você volta ao menu.

## Uso rápido (linha de comando)

```bash
python flappy_bot.py
```

1. Na primeira execução ele entra na **calibração** (veja abaixo) e salva o resultado em `flappy_config.json`.
2. Depois disso, clique no jogo, comece a partida e aperte **F8** para ligar o bot.
3. **ESC** encerra.

Nas próximas vezes ele usa a calibração salva direto.

### Opções

| Opção | O que faz |
|---|---|
| `--calibrate` | Refaz a calibração (outro jogo, outro site, janela movida) e pergunta se já quer rodar o bot |
| `--action space` | Pula com a tecla espaço em vez de clicar no centro da área do jogo |
| `--debug` | Abre uma janela mostrando o que o bot está vendo |
| `--config X.json` | Usa outro arquivo de calibração (dá para ter um por jogo) |

Exemplo: `python flappy_bot.py --config site2.json --action space --debug`

### Teclas

| Tecla | Onde | Ação |
|---|---|---|
| F9 | calibração | Captura a tela |
| ESC | calibração | Cancela |
| F8 | jogo | Liga / pausa o bot |
| ESC | jogo | Sai |
| Mouse no canto superior esquerdo | jogo | Parada de emergência (failsafe do pyautogui) |

As teclas são globais, então funcionam com o jogo em foco.

## Calibração

1. Abra o jogo com o pássaro e pelo menos um cano visíveis (se der, pause).
2. Com o jogo em foco, aperte **F9**.
3. Arraste um retângulo sobre a área do jogo, **do topo até logo acima do chão**, e confirme com ENTER ou espaço. Se o chão ficar dentro da área, a detecção de cor pode se confundir.
4. O bot tenta achar sozinho a cor dos canos e a do pássaro, e mostra uma janela de conferência:
   - **ENTER**: aceita (se ele não achou o pássaro ou os canos, vai para a marcação manual)
   - **M**: marcar com o mouse. Clique primeiro no **corpo do pássaro** e depois num **cano**
   - **R**: recapturar (aperte F9 de novo, mesma área)
   - **ESC**: sair

O arquivo salvo guarda a área da tela (`roi`), a cor HSV do pássaro e dos canos e a posição horizontal do pássaro. Se você mover ou redimensionar a janela do jogo, calibre de novo.

> A captura da calibração usa o **monitor principal**. Em quem tem mais de uma tela, deixe o jogo nele.

## Como funciona

### Detecção

- **Canos**: colunas da imagem em que boa parte dos pixels tem a cor do cano. Colunas vizinhas são agrupadas num cano, e o vão é o maior trecho vertical sem cano.
- **Pássaro**: a maior mancha com a cor do pássaro numa faixa vertical perto da posição calibrada (o pássaro não anda para os lados).
- **Autodetecção**: testa faixas de matiz e fica com a que mais parece cano (estruturas verticais altas com um vão). O pássaro é a mancha colorida compacta mais à esquerda que não é cano nem fundo.

### Decisão de pulo

O controle tem dois modos (aparecem no log como `modo=regra` e `modo=planejador`):

1. **Regra** (no começo): prevê a posição do pássaro descontando o atraso do clique e pula quando ela passa de uma linha-alvo dentro do vão do próximo cano. A linha-alvo também considera o vão do cano seguinte.
2. **Planejador** (assim que a física foi medida): a cada quadro simula cerca de 1 a 2,5 s do futuro e pergunta: *"se eu não pular agora, ainda existe alguma sequência de pulos que passa pelos próximos canos?"* Se existe, espera; se não existe, pula. Quando as duas opções são seguras, prefere a que deixa mais folga.

### Aprendizado automático

Enquanto joga, o bot mede sozinho:

- gravidade (ajuste de parábola na queda livre)
- atraso entre o clique e a reação do jogo
- força do pulo e altura que o pássaro sobe
- velocidade máxima de queda (no começo, se não há cano na tela, ele deixa o pássaro cair perto do fundo algumas vezes para medir isso)
- velocidade e largura dos canos

Ele começa no modo regra e passa para o planejador quando já tem medidas suficientes.

### Janela de debug (`--debug`)

- retângulo **magenta**: vão de cada cano detectado
- elipse **vermelha**: pássaro
- linha **amarela**: altura-alvo atual
- texto ON/OFF: estado do bot

A cada 5 s o terminal mostra FPS, se achou pássaro, nº de canos, atraso medido, gravidade e modo.

## Ajustes finos

Todos os valores ficam em `flappy_config.json` e podem ser editados à mão:

| Chave | Padrão | Significado |
|---|---|---|
| `aim` | 0.20 | Mira no modo regra: fração do vão acima da borda de baixo (0 = borda, 0.5 = centro) |
| `latency` | 0.08 | Atraso inicial clique→jogo, em segundos (é medido e ajustado sozinho) |
| `gravity` | `null` | Gravidade em px/s²; `null` deixa o bot estimar |
| `cooldown` | 0.0 | Tempo mínimo extra entre pulos (s) |
| `margin` | 1 | Folga vertical dentro do vão (px) |
| `x_scale` | 1.0 | Escala da largura detectada do pássaro |
| `x_margin` | 6 | Folga horizontal (bico e asas não têm a cor do corpo) |
| `y_margin` | 0 | Folga extra na altura do pássaro |
| `h_tol` / `s_tol` / `v_tol` | 10 / 70 / 70 | Tolerância de matiz, saturação e brilho na detecção de cor |
| `pipe_fill` | 0.25 | Fração mínima de uma coluna com a cor do cano para ela contar como cano |
| `min_bird_area` | 15 | Área mínima (px) da mancha do pássaro |

Chaves opcionais do planejador: `robust` (ex.: `0.1` só considera uma ação segura se ela funcionar com a gravidade 10% menor e 10% maior), `max_horizon` (segundos simulados, padrão 2.5) e `tiebreak` (folgas extras usadas para desempatar, padrão `[4, 2]`).

## Problemas comuns

- **Não acha o pássaro ou os canos**: refaça com `--calibrate` e use **M** para marcar à mão. Se ainda falhar, aumente `h_tol` / `s_tol` / `v_tol`.
- **Clica no lugar errado (Windows com escala 125%, 150%…)**: o script já ativa o modo "DPI aware" para corrigir isso. Se persistir, deixe a escala do Windows em 100%.
- **Bate na parte de baixo do cano**: aumente `margin` ou `y_margin`.
- **Bate na quina ao entrar ou sair do cano**: aumente `x_margin`.
- **Não reage na hora**: confira o FPS no log. Fechar a janela de debug e outros programas ajuda.
- **macOS**: dê permissão de *Gravação de Tela* e *Acessibilidade* ao terminal. **Linux**: em Wayland a captura e as teclas globais podem não funcionar; use uma sessão X11.

## Referências

- [SarvagyaVaish/FlappyBirdRL](https://github.com/SarvagyaVaish/FlappyBirdRL): estado = distância (dx, dy) do pássaro até o próximo cano
- [boppreh/flappybot](https://github.com/boppreh/flappybot): regra simples de "pula se estiver abaixo do vão"
- Bots do Dino do Chrome (ex.: dperyel/run-dino-run): captura com `mss` + ação com `pyautogui` em tempo real

## Licença

[MIT](LICENSE)

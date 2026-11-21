"""
flappy_bot.py - Bot universal de Flappy Bird por visao computacional.

Funciona em qualquer versao que apareca na tela (site, emulador, celular
espelhado), porque nao le o codigo do jogo: ele OLHA a tela.

Referencias de ideias:
  - SarvagyaVaish/FlappyBirdRL : estado = distancia (dx, dy) do passaro ate o
    proximo cano. Aqui usamos o mesmo estado, mas com uma regra fixa em vez
    de tabela Q.
  - boppreh/flappybot          : regra simples "pula se estiver abaixo do vao".
  - bots do Dino do Chrome (dperyel/run-dino-run etc.): captura com mss +
    acao com pyautogui, loop em tempo real.

Instalar (Windows/Linux/Mac):
  pip install -r requirements.txt
  (ou: pip install mss opencv-python numpy pyautogui pynput)

Uso:
  python flappy_bot.py            -> na 1a vez calibra sozinho, depois roda o bot
  python flappy_bot.py --calibrate  -> refaz a calibracao (outro jogo/site)
  Calibracao: F9 captura a tela; ele acha passaro e canos sozinho
  (se errar, aperte M e clique neles). No jogo: F8 liga/desliga, ESC sai.

Opcoes uteis:
  --action space    usa a tecla espaco em vez de clique
  --debug           mostra janela com o que o bot esta vendo
  --config X.json   arquivo de calibracao (um por jogo, se quiser)
"""

import argparse
import importlib.util
import json
import math
import os
import sys
import time

# ------------------------------------------------------------------ inicializacao
REQUIRED = {"cv2": "opencv-python", "numpy": "numpy", "mss": "mss",
            "pyautogui": "pyautogui", "pynput": "pynput"}


def check_deps(needed=REQUIRED):
    """Avisa de uma vez tudo o que falta, com o comando pronto."""
    missing = [pkg for mod, pkg in needed.items() if importlib.util.find_spec(mod) is None]
    if missing:
        sys.exit("[!] Faltam bibliotecas. Rode:\n    pip install " + " ".join(missing))


def enable_dpi_awareness():
    """No Windows com escala de tela (125%, 150%...) a captura e o clique usam
    coordenadas diferentes e o bot clica no lugar errado. Isso corrige."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def wait_hotkey(key_name="f9", msg=""):
    """Espera uma tecla global (funciona com o jogo em foco). ESC cancela."""
    from pynput import keyboard
    target = getattr(keyboard.Key, key_name)
    print(msg)
    result = {}

    def on_press(k):
        if k == target:
            result["ok"] = True
            return False
        if k == keyboard.Key.esc:
            result["ok"] = False
            return False

    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()
    if not result.get("ok"):
        sys.exit("Cancelado.")


check_deps({"cv2": "opencv-python", "numpy": "numpy"})
import cv2  # noqa: E402
import numpy as np  # noqa: E402

# ------------------------------------------------------------------ ajustes
DEFAULTS = {
    "aim": 0.20,          # mira: fracao do vao acima da borda de baixo (0=borda, 0.5=centro)
    "latency": 0.08,      # atraso inicial clique->jogo (s); o bot mede e ajusta sozinho
    "gravity": None,      # px/s^2; None = o bot estima sozinho observando a queda
    "cooldown": 0.0,      # tempo minimo extra entre pulos (s); o atraso medido ja limita
    "margin": 1,          # folga vertical no vao (px)
    "x_scale": 1.0,       # escala da largura detectada do passaro
    "x_margin": 6,        # folga horizontal (bico/asas fora da cor do corpo)
    "y_margin": 0,        # folga extra na altura do passaro
    "h_tol": 10,          # tolerancia de matiz (HSV)
    "s_tol": 70,          # tolerancia de saturacao
    "v_tol": 70,          # tolerancia de brilho
    "pipe_fill": 0.25,    # fracao minima da coluna preenchida p/ contar como cano
    "min_bird_area": 15,  # area minima (px) do blob do passaro
}


# ------------------------------------------------------------------ cor
def sample_hsv(img_bgr, x, y, r=3):
    """Mediana HSV de um quadradinho em volta do clique."""
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    patch = hsv[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1].reshape(-1, 3)
    return [int(v) for v in np.median(patch, axis=0)]


def color_mask(hsv, ref, cfg):
    """Mascara binaria dos pixels parecidos com a cor de referencia.
    Trata a 'volta' da matiz (vermelho fica em 0 e 180 no OpenCV)."""
    h, s, v = ref
    ht, st, vt = cfg["h_tol"], cfg["s_tol"], cfg["v_tol"]
    s_lo, s_hi = max(0, s - st), min(255, s + st)
    v_lo, v_hi = max(0, v - vt), min(255, v + vt)
    h_lo, h_hi = h - ht, h + ht
    ranges = []
    if h_lo < 0:
        ranges += [(0, h_hi), (180 + h_lo, 179)]
    elif h_hi > 179:
        ranges += [(h_lo, 179), (0, h_hi - 180)]
    else:
        ranges += [(h_lo, h_hi)]
    mask = None
    for lo, hi in ranges:
        m = cv2.inRange(hsv, (lo, s_lo, v_lo), (hi, s_hi, v_hi))
        mask = m if mask is None else cv2.bitwise_or(mask, m)
    return mask


# ------------------------------------------------------------------ deteccao
def find_bird(hsv, cfg):
    """Retorna (x, y, raio_horizontal, raio_vertical) do passaro ou None. Procura numa faixa vertical
    perto do x calibrado (o passaro nao anda na horizontal)."""
    W = hsv.shape[1]
    bx = cfg["bird_x"]
    half = max(20, int(W * 0.15))
    x0, x1 = max(0, bx - half), min(W, bx + half)
    mask = color_mask(hsv[:, x0:x1], cfg["bird_hsv"], cfg)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _, stats, cents = cv2.connectedComponentsWithStats(mask)
    if n <= 1:
        return None
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[i, cv2.CC_STAT_AREA] < cfg["min_bird_area"]:
        return None
    cx, cy = cents[i]
    rx = stats[i, cv2.CC_STAT_WIDTH] / 2
    ry = stats[i, cv2.CC_STAT_HEIGHT] / 2
    return float(cx) + x0, float(cy), rx, ry      # centro com casas decimais


def find_pipes(hsv, cfg):
    """Retorna lista de canos [(x_esq, x_dir, vao_topo, vao_base)] da
    esquerda pra direita."""
    W = hsv.shape[1]
    mask = color_mask(hsv, cfg["pipe_hsv"], cfg) > 0
    col_fill = mask.mean(axis=0)
    is_pipe = col_fill >= cfg["pipe_fill"]

    # agrupa colunas consecutivas em canos
    pipes, x = [], 0
    while x < W:
        if is_pipe[x]:
            start = x
            while x < W and is_pipe[x]:
                x += 1
            if x - start >= 4:  # ignora ruido fino
                pipes.append((start, x - 1))
        x += 1

    result = []
    for xl, xr in pipes:
        # perfil vertical do cano: linha tem cano se boa parte das colunas tem
        rows = mask[:, xl:xr + 1].mean(axis=1) > 0.5
        gap = largest_gap(rows)
        if gap:
            result.append((xl, xr, gap[0], gap[1]))
    return result


def largest_gap(rows):
    """Maior sequencia de linhas SEM cano que tenha cano acima e/ou abaixo."""
    H = len(rows)
    best, y = None, 0
    while y < H:
        if not rows[y]:
            start = y
            while y < H and not rows[y]:
                y += 1
            end = y - 1
            touches_top, touches_bot = start == 0, end == H - 1
            if not (touches_top and touches_bot):  # coluna vazia inteira nao e vao
                # vao "de verdade" (cano dos dois lados) tem prioridade
                score = (end - start) + (10000 if not touches_top and not touches_bot else 0)
                if best is None or score > best[2]:
                    best = (start, end, score)
        y += 1
    return (best[0], best[1]) if best else None


def next_pipe(pipes, bird):
    """Primeiro cano que o passaro ainda nao passou."""
    bx, r = bird[0], bird[2]
    for p in pipes:
        if p[1] > bx - r:
            return p
    return None


# ------------------------------------------------------------------ controle
class Controller:
    """Decide quando pular.

    Modo 1 (inicio, enquanto ainda nao mediu a fisica): pula quando a posicao
    prevista do passaro passa de uma linha-alvo no vao do proximo cano.

    Modo 2 (planejador, assim que a fisica foi medida): a cada quadro simula
    o futuro (~1 s) com a fisica do jogo e pergunta: "se eu NAO pular agora,
    ainda existe alguma sequencia de pulos que passa pelos proximos canos?"
    Se existe, nao pula; se nao existe, pula. Isso faz ele, por exemplo, ja
    se posicionar no fundo de um vao quando o proximo vao e bem mais baixo.

    Tudo e medido sozinho durante o jogo: gravidade, atraso do clique, forca
    do pulo, velocidade maxima de queda, velocidade e largura dos canos."""

    def __init__(self, cfg, screen_h, screen_w=None):
        self.cfg = cfg
        self.screen_h, self.screen_w = screen_h, screen_w or 10 ** 6
        self.g_fixed = cfg.get("gravity")
        self.g_fallback = 3.0 * screen_h      # chute inicial tipico
        self.g_samples, self.lat_samples = [], []
        self.term_samples, self.jump_samples = [], []
        self.v_fall_max, self.vbuf = 0.0, []
        self.dives, self.in_dive = 0, False
        self.speed_samples, self.width_samples = [], []
        self.gap_centers, self.gap_heights = [], []
        self.latency = cfg["latency"]
        self.hist = []                        # [(t, y)]
        self.last_flap = -1e9
        self.flap_probe = None                # t do pulo aguardando medir atraso
        self.jump_window = None               # (t_fim, menor_v) medindo forca do pulo
        self.track = None                     # (t, x) de um cano p/ medir velocidade
        self.dt = 1 / 30
        self.rise_samples = []
        self.cur_flap_pred, self.cur_min = None, None
        self.last_target = None
        self.mode = "regra"

    # ---------------- parametros medidos
    @staticmethod
    def _med(xs, n=3):
        return float(np.median(xs)) if len(xs) >= n else None

    @property
    def g(self):
        if self.g_fixed:
            return self.g_fixed
        return self._med(self.g_samples, 5) or self.g_fallback

    @property
    def rise(self):
        return self._med(self.rise_samples)

    @property
    def vjump(self):
        return self._med(self.jump_samples)

    @property
    def vmax(self):
        # so limita a queda se a velocidade terminal foi confirmada
        term = self._med(self.term_samples, 1)
        return term if term else float("inf")

    @property
    def speed(self):
        return self._med(self.speed_samples, 5)

    @property
    def pipe_w(self):
        return self._med(self.width_samples)

    # ---------------- modo regra (fallback)
    def _base_target(self, gap, r):
        gt, gb = gap
        lo, hi = gt + r, gb - r
        if self.rise and hi > lo:
            tgt = (lo + hi) / 2 + self.rise / 2
        else:
            tgt = gb - (gb - gt) * self.cfg["aim"]
        return min(tgt, hi - 2), lo, hi

    def target_for(self, gap, r, gap2=None):
        if gap is None:
            # sem cano na tela e sem saber a queda maxima: deixa cair ate perto
            # do fundo (1-2 vezes) pra medir a velocidade terminal
            if not self.term_samples and self.dives < 3:
                return self.screen_h * 0.9, None
            mid = np.median(self.gap_centers) if self.gap_centers else self.screen_h * 0.5
            return float(mid) + (self.rise or 0) / 2, None
        tgt, lo, hi = self._base_target(gap, r)
        if gap2 is not None:
            want = self._base_target(gap2, r)[0]
            top_ok, bot_ok = lo + (self.rise or 0) + 2, hi - 2
            if top_ok <= bot_ok:
                tgt = min(max(want, top_ok), bot_ok)
        return tgt, hi

    def reset(self):
        self.hist = []
        self.flap_probe = None
        self.jump_window = None
        self.cur_flap_pred, self.cur_min = None, None

    # ---------------- entrada principal
    def update(self, t, bird, pipes):
        """bird = (x, y, rx, ry); pipes = [(x_esq, x_dir, vao_topo, vao_base)].
        Retorna True se deve pular agora."""
        # o passaro nao anda na horizontal: suaviza x e tamanho com a mediana
        self.box_hist = (getattr(self, "box_hist", []) + [(bird[0], bird[2], bird[3])])[-25:]
        bx, rx, ry = (float(v) for v in np.median(self.box_hist, axis=0))
        rx = max(rx, float(bird[2]))
        y = bird[1]
        bird = (bx, y, rx, ry)
        self._learn_pipes(t, pipes)
        nxt = next_pipe(pipes, bird)
        gap = gap2 = None
        if nxt:
            gap = (nxt[2], nxt[3])
            i = pipes.index(nxt)
            if i + 1 < len(pipes):
                gap2 = (pipes[i + 1][2], pipes[i + 1][3])
        target, _ = self.target_for(gap, ry, gap2)
        self.last_target = target

        if self.cur_min is not None:
            self.cur_min = min(self.cur_min, y)
        if y > 0.88 * self.screen_h and not self.in_dive:
            self.in_dive, self.dives = True, self.dives + 1
        elif y < 0.6 * self.screen_h:
            self.in_dive = False
        h = self.hist
        h.append((t, y))
        if len(h) > 6:
            h.pop(0)
        if len(h) >= 2:
            self.dt = 0.8 * self.dt + 0.2 * max(1e-3, h[-1][0] - h[-2][0])
        self._learn()
        if len(h) < 2:
            return False

        (t1, y1), (t2, y2) = h[-2], h[-1]
        g = self.g
        d = max(1e-3, t2 - t1)
        v = (y2 - y1) / d + 0.5 * g * d       # velocidade no instante atual
        L = self.latency + 0.5 * self.dt
        pred = y + v * L + 0.5 * g * L * L

        ready = t - self.last_flap > max(self.cfg["cooldown"], self.latency) + 0.25 * self.dt
        if not ready:
            return False

        if self.vjump and self.speed and self.pipe_w:
            self.mode = "planejador"
            # o planejador simula em passos discretos: usa a velocidade media
            # do ultimo intervalo (proximo passo = v + g*dt)
            vfit = self._fit_velocity()
            self._extra = 0
            ok_wait, ok_flap = self._plan(y, vfit, bx, rx, ry, pipes)
            if ok_wait and ok_flap:
                # os dois sao seguros: prefere o que continua seguro com folga
                # maior; se empatar, a regra decide (mantem o passaro centralizado)
                flap = pred > target
                for extra in self.cfg.get("tiebreak", (4, 2)):
                    self._extra = extra
                    w2, f2 = self._plan(y, vfit, bx, rx, ry, pipes)
                    if w2 != f2:
                        flap = f2
                        break
                    if w2 and f2:
                        break
                self._extra = 0
            elif ok_wait or ok_flap:          # so um e seguro: obrigatorio
                flap = ok_flap
            else:                             # sem saida: tenta a regra
                flap = pred > target
        else:
            self.mode = "regra"
            flap = pred > target

        if flap:
            self._register_flap(t, v, pred, y)
        return flap

    def _fit_velocity(self):
        """Velocidade media do ultimo intervalo, ajustando uma parabola (com a
        gravidade medida) aos ultimos quadros depois do ultimo pulo. Bem menos
        sensivel ao ruido de 1 px da deteccao do que a diferenca simples."""
        g = self.g
        eff = self.last_flap + self.latency + 0.5 * self.dt   # pulo ja fez efeito
        pts = [(t, y) for t, y in self.hist if t > eff]
        if len(pts) < 3:
            (t1, y1), (t2, y2) = self.hist[-2:]
            return (y2 - y1) / max(1e-3, t2 - t1)
        ts = np.array([p[0] for p in pts]) - pts[-1][0]
        ys = np.array([p[1] for p in pts]) - 0.5 * g * ts ** 2
        v_end = np.polyfit(ts, ys, 1)[0]                # velocidade no ultimo quadro
        v_end = min(v_end, self.vmax)
        return v_end - 0.5 * g * self.dt                 # media do ultimo intervalo

    def _register_flap(self, t, v, pred, y):
        self.last_flap = t
        if self.jump_window is not None and self.jump_window[1] < 0:
            # pulo seguido de outro: guarda a medida do anterior antes de reiniciar
            self.jump_samples = (self.jump_samples + [self.jump_window[1]])[-15:]
        self.jump_window = (t + self.latency + 0.25, 0.0)
        if v > 0:
            if self.flap_probe is None:       # nao sobrescreve medicao em andamento
                self.flap_probe = t
            if self.cur_flap_pred is not None and self.cur_min is not None:
                rise = self.cur_flap_pred - self.cur_min
                if rise > 2:
                    self.rise_samples = (self.rise_samples + [rise])[-15:]
            self.cur_flap_pred, self.cur_min = pred, y
        else:
            self.cur_flap_pred, self.cur_min = None, None

    # ---------------- planejador
    def _plan(self, y, v, bx, rx, ry, pipes):
        """Retorna (seguro_esperar, seguro_pular). Robusto a erro de medicao:
        a acao so e segura se for segura com a gravidade um pouco menor E maior."""
        e = self.cfg.get("robust", 0.0)
        fs = (1 - e, 1 + e) if e else (1.0,)
        res = [self._plan_one(self.g * f, y, v, bx, rx, ry, pipes) for f in fs]
        return all(r[0] for r in res), all(r[1] for r in res)

    def _plan_one(self, g, y, v, bx, rx, ry, pipes):
        vj, vmax, spd, pw = self.vjump, self.vmax, self.speed, self.pipe_w
        W, Hs = self.screen_w, self.screen_h
        step = min(1 / 20, max(1 / 60, self.dt))
        cd = max(1, int(np.ceil((max(self.cfg["cooldown"], self.latency) + 0.25 * self.dt) / step)))
        # folgas: a cor do corpo nao inclui bico/asas, e a deteccao tem erro
        m = self.cfg["margin"] + getattr(self, "_extra", 0)
        rx = rx * self.cfg["x_scale"] + self.cfg["x_margin"]
        ry = ry + self.cfg["y_margin"]

        # canos com x corrigido quando cortados pela borda da tela
        obs = []
        for xl, xr, gt, gb in pipes:
            if xl <= 0:
                xl = xr - pw
            if xr >= W - 1:
                xr = xl + pw
            obs.append((xl, xr, gt + m, gb - m))

        def hit(yy, tt):
            if yy + ry > Hs or yy - ry < 0:
                return True
            shift = spd * tt
            # pixels xl..xr e gt..gb viram intervalos continuos [xl, xr+1)
            for xl, xr, gt, gb in obs:
                if bx + rx > xl - shift and bx - rx < xr + 1 - shift:
                    if yy - ry < gt or yy + ry > gb + 1:
                        return True
            return False

        def fall(vv):
            return min(vv + g * step, vmax)

        # avanca ate o momento em que um pulo decidido agora faria efeito
        L = self.latency
        tt, yy, vv = 0.0, y, v
        while tt + step <= L:
            vv = fall(vv); yy += vv * step; tt += step
        if L - tt > 1e-6:
            r = L - tt
            vv2 = min(vv + g * r, vmax); yy += vv2 * r; vv = vv2; tt = L

        # horizonte: ate passar TODOS os canos visiveis (decisoes de agora
        # afetam o cano seguinte tambem)
        far = max([o[1] for o in obs], default=bx)
        horizon = (far - (bx - rx)) / spd + 0.15
        horizon = min(self.cfg.get("max_horizon", 2.5), max(0.6, horizon))
        n_steps = int(horizon / step)

        memo = {}

        def safe(k, yy, vv, cool):
            if k >= n_steps:
                return True
            # floor (e nao int) para nao juntar velocidades +/- no mesmo grupo
            key = (k, math.floor(yy), math.floor(vv / 8), max(cool, 0))
            if key in memo:
                return memo[key]
            ok = False
            # tenta primeiro nao pular, depois pular
            v_n = fall(vv); y_n = yy + v_n * step
            if not hit(y_n, tt + (k + 1) * step) and safe(k + 1, y_n, v_n, cool - 1):
                ok = True
            elif cool <= 0:
                y_f = yy + vj * step
                if not hit(y_f, tt + (k + 1) * step) and safe(k + 1, y_f, vj, cd - 1):
                    ok = True
            memo[key] = ok
            return ok

        sys.setrecursionlimit(max(1000, n_steps * 4 + 100))
        v_n = fall(vv); y_n = yy + v_n * step
        y_f = yy + vj * step
        ok_wait = not hit(y_n, tt + step) and safe(1, y_n, v_n, 0)
        ok_flap = not hit(y_f, tt + step) and safe(1, y_f, vj, cd - 1)
        return ok_wait, ok_flap

    # ---------------- aprendizado
    def _learn_pipes(self, t, pipes):
        W = self.screen_w
        for xl, xr, gt, gb in pipes:
            if xl > 0 and xr < W - 1:
                self.width_samples = (self.width_samples + [xr - xl])[-30:]
            if gt > 0 and gb < self.screen_h - 1:
                self.gap_centers = (self.gap_centers + [(gt + gb) / 2])[-200:]
                self.gap_heights = (self.gap_heights + [gb - gt])[-200:]
        # velocidade: acompanha a borda esquerda do primeiro cano nao cortado
        cand = [p[0] for p in pipes if p[0] > 0]
        if cand:
            x = cand[0]
            if self.track is not None:
                t0, x0 = self.track
                dx, dtt = x0 - x, t - t0
                if dtt > 0 and 0 < dx < 0.25 * min(W, 4000):
                    self.speed_samples = (self.speed_samples + [dx / dtt])[-30:]
            self.track = (t, x)
        else:
            self.track = None

    def _learn(self):
        h = self.hist
        if len(h) < 3:
            return
        (t0, y0), (t1, y1), (t2, y2) = h[-3:]
        if t2 - t0 <= 0:
            return
        v01 = (y1 - y0) / max(1e-3, t1 - t0)
        v12 = (y2 - y1) / max(1e-3, t2 - t1)

        # forca do pulo: velocidade mais negativa logo apos o pulo
        if self.jump_window is not None:
            t_end, vmin = self.jump_window
            vmin = min(vmin, v12)
            if t2 > t_end:
                if vmin < 0:
                    self.jump_samples = (self.jump_samples + [vmin])[-15:]
                self.jump_window = None
            else:
                self.jump_window = (t_end, vmin)

        # atraso: primeiro intervalo em que o passaro passa a subir apos o pulo
        if self.flap_probe is not None:
            elapsed = t2 - self.flap_probe
            if v12 < 0 <= v01 or (v12 < 0 and v01 < 0 and elapsed < 0.05):
                lat = (t1 + t2) / 2 - self.flap_probe - 0.5 * self.dt
                self.lat_samples = (self.lat_samples + [min(0.3, max(0.0, lat))])[-15:]
                self.latency = float(np.median(self.lat_samples))
                self.flap_probe = None
            elif elapsed > 0.4:
                self.flap_probe = None

        # gravidade: parabola ajustada a >= 5 quadros de queda livre (robusto a
        # ruido de 1 px); velocidade maxima de queda: velocidade que para de subir
        eff = self.last_flap + self.latency + 2 * self.dt
        free = [(t, y) for t, y in h if t > eff]
        if len(free) >= 5:
            ts = np.array([p[0] for p in free]); ts -= ts[-1]
            ys = np.array([p[1] for p in free])
            c2, c1, _ = np.polyfit(ts, ys, 2)
            a, vend = 2 * c2, c1
            if vend > 0:
                self.v_fall_max = max(self.v_fall_max, vend)
            if 0.2 * self.g_fallback < a < 10 * self.g_fallback:
                if not (self.term_samples and vend > 0.9 * self.vmax):
                    self.g_samples = (self.g_samples + [a])[-40:]
            elif abs(a) < 0.15 * self.g and vend > 0:
                # parou de acelerar caindo: velocidade terminal
                self.term_samples = (self.term_samples + [vend])[-20:]


# ------------------------------------------------------------------ autodeteccao
def auto_detect(roi):
    """Tenta achar sozinho a cor dos canos e do passaro.
    Canos  = estruturas verticais altas, de uma cor so, com um vao no meio.
    Passaro = mancha colorida compacta, fora dos canos, na metade esquerda.
    Retorna dict com pipe_hsv, bird_hsv, bird_x (ou None no que nao achar)."""
    H, W = roi.shape[:2]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    hch, sch, vch = hsv[:, :, 0].astype(int), hsv[:, :, 1], hsv[:, :, 2]
    colorful = (sch > 60) & (vch > 50)
    out = {"pipe_hsv": None, "bird_hsv": None, "bird_x": None}

    # --- canos: testa faixas de matiz e fica com a que mais parece cano
    best = None
    for hc in range(0, 180, 4):
        dh = np.abs(hch - hc)
        dh = np.minimum(dh, 180 - dh)
        mask = colorful & (dh <= 8)
        fill = mask.mean(axis=0)
        cols = fill >= 0.25
        if cols.mean() > 0.6 or not cols.any():      # cor do fundo, ou nada
            continue
        score, x = 0, 0
        while x < W:
            if cols[x]:
                s = x
                while x < W and cols[x]:
                    x += 1
                width = x - s
                if 0.03 * W <= width <= 0.3 * W:
                    rows = mask[:, s:x].mean(axis=1) > 0.5
                    gap = largest_gap(rows)
                    if gap and 0.1 * H < gap[1] - gap[0] < 0.7 * H:
                        score += width * (2 if gap[0] > 0 and gap[1] < H - 1 else 1)
            x += 1
        if score and (best is None or score > best[0]):
            best = (score, hc, mask)
    pipe_cols = np.zeros(W, bool)
    if best:
        _, hc, mask = best
        out["pipe_hsv"] = [int(v) for v in np.median(hsv[mask], axis=0)]
        pipe_cols = mask.mean(axis=0) >= 0.15

    # --- passaro: maior mancha compacta colorida fora dos canos
    cand = colorful.copy()
    cand[:, pipe_cols] = False
    cand[:, int(W * 0.6):] = False                     # passaro fica a esquerda
    if out["pipe_hsv"]:
        dh = np.abs(hch - out["pipe_hsv"][0])
        cand &= np.minimum(dh, 180 - dh) > 12
    # tira a cor de fundo dominante (ceu colorido, cenario)
    if cand.any():
        hist = np.bincount(hch[colorful].ravel() // 6, minlength=31)
        bg = int(np.argmax(hist)) * 6 + 3
        if hist.max() > 0.3 * colorful.sum():
            dh = np.abs(hch - bg)
            near = colorful & (np.minimum(dh, 180 - dh) <= 10)
            bg_v = np.median(vch[near]) if near.any() else 0
            bg_s = np.median(sch[near]) if near.any() else 0
            like_bg = (np.minimum(dh, 180 - dh) <= 10) & \
                      (np.abs(vch.astype(int) - bg_v) < 50) & (np.abs(sch.astype(int) - bg_s) < 60)
            cand &= ~like_bg
    n, lab, stats, cents = cv2.connectedComponentsWithStats(cand.astype(np.uint8))
    area_min, area_max = 0.0004 * H * W, 0.03 * H * W
    best_b = None
    for i in range(1, n):
        _, _, w, h, a = stats[i]
        if not (area_min <= a <= area_max):
            continue
        if not (0.4 <= w / max(h, 1) <= 2.5) or a < 0.35 * w * h:
            continue
        if best_b is None or a > best_b[1]:
            best_b = (i, a)
    if best_b:
        i = best_b[0]
        px = hsv[lab == i]
        mode = int(np.argmax(np.bincount(px[:, 0] // 4, minlength=46))) * 4 + 2
        dh = np.abs(px[:, 0].astype(int) - mode)
        main = px[np.minimum(dh, 180 - dh) <= 8]
        out["bird_hsv"] = [int(v) for v in np.median(main if len(main) else px, axis=0)]
        out["bird_x"] = int(cents[i][0])
    return out


# ------------------------------------------------------------------ calibracao
def grab_screen():
    import mss
    with mss.mss() as sct:
        mon = sct.monitors[1]
        return mon, np.array(sct.grab(mon))[:, :, :3].copy()


def fit(img, max_w, max_h):
    s = min(1.0, max_w / img.shape[1], max_h / img.shape[0])
    return cv2.resize(img, None, fx=s, fy=s), s


def manual_pick(roi):
    """Fallback: usuario clica no passaro e no cano."""
    clicks = []
    def on_click(ev, cx, cy, *_):
        if ev == cv2.EVENT_LBUTTONDOWN:
            clicks.append((cx, cy))
    view, rs = fit(roi, 900, 800)
    win = "Clique: 1) no corpo do passaro  2) num cano  (ESC cancela)"
    cv2.namedWindow(win)
    cv2.setMouseCallback(win, on_click)
    while len(clicks) < 2:
        disp = view.copy()
        for c in clicks:
            cv2.circle(disp, c, 5, (0, 0, 255), 2)
        cv2.imshow(win, disp)
        if cv2.waitKey(20) == 27:
            cv2.destroyAllWindows()
            return None
        if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:   # fechou no X
            cv2.destroyAllWindows()
            return None
    cv2.destroyAllWindows()
    (bx, by), (px, py) = [(int(cx / rs), int(cy / rs)) for cx, cy in clicks]
    return {"bird_x": bx, "bird_hsv": sample_hsv(roi, bx, by),
            "pipe_hsv": sample_hsv(roi, px, py)}


def review(roi, cfg):
    """Mostra o que foi detectado. Retorna a tecla escolhida."""
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    bird = find_bird(hsv, cfg) if cfg.get("bird_hsv") else None
    pipes = find_pipes(hsv, cfg) if cfg.get("pipe_hsv") else []
    dbg = draw_debug(roi, bird, pipes, None)
    view, _ = fit(dbg, 900, 760)
    bar = np.zeros((70, view.shape[1], 3), np.uint8)
    ok = bird is not None and len(pipes) > 0
    msg = (f"passaro: {'OK' if bird else 'NAO ACHOU'}   canos: {len(pipes)}")
    cv2.putText(bar, msg, (8, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (0, 255, 0) if ok else (0, 0, 255), 2)
    cv2.putText(bar, "ENTER=aceitar  M=marcar com mouse  R=recapturar  ESC=sair",
                (8, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
    win = "Conferencia da calibracao"
    cv2.imshow(win, np.vstack([view, bar]))
    while True:
        k = cv2.waitKey(50) & 0xFF
        if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:   # fechou no X
            cv2.destroyAllWindows()
            return "quit"
        if k in (13, 10):
            r = "accept" if ok else "manual"
        elif k in (ord("m"), ord("M")):
            r = "manual"
        elif k in (ord("r"), ord("R")):
            r = "retry"
        elif k == 27:
            r = "quit"
        else:
            continue
        cv2.destroyAllWindows()
        return r


def calibrate(path):
    print("=" * 60)
    print(" CALIBRACAO")
    print("  1. Abra o jogo e deixe o passaro e pelo menos 1 cano na tela")
    print("     (pause o jogo se der).")
    print("  2. Com o jogo em foco, aperte F9 para capturar (ESC cancela).")
    print("=" * 60)
    old = {}
    if os.path.exists(path):
        with open(path) as f:
            old = json.load(f)

    region = None
    while True:
        wait_hotkey("f9", "[*] Esperando F9...")
        mon, full = grab_screen()

        if region is None:
            small, s = fit(full, 1400, 800)
            print("[1] Arraste um retangulo na area do jogo (do topo ate LOGO ACIMA do chao).")
            print("    ENTER/ESPACO confirma, C cancela.")
            x, y, w, h = cv2.selectROI("Selecione a area do jogo", small, showCrosshair=False)
            cv2.destroyAllWindows()
            if w == 0 or h == 0:
                sys.exit("Nenhuma area selecionada.")
            region = [int(v / s) for v in (x, y, w, h)]
        x, y, w, h = region
        roi = full[y:y + h, x:x + w].copy()

        print("[2] Detectando passaro e canos automaticamente...")
        found = auto_detect(roi)
        cfg = {**DEFAULTS, **{k: v for k, v in old.items() if k in DEFAULTS}}
        cfg.update(found)
        cfg["roi"] = {"left": mon["left"] + x, "top": mon["top"] + y, "width": w, "height": h}

        choice = review(roi, cfg)
        while choice == "manual":
            print("[3] Clique no CORPO do passaro e depois num CANO.")
            picked = manual_pick(roi)
            if picked is None:
                choice = "retry"
                break
            cfg.update(picked)
            choice = review(roi, cfg)
        if choice == "accept":
            break
        if choice == "quit":
            sys.exit("Cancelado.")
        print("[*] Ok, posicione o jogo e aperte F9 de novo (mesma area).")

    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"[ok] Calibracao salva em {path}")
    print(f"     passaro HSV={cfg['bird_hsv']}  cano HSV={cfg['pipe_hsv']}")
    return cfg


# ------------------------------------------------------------------ debug
def draw_debug(img, bird, pipes, target):
    out = img.copy()
    for xl, xr, gt, gb in pipes:
        cv2.rectangle(out, (xl, gt), (xr, gb), (255, 0, 255), 2)
    if bird:
        cv2.ellipse(out, (int(bird[0]), int(bird[1])), (int(bird[2]), int(bird[3])), 0, 0, 360,
                    (0, 0, 255), 2)
    if target is not None:
        cv2.line(out, (0, int(target)), (out.shape[1], int(target)), (0, 255, 255), 1)
    return out


# ------------------------------------------------------------------ loop
def check_config(cfg, path):
    """Para com uma mensagem clara se a calibracao estiver incompleta ou
    inconsistente (ex.: arquivo editado a mao)."""
    fix = f"\n    Refaca a calibracao: python flappy_bot.py --calibrate --config {path}"
    missing = [k for k in ("roi", "bird_x", "bird_hsv", "pipe_hsv") if cfg.get(k) is None]
    if missing:
        sys.exit(f"[!] Calibracao incompleta em '{path}': falta {', '.join(missing)}." + fix)
    roi = cfg["roi"]
    if not all(isinstance(roi.get(k), int) for k in ("left", "top", "width", "height")) \
            or roi["width"] <= 0 or roi["height"] <= 0:
        sys.exit(f"[!] 'roi' invalido em '{path}': {roi}" + fix)
    if not 0 <= cfg["bird_x"] < roi["width"]:
        sys.exit(f"[!] 'bird_x'={cfg['bird_x']} fica fora da area do jogo "
                 f"(largura {roi['width']})." + fix)
    for k in ("bird_hsv", "pipe_hsv"):
        if not (isinstance(cfg[k], list) and len(cfg[k]) == 3):
            sys.exit(f"[!] '{k}' invalido em '{path}': {cfg[k]}" + fix)


def run(path, action, debug):
    import mss
    import pyautogui
    from pynput import keyboard

    if not os.path.exists(path):
        print(f"[*] Nenhuma calibracao em '{path}'. Vamos calibrar agora.")
        cfg = {**DEFAULTS, **calibrate(path)}
    else:
        with open(path) as f:
            cfg = {**DEFAULTS, **json.load(f)}
        print(f"[*] Usando calibracao de '{path}' (para refazer: --calibrate)")
    check_config(cfg, path)

    pyautogui.PAUSE = 0          # sem atraso entre acoes
    pyautogui.FAILSAFE = True    # mouse no canto superior esquerdo = para tudo
    roi = cfg["roi"]
    click_pt = (roi["left"] + roi["width"] // 2, roi["top"] + roi["height"] // 2)

    state = {"on": False, "quit": False}
    def on_key(k):
        if k == keyboard.Key.f8:
            state["on"] = not state["on"]
            print("[bot]", "LIGADO" if state["on"] else "pausado")
        elif k == keyboard.Key.esc:
            state["quit"] = True
            return False
    keyboard.Listener(on_press=on_key).start()

    def flap():
        if action == "space":
            pyautogui.press("space")
        else:
            pyautogui.click(*click_pt)

    print("[bot] Pronto. Clique no jogo, comece a partida e aperte F8. ESC sai.")
    ctrl = Controller(cfg, roi["height"], roi["width"])
    fps_t, frames = time.time(), 0

    with mss.mss() as sct:
        while not state["quit"]:
            img = np.array(sct.grab(roi))[:, :, :3]
            now = time.time()
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            bird = find_bird(hsv, cfg)
            pipes = find_pipes(hsv, cfg)
            target = None

            if bird:
                if state["on"]:
                    if ctrl.update(now, bird, pipes):
                        flap()
                    target = ctrl.last_target
                else:
                    ctrl.reset()
            else:
                ctrl.reset()

            if debug:
                dbg = draw_debug(img, bird, pipes, target)
                cv2.putText(dbg, "ON" if state["on"] else "OFF", (5, 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                cv2.imshow("flappy_bot debug", dbg)
                cv2.waitKey(1)

            frames += 1
            if now - fps_t >= 5:
                print(f"[bot] {frames / (now - fps_t):.0f} fps | passaro={'sim' if bird else 'nao'}"
                      f" | canos={len(pipes)} | atraso={ctrl.latency * 1000:.0f}ms"
                      f" | gravidade={ctrl.g:.0f}px/s2 | modo={ctrl.mode}")
                fps_t, frames = now, 0

    cv2.destroyAllWindows()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Bot universal de Flappy Bird")
    ap.add_argument("--calibrate", action="store_true", help="calibra area e cores")
    ap.add_argument("--config", default="flappy_config.json")
    ap.add_argument("--action", choices=["click", "space"], default="click")
    ap.add_argument("--debug", action="store_true", help="janela de debug")
    a = ap.parse_args()
    check_deps()
    enable_dpi_awareness()
    if a.calibrate:
        calibrate(a.config)
        if input("Rodar o bot agora? [S/n] ").strip().lower() in ("", "s", "sim", "y"):
            run(a.config, a.action, a.debug)
    else:
        run(a.config, a.action, a.debug)

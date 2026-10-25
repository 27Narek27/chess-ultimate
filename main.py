"""
Chess Ultimate — шахматы на Pygame с ИИ (6 уровней) и режимом PvP.

Установка:  pip install pygame python-chess
Запуск:     python chess_ultimate.py

Управление: ЛКМ — ход, U — отмена хода, F — перевернуть доску, Esc — меню.
"""
from __future__ import annotations

import math
import random
import sys
import threading
import time

import chess
import chess.polyglot
import pygame

pygame.init()

# ──────────────────────────────────────────────────────────────────────────
#  Константы и оформление
# ──────────────────────────────────────────────────────────────────────────
W, H = 980, 760
SQ = 80
BOARD_PX = SQ * 8
BX, BY = 40, 60
PANEL_X = 710
TIME_CONTROL = 600  # секунд на партию каждому игроку
FLIP_SECONDS = 1.4  # длительность поворота доски в PvP

LIGHT = (234, 233, 210)
DARK = (75, 115, 153)
ACCENT = (86, 156, 214)
GREEN = (76, 175, 110)
RED = (224, 80, 80)
TEXT = (232, 234, 240)
MUTED = (140, 148, 163)
CARD = (34, 38, 48)
CARD_HI = (46, 52, 66)

screen = pygame.display.set_mode((W, H))
pygame.display.set_caption("Chess Ultimate")


def _font(names, size, bold=False):
    return pygame.font.SysFont(names, size, bold=bold)


F_TITLE = _font("segoeui,arial,helvetica", 48, True)
F_BIG = _font("segoeui,arial,helvetica", 28, True)
F_MID = _font("segoeui,arial,helvetica", 20, True)
F_SMALL = _font("segoeui,arial,helvetica", 15)
F_COORD = _font("segoeui,arial,helvetica", 13, True)
F_MONO = _font("consolas,couriernew,dejavusansmono,monospace", 17)

GLYPH_FONT_NAMES = [
    "segoeuisymbol", "dejavusans", "freesans", "notosanssymbols2",
    "arialunicodems", "applesymbols", "symbola",
]
GLYPHS = {
    chess.PAWN: "♟", chess.KNIGHT: "♞", chess.BISHOP: "♝",
    chess.ROOK: "♜", chess.QUEEN: "♛", chess.KING: "♚",
}
PIECES: dict = {}


def build_pieces():
    """Рендерит спрайты фигур один раз (сплошные символы + обводка + тень)."""
    path = None
    for name in GLYPH_FONT_NAMES:
        path = pygame.font.match_font(name)
        if path:
            break
    glyph_font = pygame.font.Font(path, 64) if path else None
    letter_font = _font("arial", 40, True)
    offs = [(-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, 1), (-1, 1), (1, -1)]
    for color in (chess.WHITE, chess.BLACK):
        fill = (252, 250, 242) if color else (28, 30, 36)
        edge = (30, 30, 36) if color else (205, 208, 215)
        for pt, ch in GLYPHS.items():
            surf = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
            if glyph_font:
                base = glyph_font.render(ch, True, fill)
                out = glyph_font.render(ch, True, edge)
                sh = glyph_font.render(ch, True, (0, 0, 0))
                sh.set_alpha(80)
                rect = base.get_rect(center=(SQ // 2, SQ // 2 + 2))
                surf.blit(sh, rect.move(3, 4))
                for dx, dy in offs:
                    surf.blit(out, rect.move(dx, dy))
                surf.blit(base, rect)
            else:  # запасной вариант: буквы
                pygame.draw.circle(surf, fill, (SQ // 2, SQ // 2), 30)
                pygame.draw.circle(surf, edge, (SQ // 2, SQ // 2), 30, 3)
                letter = chess.piece_symbol(pt).upper()
                t = letter_font.render(letter, True, edge)
                surf.blit(t, t.get_rect(center=(SQ // 2, SQ // 2)))
            PIECES[(color, pt)] = surf


build_pieces()


def make_background():
    bg = pygame.Surface((W, H))
    for y in range(H):
        k = y / H
        c = (int(30 - 14 * k), int(34 - 17 * k), int(44 - 22 * k))
        pygame.draw.line(bg, c, (0, y), (W, y))
    return bg


BG = make_background()


def make_tint(color):
    s = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
    s.fill(color)
    return s


T_LAST = make_tint((255, 213, 79, 95))
T_SEL = make_tint((60, 210, 140, 130))
T_CHECK = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
for _r in range(40, 0, -3):
    pygame.draw.circle(T_CHECK, (230, 40, 40, int(200 * (1 - _r / 40) + 30)),
                       (SQ // 2, SQ // 2), _r)
T_DOT = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
pygame.draw.circle(T_DOT, (20, 20, 20, 70), (SQ // 2, SQ // 2), 12)
T_RING = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
pygame.draw.circle(T_RING, (20, 20, 20, 70), (SQ // 2, SQ // 2), 38, 7)
SHADE = pygame.Surface((BOARD_PX, BOARD_PX), pygame.SRCALPHA)  # тень вращающейся доски
pygame.draw.rect(SHADE, (0, 0, 0, 95), SHADE.get_rect(), border_radius=6)


# ──────────────────────────────────────────────────────────────────────────
#  UI-помощники
# ──────────────────────────────────────────────────────────────────────────
def draw_text(surf, txt, font, color, pos, anchor="topleft"):
    img = font.render(txt, True, color)
    rect = img.get_rect()
    setattr(rect, anchor, pos)
    surf.blit(img, rect)
    return rect


def shadow(surf, rect, radius=14, off=8, alpha=90):
    s = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(s, (0, 0, 0, alpha), s.get_rect(), border_radius=radius)
    surf.blit(s, (rect.x + off // 2, rect.y + off))


def lighten(c, d=22):
    return tuple(min(255, v + d) for v in c)


class Button:
    def __init__(self, rect, text, color=ACCENT):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.color = color

    def draw(self, surf, mouse, font=F_MID, enabled=True):
        hover = enabled and self.rect.collidepoint(mouse)
        col = lighten(self.color) if hover else self.color
        if not enabled:
            col = (62, 66, 76)
        shadow(surf, self.rect, 10, 6, 80)
        pygame.draw.rect(surf, col, self.rect, border_radius=10)
        draw_text(surf, self.text, font, TEXT if enabled else MUTED,
                  self.rect.center, "center")

    def hit(self, pos):
        return self.rect.collidepoint(pos)


# ──────────────────────────────────────────────────────────────────────────
#  Оценочные таблицы (вид со стороны белых, верхняя строка = 8-я горизонталь)
# ──────────────────────────────────────────────────────────────────────────
def flat(rows):
    return [v for r in rows for v in r]


PST = {
    chess.PAWN: flat([
        [0, 0, 0, 0, 0, 0, 0, 0], [50, 50, 50, 50, 50, 50, 50, 50],
        [10, 10, 20, 30, 30, 20, 10, 10], [5, 5, 10, 25, 25, 10, 5, 5],
        [0, 0, 0, 20, 20, 0, 0, 0], [5, -5, -10, 0, 0, -10, -5, 5],
        [5, 10, 10, -20, -20, 10, 10, 5], [0, 0, 0, 0, 0, 0, 0, 0]]),
    chess.KNIGHT: flat([
        [-50, -40, -30, -30, -30, -30, -40, -50], [-40, -20, 0, 0, 0, 0, -20, -40],
        [-30, 0, 10, 15, 15, 10, 0, -30], [-30, 5, 15, 20, 20, 15, 5, -30],
        [-30, 0, 15, 20, 20, 15, 0, -30], [-30, 5, 10, 15, 15, 10, 5, -30],
        [-40, -20, 0, 5, 5, 0, -20, -40], [-50, -40, -30, -30, -30, -30, -40, -50]]),
    chess.BISHOP: flat([
        [-20, -10, -10, -10, -10, -10, -10, -20], [-10, 0, 0, 0, 0, 0, 0, -10],
        [-10, 0, 5, 10, 10, 5, 0, -10], [-10, 5, 5, 10, 10, 5, 5, -10],
        [-10, 0, 10, 10, 10, 10, 0, -10], [-10, 10, 10, 10, 10, 10, 10, -10],
        [-10, 5, 0, 0, 0, 0, 5, -10], [-20, -10, -10, -10, -10, -10, -10, -20]]),
    chess.ROOK: flat([
        [0, 0, 0, 0, 0, 0, 0, 0], [5, 10, 10, 10, 10, 10, 10, 5],
        [-5, 0, 0, 0, 0, 0, 0, -5], [-5, 0, 0, 0, 0, 0, 0, -5],
        [-5, 0, 0, 0, 0, 0, 0, -5], [-5, 0, 0, 0, 0, 0, 0, -5],
        [-5, 0, 0, 0, 0, 0, 0, -5], [0, 0, 0, 5, 5, 0, 0, 0]]),
    chess.QUEEN: flat([
        [-20, -10, -10, -5, -5, -10, -10, -20], [-10, 0, 0, 0, 0, 0, 0, -10],
        [-10, 0, 5, 5, 5, 5, 0, -10], [-5, 0, 5, 5, 5, 5, 0, -5],
        [0, 0, 5, 5, 5, 5, 0, -5], [-10, 5, 5, 5, 5, 5, 0, -10],
        [-10, 0, 5, 0, 0, 0, 0, -10], [-20, -10, -10, -5, -5, -10, -10, -20]]),
}
KING_MG = flat([
    [-30, -40, -40, -50, -50, -40, -40, -30], [-30, -40, -40, -50, -50, -40, -40, -30],
    [-30, -40, -40, -50, -50, -40, -40, -30], [-30, -40, -40, -50, -50, -40, -40, -30],
    [-20, -30, -30, -40, -40, -30, -30, -20], [-10, -20, -20, -20, -20, -20, -20, -10],
    [20, 20, 0, 0, 0, 0, 20, 20], [20, 30, 10, 0, 0, 10, 30, 20]])
KING_EG = flat([
    [-50, -40, -30, -20, -20, -30, -40, -50], [-30, -20, -10, 0, 0, -10, -20, -30],
    [-30, -10, 20, 30, 30, 20, -10, -30], [-30, -10, 30, 40, 40, 30, -10, -30],
    [-30, -10, 30, 40, 40, 30, -10, -30], [-30, -10, 20, 30, 30, 20, -10, -30],
    [-30, -30, 0, 0, 0, 0, -30, -30], [-50, -30, -30, -30, -30, -30, -30, -50]])

VAL = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330,
       chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}

BOOK = [
    "e2e4 e7e5 g1f3 b8c6 f1b5 a7a6 b5a4 g8f6 e1g1 f8e7",
    "e2e4 e7e5 g1f3 b8c6 f1c4 f8c5 c2c3 g8f6 d2d3 d7d6",
    "e2e4 c7c5 g1f3 d7d6 d2d4 c5d4 f3d4 g8f6 b1c3 a7a6",
    "e2e4 e7e6 d2d4 d7d5 b1c3 g8f6 c1g5 f8e7",
    "d2d4 d7d5 c2c4 e7e6 b1c3 g8f6 c1g5 f8e7 e2e3 e8g8",
    "d2d4 g8f6 c2c4 e7e6 b1c3 f8b4 e2e3 e8g8",
    "d2d4 g8f6 c2c4 g7g6 b1c3 f8g7 e2e4 d7d6",
    "c2c4 e7e5 b1c3 g8f6 g1f3 b8c6 g2g3 d7d5",
    "g1f3 d7d5 g2g3 g8f6 f1g2 e7e6 e1g1 f8e7",
]
BOOK = [line.split() for line in BOOK]

# ──────────────────────────────────────────────────────────────────────────
#  Уровни ИИ
# ──────────────────────────────────────────────────────────────────────────
LEVELS = [
    dict(name="Лёгкий", desc="Часто ошибается — для новичков",
         depth=1, time=1.0, noise=170, blunder=0.18, aggr=0, pos=0,
         book=False, color=(76, 175, 80)),
    dict(name="Нормальный", desc="Видит простые тактики на 2 хода",
         depth=2, time=2.0, noise=45, blunder=0.02, aggr=0, pos=0,
         book=False, color=(139, 195, 74)),
    dict(name="Сложный", desc="Считает на 4 хода, учитывает размены",
         depth=4, time=3.0, noise=0, blunder=0, aggr=0, pos=0,
         book=False, color=(255, 193, 7)),
    dict(name="Невозможный", desc="Глубокий перебор, до 6 сек на ход",
         depth=12, time=6.0, noise=0, blunder=0, aggr=0, pos=0,
         book=False, color=(244, 81, 30)),
    dict(name="Magnus Carlsen", desc="Позиционный стиль, дебютная книга, до 9 сек",
         depth=14, time=9.0, noise=0, blunder=0, aggr=0, pos=1,
         book=True, color=(126, 87, 194)),
    dict(name="Narek Hakobyan", desc="Агрессивный стиль, атака на короля, до 7 сек",
         depth=14, time=7.0, noise=0, blunder=0, aggr=1, pos=0,
         book=True, color=(216, 27, 96)),
]

MATE = 100000
INF = 10 ** 9


class Timeout(Exception):
    pass


# ──────────────────────────────────────────────────────────────────────────
#  Шахматный движок
# ──────────────────────────────────────────────────────────────────────────
class Engine:
    def __init__(self, level):
        self.cfg = level
        self.tt = {}
        self.killers = [[None, None] for _ in range(80)]
        self.history = {}
        self.nodes = 0
        self.deadline = 0.0
        self.best = None

    # ---- оценка (с точки зрения белых) ----
    def evaluate(self, b):
        pieces = b.piece_map()
        npm = 0
        pawns = {True: [], False: []}
        bishops = {True: 0, False: 0}
        for sq, p in pieces.items():
            if p.piece_type == chess.PAWN:
                pawns[p.color].append(sq)
            elif p.piece_type != chess.KING:
                npm += VAL[p.piece_type]
        endgame = npm <= 2600
        aggr, pos = self.cfg["aggr"], self.cfg["pos"]
        score = 0
        for sq, p in pieces.items():
            c, t = p.color, p.piece_type
            idx = sq ^ 56 if c else sq
            if t == chess.KING:
                v = (KING_EG if endgame else KING_MG)[idx]
            else:
                v = VAL[t] + PST[t][idx]
            if t == chess.BISHOP:
                bishops[c] += 1
            elif t == chess.PAWN:
                f, r = chess.square_file(sq), chess.square_rank(sq)
                passed = True
                for e in pawns[not c]:
                    if abs(chess.square_file(e) - f) <= 1 and (
                            chess.square_rank(e) > r if c else chess.square_rank(e) < r):
                        passed = False
                        break
                if passed:
                    rel = r if c else 7 - r
                    v += int(rel * rel * 2 * (1.6 if pos else 1))
            elif t == chess.ROOK and pos:
                f = chess.square_file(sq)
                own = any(chess.square_file(x) == f for x in pawns[c])
                opp = any(chess.square_file(x) == f for x in pawns[not c])
                v += 0 if own else (18 if not opp else 9)
            if aggr and t in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
                ek = b.king(not c)
                if ek is not None:
                    zone = chess.BB_KING_ATTACKS[ek] | chess.BB_SQUARES[ek]
                    v += bin(b.attacks_mask(sq) & zone).count("1") * 8 * aggr
            score += v if c else -v
        if bishops[True] >= 2:
            score += 30
        if bishops[False] >= 2:
            score -= 30
        score += 10 if b.turn else -10
        return score

    def eval_stm(self, b):
        s = self.evaluate(b)
        return s if b.turn else -s

    # ---- сортировка ходов ----
    def move_score(self, b, m, tt_move, ply):
        if m == tt_move:
            return 10 ** 6
        if b.is_capture(m):
            victim = b.piece_type_at(m.to_square) or chess.PAWN
            att = b.piece_type_at(m.from_square)
            return 10 ** 5 + 10 * VAL[victim] - VAL[att]
        if m.promotion:
            return 9 * 10 ** 4 + VAL[m.promotion]
        k = self.killers[ply]
        if m == k[0] or m == k[1]:
            return 8 * 10 ** 4
        return self.history.get((m.from_square, m.to_square), 0)

    def order(self, b, tt_move, ply):
        moves = list(b.legal_moves)
        moves.sort(key=lambda m: -self.move_score(b, m, tt_move, ply))
        return moves

    def check_time(self):
        self.nodes += 1
        if (self.nodes & 1023) == 0 and time.time() > self.deadline:
            raise Timeout

    # ---- поиск ----
    def quiesce(self, b, alpha, beta, ply, qd):
        self.check_time()
        stand = self.eval_stm(b)
        if stand >= beta:
            return stand
        alpha = max(alpha, stand)
        if qd >= 6 or ply >= 70:
            return alpha
        caps = list(b.generate_legal_captures())
        caps.sort(key=lambda m: -self.move_score(b, m, None, 0))
        for m in caps:
            b.push(m)
            s = -self.quiesce(b, -beta, -alpha, ply + 1, qd + 1)
            b.pop()
            if s >= beta:
                return s
            if s > alpha:
                alpha = s
        return alpha

    def negamax(self, b, depth, alpha, beta, ply):
        self.check_time()
        if b.is_insufficient_material() or b.halfmove_clock >= 100:
            return 0
        if ply > 0 and b.is_repetition(2):
            return 0
        in_check = b.is_check()
        if in_check:
            depth += 1
        if depth <= 0 or ply >= 70:
            return self.quiesce(b, alpha, beta, ply, 0)

        key = chess.polyglot.zobrist_hash(b)
        entry = self.tt.get(key)
        tt_move = None
        if entry:
            d, flag, val, tt_move = entry
            if d >= depth and ply > 0:
                if flag == 0:
                    return val
                if flag == 1 and val >= beta:
                    return val
                if flag == 2 and val <= alpha:
                    return val

        moves = self.order(b, tt_move, ply)
        if not moves:
            return -MATE + ply if in_check else 0

        best, best_move, orig_alpha = -INF, None, alpha
        for i, m in enumerate(moves):
            quiet = not b.is_capture(m) and not m.promotion
            b.push(m)
            if i >= 4 and depth >= 3 and quiet and not in_check:
                s = -self.negamax(b, depth - 2, -alpha - 1, -alpha, ply + 1)
                if s > alpha:
                    s = -self.negamax(b, depth - 1, -beta, -alpha, ply + 1)
            else:
                s = -self.negamax(b, depth - 1, -beta, -alpha, ply + 1)
            b.pop()
            if s > best:
                best, best_move = s, m
            if s > alpha:
                alpha = s
            if alpha >= beta:
                if quiet:
                    k = self.killers[ply]
                    if m != k[0]:
                        k[1], k[0] = k[0], m
                    hk = (m.from_square, m.to_square)
                    self.history[hk] = self.history.get(hk, 0) + depth * depth
                break

        if len(self.tt) > 400_000:
            self.tt.clear()
        flag = 2 if best <= orig_alpha else (1 if best >= beta else 0)
        self.tt[key] = (depth, flag, best, best_move)
        return best

    def root(self, b, depth):
        alpha, best = -INF, None
        for m in self.order(b, self.best, 0):
            b.push(m)
            s = -self.negamax(b, depth - 1, -INF, -alpha, 1)
            b.pop()
            if best is None or s > alpha:
                alpha, best = s, m
        return alpha, best

    # ---- выбор хода ----
    def book_move(self, b, hist):
        n = len(hist)
        cands = [ln[n] for ln in BOOK if len(ln) > n and ln[:n] == hist]
        random.shuffle(cands)
        for uci in cands:
            m = chess.Move.from_uci(uci)
            if m in b.legal_moves:
                return m
        return None

    def choose(self, b, hist):
        cfg = self.cfg
        legal = list(b.legal_moves)
        if len(legal) == 1:
            return legal[0]
        if cfg["book"] and len(hist) < 14:
            m = self.book_move(b, hist)
            if m:
                return m
        if cfg["blunder"] and random.random() < cfg["blunder"]:
            return random.choice(legal)

        b = b.copy()
        if cfg["noise"] > 0:  # слабые уровни: поиск с шумом оценки
            self.deadline = time.time() + 30
            scored = []
            for m in legal:
                b.push(m)
                s = -self.negamax(b, cfg["depth"] - 1, -INF, INF, 1)
                b.pop()
                scored.append((s + random.gauss(0, cfg["noise"]), m))
            return max(scored, key=lambda x: x[0])[1]

        self.deadline = time.time() + cfg["time"]
        best = None
        for d in range(1, cfg["depth"] + 1):
            try:
                score, move = self.root(b, d)
            except Timeout:
                break
            best = self.best = move
            if abs(score) > MATE - 100:
                break
        return best or legal[0]


class AIWorker(threading.Thread):
    """Считает ход в фоне, чтобы окно не зависало."""

    def __init__(self, board, level):
        super().__init__(daemon=True)
        self.board = board.copy()
        self.hist = [m.uci() for m in board.move_stack]
        self.level = level
        self.result = None
        self.done = False

    def run(self):
        try:
            self.result = Engine(self.level).choose(self.board, self.hist)
        except Exception:
            self.result = random.choice(list(self.board.legal_moves))
        self.done = True


# ──────────────────────────────────────────────────────────────────────────
#  Игра
# ──────────────────────────────────────────────────────────────────────────
RU_DRAW = {
    chess.Termination.STALEMATE: "Пат — ничья",
    chess.Termination.INSUFFICIENT_MATERIAL: "Ничья: недостаточно материала",
    chess.Termination.FIFTY_MOVES: "Ничья по правилу 50 ходов",
    chess.Termination.SEVENTYFIVE_MOVES: "Ничья по правилу 75 ходов",
    chess.Termination.THREEFOLD_REPETITION: "Ничья: троекратное повторение",
    chess.Termination.FIVEFOLD_REPETITION: "Ничья: пятикратное повторение",
}


def fmt_clock(t):
    t = max(0, int(t))
    return f"{t // 60:02d}:{t % 60:02d}"


class Game:
    def __init__(self, mode, level=None, human=chess.WHITE):
        self.board = chess.Board()
        self.mode, self.level, self.human = mode, level, human
        self.flipped = mode == "ai" and human == chess.BLACK
        self.flip_target = self.flipped
        self.flip_t = 1.0
        self.sel = None
        self.targets = []
        self.last = None
        self.clocks = {chess.WHITE: TIME_CONTROL, chess.BLACK: TIME_CONTROL}
        self.sans = []
        self.anim = None
        self.worker = None
        self.ai_start = 0.0
        self.promo = None
        self.over = None
        self.pending_flip = False
        self.flip_wait = 0.0
        self.buttons = {
            "undo": Button((722, 570, 112, 40), "↶ Отмена", (90, 100, 120)),
            "flip": Button((846, 570, 112, 40), "⇅ Поворот", (90, 100, 120)),
            "new": Button((722, 620, 112, 40), "Заново", GREEN),
            "menu": Button((846, 620, 112, 40), "Меню", (160, 80, 80)),
        }

    # ---- логика ----
    def human_turn(self):
        return self.mode == "pvp" or self.board.turn == self.human

    def side_name(self, color):
        if self.mode == "ai":
            return "Вы" if color == self.human else self.level["name"]
        return "Белые" if color == chess.WHITE else "Чёрные"

    def play(self, move):
        b = self.board
        piece = b.piece_at(move.from_square)
        self.sans.append(b.san(move))
        b.push(move)
        self.last = move
        self.sel, self.targets, self.promo = None, [], None
        self.anim = dict(piece=piece, a=move.from_square, b=move.to_square,
                         t0=time.time(), dur=0.22)
        o = b.outcome(claim_draw=True)
        if o:
            if o.winner is None:
                self.over = RU_DRAW.get(o.termination, "Ничья")
            else:
                self.over = "Мат! Победили " + ("белые" if o.winner else "чёрные")
        elif self.mode == "pvp":
            self.pending_flip = True  # доска повернётся после анимации хода
            self.flip_wait = 0.35

    def start_flip(self):
        if self.flip_t < 1:
            return
        self.flip_target = not self.flipped
        self.flip_t = 0.0

    def undo(self):
        if (self.worker or self.anim or self.flip_t < 1 or self.pending_flip
                or not self.board.move_stack):
            return
        self.over = None
        if self.mode == "ai":
            while self.board.move_stack:
                self.board.pop()
                self.sans.pop()
                if self.board.turn == self.human:
                    break
        else:
            self.board.pop()
            self.sans.pop()
            self.start_flip()
        self.last = self.board.move_stack[-1] if self.board.move_stack else None
        self.sel, self.targets, self.promo = None, [], None

    def square_at(self, pos):
        x, y = pos[0] - BX, pos[1] - BY
        if not (0 <= x < BOARD_PX and 0 <= y < BOARD_PX):
            return None
        col, row = x // SQ, y // SQ
        if self.flipped:
            col, row = 7 - col, 7 - row
        return chess.square(col, 7 - row)

    def click(self, pos):
        for name, btn in self.buttons.items():
            if btn.hit(pos):
                if name == "undo":
                    self.undo()
                elif name == "flip":
                    self.start_flip()
                else:
                    return name
                return None
        if self.over or self.anim or self.flip_t < 1 or not self.human_turn():
            return None

        if self.promo:
            fr, to = self.promo
            x0, y0 = BX + (BOARD_PX - 4 * SQ) // 2, BY + (BOARD_PX - SQ) // 2
            for i, pt in enumerate((chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT)):
                if pygame.Rect(x0 + i * SQ, y0, SQ, SQ).collidepoint(pos):
                    self.play(chess.Move(fr, to, promotion=pt))
                    return None
            self.promo, self.sel, self.targets = None, None, []
            return None

        sq = self.square_at(pos)
        if sq is None:
            return None
        b = self.board
        if self.sel is not None and sq in self.targets:
            pc = b.piece_at(self.sel)
            if pc.piece_type == chess.PAWN and chess.square_rank(sq) in (0, 7):
                self.promo = (self.sel, sq)
            else:
                self.play(chess.Move(self.sel, sq))
            return None
        p = b.piece_at(sq)
        if p and p.color == b.turn:
            self.sel = sq
            self.targets = [m.to_square for m in b.legal_moves if m.from_square == sq]
        else:
            self.sel, self.targets = None, []
        return None

    def update(self, dt):
        flipping = self.flip_t < 1
        if flipping:
            self.flip_t = min(1.0, self.flip_t + dt / FLIP_SECONDS)
            if self.flip_t >= 1.0:
                self.flipped = self.flip_target
        if self.anim and time.time() - self.anim["t0"] > self.anim["dur"]:
            self.anim = None
        if self.pending_flip and not self.anim and not flipping and not self.over:
            self.flip_wait -= dt
            if self.flip_wait <= 0:
                self.pending_flip = False
                self.start_flip()
                flipping = True
        if self.over:
            self.pending_flip = False
            return
        if not flipping and not self.pending_flip:
            self.clocks[self.board.turn] -= dt
            if self.clocks[self.board.turn] <= 0:
                loser = self.board.turn
                self.over = "Время вышло! Победили " + ("чёрные" if loser else "белые")
                return
        if (self.mode == "ai" and self.board.turn != self.human
                and not self.anim and not flipping):
            if self.worker is None:
                self.worker = AIWorker(self.board, self.level)
                self.ai_start = time.time()
                self.worker.start()
            elif self.worker.done and time.time() - self.ai_start > 0.6:
                move, self.worker = self.worker.result, None
                if move in self.board.legal_moves:
                    self.play(move)

    # ---- отрисовка ----
    def sq_xy(self, sq):
        f, r = chess.square_file(sq), chess.square_rank(sq)
        col = 7 - f if self.flipped else f
        row = r if self.flipped else 7 - r
        return col * SQ, row * SQ

    def draw_squares(self, surf, labels=True):
        b = self.board
        check_sq = b.king(b.turn) if b.is_check() else None
        for sq in chess.SQUARES:
            x, y = self.sq_xy(sq)
            f, r = chess.square_file(sq), chess.square_rank(sq)
            light = (f + r) % 2 == 1
            surf.fill(LIGHT if light else DARK, (x, y, SQ, SQ))
            if self.last and sq in (self.last.from_square, self.last.to_square):
                surf.blit(T_LAST, (x, y))
            if sq == self.sel:
                surf.blit(T_SEL, (x, y))
            if sq == check_sq:
                surf.blit(T_CHECK, (x, y))
            if not labels:
                continue
            lbl_col = DARK if light else LIGHT
            if x == 0:
                draw_text(surf, str(r + 1), F_COORD, lbl_col, (x + 4, y + 3))
            if y == SQ * 7:
                draw_text(surf, "abcdefgh"[f], F_COORD, lbl_col,
                          (x + SQ - 4, y + SQ - 3), "bottomright")

    def draw_board(self, surf):
        b = self.board
        anim = self.anim
        self.draw_squares(surf)
        for sq in self.targets:
            x, y = self.sq_xy(sq)
            cap = b.is_capture(chess.Move(self.sel, sq))
            surf.blit(T_RING if cap else T_DOT, (x, y))
        for sq, p in b.piece_map().items():
            if anim and sq == anim["b"]:
                continue
            surf.blit(PIECES[(p.color, p.piece_type)], self.sq_xy(sq))
        if anim:
            t = min(1.0, (time.time() - anim["t0"]) / anim["dur"])
            t = t * t * (3 - 2 * t)
            ax, ay = self.sq_xy(anim["a"])
            bx, by = self.sq_xy(anim["b"])
            piece = anim["piece"]
            surf.blit(PIECES[(piece.color, piece.piece_type)],
                      (ax + (bx - ax) * t, ay + (by - ay) * t))
        if self.promo:
            dim = pygame.Surface((BOARD_PX, BOARD_PX), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 150))
            surf.blit(dim, (0, 0))
            x0, y0 = (BOARD_PX - 4 * SQ) // 2, (BOARD_PX - SQ) // 2
            pygame.draw.rect(surf, (245, 245, 245),
                             (x0 - 10, y0 - 10, 4 * SQ + 20, SQ + 20), border_radius=16)
            for i, pt in enumerate((chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT)):
                pygame.draw.rect(surf, (200, 205, 215), (x0 + i * SQ + 4, y0 + 4, SQ - 8, SQ - 8),
                                 border_radius=10)
                surf.blit(PIECES[(b.turn, pt)], (x0 + i * SQ, y0))

    def draw_flipping(self, surf, center):
        """Плавное вращение доски на 180°: фигуры «парят» над доской и остаются прямыми."""
        t = self.flip_t
        e = t * t * t * (t * (6 * t - 15) + 10)  # smootherstep: мягкий старт и финиш
        theta = math.pi * e
        deg = math.degrees(theta)
        scale = 1 - 0.34 * abs(math.sin(2 * theta)) ** 1.5  # доска отдаляется на диагоналях
        lift = math.sin(theta)  # «подъём» над столом в середине поворота

        shade = pygame.transform.rotozoom(SHADE, deg, scale)
        surf.blit(shade, shade.get_rect(center=(center[0], center[1] + 10 + 26 * lift)))
        squares = pygame.Surface((BOARD_PX, BOARD_PX), pygame.SRCALPHA)
        self.draw_squares(squares, labels=False)
        img = pygame.transform.rotozoom(squares, deg, scale)
        surf.blit(img, img.get_rect(center=center))

        c, s = math.cos(theta), math.sin(theta)
        half = BOARD_PX / 2
        items = []
        for sq, p in self.board.piece_map().items():
            x, y = self.sq_xy(sq)
            dx, dy = x + SQ / 2 - half, y + SQ / 2 - half
            rx = (dx * c + dy * s) * scale
            ry = (-dx * s + dy * c) * scale - 14 * lift
            items.append((ry, rx, p))
        size = max(1, int(SQ * scale * (1 + 0.10 * lift)))
        for ry, rx, p in sorted(items, key=lambda it: it[0]):
            spr = pygame.transform.smoothscale(PIECES[(p.color, p.piece_type)], (size, size))
            surf.blit(spr, spr.get_rect(center=(center[0] + rx, center[1] + ry)))

    def draw_strip(self, surf, color, y):
        rect = pygame.Rect(BX, y, BOARD_PX, 40)
        active = self.board.turn == color and not self.over
        pygame.draw.rect(surf, CARD_HI if active else CARD, rect, border_radius=10)
        if active:
            pygame.draw.rect(surf, ACCENT, rect, 2, border_radius=10)
        dot = (245, 245, 240) if color else (20, 20, 24)
        pygame.draw.circle(surf, dot, (rect.x + 24, rect.centery), 11)
        pygame.draw.circle(surf, (120, 120, 130), (rect.x + 24, rect.centery), 11, 2)
        draw_text(surf, self.side_name(color), F_MID, TEXT, (rect.x + 46, rect.centery), "midleft")
        t = self.clocks[color]
        draw_text(surf, fmt_clock(t), F_BIG, RED if t < 20 else TEXT,
                  (rect.right - 16, rect.centery), "midright")

    def status_text(self):
        if self.over:
            return self.over, RED
        if self.worker:
            dots = "." * (int(time.time() * 2.5) % 4)
            return f"{self.level['name']} думает{dots}", (255, 190, 90)
        side = "белых" if self.board.turn else "чёрных"
        if self.board.is_check():
            return f"Шах! Ход {side}", RED
        return f"Ход {side}", TEXT

    def draw(self, surf, mouse):
        surf.blit(BG, (0, 0))
        board_rect = pygame.Rect(BX, BY, BOARD_PX, BOARD_PX)
        if self.flip_t >= 1:
            shadow(surf, board_rect.inflate(16, 16).move(-8, -8), 18, 10, 110)

        if self.flip_t < 1:
            self.draw_flipping(surf, board_rect.center)
        else:
            board_surf = pygame.Surface((BOARD_PX, BOARD_PX))
            self.draw_board(board_surf)
            surf.blit(board_surf, board_rect.topleft)

        shown = self.flip_target if self.flip_t >= 0.5 else self.flipped
        top = chess.WHITE if shown else chess.BLACK
        self.draw_strip(surf, top, 10)
        self.draw_strip(surf, not top, BY + BOARD_PX + 10)

        if self.over:
            msg = pygame.Surface((BOARD_PX, 120), pygame.SRCALPHA)
            pygame.draw.rect(msg, (10, 12, 18, 220), msg.get_rect(), border_radius=18)
            surf.blit(msg, (BX, BY + BOARD_PX // 2 - 60))
            draw_text(surf, self.over, F_BIG, TEXT,
                      (BX + BOARD_PX // 2, BY + BOARD_PX // 2 - 14), "center")
            draw_text(surf, "«Заново» — новая партия, «Меню» — выбор режима", F_SMALL, MUTED,
                      (BX + BOARD_PX // 2, BY + BOARD_PX // 2 + 24), "center")

        # правая панель
        panel = pygame.Rect(PANEL_X, 10, 260, 690 + 40)
        shadow(surf, panel, 16, 10, 90)
        pygame.draw.rect(surf, CARD, panel, border_radius=16)
        draw_text(surf, "Chess Ultimate", F_BIG, TEXT, (panel.centerx, 40), "center")
        subtitle = (f"Режим: ИИ — {self.level['name']}" if self.mode == "ai"
                    else "Режим: два игрока")
        draw_text(surf, subtitle, F_SMALL, MUTED, (panel.centerx, 70), "center")
        txt, col = self.status_text()
        pygame.draw.rect(surf, (24, 27, 35), (722, 95, 236, 44), border_radius=10)
        draw_text(surf, txt, F_MID, col, (840, 117), "center")

        draw_text(surf, "Ходы", F_SMALL, MUTED, (726, 155))
        rows = [self.sans[i:i + 2] for i in range(0, len(self.sans), 2)]
        start = max(0, len(rows) - 15)
        for n, pair in enumerate(rows[start:]):
            y = 180 + n * 25
            num = start + n + 1
            if n % 2 == 0:
                pygame.draw.rect(surf, (30, 34, 43), (722, y - 2, 236, 24), border_radius=6)
            draw_text(surf, f"{num:>2}.", F_MONO, MUTED, (728, y))
            draw_text(surf, pair[0], F_MONO, TEXT, (775, y))
            if len(pair) > 1:
                draw_text(surf, pair[1], F_MONO, TEXT, (860, y))

        busy = bool(self.worker) or bool(self.anim)
        for name, btn in self.buttons.items():
            btn.draw(surf, mouse, F_SMALL, enabled=not (name == "undo" and busy))

    def run(self):
        clock = pygame.time.Clock()
        last = time.time()
        while True:
            now = time.time()
            dt, last = min(now - last, 0.1), now
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    return "quit"
                if e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_ESCAPE:
                        return "menu"
                    if e.key == pygame.K_u:
                        self.undo()
                    if e.key == pygame.K_f:
                        self.start_flip()
                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    act = self.click(e.pos)
                    if act:
                        return act
            self.update(dt)
            self.draw(screen, pygame.mouse.get_pos())
            pygame.display.flip()
            clock.tick(60)


# ──────────────────────────────────────────────────────────────────────────
#  Меню
# ──────────────────────────────────────────────────────────────────────────
def select_mode():
    b1 = Button((250, 300, 480, 90), "Играть против ИИ", GREEN)
    b2 = Button((250, 420, 480, 90), "Два игрока (PvP)", ACCENT)
    clock = pygame.time.Clock()
    while True:
        mouse = pygame.mouse.get_pos()
        screen.blit(BG, (0, 0))
        draw_text(screen, "CHESS ULTIMATE", F_TITLE, TEXT, (W // 2, 150), "center")
        draw_text(screen, "Шахматы с анимацией и шестью уровнями ИИ", F_MID, MUTED,
                  (W // 2, 205), "center")
        b1.draw(screen, mouse, F_BIG)
        b2.draw(screen, mouse, F_BIG)
        pygame.display.flip()
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return None
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                if b1.hit(e.pos):
                    return "ai"
                if b2.hit(e.pos):
                    return "pvp"
        clock.tick(60)


def select_level():
    cards = []
    for i, lv in enumerate(LEVELS):
        x = 60 + (i % 2) * 440
        y = 150 + (i // 2) * 112
        cards.append(pygame.Rect(x, y, 420, 96))
    toggle = Button((60, 500, 420, 56), "", (90, 100, 120))
    back = Button((500, 500, 420, 56), "← Назад", (160, 80, 80))
    human = chess.WHITE
    clock = pygame.time.Clock()
    while True:
        mouse = pygame.mouse.get_pos()
        screen.blit(BG, (0, 0))
        draw_text(screen, "Выберите соперника", F_TITLE, TEXT, (W // 2, 80), "center")
        for i, (lv, rect) in enumerate(zip(LEVELS, cards)):
            hover = rect.collidepoint(mouse)
            shadow(screen, rect, 14, 8, 90)
            pygame.draw.rect(screen, CARD_HI if hover else CARD, rect, border_radius=14)
            pygame.draw.rect(screen, lv["color"], (rect.x, rect.y, 8, rect.h),
                             border_top_left_radius=14, border_bottom_left_radius=14)
            draw_text(screen, lv["name"], F_BIG, TEXT, (rect.x + 28, rect.y + 14))
            draw_text(screen, lv["desc"], F_SMALL, MUTED, (rect.x + 28, rect.y + 52))
            for k in range(6):
                c = lv["color"] if k <= i else (60, 65, 78)
                pygame.draw.circle(screen, c, (rect.x + 30 + k * 18, rect.bottom - 16), 5)
        toggle.text = "Вы играете: " + ("белыми ♔" if human else "чёрными ♚")
        toggle.draw(screen, mouse, F_MID)
        back.draw(screen, mouse, F_MID)
        pygame.display.flip()
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return "quit"
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                return None
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                if back.hit(e.pos):
                    return None
                if toggle.hit(e.pos):
                    human = not human
                for lv, rect in zip(LEVELS, cards):
                    if rect.collidepoint(e.pos):
                        return lv, human
        clock.tick(60)


def main():
    while True:
        mode = select_mode()
        if mode is None:
            break
        level, human = None, chess.WHITE
        if mode == "ai":
            res = select_level()
            if res == "quit":
                break
            if res is None:
                continue
            level, human = res
        action = "new"
        while action == "new":
            action = Game(mode, level, human).run()
        if action == "quit":
            break
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
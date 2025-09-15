#!/usr/bin/env python3
from __future__ import annotations
"""
RLCE (Route-Lock Cellular Enforcement) Demo — Charlotte LRV v0.6 (ESC double-press + debounce)

Fixes:
- Prevents the “opens then instantly closes” after exiting with ESC by:
  * Debouncing ESC for the first 500 ms after startup
  * Requiring a **double-press** of ESC within 800 ms to exit
- You can still close with the window [X] normally.

If anything fails, errors go to rlce_debug.log.
"""
import os, time, math, random, traceback
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Set
import pygame

# ——— Safety for systems without audio, and hide support prompt ———
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

LOGFILE = "rlce_debug.log"

def log(msg: str):
    try:
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass

# ---------------------------- Config ---------------------------------
W, H = 1200, 800
FPS = 60
ROUTE_COLOR = (20, 140, 200)
SEG_COLOR = (140, 180, 220)
CUR_SEG_COLOR = (255, 200, 40)
TRAIN_COLOR = (200, 200, 240)
TEXT_COLOR = (235, 235, 235)
PANEL_BG = (22, 24, 32)
BG = (18, 20, 26)

TOWER_COLORS = {
    "clean": (90, 200, 90),
    "rogue": (230, 80, 80),
    "serving": (80, 180, 255),
}

random.seed(42)

# ---------------------------- Geometry utils --------------------------
def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def dist(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])

def project_point_to_segment(p, a, b):
    ax, ay = a; bx, by = b; px, py = p
    abx, aby = bx-ax, by-ay
    ab2 = abx*abx + aby*aby
    if ab2 == 0:
        return a, 0.0, dist(p, a)
    apx, apy = px-ax, py-ay
    t = (apx*abx + apy*aby) / ab2
    t = clamp(t, 0.0, 1.0)
    q = (ax + abx*t, ay + aby*t)
    return q, t, dist(p, q)

# ---------------------------- Domain types ----------------------------
PLMNS = ["310260", "311480", "310410"]  # demo operators
ALLOWED_ARFCN = {"LTE": {66486, 66490, 66500, 5140, 1302}, "NR": {523800, 627936}}

@dataclass
class CellTower:
    id: int
    x: float
    y: float
    plmn: str
    tech: str  # "LTE" or "NR"
    arfcn: int
    tac: int
    pci: int
    rogue: bool = False
    def pos(self):
        return (self.x, self.y)

@dataclass
class Segment:
    idx: int
    a: Tuple[float, float]
    b: Tuple[float, float]
    cal: Set[int] = field(default_factory=set)
    def mid(self):
        return ((self.a[0]+self.b[0])/2, (self.a[1]+self.b[1])/2)

@dataclass
class Route:
    points: List[Tuple[float, float]]
    segments: List[Segment]
    operator_plmn: str = "310260"
    @classmethod
    def from_polyline(cls, pts):
        segs = [Segment(i, pts[i], pts[i+1]) for i in range(len(pts)-1)]
        return cls(points=pts, segments=segs)

@dataclass
class Train:
    x: float; y: float
    speed: float = 120.0       # px/s manual
    auto_speed: float = 140.0  # px/s along route
    w: int = 36; h: int = 14
    route_t: float = 0.0       # param along route [0..len(segments))
    auto: bool = False
    def pos(self): return (self.x, self.y)

# ---------------------------- RLCE Engine -----------------------------
class RLCE:
    def __init__(self, route: Route, towers: List[CellTower]):
        self.route = route
        self.towers = towers
        self.grace = 1
        self.hysteresis = 40.0
        self.poll_ms = 250
        self.last_seg_idx: Optional[int] = None
        self.last_serving: Optional[CellTower] = None
        self.last_poll_time = 0.0
        self.log: List[str] = []

    def rebuild_cal(self, radius_px: float = 220.0):
        for seg in self.route.segments:
            seg.cal.clear()
            mid = seg.mid()
            for tw in self.towers:
                if dist(mid, tw.pos()) <= radius_px and not tw.rogue:
                    seg.cal.add(tw.id)

    def locate_segment(self, p):
        dists = []
        for seg in self.route.segments:
            _, _, dpx = project_point_to_segment(p, seg.a, seg.b)
            dists.append((dpx, seg.idx))
        dists.sort()
        nearest_idx = dists[0][1]
        if self.last_seg_idx is None:
            self.last_seg_idx = nearest_idx
            return nearest_idx
        cur_seg = self.route.segments[self.last_seg_idx]
        _, _, d_current = project_point_to_segment(p, cur_seg.a, cur_seg.b)
        _, _, d_new = project_point_to_segment(p, self.route.segments[nearest_idx].a, self.route.segments[nearest_idx].b)
        if d_new + self.hysteresis < d_current:
            self.last_seg_idx = nearest_idx
        return self.last_seg_idx

    def cal_window(self, idx):
        s = set()
        for j in range(max(0, idx-self.grace), min(len(self.route.segments)-1, idx+self.grace)+1):
            s |= self.route.segments[j].cal
        return s

    def nearest_tower(self, p):
        return min(self.towers, key=lambda tw: dist(p, tw.pos()))

    def legitimacy_check(self, cur, prev):
        score = 0
        if cur.plmn == self.route.operator_plmn: score += 1
        if prev is None or abs(cur.tac - prev.tac) <= 1: score += 1
        if cur.arfcn in ALLOWED_ARFCN.get(cur.tech, set()): score += 1
        return score

    def step(self, train: Train, now: float):
        if (now - self.last_poll_time) * 1000.0 < self.poll_ms:
            return None
        self.last_poll_time = now
        seg_idx = self.locate_segment(train.pos())
        window = self.cal_window(seg_idx)
        serving = self.nearest_tower(train.pos())
        allowed = serving.id in window
        decision = "ALLOWED" if allowed else "CHECK"
        if not allowed:
            score = self.legitimacy_check(serving, self.last_serving)
            if score >= 2 and not serving.rogue:
                decision = "ALLOWED*"
            else:
                decision = "BARRED"
                candidates = [tw for tw in self.towers if tw.id in window]
                serving = min(candidates, key=lambda tw: dist(train.pos(), tw.pos())) if candidates else None
        if serving is not None:
            self.last_serving = serving
        self.log_event(seg_idx, decision, serving.id if serving else None)
        return seg_idx, decision, serving

    def log_event(self, seg_idx, decision, cell_id):
        ts = time.strftime("%H:%M:%S")
        line = f"{ts} seg={seg_idx} decision={decision} cell={cell_id}"
        self.log.append(line)
        self.log = self.log[-8:]

# ---------------------------- World setup -----------------------------
def make_route() -> Route:
    pts = [
        (120, 720),(200, 660),(260, 620),(320, 590),(380, 560),(460, 540),
        (520, 520),(560, 500),(600, 470),(630, 440),(660, 410),(690, 380),
        (720, 350),(750, 320),(770, 300),(820, 280),(860, 260),(900, 240),
        (940, 220),(980, 210),(1040, 200),
    ]
    return Route.from_polyline(pts)

def make_towers(n=70):
    import random as _rand
    towers = []
    for i in range(n):
        x = _rand.uniform(60, W-60)
        y = _rand.uniform(60, H-60)
        plmn = _rand.choice(PLMNS)
        tech = _rand.choice(["LTE", "NR"])
        if _rand.random() < 0.7:
            arfcn = _rand.choice(list(ALLOWED_ARFCN[tech]))
        else:
            arfcn = _rand.choice([1492, 3350, 4990, 700000])
        tac = _rand.randint(100, 120)
        pci = _rand.randint(1, 503)
        towers.append(CellTower(i, x, y, plmn, tech, arfcn, tac, pci))
    for tw in _rand.sample(towers, k=max(2, n//15)):
        tw.rogue = True
        other = _rand.choice([p for p in PLMNS if p != tw.plmn])
        tw.plmn = other
        tw.arfcn = _rand.choice([1492, 3350, 4990, 700000])
    return towers

# ---------------------------- Rendering -------------------------------
class UI:
    def __init__(self, rlce: RLCE, train: Train):
        pygame.init()
        pygame.display.init()
        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("RLCE Demo — Charlotte LRV")
        self.clock = pygame.time.Clock()
        try:
            self.font = pygame.font.SysFont("consolas", 16)
            self.font_small = pygame.font.SysFont("consolas", 14)
        except Exception:
            log("SysFont failed; using default font")
            self.font = pygame.font.Font(None, 16)
            self.font_small = pygame.font.Font(None, 14)
        self.rlce = rlce
        self.train = train
        self.stations = [
            "I-485/S Blvd","Sharon W","Arrowood","Archdale","Tyvola","Woodlawn",
            "Scaleybark","New Bern","East/West","Bland","Carson","Stonewall",
            "3rd/CTC","Arena","7th St","Parkwood","25th","36th","Sugar Ck","Tryon","JW Clay"
        ]

    def draw_route(self):
        pygame.draw.lines(self.screen, ROUTE_COLOR, False, self.rlce.route.points, 3)
        for i, seg in enumerate(self.rlce.route.segments):
            mid = seg.mid()
            pygame.draw.circle(self.screen, SEG_COLOR, (int(mid[0]), int(mid[1])), 4)
            if i < len(self.stations):
                label = self.font_small.render(self.stations[i], True, (180, 200, 230))
                self.screen.blit(label, (int(mid[0]) + 6, int(mid[1]) - 10))

    def draw_segment_window(self, seg_idx):
        g = self.rlce.grace
        for j in range(max(0, seg_idx-g), min(len(self.rlce.route.segments)-1, seg_idx+g)+1):
            seg = self.rlce.route.segments[j]
            pygame.draw.line(self.screen, CUR_SEG_COLOR, seg.a, seg.b, 6)
        left = max(0, seg_idx-g)
        right = min(len(self.rlce.route.segments)-1, seg_idx+g)
        for k in (left, right):
            seg = self.rlce.route.segments[k]
            pygame.draw.circle(self.screen, (255,230,120), (int(seg.a[0]), int(seg.a[1])), 6, 2)
            pygame.draw.circle(self.screen, (255,230,120), (int(seg.b[0]), int(seg.b[1])), 6, 2)

    def draw_towers(self, serving: Optional[CellTower], window_ids: Set[int]):
        for tw in self.rlce.towers:
            if serving and tw.id == serving.id:
                color = TOWER_COLORS["serving"]
            elif tw.rogue:
                color = TOWER_COLORS["rogue"]
            else:
                color = TOWER_COLORS["clean"]
            r = 7 if serving and tw.id == serving.id else 4
            pygame.draw.circle(self.screen, color, (int(tw.x), int(tw.y)), r)
            if tw.id in window_ids:
                pygame.draw.circle(self.screen, (200,200,255), (int(tw.x), int(tw.y)), r+3, 1)

    def draw_train(self):
        x, y = int(self.train.x), int(self.train.y)
        body = pygame.Rect(x-18, y-7, self.train.w, self.train.h)
        pygame.draw.rect(self.screen, TRAIN_COLOR, body, border_radius=4)
        pygame.draw.polygon(self.screen, (180,180,200), [(x-4,y-7),(x+4,y-7),(x,y-18)],1)

    def draw_panel(self, seg_idx, decision, serving: Optional[CellTower]):
        pygame.draw.rect(self.screen, PANEL_BG, pygame.Rect(0, 0, W, 92))
        lines = [f"seg={seg_idx} grace={self.rlce.grace} d={int(self.rlce.hysteresis)} Dt={self.rlce.poll_ms}ms auto={'ON' if self.train.auto else 'OFF'}"]
        if serving:
            lines.append(f"serving id:{serving.id} plmn:{serving.plmn} tech:{serving.tech} arfcn:{serving.arfcn} tac:{serving.tac} rogue={serving.rogue}")
        else:
            lines.append("serving=NONE")
        lines.append(f"decision={decision}")
        for i, t in enumerate(lines):
            self.screen.blit(self.font.render(t, True, TEXT_COLOR), (16, 10 + i*18))
        x0 = W-460
        self.screen.blit(self.font.render("events:", True, TEXT_COLOR), (x0, 10))
        for i, line in enumerate(self.rlce.log[-5:][::-1]):
            self.screen.blit(self.font_small.render(line, True, (200,200,200)), (x0,30+i*16))
        hint = "Arrows | Space auto | R rogue | G/H grace | 1/2 d | 3/4 Dt | L reselection | N new net | S screenshot | Esc x2 to exit"
        self.screen.blit(self.font_small.render(hint, True, (180,180,200)), (16,72))

    def save_screenshot(self):
        fn = f"rlce_demo_{int(time.time())}.png"
        pygame.image.save(self.screen, fn)
        self.rlce.log.append(f"saved {fn}")

# ---------------------------- Simulation loop -------------------------
def advance_along_route(train: Train, route: Route, dt: float):
    if not route.segments:
        return
    total_segments = len(route.segments)
    seg_i = int(math.floor(train.route_t))
    local_t = train.route_t - seg_i
    seg_i = clamp(seg_i, 0, total_segments-1)
    seg = route.segments[seg_i]
    a, b = seg.a, seg.b
    seg_len = dist(a, b)
    if seg_len < 1e-6:
        train.route_t += 1e-3
        return
    dt_px = train.auto_speed * dt
    d_t = dt_px / seg_len
    local_t += d_t
    while local_t > 1.0 and seg_i < total_segments-1:
        local_t -= 1.0
        seg_i += 1
        seg = route.segments[seg_i]
        a, b = seg.a, seg.b
        seg_len = dist(a, b)
    if local_t > 1.0 and seg_i == total_segments-1:
        seg_i = 0
        local_t = 0.0
    train.route_t = seg_i + local_t
    train.x, train.y = lerp(a, b, local_t)

def find_nearby_tower(towers: List[CellTower], pos: Tuple[float, float], radius=150) -> Optional[CellTower]:
    best = None; best_d = 1e9
    for tw in towers:
        d = dist(tw.pos(), pos)
        if d <= radius and d < best_d:
            best = tw; best_d = d
    return best

def main():
    try:
        # --- init
        pygame.init()
        screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("RLCE Demo — Charlotte LRV")
        # clear any stale events (e.g., prior ESC) and give OS a tick
        pygame.event.clear()
        pygame.event.get()
        start_time = time.time()
        esc_first: Optional[float] = None
        ESC_DEBOUNCE_S = 0.50   # ignore ESC for 500ms after startup
        ESC_DOUBLE_S   = 0.80   # require 2nd ESC within 800ms to exit

        route = make_route()
        towers = make_towers(70)
        rlce = RLCE(route, towers)
        rlce.rebuild_cal()
        train = Train(*route.points[0])
        ui = UI(rlce, train)
        running = True
        last = time.time()
        log("startup OK")

        while running:
            now = time.time()
            dt = now - last
            last = now

            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    running = False
                elif e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_ESCAPE:
                        # Debounce: ignore ESC for first 500ms after startup
                        if now - start_time < ESC_DEBOUNCE_S:
                            rlce.log.append("ESC ignored (debounce)")
                        else:
                            if esc_first is None or (now - esc_first) > ESC_DOUBLE_S:
                                esc_first = now
                                rlce.log.append("Press ESC again to exit…")  # arm
                            else:
                                running = False  # confirmed
                    elif e.key == pygame.K_SPACE:
                        train.auto = not train.auto
                    elif e.key == pygame.K_r:
                        tw = find_nearby_tower(towers, train.pos(), radius=200)
                        if tw is None:
                            rlce.log.append("no tower nearby to toggle")
                        else:
                            tw.rogue = not tw.rogue
                            if tw.rogue:
                                tw.plmn = [p for p in PLMNS if p != rlce.route.operator_plmn][0]
                                tw.arfcn = [1492, 3350, 4990, 700000][0]
                            else:
                                tw.plmn = rlce.route.operator_plmn
                                tw.arfcn = list(ALLOWED_ARFCN[tw.tech])[0]
                            rlce.rebuild_cal()
                            rlce.log.append(f"tower {tw.id} rogue={tw.rogue}")
                    elif e.key == pygame.K_g:
                        rlce.grace = max(0, rlce.grace-1)
                    elif e.key == pygame.K_h:
                        rlce.grace = min(3, rlce.grace+1)
                    elif e.key == pygame.K_1:
                        rlce.hysteresis = max(0.0, rlce.hysteresis - 10.0)
                    elif e.key == pygame.K_2:
                        rlce.hysteresis = min(120.0, rlce.hysteresis + 10.0)
                    elif e.key == pygame.K_3:
                        rlce.poll_ms = max(50, rlce.poll_ms - 25)
                    elif e.key == pygame.K_4:
                        rlce.poll_ms = min(1000, rlce.poll_ms + 25)
                    elif e.key == pygame.K_l:
                        seg_idx = rlce.locate_segment(train.pos())
                        window = rlce.cal_window(seg_idx)
                        candidates = [tw for tw in towers if tw.id in window]
                        if candidates:
                            rlce.last_serving = min(candidates, key=lambda tw: dist(tw.pos(), train.pos()))
                            rlce.log.append(f"forced reselection -> {rlce.last_serving.id}")
                        else:
                            rlce.log.append("no in-window towers for reselection")
                    elif e.key == pygame.K_n:
                        towers[:] = make_towers(70)
                        rlce.towers = towers
                        rlce.rebuild_cal()
                    elif e.key == pygame.K_s:
                        ui.save_screenshot()

            # movement
            keys = pygame.key.get_pressed()
            if not train.auto:
                vx = vy = 0.0
                if keys[pygame.K_LEFT]:  vx -= train.speed
                if keys[pygame.K_RIGHT]: vx += train.speed
                if keys[pygame.K_UP]:    vy -= train.speed
                if keys[pygame.K_DOWN]:  vy += train.speed
                if vx or vy:
                    n = math.hypot(vx, vy)
                    if n > 0:
                        train.x += (vx/n) * dt * train.speed
                        train.y += (vy/n) * dt * train.speed
            else:
                advance_along_route(train, route, dt)

            # RLCE step
            step_out = rlce.step(train, now)
            if step_out is None:
                seg_idx = rlce.locate_segment(train.pos())
                decision = "…"
                serving = rlce.last_serving
            else:
                seg_idx, decision, serving = step_out

            # draw
            ui.screen.fill(BG)
            ui.draw_route()
            ui.draw_segment_window(seg_idx)
            window_ids = rlce.cal_window(seg_idx)
            ui.draw_towers(serving, window_ids)
            ui.draw_train()
            ui.draw_panel(seg_idx, decision, serving)
            pygame.display.flip()
            ui.clock.tick(FPS)

    except Exception as e:
        trace = traceback.format_exc()
        log(f"FATAL: {e!r}\n{trace}")
        print("Fatal:", e)
        print(trace)
        time.sleep(1.0)
        raise

if __name__ == "__main__":
    main()

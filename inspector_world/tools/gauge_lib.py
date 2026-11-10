"""Геометрия стрелочного прибора и рисование его таблички (текстуры для Gazebo).

Табличка — прямоугольник (текстура на грани +X box в Gazebo):
  шапка с названием → круглый циферблат со шкалой → шильдик с номером прибора.
Стрелка — отдельная геометрия в мире (её можно поворачивать), в текстуре её нет.

Шкала: 270°, от «7:30» (минимум) по часовой стрелке до «4:30» (максимум).
Угол φ отсчитывается от вертикали вверх, по часовой стрелке, как видит наблюдатель.
"""
from __future__ import annotations

import math
from pathlib import Path

PX_PER_M = 2000
PLATE_W, PLATE_H = 600, 700                 # 0.30 × 0.35 м
HEADER_H = 80
DIAL_C = (300, 360)                         # центр циферблата, px
R_BEZEL, R_FACE = 260, 240                  # корпус и белый циферблат
R_TICK_OUT, R_TICK_MAJ, R_TICK_MIN = 230, 198, 212
R_LABEL = 168
SWEEP = 270.0
PHI_MIN = -SWEEP / 2

NEEDLE_LEN_M = 0.105                        # от центра до кончика
NEEDLE_TAIL_M = 0.022


def plate_size_m():
    return PLATE_W / PX_PER_M, PLATE_H / PX_PER_M


def dial_center_offset_m():
    """Смещение центра циферблата от центра таблички (вверх), м."""
    return (PLATE_H / 2 - DIAL_C[1]) / PX_PER_M


def phi_for_value(v, rng):
    lo, hi = rng
    t = (min(max(v, lo), hi) - lo) / (hi - lo)
    return PHI_MIN + SWEEP * t


def _pt(phi_deg, r, c=DIAL_C):
    a = math.radians(phi_deg)
    return c[0] + r * math.sin(a), c[1] - r * math.cos(a)


def nice_ticks(rng):
    lo, hi = rng
    span = hi - lo
    steps = (0.01, 0.02, 0.025, 0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10, 20, 25, 50, 100, 200, 250, 500)
    for lo_n, hi_n in ((4, 6), (4, 8), (3, 10)):                  # не больше ~6 подписей — иначе налезают
        for step in steps:
            n = span / step
            if lo_n <= n <= hi_n and abs(n - round(n)) < 1e-6:
                return step
    return span / 5


def fmt(v):
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def status(value, norm):
    return "OK" if norm[0] <= value <= norm[1] else "ALARM"


def draw_plate(inst, station_id, header_rgb=(55, 70, 95)):
    """Текстура таблички прибора (PIL.Image). inst: id, title, unit, range, norm."""
    from PIL import Image, ImageDraw, ImageFont

    def font(size, bold=False):
        name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
        for d in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu"):
            if (Path(d) / name).exists():
                return ImageFont.truetype(str(Path(d) / name), size)
        return ImageFont.load_default()

    S = 2                                                     # суперсэмплинг
    img = Image.new("RGB", (PLATE_W * S, PLATE_H * S), (205, 208, 212))
    d = ImageDraw.Draw(img)
    sc = lambda p: (p[0] * S, p[1] * S)
    d.rectangle([0, 0, PLATE_W * S, HEADER_H * S], fill=header_rgb)
    d.text(sc((PLATE_W / 2, HEADER_H / 2)), f"{station_id} · {inst['id']}  {inst['title']}",
           font=font(30 * S, True), fill="white", anchor="mm")
    cx, cy = DIAL_C
    box = lambda r: [(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S]
    d.ellipse(box(R_BEZEL), fill=(25, 25, 28))
    d.ellipse(box(R_FACE), fill=(250, 250, 248))
    lo, hi = inst["range"]
    nlo, nhi = inst["norm"]

    def arc(v0, v1, color):                                   # зелёная — норма, красная — вне нормы
        if v1 <= v0:
            return
        a0 = phi_for_value(v0, inst["range"]) - 90             # PIL: 0° = вправо, по часовой
        a1 = phi_for_value(v1, inst["range"]) - 90
        d.arc(box(R_TICK_OUT - 4), a0, a1, fill=color, width=16 * S)
    arc(nlo, nhi, (60, 170, 80))
    arc(lo, nlo, (215, 45, 40))
    arc(nhi, hi, (215, 45, 40))
    step = nice_ticks(inst["range"])
    n_major = int(round((hi - lo) / step))
    for k in range(n_major + 1):
        v = lo + k * step
        phi = phi_for_value(v, inst["range"])
        d.line([sc(_pt(phi, R_TICK_OUT)), sc(_pt(phi, R_TICK_MAJ))], fill=(20, 20, 20), width=6 * S)
        d.text(sc(_pt(phi, R_LABEL)), fmt(v), font=font(26 * S, True), fill=(20, 20, 20), anchor="mm")
        if k < n_major:
            for m in range(1, 5):
                pm = phi_for_value(v + step * m / 5, inst["range"])
                d.line([sc(_pt(pm, R_TICK_OUT)), sc(_pt(pm, R_TICK_MIN))], fill=(40, 40, 40), width=3 * S)
    d.text(sc((cx, cy + 115)), inst["unit"], font=font(34 * S, True), fill=(30, 30, 30), anchor="mm")
    d.ellipse(box(14), fill=(30, 30, 30))
    # шильдик с номером прибора
    ny = (cy + R_BEZEL + PLATE_H) / 2
    d.rounded_rectangle([sc((200, ny - 18)), sc((400, ny + 18))], radius=6 * S, fill=(240, 240, 235),
                        outline=(90, 90, 90), width=2 * S)
    d.text(sc((PLATE_W / 2, ny)), inst["id"], font=font(22 * S, True), fill=(40, 40, 40), anchor="mm")
    d.rectangle([0, 0, PLATE_W * S - 1, PLATE_H * S - 1], outline=(70, 70, 75), width=6 * S)
    return img.resize((PLATE_W, PLATE_H), Image.LANCZOS)

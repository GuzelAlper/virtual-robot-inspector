#!/usr/bin/env python3
"""Генератор сцены инспекции для Gazebo Sim (Harmonic).

Из config/scene.yaml создаёт:
  worlds/inspection_hall.sdf                    — мир Gazebo (стены, препятствия, станции, приборы)
  models/inspector_assets/textures/*.png        — таблички стрелочных приборов
  config/route.yaml                             — маршрут: контрольные точки перед каждым прибором
  docs/scene_map.png                            — схема сцены (вид сверху)

Запуск:  python3 scripts/generate_world.py [--config config/scene.yaml]
Нужны: python3-yaml, python3-numpy, python3-pil, python3-matplotlib.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = "inspector_assets"

import sys
sys.path.insert(0, str(ROOT / "tools"))
import gauge_lib as gl  # noqa: E402

PIPE_Z, PIPE_R = 0.09, 0.03                       # трубопровод вдоль стойки, к нему подключены приборы



# ----------------------------------------------------------------------------- SDF helpers
def material(rgb, emissive=False):
    r, g, b = rgb
    em = f"<emissive>{r} {g} {b} 1</emissive>" if emissive else ""
    return (f"<material><ambient>{r} {g} {b} 1</ambient><diffuse>{r} {g} {b} 1</diffuse>"
            f"<specular>0.1 0.1 0.1 1</specular>{em}</material>")


def geom(kind, size=None, radius=None, length=None):
    if kind == "box":
        return f"<geometry><box><size>{size[0]} {size[1]} {size[2]}</size></box></geometry>"
    return f"<geometry><cylinder><radius>{radius}</radius><length>{length}</length></cylinder></geometry>"


COLLIDERS = []                                    # препятствия для карты Nav2: ("rect", cx, cy, sx, sy, yaw) | ("circle", cx, cy, r)


def add_collider(g, x, y, yaw):
    import re
    m = re.search(r"<box><size>([\d.e+-]+) ([\d.e+-]+) ([\d.e+-]+)</size>", g)
    if m:
        COLLIDERS.append(("rect", x, y, float(m.group(1)), float(m.group(2)), yaw))
        return
    m = re.search(r"<radius>([\d.e+-]+)</radius>", g)
    if m:
        COLLIDERS.append(("circle", x, y, float(m.group(1))))


def static_model(name, pose, g, mat, collide=True, roll=0.0):
    x, y, z, yaw = pose
    col = f'<collision name="c">{g}</collision>' if collide else ""
    if collide and roll == 0.0:
        add_collider(g, x, y, yaw)
    return (f'<model name="{name}"><static>true</static><pose>{x:.4f} {y:.4f} {z:.4f} {roll:.6f} 0 {yaw:.6f}</pose>'
            f'<link name="link">{col}<visual name="v">{g}{mat}</visual></link></model>')


# ----------------------------------------------------------------------------- scene parts
def walls(scene):
    t, h = scene["wall_thickness"], scene["wall_height"]
    segs = []                                     # (x0, y0, x1, y1)
    for r in scene["rooms"]:
        x0, y0, x1, y1 = r["x0"], r["y0"], r["x1"], r["y1"]
        segs += [(x0, y0, x1, y0), (x0, y1, x1, y1), (x0, y0, x0, y1), (x1, y0, x1, y1)]
    out = []
    for (x0, y0, x1, y1) in segs:
        pieces = [(x0, y0, x1, y1)]
        if x0 == x1:                              # вертикальная стена: вырезаем проёмы
            for op in scene.get("openings", []):
                if abs(op["x"] - x0) > 1e-6:
                    continue
                nxt = []
                for (a, b, c, e) in pieces:
                    lo, hi = min(b, e), max(b, e)
                    if hi > op["y0"] and lo < op["y1"]:
                        if lo < op["y0"] - 1e-6:
                            nxt.append((a, lo, a, op["y0"]))
                        if hi > op["y1"] + 1e-6:
                            nxt.append((a, op["y1"], a, hi))
                    else:
                        nxt.append((a, b, c, e))
                pieces = nxt
        out += pieces
    # убрать дубликаты (общие стены соседних помещений)
    uniq = []
    for s in out:
        if not any(all(abs(p - q) < 1e-6 for p, q in zip(s, u)) for u in uniq):
            uniq.append(s)
    models = []
    for i, (x0, y0, x1, y1) in enumerate(uniq):
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 1e-6:
            continue
        horiz = abs(y1 - y0) < 1e-9
        size = (L + t, t, h) if horiz else (t, L + t, h)
        models.append(static_model(f"wall_{i}", ((x0 + x1) / 2, (y0 + y1) / 2, h / 2, 0),
                                   geom("box", size), material((0.72, 0.72, 0.70))))
    return models, uniq


def rot(yaw, x, y):
    c, s = math.cos(yaw), math.sin(yaw)
    return c * x - s * y, s * x + c * y


def stations(cfg, tex_dir):
    """Стойки со стрелочными приборами. Табличка (циферблат) — текстура на грани
    +X box (gz-common CreateBox: u вдоль +Y, v сверху вниз → изображение не зеркальное).
    Стрелка — отдельная модель: её поворот (roll вокруг нормали) задаёт показание."""
    lay = cfg["instrument_layout"]
    pw, ph = gl.plate_size_m()
    zc = lay["panel_center_z"]
    dz = gl.dial_center_offset_m()
    models, route, panels = [], [], []
    k = 0
    for st in cfg["stations"]:
        sx, sy, yaw = st["pose"]["x"], st["pose"]["y"], st["pose"]["yaw"]
        n = len(st["instruments"])
        offs = [(i - (n - 1) / 2) * lay["spacing"] for i in range(n)]
        span = (n - 1) * lay["spacing"] + pw + 0.3
        bx, by = rot(yaw, -0.05, 0)
        models.append(static_model(f"{st['id']}_board", (sx + bx, sy + by, 0.5, yaw),
                                   geom("box", (0.06, span, 1.0)), material((0.25, 0.30, 0.38))))
        bx, by = rot(yaw, 0.03, 0)                       # низкое основание вплотную к плите — не цепляет лапы
        models.append(static_model(f"{st['id']}_base", (sx + bx, sy + by, 0.03, yaw),
                                   geom("box", (0.14, span, 0.06)), material((0.20, 0.22, 0.25))))
        # трубопровод вдоль стойки — к нему «подключены» приборы
        bx, by = rot(yaw, 0.02, 0)
        models.append(static_model(f"{st['id']}_pipe", (sx + bx, sy + by, PIPE_Z, yaw),
                                   geom("cylinder", radius=PIPE_R, length=span), material((0.55, 0.55, 0.58)),
                                   False, roll=math.pi / 2))
        for inst, off in zip(st["instruments"], offs):
            tex = f"{st['id']}_{inst['id']}.png".lower()
            gl.draw_plate(inst, st["id"]).save(tex_dir / tex)
            px, py = rot(yaw, 0.0, off)
            x, y = sx + px, sy + py
            add_collider(geom("box", (0.03, pw, ph)), x, y, yaw)
            models.append(
                f'<model name="{st["id"]}_{inst["id"]}"><static>true</static>'
                f'<pose>{x:.4f} {y:.4f} {zc:.4f} 0 0 {yaw:.6f}</pose><link name="link">'
                f'<collision name="c">{geom("box", (0.03, pw, ph))}</collision>'
                f'<visual name="plate">{geom("box", (0.03, pw, ph))}<material>'
                f'<diffuse>1 1 1 1</diffuse><ambient>1 1 1 1</ambient><pbr><metal>'
                f'<albedo_map>model://{ASSETS}/textures/{tex}</albedo_map>'
                f'<roughness>0.9</roughness><metalness>0.0</metalness></metal></pbr></material></visual>'
                f'<visual name="stem"><pose>-0.01 0 {((PIPE_Z + PIPE_R - zc) - ph / 2) / 2:.4f} 0 0 0</pose>'
                f'{geom("cylinder", radius=0.012, length=max(0.02, -ph / 2 - (PIPE_Z + PIPE_R - zc) + 0.02))}'
                f'{material((0.75, 0.6, 0.25))}</visual>'
                f'</link></model>')
            # стрелка: вращается вокруг нормали к циферблату (локальная ось X модели)
            phi = gl.phi_for_value(inst["value"], inst["range"])
            nx, ny = rot(yaw, 0.017, off)
            L, T = gl.NEEDLE_LEN_M, gl.NEEDLE_TAIL_M
            models.append(
                f'<model name="{st["id"]}_{inst["id"]}_needle"><static>true</static>'
                f'<pose>{sx + nx:.4f} {sy + ny:.4f} {zc + dz:.4f} {-math.radians(phi):.6f} 0 {yaw:.6f}</pose>'
                f'<link name="link">'
                f'<visual name="needle"><pose>0 0 {(L - T) / 2:.4f} 0 0 0</pose>'
                f'{geom("box", (0.004, 0.007, L + T))}{material((0.08, 0.08, 0.09))}</visual>'
                f'<visual name="hub"><pose>0.002 0 0 0 1.570796 0</pose>'
                f'{geom("cylinder", radius=0.011, length=0.006)}{material((0.08, 0.08, 0.09))}</visual>'
                f'</link></model>')
            cx, cy = rot(yaw, lay["checkpoint_distance"], off)
            ryaw = math.atan2(math.sin(yaw + math.pi), math.cos(yaw + math.pi))
            stt = gl.status(inst["value"], inst["norm"])
            route.append({"id": f"CP-{len(route) + 1:02d}", "station": st["id"], "instrument": inst["id"],
                          "title": inst["title"],
                          "range": inst["range"], "unit": inst["unit"], "norm": inst["norm"],
                          "pose": {"x": round(sx + cx, 3), "y": round(sy + cy, 3), "yaw": round(ryaw, 4)},
                          "expected": {"value": inst["value"], "status": stt}})
            panels.append((x, y, yaw, inst["id"], stt == "ALARM"))
            k += 1
    return models, route, panels


def floor_marks(cfg, route):
    s = cfg["scene"]["spawn"]
    out = [static_model("start_zone", (s["x"], s["y"], 0.002, 0), geom("box", (1.2, 1.2, 0.004)),
                        material((0.2, 0.7, 0.3)), False)]
    for cp in route:
        p = cp["pose"]
        out.append(static_model(f"pad_{cp['id']}", (p["x"], p["y"], 0.002, p["yaw"]),
                                geom("box", (0.45, 0.45, 0.004)), material((0.95, 0.85, 0.15)), False))
    return out


def obstacles(cfg):
    out = []
    for ob in cfg["scene"].get("obstacles", []):
        if ob["type"] == "box":
            g = geom("box", ob["size"])
            z = ob["size"][2] / 2
        else:
            g = geom("cylinder", radius=ob["radius"], length=ob["height"])
            z = ob["height"] / 2
        out.append(static_model(ob["name"], (ob["x"], ob["y"], z, ob.get("yaw", 0.0)), g, material(ob["color"])))
    return out


WORLD_HEADER = """<?xml version="1.0" ?>
<!-- СГЕНЕРИРОВАНО scripts/generate_world.py из config/scene.yaml — правьте YAML, а не этот файл -->
<sdf version="1.8">
  <world name="{name}">
    <spherical_coordinates>
      <surface_model>EARTH_WGS84</surface_model>
      <world_frame_orientation>ENU</world_frame_orientation>
      <latitude_deg>59.7525</latitude_deg>
      <longitude_deg>30.5900</longitude_deg>
      <elevation>20.0</elevation>
      <heading_deg>0</heading_deg>
    </spherical_coordinates>
    <physics name="1ms" type="bullet-featherstone">
      <max_step_size>0.001</max_step_size>
      <real_time_factor>1.0</real_time_factor>
    </physics>
    <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
    <plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors">
      <render_engine>ogre2</render_engine>
    </plugin>
    <plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
    <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
    <plugin filename="gz-sim-navsat-system" name="gz::sim::systems::NavSat"/>
    <plugin filename="gz-sim-contact-system" name="gz::sim::systems::Contact"/>
    <scene>
      <ambient>0.55 0.55 0.55 1</ambient>
      <background>0.75 0.80 0.85 1</background>
      <shadows>true</shadows>
    </scene>
    <light type="directional" name="sun">
      <cast_shadows>true</cast_shadows>
      <pose>0 0 10 0 0 0</pose>
      <diffuse>0.85 0.85 0.85 1</diffuse>
      <specular>0.2 0.2 0.2 1</specular>
      <direction>-0.4 0.2 -0.9</direction>
    </light>
    <light type="directional" name="fill">
      <cast_shadows>false</cast_shadows>
      <pose>0 0 10 0 0 0</pose>
      <diffuse>0.35 0.35 0.35 1</diffuse>
      <specular>0 0 0 1</specular>
      <direction>0.6 -0.3 -0.7</direction>
    </light>
    <model name="ground_plane">
      <static>true</static>
      <link name="link">
        <collision name="collision"><geometry><plane><normal>0 0 1</normal><size>60 60</size></plane></geometry></collision>
        <visual name="visual"><geometry><plane><normal>0 0 1</normal><size>60 60</size></plane></geometry>
          <material><ambient>0.55 0.56 0.58 1</ambient><diffuse>0.55 0.56 0.58 1</diffuse><specular>0.1 0.1 0.1 1</specular></material>
        </visual>
      </link>
    </model>
"""


def scene_map(cfg, wall_segs, panels, route, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Rectangle
    fig, ax = plt.subplots(figsize=(12, 6), dpi=110)
    for (x0, y0, x1, y1) in wall_segs:
        ax.plot([x0, x1], [y0, y1], color="#555", lw=4, solid_capstyle="butt")
    for ob in cfg["scene"]["obstacles"]:
        if ob["type"] == "box":
            sx, sy = ob["size"][:2]
            ax.add_patch(Rectangle((ob["x"] - sx / 2, ob["y"] - sy / 2), sx, sy, color=ob["color"]))
        else:
            ax.add_patch(Circle((ob["x"], ob["y"]), ob["radius"], color=ob["color"]))
        ax.text(ob["x"], ob["y"], ob["name"], ha="center", va="center", fontsize=8, color="white")
    s = cfg["scene"]["spawn"]
    ax.add_patch(Rectangle((s["x"] - 0.6, s["y"] - 0.6), 1.2, 1.2, color="#3c3", alpha=0.5))
    ax.annotate("", xy=(s["x"] + 0.5, s["y"]), xytext=(s["x"], s["y"]), arrowprops=dict(arrowstyle="->", lw=2))
    ax.text(s["x"], s["y"] - 0.85, "старт Go2", ha="center", fontsize=9)
    for (x, y, yaw, iid, alarm) in panels:
        dx, dy = -math.sin(yaw) * 0.18, math.cos(yaw) * 0.18          # панель вдоль локальной оси y
        ax.plot([x - dx, x + dx], [y - dy, y + dy], color="#c22" if alarm else "#2a2", lw=6)
        ax.text(x - 0.25 * math.cos(yaw), y - 0.25 * math.sin(yaw), iid, va="center", fontsize=8)
    xs = [s["x"]] + [c["pose"]["x"] for c in route]
    ys = [s["y"]] + [c["pose"]["y"] for c in route]
    ax.plot(xs, ys, "--", color="#e8a400", lw=1.5)
    for c in route:
        p = c["pose"]
        ax.add_patch(Rectangle((p["x"] - 0.22, p["y"] - 0.22), 0.45, 0.45, color="#f2d421", alpha=0.8))
        ax.text(p["x"], p["y"], c["id"].split("-")[1], ha="center", va="center", fontsize=7)
    ax.set_aspect("equal")
    ax.set_xlim(-2, 13)
    ax.set_ylim(-3.5, 3.5)
    ax.grid(alpha=0.3)
    ax.set_xlabel("x, м")
    ax.set_ylabel("y, м")
    ax.set_title(f"Сцена «{cfg['scene']['name']}»: старт → коридор → цех со станцией\n"
                 "пунктир — порядок обхода контрольных точек (путь в обход препятствий строит навигация)", fontsize=10)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def write_map(cfg, path_stem, res=0.05, margin=0.5):
    """Карта занятости для Nav2 (map_server): всё вне помещений — занято,
    внутри — свободно, плюс стены, препятствия и стойки. Кадр карты — world (= мир Gazebo)."""
    rooms = cfg["scene"]["rooms"]
    x0 = min(r["x0"] for r in rooms) - margin
    y0 = min(r["y0"] for r in rooms) - margin
    x1 = max(r["x1"] for r in rooms) + margin
    y1 = max(r["y1"] for r in rooms) + margin
    W, H = int(math.ceil((x1 - x0) / res)), int(math.ceil((y1 - y0) / res))
    occ = np.ones((H, W), np.uint8)                       # 1 — занято
    xs = x0 + (np.arange(W) + 0.5) * res
    ys = y0 + (np.arange(H) + 0.5) * res
    X, Y = np.meshgrid(xs, ys)
    for r in rooms:
        occ[(X >= r["x0"]) & (X <= r["x1"]) & (Y >= r["y0"]) & (Y <= r["y1"])] = 0
    for c in COLLIDERS:
        if c[0] == "rect":
            _, cx, cy, sx, sy, yaw = c
            dx, dy = X - cx, Y - cy
            lx = dx * math.cos(yaw) + dy * math.sin(yaw)
            ly = -dx * math.sin(yaw) + dy * math.cos(yaw)
            occ[(np.abs(lx) <= sx / 2 + res / 2) & (np.abs(ly) <= sy / 2 + res / 2)] = 1
        else:
            _, cx, cy, r = c
            occ[(X - cx) ** 2 + (Y - cy) ** 2 <= (r + res / 2) ** 2] = 1
    img = np.where(occ, 0, 254).astype(np.uint8)[::-1]     # PGM: строка 0 — верх (max y)
    pgm = path_stem.with_suffix(".pgm")
    pgm.parent.mkdir(parents=True, exist_ok=True)
    with open(pgm, "wb") as f:
        f.write(f"P5\n{W} {H}\n255\n".encode())
        f.write(img.tobytes())
    path_stem.with_suffix(".yaml").write_text(
        f"image: {pgm.name}\nmode: trinary\nresolution: {res}\norigin: [{x0:.3f}, {y0:.3f}, 0.0]\n"
        f"negate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n", encoding="utf-8")
    return occ, (x0, y0, res)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config" / "scene.yaml"))
    args = ap.parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    tex_dir = ROOT / "models" / ASSETS / "textures"
    for old in tex_dir.glob("*.png"):
        old.unlink()

    wall_models, wall_segs = walls(cfg["scene"])
    st_models, route, panels = stations(cfg, tex_dir)
    body = wall_models + obstacles(cfg) + st_models + floor_marks(cfg, route)
    world = WORLD_HEADER.format(name=cfg["scene"]["name"]) + "\n".join("    " + m for m in body) + \
        "\n  </world>\n</sdf>\n"
    (ROOT / "worlds").mkdir(exist_ok=True)
    (ROOT / "worlds" / "inspection_hall.sdf").write_text(world, encoding="utf-8")

    (ROOT / "models" / ASSETS / "model.config").write_text(
        f'<?xml version="1.0"?>\n<model><name>{ASSETS}</name><version>1.0</version>'
        f'<sdf version="1.8">model.sdf</sdf><description>Текстуры приборов сцены инспекции</description></model>\n',
        encoding="utf-8")
    (ROOT / "models" / ASSETS / "model.sdf").write_text(
        f'<?xml version="1.0"?>\n<sdf version="1.8"><model name="{ASSETS}"><static>true</static>'
        f'<link name="link"/></model></sdf>\n', encoding="utf-8")

    sp = cfg["scene"]["spawn"]
    route_doc = {"scene": cfg["scene"]["name"],
                 "start": {"x": sp["x"], "y": sp["y"], "yaw": sp["yaw"]},
                 "checkpoints": route,
                 "finish": {"x": sp["x"], "y": sp["y"], "yaw": sp["yaw"]}}
    (ROOT / "config" / "route.yaml").write_text(
        "# СГЕНЕРИРОВАНО scripts/generate_world.py — маршрут обхода приборов\n" +
        yaml.safe_dump(route_doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    write_map(cfg, ROOT / "maps" / "inspection_hall")
    (ROOT / "docs").mkdir(exist_ok=True)
    scene_map(cfg, wall_segs, panels, route, ROOT / "docs" / "scene_map.png")
    print(f"мир: worlds/inspection_hall.sdf  стен: {len(wall_models)}  приборов: {len(route)}  "
          f"тревог: {sum(1 for c in route if c['expected']['status'] == 'ALARM')}")


if __name__ == "__main__":
    main()

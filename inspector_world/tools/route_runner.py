#!/usr/bin/env python3
"""Миссия обхода: Go2 сам объезжает контрольные точки через Nav2.

    ros2 run inspector_world route_runner.py
    ros2 run inspector_world route_runner.py --dwell 3 --no-return

Порядок: ждёт готовности Nav2 → для каждой точки из config/route.yaml отправляет цель
NavigateToPose → у прибора стоит dwell секунд (камера смотрит на прибор, кадр
сохраняется) → следующая точка → возврат на старт → отчёт
~/inspection_reports/<дата_время>/ (report.md, results.json, results.csv, кадры).

Показания приборов в этой версии не считываются: отчёт фиксирует только,
удалось ли доехать до каждой точки («посещено» / «не доехал»).
Ошибка на одной точке не останавливает миссию; итог — COMPLETED / PARTIALLY_COMPLETED / FAILED.
Состояние миссии публикуется в /inspection/mission_state (std_msgs/String, JSON).
"""
import argparse
import csv
import json
import math
import os
import time

import cv2
import numpy as np
import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped, Twist
from nav_msgs.msg import Odometry
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
from rclpy.parameter import Parameter
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from std_msgs.msg import String

FRAME = "world"


def make_pose(nav, p):
    m = PoseStamped()
    m.header.frame_id = FRAME
    m.header.stamp = nav.get_clock().now().to_msg()
    m.pose.position.x, m.pose.position.y = float(p["x"]), float(p["y"])
    m.pose.orientation.z, m.pose.orientation.w = math.sin(p["yaw"] / 2), math.cos(p["yaw"] / 2)
    return m


def to_bgr(msg):
    a = np.frombuffer(msg.data, np.uint8)
    ch = {"rgb8": 3, "bgr8": 3, "rgba8": 4, "bgra8": 4, "mono8": 1}.get(msg.encoding)
    if ch is None:
        return None
    img = a.reshape(msg.height, msg.step)[:, :msg.width * ch]
    if ch == 1:
        return cv2.cvtColor(img.reshape(msg.height, msg.width), cv2.COLOR_GRAY2BGR)
    img = img.reshape(msg.height, msg.width, ch)
    code = {"rgb8": cv2.COLOR_RGB2BGR, "rgba8": cv2.COLOR_RGBA2BGR, "bgra8": cv2.COLOR_BGRA2BGR}.get(msg.encoding)
    return cv2.cvtColor(img, code) if code is not None else img.copy()


class Mission:
    def __init__(self, args):
        self.args = args
        share = get_package_share_directory("inspector_world")
        with open(os.path.join(share, "config", "route.yaml"), encoding="utf-8") as f:
            self.route = yaml.safe_load(f)
        self.nav = BasicNavigator(node_name="route_runner")
        self.nav.set_parameters([Parameter("use_sim_time", Parameter.Type.BOOL, True)])
        self.last_frame = None
        self.gt = None                                         # (x, y, z) истинная поза из Gazebo
        self.gt_yaw = None
        self.nav.create_subscription(Image, args.camera, self.on_image, qos_profile_sensor_data)
        self.nav.create_subscription(Odometry, "/odom/ground_truth", self.on_gt, 10)
        self.state_pub = self.nav.create_publisher(String, "/inspection/mission_state", 10)
        self.cmd_pub = self.nav.create_publisher(Twist, "/cmd_vel", 10)
        self.results = []
        self.returned = None
        self.t0 = time.time()
        self.out = os.path.expanduser(os.path.join("~/inspection_reports", time.strftime("%Y%m%d_%H%M%S")))
        os.makedirs(self.out, exist_ok=True)

    # ------------------------------------------------------------------ helpers
    def log(self, text):
        print(f"[{time.time() - self.t0:6.1f} с] {text}", flush=True)

    def state(self, state, **extra):
        try:                                                   # после Ctrl+C контекст ROS уже закрыт
            self.state_pub.publish(String(data=json.dumps({"state": state, **extra}, ensure_ascii=False)))
        except Exception:
            pass

    def on_gt(self, msg):
        p, q = msg.pose.pose.position, msg.pose.pose.orientation
        self.gt = (p.x, p.y, p.z)
        self.gt_yaw = math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))

    def send_cmd(self, vx=0.0, vy=0.0, wz=0.0):
        t = Twist()
        t.linear.x, t.linear.y, t.angular.z = float(vx), float(vy), float(wz)
        try:
            self.cmd_pub.publish(t)
        except Exception:
            pass

    def align(self, pose, timeout=None):
        """Точная постановка напротив прибора (или короткий переход вдоль стойки).
        Go2 — голономный: одновременно сдвиг вперёд/вбок и поворот, без «повернуть-пройти-повернуть».
        Управление по истинной позе; минимальные скорости — чтобы CHAMP реально шагал, а не топтался."""
        a = self.args
        timeout = timeout or a.align_timeout
        start, held = time.time(), None
        while time.time() - start < timeout:
            rclpy.spin_once(self.nav, timeout_sec=0.05)
            if self.gt is None or getattr(self, "gt_yaw", None) is None:
                continue
            if self.fallen():
                break
            dx, dy = pose["x"] - self.gt[0], pose["y"] - self.gt[1]
            c, s_ = math.cos(self.gt_yaw), math.sin(self.gt_yaw)
            ex, ey = c * dx + s_ * dy, -s_ * dx + c * dy               # ошибка в СК робота
            eth = math.atan2(math.sin(pose["yaw"] - self.gt_yaw), math.cos(pose["yaw"] - self.gt_yaw))
            if abs(ex) < a.align_xy and abs(ey) < a.align_xy and abs(eth) < a.align_yaw:
                held = held or time.time()
                self.send_cmd()
                if time.time() - held > 0.4:                         # стоит в допуске — готово
                    break
                continue
            held = None

            def axis(err, gain, vmin, vmax, tol):
                if abs(err) < tol:
                    return 0.0
                v = gain * err
                return math.copysign(min(max(abs(v), vmin), vmax), err)
            self.send_cmd(axis(ex, 1.2, 0.10, 0.35, a.align_xy),
                          axis(ey, 1.2, 0.10, 0.25, a.align_xy),
                          axis(eth, 1.5, 0.25, 0.7, a.align_yaw))
        for _ in range(5):
            self.send_cmd()
            rclpy.spin_once(self.nav, timeout_sec=0.02)
        if self.gt is None:
            return None
        return math.hypot(pose["x"] - self.gt[0], pose["y"] - self.gt[1])

    def fallen(self):
        return self.gt is not None and self.gt[2] < self.args.fall_height

    def on_image(self, msg):
        self.last_frame = msg

    def spin_for(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            rclpy.spin_once(self.nav, timeout_sec=0.05)

    def cancel(self):
        """Отменить задачу Nav2 и дать ему время освободиться (иначе следующая цель сразу падает)."""
        try:
            self.nav.cancelTask()
        except Exception:
            pass
        self.spin_for(1.5)

    def dist_to(self, pose):
        if self.gt is None:
            return None
        return math.hypot(self.gt[0] - pose["x"], self.gt[1] - pose["y"])

    def go(self, pose, label, retry=True):
        """→ (успех, примечание)"""
        if not self.nav.goToPose(make_pose(self.nav, pose)):
            return False, "цель отклонена Nav2"
        start, last_print = time.time(), 0.0
        anchor, anchor_t = self.gt, time.time()                # «застрял»: нет движения
        best, best_t = float("inf"), time.time()               # «топчется у цели»: не приближается
        while not self.nav.isTaskComplete():
            now = time.time()
            if now - start > self.args.goal_timeout:
                self.cancel()
                return False, f"тайм-аут {self.args.goal_timeout:.0f} с"
            if self.fallen():
                self.cancel()
                return False, "робот упал"
            d = self.dist_to(pose)
            if d is not None:
                if d < best - 0.05:
                    best, best_t = d, now
                elif d < self.args.near_dist and now - best_t > self.args.near_time:
                    self.cancel()                                # рядом с целью, но не «доводится» — засчитать
                    return True, f"остановился в {d:.2f} м от точки"
            if self.gt is not None:
                if anchor is None or math.hypot(self.gt[0] - anchor[0], self.gt[1] - anchor[1]) > 0.15:
                    anchor, anchor_t = self.gt, now
                elif now - anchor_t > self.args.stuck_time:
                    self.cancel()
                    return False, f"застрял: не сдвинулся за {self.args.stuck_time:.0f} с"
            fb = self.nav.getFeedback()
            if fb and now - last_print > 5:
                last_print = now
                self.log(f"  → {label}: осталось {fb.distance_remaining:.1f} м")
        res = self.nav.getResult()
        if res == TaskResult.SUCCEEDED:
            return True, ""
        if retry and time.time() - start < 5.0:                # мгновенный отказ — Nav2 ещё занят
            self.log("  Nav2 сразу отказал, повторяю цель")
            self.spin_for(2.0)
            return self.go(pose, label, retry=False)
        return False, {TaskResult.CANCELED: "отменено", TaskResult.FAILED: "Nav2 не смог доехать"}.get(res, str(res))

    def look(self, cp):
        """Постоять перед прибором dwell секунд и сохранить кадр камеры → имя файла или ''."""
        self.last_frame = None
        self.spin_for(self.args.dwell)
        if self.last_frame is None:
            return ""
        img = to_bgr(self.last_frame)
        if img is None:
            return ""
        name = f"{cp['id']}_{cp['station']}_{cp['instrument']}.png"
        cv2.imwrite(os.path.join(self.out, name), img)
        return name

    # ------------------------------------------------------------------ mission
    def run(self):
        self.log("жду готовности Nav2 (map_server, bt_navigator)…")
        self.state("PREPARING")
        self.nav.waitUntilNav2Active(localizer="map_server")
        cps = self.route["checkpoints"]
        a_hop = self.args.hop_dist
        self.log(f"Nav2 готов. Маршрут: {len(cps)} точек, сцена «{self.route['scene']}»")
        self.state("RUNNING", total=len(cps))
        for i, cp in enumerate(cps, 1):
            label = f"{cp['id']} ({cp['station']}/{cp['instrument']} {cp['title']})"
            self.log(f"[{i}/{len(cps)}] еду к {label}")
            self.state("NAVIGATING", checkpoint=cp["id"], index=i)
            t_nav = time.time()
            prev = cps[i - 2] if i > 1 else None
            hop = (prev is not None and prev["station"] == cp["station"] and self.results
                   and self.results[-1]["result"] == "VISITED"
                   and math.hypot(prev["pose"]["x"] - cp["pose"]["x"], prev["pose"]["y"] - cp["pose"]["y"]) <= a_hop)
            if hop:                                                     # соседний прибор на той же стойке
                self.log("  переход вдоль стойки (боком, без разворотов)")
                err = self.align(cp["pose"], timeout=self.args.hop_timeout)
                ok, why = (err is not None and err < 0.3), ""
                if not ok:
                    self.log("  переход не удался — еду через Nav2")
                    ok, why = self.go(cp["pose"], label)
            else:
                ok, why = self.go(cp["pose"], label)
            if ok:
                err = self.align(cp["pose"])
                if err is not None:
                    self.log(f"  встал напротив прибора (ошибка {err * 100:.0f} см)")
            row = {"checkpoint": cp["id"], "station": cp["station"], "instrument": cp["instrument"],
                   "title": cp["title"], "nav_time_s": round(time.time() - t_nav, 1)}
            if ok:
                self.state("AT_INSTRUMENT", checkpoint=cp["id"])
                self.log(f"  ✓ на месте{' (' + why + ')' if why else ''}, смотрю на прибор {self.args.dwell:g} с")
                row.update(result="VISITED", reason=why, photo=self.look(cp))
            else:
                self.log(f"  ✗ не доехал: {why} — перехожу к следующей точке")
                row.update(result="NAV_FAILED", reason=why, photo="")
            self.results.append(row)
            if self.fallen():
                self.log("  ✗ робот упал — миссия прервана")
                for rest in cps[i:]:
                    self.results.append({"checkpoint": rest["id"], "station": rest["station"],
                                         "instrument": rest["instrument"], "title": rest["title"],
                                         "nav_time_s": 0, "result": "NAV_FAILED", "reason": "робот упал", "photo": ""})
                self.finish("done")
                return
        if not self.args.no_return:
            self.log("возвращаюсь на старт")
            self.state("RETURNING")
            ok, why = self.go(self.route["finish"], "старт")
            if ok and why:
                why = ""
            self.returned = ok
            self.log("  ✓ на старте" if ok else f"  ✗ не вернулся: {why}")
        self.finish("done")

    def finish(self, how):
        visited = sum(r["result"] == "VISITED" for r in self.results)
        total = len(self.route["checkpoints"])
        if how == "canceled":
            final = "CANCELED"
        elif visited == total:
            final = "COMPLETED"
        elif visited:
            final = "PARTIALLY_COMPLETED"
        else:
            final = "FAILED"
        self.state(final, visited=visited, total=total)
        self.write_report(final, visited, total)

    def write_report(self, final, visited, total):
        summary = {"scene": self.route["scene"], "status": final,
                   "started": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.t0)),
                   "duration_s": round(time.time() - self.t0, 1), "checkpoints": total,
                   "visited": visited, "returned_to_start": self.returned, "results": self.results}
        with open(os.path.join(self.out, "results.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        keys = ["checkpoint", "station", "instrument", "title", "result", "nav_time_s", "photo", "reason"]
        with open(os.path.join(self.out, "results.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            w.writeheader()
            w.writerows(self.results)
        ret = {True: "да", False: "нет", None: "не выполнялся"}[self.returned]
        lines = [f"# Отчёт об обходе — {summary['started']}", "",
                 f"* Сцена: **{summary['scene']}**",
                 f"* Итог миссии: **{final}**",
                 f"* Посещено точек: **{visited} из {total}**",
                 f"* Длительность: {summary['duration_s']} с (реального времени)",
                 f"* Возврат на старт: {ret}", "",
                 "| Точка | Станция | Прибор | Результат | Время в пути, с | Кадр | Примечание |",
                 "|---|---|---|---|---|---|---|"]
        for r in self.results:
            res = "✅ посещено" if r["result"] == "VISITED" else "❌ не доехал"
            photo = f"![{r['checkpoint']}]({r['photo']})" if r["photo"] else "—"
            lines.append(f"| {r['checkpoint']} | {r['station']} | {r['instrument']} {r['title']} | {res} | "
                         f"{r['nav_time_s']} | {photo} | {r['reason']} |")
        with open(os.path.join(self.out, "report.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        self.log(f"ИТОГ: {final}. Посещено {visited}/{total}.")
        self.log(f"Отчёт: {self.out}/report.md")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dwell", type=float, default=2.5, help="сколько секунд стоять у прибора")
    ap.add_argument("--goal-timeout", type=float, default=240.0, help="макс. время на одну точку, с (реальных)")
    ap.add_argument("--stuck-time", type=float, default=60.0, help="не сдвинулся на 15 см за это время → пропустить точку")
    ap.add_argument("--align-xy", type=float, default=0.06, help="допуск точной постановки, м")
    ap.add_argument("--align-yaw", type=float, default=0.06, help="допуск по углу, рад (~3.5°)")
    ap.add_argument("--align-timeout", type=float, default=15.0, help="макс. время точной постановки, с")
    ap.add_argument("--hop-dist", type=float, default=1.5, help="соседние точки на одной стойке ближе этого — переход боком")
    ap.add_argument("--hop-timeout", type=float, default=30.0, help="макс. время перехода боком, с")
    ap.add_argument("--near-dist", type=float, default=0.45, help="ближе этого к точке и не приближается → засчитать, м")
    ap.add_argument("--near-time", type=float, default=6.0, help="сколько секунд «топтаться» у точки до зачёта")
    ap.add_argument("--fall-height", type=float, default=0.12, help="корпус ниже этой высоты, м → робот упал")
    ap.add_argument("--camera", default="/rgb_image", help="топик камеры для кадра у прибора")
    ap.add_argument("--no-return", action="store_true", help="не возвращаться на старт")
    args, ros_args = ap.parse_known_args()
    rclpy.init(args=ros_args)
    m = Mission(args)
    try:
        m.run()
    except KeyboardInterrupt:
        m.log("прервано пользователем")
        try:
            m.nav.cancelTask()
        except Exception:
            pass
        m.finish("canceled")
    finally:
        m.nav.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()

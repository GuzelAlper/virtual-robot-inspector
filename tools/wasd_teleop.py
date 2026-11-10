#!/usr/bin/env python3
"""Ручное управление Go2 с клавиатуры (WASD).

W/S — скорость вперёд/назад, A/D — поворот, Q/E — движение боком,
Пробел — стоп, X — выход. Скорость меняется шагами и сохраняется,
пока не нажата другая клавиша (удобно при медленной симуляции).

Запуск:  python3 tools/wasd_teleop.py [топик]   (по умолчанию /cmd_vel)
Тип сообщения (Twist или TwistStamped) определяется автоматически.
"""
import select
import sys
import termios
import tty

import rclpy
from geometry_msgs.msg import Twist, TwistStamped
from rclpy.node import Node

TOPIC = sys.argv[1] if len(sys.argv) > 1 else "/cmd_vel"
STEP_V, STEP_W, MAX_V, MAX_W = 0.2, 0.4, 1.0, 1.5


class WasdTeleop(Node):
    def __init__(self):
        super().__init__("wasd_teleop")
        types = dict(self.get_topic_names_and_types()).get(TOPIC, [])
        self.stamped = any("TwistStamped" in t for t in types)
        self.pub = self.create_publisher(TwistStamped if self.stamped else Twist, TOPIC, 10)
        self.vx = self.vy = self.wz = 0.0
        self.create_timer(0.1, self.send)          # 10 Гц

    def send(self):
        t = Twist()
        t.linear.x, t.linear.y, t.angular.z = self.vx, self.vy, self.wz
        if self.stamped:
            m = TwistStamped()
            m.header.stamp = self.get_clock().now().to_msg()
            m.twist = t
            self.pub.publish(m)
        else:
            self.pub.publish(t)


def clamp(v, m):
    return max(-m, min(m, v))


def main():
    rclpy.init()
    n = WasdTeleop()
    old = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())
    print(f"Топик: {TOPIC} ({'TwistStamped' if n.stamped else 'Twist'})")
    print("W/S: вперёд/назад   A/D: поворот   Q/E: боком   Пробел: стоп   X: выход")
    try:
        while rclpy.ok():
            rclpy.spin_once(n, timeout_sec=0.05)
            if not select.select([sys.stdin], [], [], 0)[0]:
                continue
            k = sys.stdin.read(1).lower()
            if k == "w":
                n.vx = clamp(n.vx + STEP_V, MAX_V)
            elif k == "s":
                n.vx = clamp(n.vx - STEP_V, MAX_V)
            elif k == "a":
                n.wz = clamp(n.wz + STEP_W, MAX_W)
            elif k == "d":
                n.wz = clamp(n.wz - STEP_W, MAX_W)
            elif k == "q":
                n.vy = clamp(n.vy + STEP_V, MAX_V)
            elif k == "e":
                n.vy = clamp(n.vy - STEP_V, MAX_V)
            elif k == " ":
                n.vx = n.vy = n.wz = 0.0
            elif k == "x":
                break
            subs = n.pub.get_subscription_count()
            print(f"\rvx={n.vx:+.1f} м/с  vy={n.vy:+.1f}  wz={n.wz:+.1f} рад/с  | подписчиков: {subs}   ",
                  end="", flush=True)
    finally:
        n.vx = n.vy = n.wz = 0.0
        n.send()                                   # робот останавливается при выходе
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
        n.destroy_node()
        rclpy.shutdown()
        print()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Локализация в симуляции: публикует TF world → map по «истинной» позе из Gazebo.

Дерево TF пакета Go2:  map →(статично, единичное) odom →(EKF CHAMP) base_footprint → base_link.
Одометрия шагающего робота накапливает ошибку, поэтому сверху добавляем кадр world
(= мир Gazebo, в нём же карта Nav2) и держим world → map таким, чтобы
world → base_link совпадало с /odom/ground_truth (плагин OdometryPublisher).

На реальном роботе этот узел заменяется AMCL / SLAM — Nav2 и маршрут не меняются.
Работает в 2D (x, y, yaw): наклоны корпуса при ходьбе не переносятся на карту.
"""
import math

import rclpy
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.time import Time
from tf2_ros import Buffer, TransformBroadcaster, TransformListener


def yaw_of(q):
    return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))


def compose(a, b):
    """(x, y, θ) ∘ (x, y, θ)"""
    c, s = math.cos(a[2]), math.sin(a[2])
    return (a[0] + c * b[0] - s * b[1], a[1] + s * b[0] + c * b[1], a[2] + b[2])


def inverse(a):
    c, s = math.cos(a[2]), math.sin(a[2])
    return (-c * a[0] - s * a[1], s * a[0] - c * a[1], -a[2])


class GtLocalizer(Node):
    def __init__(self):
        super().__init__("gt_localizer")
        self.declare_parameter("world_frame", "world")
        self.declare_parameter("map_frame", "map")
        self.declare_parameter("base_frame", "base_link")
        self.declare_parameter("future_dating", 0.2)            # как transform_tolerance у AMCL
        self.world = self.get_parameter("world_frame").value
        self.map = self.get_parameter("map_frame").value
        self.base = self.get_parameter("base_frame").value
        self.future = Duration(seconds=float(self.get_parameter("future_dating").value))
        self.buf = Buffer()
        TransformListener(self.buf, self)
        self.br = TransformBroadcaster(self)
        self.last = None
        self.warned = False
        self.create_subscription(Odometry, "/odom/ground_truth", self.on_gt, 10)
        self.create_timer(0.05, self.publish)                     # 20 Гц, даже если GT реже
        self.get_logger().info(f"{self.world} → {self.map} по /odom/ground_truth")

    def on_gt(self, msg):
        p = msg.pose.pose
        gt = (p.position.x, p.position.y, yaw_of(p.orientation))
        try:
            t = self.buf.lookup_transform(self.map, self.base, Time())
        except Exception as e:                                    # TF ещё не готово
            if not self.warned:
                self.get_logger().warn(f"жду TF {self.map}→{self.base}: {e}")
                self.warned = True
            return
        mb = (t.transform.translation.x, t.transform.translation.y, yaw_of(t.transform.rotation))
        self.last = compose(gt, inverse(mb))                      # world→map = world→base · (map→base)⁻¹

    def publish(self):
        if self.last is None:
            return
        x, y, th = self.last
        m = TransformStamped()
        m.header.stamp = (self.get_clock().now() + self.future).to_msg()
        m.header.frame_id = self.world
        m.child_frame_id = self.map
        m.transform.translation.x, m.transform.translation.y = x, y
        m.transform.rotation.z, m.transform.rotation.w = math.sin(th / 2), math.cos(th / 2)
        self.br.sendTransform(m)


def main():
    rclpy.init()
    node = GtLocalizer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()

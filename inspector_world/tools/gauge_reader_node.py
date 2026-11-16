#!/usr/bin/env python3
"""ROS 2 node that reads a gauge when the robot reaches a checkpoint."""

import argparse
import json
import os
import sys
import time
from dataclasses import asdict

import numpy as np
import rclpy
from PIL import Image, ImageDraw
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image as ImageMessage
from std_msgs.msg import String

from gauge_inference import GaugeInference


def message_to_pil(message: ImageMessage) -> Image.Image:
    channels = {
        "rgb8": 3,
        "bgr8": 3,
        "rgba8": 4,
        "bgra8": 4,
        "mono8": 1,
    }.get(message.encoding)
    if channels is None:
        raise ValueError("unsupported image encoding: %s" % message.encoding)
    raw = np.frombuffer(message.data, dtype=np.uint8)
    rows = raw.reshape(message.height, message.step)
    pixels = rows[:, : message.width * channels].reshape(
        message.height, message.width, channels
    )
    if message.encoding == "mono8":
        return Image.fromarray(pixels[:, :, 0], mode="L").convert("RGB")
    if message.encoding in ("bgr8", "bgra8"):
        pixels = pixels[:, :, [2, 1, 0] + ([3] if channels == 4 else [])]
    if channels == 4:
        pixels = pixels[:, :, :3]
    return Image.fromarray(pixels, mode="RGB")


def pil_to_message(image: Image.Image, source: ImageMessage) -> ImageMessage:
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    message = ImageMessage()
    message.header = source.header
    message.height, message.width = rgb.shape[:2]
    message.encoding = "rgb8"
    message.is_bigendian = False
    message.step = message.width * 3
    message.data = rgb.tobytes()
    return message


def annotate(image: Image.Image, payload: dict) -> Image.Image:
    output = image.copy()
    drawer = ImageDraw.Draw(output)
    box = tuple(payload["box"])
    color = "#25b34b" if payload["status"] == "OK" else "#e53935"
    drawer.rectangle(box, outline=color, width=5)
    label = "%s  %.3f %s  %s" % (
        payload["instrument_code"],
        payload["value"],
        payload["unit"],
        payload["status"],
    )
    drawer.rectangle(
        (box[0], max(0, box[1] - 24), box[0] + max(180, len(label) * 8), box[1]),
        fill=color,
    )
    drawer.text((box[0] + 4, max(0, box[1] - 20)), label, fill="white")
    return output


class GaugeReaderNode(Node):
    def __init__(self, args):
        super().__init__("gauge_reader")
        self.inference = GaugeInference(args.locator, args.reader, args.device)
        self.retake_threshold = args.retake_threshold
        self.output_dir = os.path.abspath(os.path.expanduser(args.output_dir))
        os.makedirs(self.output_dir, exist_ok=True)
        self.pending = None
        self.result_publisher = self.create_publisher(
            String, "/inspection/gauge_result", 10
        )
        self.image_publisher = self.create_publisher(
            ImageMessage, "/inspection/annotated_image", 10
        )
        self.create_subscription(
            String, "/inspection/mission_state", self.on_state, 10
        )
        self.create_subscription(
            ImageMessage, args.camera, self.on_image, qos_profile_sensor_data
        )
        self.get_logger().info(
            "Gauge reader ready: camera=%s, device=%s"
            % (args.camera, self.inference.device)
        )

    def on_state(self, message: String) -> None:
        try:
            state = json.loads(message.data)
        except json.JSONDecodeError:
            return
        if state.get("state") != "AT_INSTRUMENT":
            return
        instrument = state.get("instrument")
        if not instrument:
            self.get_logger().warning("checkpoint state has no instrument code")
            return
        self.pending = state
        self.get_logger().info(
            "Waiting for frame at %s/%s"
            % (state.get("checkpoint", "?"), instrument)
        )

    def on_image(self, message: ImageMessage) -> None:
        if self.pending is None:
            return
        checkpoint = self.pending
        self.pending = None
        stamp = time.strftime("%Y%m%d_%H%M%S")
        instrument = checkpoint["instrument"]
        source_path = os.path.join(
            self.output_dir,
            "%s_%s_%s_source.png"
            % (stamp, checkpoint.get("checkpoint", "CP"), instrument),
        )
        try:
            image = message_to_pil(message)
            image.save(source_path)
            reading = self.inference.predict(
                source_path, instrument, self.retake_threshold
            )
            payload = asdict(reading)
            payload.update(
                checkpoint=checkpoint.get("checkpoint"),
                station=checkpoint.get("station"),
                ros_stamp={
                    "sec": message.header.stamp.sec,
                    "nanosec": message.header.stamp.nanosec,
                },
            )
            annotated = annotate(image, payload)
            annotated_path = os.path.join(
                self.output_dir,
                "%s_%s_%s_result.png"
                % (stamp, checkpoint.get("checkpoint", "CP"), instrument),
            )
            annotated.save(annotated_path)
            payload["annotated_image_path"] = annotated_path
            self.image_publisher.publish(pil_to_message(annotated, message))
            self.result_publisher.publish(
                String(data=json.dumps(payload, ensure_ascii=False))
            )
            self.get_logger().info(
                "%s = %.3f %s, %s, confidence=%.1f%%"
                % (
                    instrument,
                    reading.value,
                    reading.unit,
                    reading.status,
                    reading.confidence * 100.0,
                )
            )
            if reading.needs_retake:
                self.get_logger().warning("Low confidence: another frame is required")
        except Exception as error:
            payload = {
                "checkpoint": checkpoint.get("checkpoint"),
                "station": checkpoint.get("station"),
                "instrument_code": instrument,
                "status": "ERROR",
                "error": str(error),
            }
            self.result_publisher.publish(
                String(data=json.dumps(payload, ensure_ascii=False))
            )
            self.get_logger().error("Gauge inference failed: %s" % error)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Live ROS 2 gauge reader")
    parser.add_argument("--locator", required=True)
    parser.add_argument("--reader", required=True)
    parser.add_argument("--camera", default="/rgb_image")
    parser.add_argument("--device", choices=("cpu", "cuda"))
    parser.add_argument("--retake-threshold", type=float, default=0.10)
    parser.add_argument("--output-dir", default="~/inspection_ai")
    args, ros_args = parser.parse_known_args()
    rclpy.init(args=ros_args)
    node = GaugeReaderNode(args)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()

#!/usr/bin/python3
"""Software-only ROS 2 image probe for the DENTOBOT SlicerROS2 bridge."""

import sys
import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image


HOST_TO_SLICER_TOPIC = "/dentobot/test/host_to_slicer_image"
SLICER_TO_HOST_TOPIC = "/dentobot/test/slicer_to_host_image"
HOST_IMAGE_DATA = bytes([11, 22, 33, 44, 55, 66])
SLICER_IMAGE_DATA = bytes([7] + [200] * 10 + [249])


class ImageProbe(Node):
    def __init__(self):
        super().__init__("dentobot_host_image_probe")
        self.received_valid_image = False
        self.publisher = self.create_publisher(Image, HOST_TO_SLICER_TOPIC, 10)
        self.subscription = self.create_subscription(
            Image, SLICER_TO_HOST_TOPIC, self.receive_image, 10
        )
        self.timer = self.create_timer(0.25, self.publish_image)

    def publish_image(self):
        message = Image()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = "synthetic_image_test"
        message.height = 2
        message.width = 3
        message.encoding = "mono8"
        message.is_bigendian = 0
        message.step = 3
        message.data = HOST_IMAGE_DATA
        self.publisher.publish(message)

    def receive_image(self, message):
        errors = []
        if message.height != 3 or message.width != 4:
            errors.append(
                f"dimensions were {message.width}x{message.height}, expected 4x3"
            )
        if message.encoding != "mono8":
            errors.append(f"encoding was {message.encoding!r}, expected 'mono8'")
        if message.step != 4:
            errors.append(f"step was {message.step}, expected 4")
        if bytes(message.data) != SLICER_IMAGE_DATA:
            errors.append("pixel payload did not match the Slicer test image")
        if errors:
            self.get_logger().error("; ".join(errors))
            return
        if not self.received_valid_image:
            self.get_logger().info(
                "received exact 4x3 mono8 synthetic image from SlicerROS2"
            )
            self.received_valid_image = True


def main():
    rclpy.init()
    node = ImageProbe()
    deadline = time.monotonic() + 60.0
    try:
        while time.monotonic() < deadline and not node.received_valid_image:
            rclpy.spin_once(node, timeout_sec=0.1)
        if not node.received_valid_image:
            node.get_logger().error("timed out waiting for the SlicerROS2 image")
            return 1
        # Keep publishing briefly after the return path is verified. This
        # gives the independently created Slicer subscriber time to complete
        # discovery and receive the host image before this node shuts down.
        linger_deadline = time.monotonic() + 3.0
        while time.monotonic() < linger_deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        return 0
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    sys.exit(main())

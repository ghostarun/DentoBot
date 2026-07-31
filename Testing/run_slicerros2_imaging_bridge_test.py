#!/usr/bin/env python3
"""Launch the DENTOBOT SlicerROS2 imaging bridge test like upstream CI."""

import base64
import subprocess
import sys


TEST_PATH = (
    "/workspace/ros2_ws/src/DentoBot/Testing/"
    "SlicerROS2ImagingBridgeTest.py"
)


def main():
    test_code = (
        f"exec(compile(open({TEST_PATH!r}).read(), "
        f"{TEST_PATH!r}, 'exec'))"
    )
    encoded = base64.b64encode(test_code.encode("utf-8")).decode("ascii")
    slicer_code = (
        "import base64; "
        f"exec(base64.b64decode('{encoded}').decode('utf-8'))"
    )
    command = [
        "ros2",
        "launch",
        "slicer_ros2_module",
        "slicer.launch.py",
        f'slicer_args:=--no-main-window --python-code "{slicer_code}"',
    ]
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())

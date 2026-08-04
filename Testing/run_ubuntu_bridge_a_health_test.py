#!/usr/bin/env python3
"""Launch the Ubuntu Bridge A health test in headless Slicer."""

import base64
import subprocess
import sys


TEST_PATH = (
    "/workspace/ros2_ws/src/DentoBot/Testing/"
    "UbuntuBridgeAHealthTest.py"
)
MODULE_PATH = "/workspace/ros2_ws/src/DentoBot/DENTOWorkflow"
SLICER_EXECUTABLE = "/opt/slicer/Slicer-SuperBuild/Slicer-build/Slicer"


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
        SLICER_EXECUTABLE,
        "--no-main-window",
        "--additional-module-paths",
        MODULE_PATH,
        "--python-code",
        slicer_code,
    ]
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())

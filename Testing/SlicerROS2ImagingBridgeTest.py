"""Headless, software-only MRML image bridge test for SlicerROS2."""

import json
import sys
import time
import traceback

import slicer
import vtk


HOST_TO_SLICER_TOPIC = "/dentobot/test/host_to_slicer_image"
SLICER_TO_HOST_TOPIC = "/dentobot/test/slicer_to_host_image"
EXPECTED_HOST_DATA = [11, 22, 33, 44, 55, 66]


def spin(ros_logic, iterations=10):
    for _ in range(iterations):
        slicer.app.processEvents()
        ros_logic.Spin()
        time.sleep(0.01)


def create_synthetic_output():
    image = vtk.vtkImageData()
    image.SetDimensions(4, 3, 1)
    image.AllocateScalars(vtk.VTK_UNSIGNED_CHAR, 1)
    scalars = image.GetPointData().GetScalars()
    scalars.Fill(200)
    scalars.SetValue(0, 7)
    scalars.SetValue(11, 249)
    return image


def run_test():
    ros_logic = slicer.util.getModuleLogic("ROS2")
    if ros_logic is None:
        raise RuntimeError("SlicerROS2 module logic is unavailable")

    ros_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLROS2NodeNode")
    if ros_node is None:
        raise RuntimeError("failed to create the SlicerROS2 node")
    ros_node.Create("dentobot_slicer_image_probe")

    volume = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLScalarVolumeNode", "SyntheticHostImage"
    )
    subscriber = ros_node.CreateAndAddSubscriberNode(
        "Image", HOST_TO_SLICER_TOPIC
    )
    publisher = ros_node.CreateAndAddPublisherNode(
        "Image", SLICER_TO_HOST_TOPIC
    )
    if subscriber is None or publisher is None:
        raise RuntimeError("failed to create SlicerROS2 image endpoints")
    subscriber.SetTargetNodeID(volume.GetID())

    output_image = create_synthetic_output()
    print(
        json.dumps(
            {
                "event": "ready",
                "host_to_slicer_topic": HOST_TO_SLICER_TOPIC,
                "slicer_to_host_topic": SLICER_TO_HOST_TOPIC,
            }
        ),
        flush=True,
    )

    deadline = time.monotonic() + 35.0
    next_publish = 0.0
    while time.monotonic() < deadline:
        now = time.monotonic()
        if now >= next_publish:
            publisher.Publish(output_image)
            next_publish = now + 0.25
        spin(ros_logic)
        if subscriber.GetNumberOfMessages() > 0:
            break
    else:
        raise TimeoutError("timed out waiting for the host ROS image")

    received = volume.GetImageData()
    if received is None:
        raise AssertionError("target MRML volume has no image data")
    dimensions = tuple(received.GetDimensions())
    if dimensions != (3, 2, 1):
        raise AssertionError(f"received dimensions {dimensions}, expected (3, 2, 1)")
    scalars = received.GetPointData().GetScalars()
    values = [int(scalars.GetValue(index)) for index in range(6)]
    if values != EXPECTED_HOST_DATA:
        raise AssertionError(
            f"received pixels {values}, expected {EXPECTED_HOST_DATA}"
        )

    # Continue publishing briefly so the host probe can complete after this
    # process has validated its incoming MRML volume.
    for _ in range(12):
        publisher.Publish(output_image)
        spin(ros_logic, 5)

    result = {
        "event": "passed",
        "host_to_slicer": {
            "dimensions": list(dimensions),
            "encoding": "mono8",
            "pixels": values,
        },
        "slicer_to_host": {
            "dimensions": [4, 3, 1],
            "encoding": "mono8",
            "first_pixel": 7,
            "last_pixel": 249,
        },
    }
    ros_node.RemoveAndDeletePublisherNode(SLICER_TO_HOST_TOPIC)
    ros_node.RemoveAndDeleteSubscriberNode(HOST_TO_SLICER_TOPIC)
    slicer.mrmlScene.RemoveNode(volume)
    ros_node.Destroy()
    spin(ros_logic)
    return result


exit_code = 1
try:
    print(json.dumps(run_test()), flush=True)
    exit_code = 0
except Exception as error:
    print(
        json.dumps(
            {
                "event": "failed",
                "error_type": type(error).__name__,
                "message": str(error),
            }
        ),
        flush=True,
    )
    traceback.print_exc()
finally:
    vtk.vtkDebugLeaks.SetExitError(False)
    slicer.app.quit()
    sys.exit(exit_code)

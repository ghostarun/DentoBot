"""World-RAS geometry boundary for independent Step 6 audits.

Copies source geometry and applies the complete parent chain (including nonlinear
transforms). Does not harden nodes, modify source meshes or apply an extra jaw
opening; unparented closed-source lower anatomy is opened by its owning caller.
"""
from __future__ import annotations


def _world_copy(polydata, node):
    import vtk

    copied = vtk.vtkPolyData()
    copied.DeepCopy(polydata)
    parent = node.GetParentTransformNode()
    if parent is None:
        return copied
    transform = vtk.vtkGeneralTransform()
    parent.GetTransformToWorld(transform)
    transformed = vtk.vtkTransformPolyDataFilter()
    transformed.SetInputData(copied)
    transformed.SetTransform(transform)
    transformed.Update()
    result = vtk.vtkPolyData()
    result.DeepCopy(transformed.GetOutput())
    return result


def model_world_polydata(model):
    """Detached model surface in world RAS mm, with all parent transforms."""
    if model is None or model.GetPolyData() is None:
        raise ValueError("Model geometry is unavailable.")
    return _world_copy(model.GetPolyData(), model)


def segment_world_polydata(segmentation_node, segment_id):
    """Detached closed segment surface in world RAS mm; no raw internal read."""
    import vtk

    if segmentation_node is None or not str(segment_id or ""):
        raise ValueError("A segmentation and explicit segment ID are required.")
    segmentation_node.CreateClosedSurfaceRepresentation()
    surface = vtk.vtkPolyData()
    if (not segmentation_node.GetClosedSurfaceRepresentation(str(segment_id), surface)
            or surface.GetNumberOfPoints() == 0 or surface.GetNumberOfCells() == 0):
        raise ValueError(f"Segment {segment_id} has no usable closed surface.")
    return _world_copy(surface, segmentation_node)

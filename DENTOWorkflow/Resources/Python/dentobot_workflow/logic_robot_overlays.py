"""Display-only Step 6 overlays (task-space box, view frame, depth peeling); public APIs remain on RobotLogicMixin."""

from __future__ import annotations

from .runtime import *


class RobotOverlayLogicMixin:
    TASK_SPACE_BOX_ROLE = "Step6TaskSpaceBox"
    TASK_SPACE_BOX_MAX_OPACITY = 0.30  # operator 2026-10-04: no use above 30 %
    TASK_SPACE_BOX_MODEL_NAME = "[Step 6] Task-Space Box (incisor-centred, display only)"

    def updateStep6TaskSpaceBox(self, center_world_ras_mm, side_mm: float, opacity: float,
                                visible: bool) -> None:
        """Optional cube around the incisor-centred task space (operator 2026-10-03).

        Display only: it neither bounds sampling nor enters the MoveIt scene. Cool
        blue with edges so it stays distinct from the rose mouth barrier.
        """
        node = next((n for n in slicer.util.getNodesByClass("vtkMRMLModelNode")
                     if n.GetAttribute("DENTOBOT.ModelRole") == self.TASK_SPACE_BOX_ROLE), None)
        if not visible or center_world_ras_mm is None:
            if node is not None and node.GetDisplayNode():
                node.GetDisplayNode().SetVisibility(False)
            return
        side = float(side_mm)
        if not side > 0.0:
            raise ValueError("Task-space box side length must be positive.")
        cube = vtk.vtkCubeSource()
        cube.SetCenter(*(float(value) for value in center_world_ras_mm))
        cube.SetXLength(side)
        cube.SetYLength(side)
        cube.SetZLength(side)
        cube.Update()
        if node is None:
            node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", self.TASK_SPACE_BOX_MODEL_NAME)
            node.SetAttribute("DENTOBOT.ModelRole", self.TASK_SPACE_BOX_ROLE)
            node.SaveWithSceneOff()
        surface = vtk.vtkPolyData()
        surface.DeepCopy(cube.GetOutput())
        node.SetAndObservePolyData(surface)
        node.CreateDefaultDisplayNodes()
        display = node.GetDisplayNode()
        display.SetColor(0.20, 0.55, 1.0)
        display.SetEdgeVisibility(True)
        display.SetEdgeColor(0.35, 0.70, 1.0)
        opacity = min(self.TASK_SPACE_BOX_MAX_OPACITY, max(0.0, float(opacity)))
        # View presets restore this instead of their solid default (as for the barrier).
        node.SetAttribute("DENTOBOT.DisplayOpacity", f"{opacity:.2f}")
        display.SetOpacity(opacity)
        display.SetVisibility2D(False)
        display.SetVisibility(True)

    def step6TaskSpaceBoxExists(self) -> bool:
        """Whether the display model exists, shown or hidden by a view preset."""
        return any(n.GetAttribute("DENTOBOT.ModelRole") == self.TASK_SPACE_BOX_ROLE
                   for n in slicer.util.getNodesByClass("vtkMRMLModelNode"))

    def step6TaskSpaceBoxShown(self) -> bool:
        return any(n.GetAttribute("DENTOBOT.ModelRole") == self.TASK_SPACE_BOX_ROLE
                   and n.GetDisplayNode() is not None and bool(n.GetDisplayNode().GetVisibility())
                   for n in slicer.util.getNodesByClass("vtkMRMLModelNode"))

    @staticmethod
    def setStep6ViewFrameBoxVisible(visible: bool) -> None:
        """Slicer's magenta 3D-view frame box (not task space); hidden in Step 6."""
        for view_node in slicer.util.getNodesByClass("vtkMRMLViewNode"):
            if bool(view_node.GetBoxVisible()) != bool(visible):
                view_node.SetBoxVisible(bool(visible))

    @staticmethod
    def setStep6DepthPeeling(enabled: bool) -> None:
        """3D-view depth peeling (display only; operator run option 2026-10-03)."""
        for view_node in slicer.util.getNodesByClass("vtkMRMLViewNode"):
            if bool(view_node.GetUseDepthPeeling()) != bool(enabled):
                view_node.SetUseDepthPeeling(bool(enabled))

    @staticmethod
    def step6DepthPeelingEnabled() -> bool:
        views = slicer.util.getNodesByClass("vtkMRMLViewNode")
        return all(bool(view_node.GetUseDepthPeeling()) for view_node in views) if views else True

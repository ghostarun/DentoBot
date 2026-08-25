"""Extracted parameter node and matrix conversion methods; public APIs remain on DENTOWorkflowLogic."""

from __future__ import annotations

from .runtime import *


class CoreLogicMixin:
    def getParameterNode(self) -> DENTOWorkflowParameterNode:
        return DENTOWorkflowParameterNode(super().getParameterNode())

    @staticmethod
    def _numpyFromVtkMatrix(matrix: vtk.vtkMatrix4x4) -> np.ndarray:
        return np.asarray(
            [
                [matrix.GetElement(row, column) for column in range(4)]
                for row in range(4)
            ],
            dtype=float,
        )

    @staticmethod
    def _vtkFromNumpyMatrix(matrix: np.ndarray) -> vtk.vtkMatrix4x4:
        result = vtk.vtkMatrix4x4()
        for row, values in enumerate(vtk_matrix_elements(matrix)):
            for column, value in enumerate(values):
                result.SetElement(row, column, value)
        return result

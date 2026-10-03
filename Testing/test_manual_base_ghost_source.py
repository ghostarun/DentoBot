import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "DENTOWorkflow/Resources/Python/dentobot_workflow/logic_robot_placement.py"


class FakeMatrix:
    def __init__(self):
        self.values = np.eye(4)

    def DeepCopy(self, other):
        self.values = other.values.copy()

    def SetElement(self, row, column, value):
        self.values[row, column] = value


class FakePolyData:
    def __init__(self, points=None, cells=None):
        self.points = list(points or [(1.0, 2.0, 3.0)])
        self.cells = list(cells or [(0, 0, 0)])

    def DeepCopy(self, other):
        self.points = list(other.points)
        self.cells = list(other.cells)

    def GetNumberOfPoints(self):
        return len(self.points)

    def GetNumberOfCells(self):
        return len(self.cells)


class FakeNode:
    next_id = 0

    def __init__(self, class_name, name, scene, polydata=None):
        FakeNode.next_id += 1
        self.class_name = class_name
        self.name = name
        self.scene = scene
        self.node_id = f"node-{FakeNode.next_id}"
        self.attributes = {}
        self.polydata = polydata
        self.display = None
        self.matrix = FakeMatrix()
        self.parent_id = None
        self.saved_with_scene = True
        self.hidden_from_editors = False

    def GetID(self):
        return self.node_id

    def IsA(self, class_name):
        return self.class_name == class_name

    def SetAttribute(self, name, value):
        self.attributes[name] = value

    def GetAttribute(self, name):
        return self.attributes.get(name)

    def SetSaveWithScene(self, value):
        self.saved_with_scene = value

    def SetHideFromEditors(self, value):
        self.hidden_from_editors = value

    def GetPolyData(self):
        return self.polydata

    def SetAndObservePolyData(self, polydata):
        self.polydata = polydata

    def GetTransformNodeID(self):
        return self.parent_id

    def SetAndObserveTransformNodeID(self, node_id):
        self.parent_id = node_id

    def GetMatrixTransformToParent(self, matrix):
        matrix.DeepCopy(self.matrix)

    def SetMatrixTransformToParent(self, matrix):
        self.matrix.DeepCopy(matrix)

    def CreateDefaultDisplayNodes(self):
        self.display = self.scene.AddNewNodeByClass(
            "vtkMRMLModelDisplayNode", f"{self.name} Display"
        )

    def GetDisplayNode(self):
        return self.display

    def SetVisibility(self, value):
        self.visible = value

    def SetColor(self, *color):
        self.color = tuple(color)

    def SetOpacity(self, value):
        self.opacity = value


class FakeScene:
    def __init__(self):
        self.nodes = []

    def AddNewNodeByClass(self, class_name, name):
        node = FakeNode(class_name, name, self)
        self.nodes.append(node)
        return node

    def IsNodePresent(self, node):
        return node in self.nodes

    def GetNodeByID(self, node_id):
        return next((node for node in self.nodes if node.GetID() == node_id), None)

    def RemoveNode(self, node):
        if node in self.nodes:
            self.nodes.remove(node)


class FakeSlicerUtil:
    def __init__(self, scene):
        self.scene = scene

    def getNodesByClass(self, class_name):
        return [node for node in self.scene.nodes if node.class_name == class_name]


class ManualBaseGhostSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source_tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        placement = next(
            node
            for node in source_tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "RobotPlacementLogicMixin"
        )
        selected = [
            node
            for node in placement.body
            if isinstance(node, ast.FunctionDef)
            and node.name
            in {
                "clearManualBaseCandidateGhost",
                "isRobotBaseTransformNode",
                "manualBaseCandidateTransformNode",
                "setManualBaseCandidateInteractionEnabled",
                "showManualBaseCandidateGhost",
            }
        ]
        isolated_class = ast.ClassDef(
            name="GhostMethods",
            bases=[],
            keywords=[],
            body=[
                ast.Assign(
                    targets=[ast.Name(id="ROBOT_BASE_ROLE", ctx=ast.Store())],
                    value=ast.Constant(value="RobotBase"),
                ),
                *selected,
            ],
            decorator_list=[],
        )
        module = ast.fix_missing_locations(
            ast.Module(body=[isolated_class], type_ignores=[])
        )
        cls.scene = FakeScene()
        cls.slicer = SimpleNamespace(
            mrmlScene=cls.scene, util=FakeSlicerUtil(cls.scene)
        )
        cls.namespace = {
            "np": np,
            "slicer": cls.slicer,
            "vtk": SimpleNamespace(vtkMatrix4x4=FakeMatrix, vtkPolyData=FakePolyData),
            "_": lambda message: message,
        }
        exec(compile(module, str(SOURCE), "exec"), cls.namespace)

    def setUp(self):
        self.scene.nodes.clear()
        self.models = []
        self.transforms = []
        self.base = self.scene.AddNewNodeByClass(
            "vtkMRMLLinearTransformNode", "accepted robot Base"
        )
        self.base.SetAttribute("DENTOBOT.TransformRole", "RobotBase")
        for index in range(7):
            name = f"link-{index}"
            transform = self.scene.AddNewNodeByClass(
                "vtkMRMLLinearTransformNode", f"source {name} pose"
            )
            transform.SetAttribute("DENTOBOT.RobotLinkName", name)
            transform.SetAndObserveTransformNodeID(self.base.GetID())
            transform.matrix.values[0, 3] = float(index)
            self.transforms.append(transform)

            model = self.scene.AddNewNodeByClass(
                "vtkMRMLModelNode", f"source {name}"
            )
            model.SetAttribute("DENTOBOT.RobotLinkName", name)
            model.polydata = FakePolyData(points=[(index, 2.0, 3.0)])
            model.SetAndObserveTransformNodeID(transform.GetID())
            self.models.append(model)

        self.unrelated_model = self.scene.AddNewNodeByClass(
            "vtkMRMLModelNode", "unrelated model"
        )
        self.unrelated_transform = self.scene.AddNewNodeByClass(
            "vtkMRMLLinearTransformNode", "unrelated transform"
        )

        methods = self.namespace["GhostMethods"]
        models, transforms = self.models, self.transforms

        class Logic(methods):
            def robotModelNodes(self):
                return models

            def robotLinkTransformNodes(self):
                return transforms

            @staticmethod
            def _vtkFromNumpyMatrix(matrix):
                result = FakeMatrix()
                result.values = np.asarray(matrix, dtype=float).copy()
                return result

        self.logic = Logic()

    def owned_nodes(self):
        return [
            node
            for node in self.scene.nodes
            if node.GetAttribute("DENTOBOT.ManualBaseCandidateGhost") == "true"
        ]

    def test_preview_is_an_owned_copy_and_cleanup_preserves_sources(self):
        source_geometry = [model.GetPolyData() for model in self.models]
        source_points = [list(model.GetPolyData().points) for model in self.models]
        source_matrices = [transform.matrix.values.copy() for transform in self.transforms]
        candidate = np.eye(4)
        candidate[:3, 3] = (12.0, -4.0, 8.0)

        ok, message = self.logic.showManualBaseCandidateGhost(candidate.reshape(-1).tolist())

        self.assertTrue(ok, message)
        owned = self.owned_nodes()
        ghost_models = [node for node in owned if node.class_name == "vtkMRMLModelNode"]
        ghost_transforms = [
            node for node in owned if node.class_name == "vtkMRMLLinearTransformNode"
        ]
        ghost_displays = [
            node for node in owned if node.class_name == "vtkMRMLModelDisplayNode"
        ]
        self.assertEqual((len(ghost_models), len(ghost_transforms), len(ghost_displays)), (7, 8, 7))
        for node in owned:
            self.assertFalse(node.saved_with_scene)
            # The detached candidate Base stays editor-visible for its drag handles.
            candidate_role = node.GetAttribute("DENTOBOT.ManualBaseCandidateGhostNodeType")
            self.assertEqual(node.hidden_from_editors, candidate_role != "CandidateBase")
        for node in ghost_models:
            self.assertIsNone(node.GetAttribute("DENTOBOT.ModelRole"))
        for node in ghost_transforms:
            self.assertIsNone(node.GetAttribute("DENTOBOT.TransformRole"))
        candidate_base = next(
            node
            for node in ghost_transforms
            if node.GetAttribute("DENTOBOT.ManualBaseCandidateGhostNodeType")
            == "CandidateBase"
        )
        np.testing.assert_array_equal(candidate_base.matrix.values, candidate)
        ghost_link_transforms = [
            node
            for node in ghost_transforms
            if node is not candidate_base
        ]
        for source, ghost in zip(self.transforms, ghost_link_transforms):
            np.testing.assert_array_equal(ghost.matrix.values, source.matrix.values)
            self.assertEqual(ghost.parent_id, candidate_base.GetID())
        for model, ghost_transform in zip(ghost_models, ghost_link_transforms):
            self.assertEqual(model.parent_id, ghost_transform.GetID())
        for index, ghost_model in enumerate(ghost_models):
            self.assertIsNot(ghost_model.GetPolyData(), source_geometry[index])
            self.assertEqual(ghost_model.GetPolyData().points, source_points[index])
            self.assertFalse(ghost_model.saved_with_scene)
            self.assertTrue(ghost_model.hidden_from_editors)
            self.assertEqual(ghost_model.display.color, (0.0, 1.0, 1.0))
            self.assertEqual(ghost_model.display.opacity, 0.25)
            self.assertFalse(ghost_model.display.saved_with_scene)
            self.assertTrue(ghost_model.display.hidden_from_editors)
        for source, matrix in zip(self.transforms, source_matrices):
            np.testing.assert_array_equal(source.matrix.values, matrix)
        for source, points in zip(self.models, source_points):
            self.assertEqual(source.GetPolyData().points, points)

        self.logic.clearManualBaseCandidateGhost()

        self.assertEqual(self.owned_nodes(), [])
        self.assertIn(self.unrelated_model, self.scene.nodes)
        self.assertIn(self.unrelated_transform, self.scene.nodes)
        for source in [*self.models, *self.transforms]:
            self.assertIn(source, self.scene.nodes)

    def test_invalid_affine_clears_old_preview(self):
        self.assertTrue(self.logic.showManualBaseCandidateGhost(np.eye(4))[0])

        for invalid in ([0.0] * 15, [float("nan")] + [0.0] * 15, [0.0] * 16):
            ok, _ = self.logic.showManualBaseCandidateGhost(invalid)
            self.assertFalse(ok)
            self.assertEqual(self.owned_nodes(), [])

    def test_missing_local_geometry_returns_false_without_ghost(self):
        self.models[3].polydata = None

        ok, _ = self.logic.showManualBaseCandidateGhost(np.eye(4))

        self.assertFalse(ok)
        self.assertEqual(self.owned_nodes(), [])
        self.assertIn(self.models[3], self.scene.nodes)

    def test_shared_unrelated_parent_is_not_accepted_as_robot_base(self):
        self.transforms[0].SetAndObserveTransformNodeID(self.unrelated_transform.GetID())
        ok, _ = self.logic.showManualBaseCandidateGhost(np.eye(4))
        self.assertFalse(ok)
        self.assertEqual(self.owned_nodes(), [])

        for transform in self.transforms:
            transform.SetAndObserveTransformNodeID(self.unrelated_transform.GetID())

        ok, _ = self.logic.showManualBaseCandidateGhost(np.eye(4))

        self.assertFalse(ok)
        self.assertEqual(self.owned_nodes(), [])


if __name__ == "__main__":
    unittest.main()

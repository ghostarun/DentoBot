import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "DENTOWorkflow/Resources/Python"


def function_node(path, name, class_name=None):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    parent = tree
    if class_name:
        parent = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        )
    return next(
        node
        for node in parent.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )


def calls_named(node, name):
    return [
        child
        for child in ast.walk(node)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Name)
        and child.func.id == name
    ]


def render_pause_finally_blocks(node):
    blocks = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Try) or not child.finalbody:
            continue
        final = ast.Module(body=child.finalbody, type_ignores=[])
        if calls_named(ast.Module(body=child.body, type_ignores=[]), "pause_render") and calls_named(
            final, "resume_render"
        ) and any(
            isinstance(item, ast.Name) and item.id == "rendering_paused"
            for item in ast.walk(final)
        ):
            blocks.append(child)
    return blocks


class Step6ConnectRenderSourceTest(unittest.TestCase):
    def test_connect_publish_and_teardown_resume_render_in_finally(self):
        bridge = PYTHON / "DENTOROS2Bridge.py"
        collision_sync = function_node(
            PYTHON / "dentobot_workflow/logic_robot_scene_sync.py",
            "syncStep6MoveItPlanningScene",
            "RobotSceneSyncLogicMixin",
        )
        connect = function_node(bridge, "connect_dentobot_motion_control")
        disconnect = function_node(bridge, "disconnect_dentobot_motion_control")

        self.assertEqual(len(render_pause_finally_blocks(connect)), 1)
        self.assertEqual(len(render_pause_finally_blocks(collision_sync)), 1)
        self.assertEqual(len(render_pause_finally_blocks(disconnect)), 2)

    def test_connect_keeps_scene_ack_identity_and_restores_widget_refresh(self):
        collision_sync = function_node(
            PYTHON / "dentobot_workflow/logic_robot_scene_sync.py",
            "syncStep6MoveItPlanningScene",
            "RobotSceneSyncLogicMixin",
        )
        constants = {
            node.value
            for node in ast.walk(collision_sync)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        names = {
            node.id for node in ast.walk(collision_sync) if isinstance(node, ast.Name)
        }
        self.assertIn("source_id", constants)
        self.assertIn("outgoing_collision_object_id", constants)
        self.assertIn("NotQueried", constants)
        self.assertIn("Publishing collision scene", constants)
        self.assertIn("sources", names)
        self.assertIn("sourceIndex", names)
        self.assertIn("acknowledge_moveit_collision_scene", names)
        self.assertIn("expected_policy_fingerprint", names)
        self.assertIn("require_correlated_readback", names)
        self.assertIn("robotBaseFingerprint", {node.attr for node in ast.walk(collision_sync) if isinstance(node, ast.Attribute)})

        connect_ui = function_node(
            PYTHON / "dentobot_workflow/widget_robot_shell.py",
            "_onShellConnectRobot",
            "RobotShellWidgetMixin",
        )
        refresh_restored = False
        for child in ast.walk(connect_ui):
            if not isinstance(child, ast.Try) or not child.finalbody:
                continue
            final = ast.Module(body=child.finalbody, type_ignores=[])
            attributes = {
                node.attr
                for node in ast.walk(final)
                if isinstance(node, ast.Attribute)
            }
            names = {
                node.id for node in ast.walk(final) if isinstance(node, ast.Name)
            }
            if (
                "_suppressParameterRefreshDuringRobotConnect" in attributes
                and "wasSuppressingParameterRefresh" in names
            ):
                refresh_restored = True
                break
        self.assertTrue(refresh_restored)


if __name__ == "__main__":
    unittest.main()

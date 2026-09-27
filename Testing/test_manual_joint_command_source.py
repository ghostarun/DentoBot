from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ManualJointCommandSourceTest(unittest.TestCase):
    def test_manual_protocol_is_separate_and_fail_closed(self):
        source = (ROOT / "dentobot_moveit_config/src/collision_guard.cpp").read_text(
            encoding="utf-8"
        )
        parser = source.split("bool parse_manual_joint_command(", 1)[1].split(
            "struct TaskGuardConfig", 1
        )[0]
        command_model = source.split("struct ManualJointCommand", 1)[1].split(
            "bool parse_manual_joint_command", 1
        )[0]
        callback = source.split("void on_manual_command(", 1)[1].split(
            "bool parse_task_config(", 1
        )[0]
        status = source.split("std::string status_json(", 1)[1].split(
            "void publish_task_status(", 1
        )[0]

        self.assertIn('"dentobot.manual_joint_command.v1"', source)
        self.assertIn('"dentobot.manual_joint_status.v1"', source)
        self.assertIn('"raw_planning_scene_acm_transition_v1"', source)
        self.assertIn('"/dentobot/manual_joint_command"', source)
        self.assertIn('"/dentobot/manual_joint_status"', source)
        for field in ("schema", "mode", "policy_id", "request_id", "session_id"):
            self.assertIn(f'"{field}"', parser)
        self.assertIn('"simulation_only"', parser)
        self.assertIn('"joint_positions"', parser)
        self.assertIn("command.joint_positions.size() == 5", parser)
        self.assertIn('json_string_field(document, "operation", command.operation)', parser)
        self.assertIn('command.operation == "jog" || command.operation == "state_query"', parser)
        self.assertIn('return malformed("operation")', parser)
        self.assertNotIn('!document.isMember("operation")', parser)
        self.assertNotIn('operation{ "jog" }', command_model)
        self.assertIn("std::isfinite(value)", source)

        rejected = callback.split("if (!command_valid)", 1)[1].split("else if", 1)[0]
        query = callback.split('command.operation == "state_query"', 1)[1].split(
            "else", 1
        )[0]
        jog = callback.split("else\n    {", 1)[1].split("last_status_json_", 1)[0]
        self.assertIn("parse_manual_joint_command", callback)
        self.assertIn("result.reason = reason", rejected)
        self.assertNotIn("validate_motion", rejected)
        self.assertNotIn("last_accepted_positions_ =", rejected)
        self.assertNotIn("publish_accepted", rejected)
        self.assertIn(
            "validate_motion(\n        last_accepted_positions_, last_accepted_positions_", query
        )
        self.assertIn("std::numeric_limits<double>::quiet_NaN(), true", query)
        self.assertNotIn("command.joint_positions", query)
        self.assertNotIn("last_accepted_positions_ =", query)
        self.assertNotIn("publish_accepted", query)
        self.assertIn("validate_motion(last_accepted_positions_, command.joint_positions)", jog)
        self.assertIn("last_accepted_positions_ = command.joint_positions", jog)
        self.assertIn("publish_accepted(last_accepted_positions_)", jog)
        self.assertEqual(callback.count("manual_status_publisher_->publish(status);"), 1)
        self.assertNotIn("publish_last_status();", callback)
        self.assertIn(r'\"command_valid\"', status)
        self.assertIn("manual_command->request_id", status)
        self.assertIn("manual_command->session_id", status)
        self.assertIn("<< MANUAL_POLICY_ID", status)
        self.assertIn(r'\"policy_id\"', status)
        self.assertNotIn("manual_command->policy_id", status)
        self.assertIn(r'\"operation\"', status)
        self.assertIn(r'\"query_only\"', status)


if __name__ == "__main__":
    unittest.main()

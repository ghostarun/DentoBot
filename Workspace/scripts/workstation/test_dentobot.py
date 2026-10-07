import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dentobot


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / "commands.json"
        self.data = {"active_machine": "B", "machines": {
            "B": {"host": None, "repo": "/active/repo", "expected_sha": "a" * 40,
                  "image_id": "sha256:" + "b" * 64},
            "A": {"host": "dentobot-a"}}}
        dentobot.write_config(self.config, self.data)
        self.args = ["--config", str(self.config)]

    def test_return_transfer_uses_active_checkout_without_committing(self):
        with patch.object(dentobot.handoff, "main", return_value=0) as run:
            code = dentobot.main([*self.args, "to-a", "--note", "Continue from B"])
        self.assertEqual(code, 0)
        self.assertEqual(run.call_args.args[0], [*self.args, "prepare", "--source", "B",
                                               "--destination", "A", "--note", "Continue from B"])
        self.assertEqual(dentobot.read_config(self.config), self.data)

    def test_selecting_other_origin_does_not_change_configuration(self):
        states = [{"branch": "feature", "origin": "other", "sha": "c" * 40},
                  {"origin": "dentobot"}]
        with patch.object(dentobot.handoff, "collect", side_effect=states), \
             contextlib.redirect_stderr(io.StringIO()):
            code = dentobot.main([*self.args, "use", "/other/repo"])
        self.assertEqual(code, 2)
        self.assertEqual(dentobot.read_config(self.config), self.data)

    def test_check_uses_saved_pin_until_explicitly_overridden(self):
        with patch.object(dentobot.handoff, "main", return_value=2) as run:
            code = dentobot.main([*self.args, "check"])
        self.assertEqual(code, 2)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--expected-sha") + 1], "a" * 40)
        self.assertEqual(command[command.index("--image-id") + 1], "sha256:" + "b" * 64)

    def test_remote_active_machine_is_refused(self):
        self.data["machines"]["B"]["host"] = "remote"
        dentobot.write_config(self.config, self.data)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(dentobot.main([*self.args, "open"]), 2)


if __name__ == "__main__":
    unittest.main()


class LaunchTests(unittest.TestCase):
    def setUp(self):
        CommandTests.setUp(self)
        self.repo = Path(self.temp.name) / 'repo'
        (self.repo / 'Workspace').mkdir(parents=True)
        (self.repo / 'Workspace/runtime-lock.json').write_text('{}')
        self.data['machines']['B']['repo'] = str(self.repo)
        dentobot.write_config(self.config, self.data)

    def test_launch_uses_selected_checkout_and_preserves_installed_runtime(self):
        state = {'dirty': False, 'sha': 'a' * 40}
        with patch.object(dentobot.handoff, 'collect', return_value=state), \
             patch.object(dentobot.subprocess, 'run', return_value=type('Result', (), {'returncode': 0})()) as run:
            self.assertEqual(dentobot.main([*self.args, 'launch', '--check-only']), 0)
        self.assertEqual(run.call_args.args[0], ['bash', str(self.repo / 'Workspace/scripts/launch-dentoworkflow.bash'),
                                                '--use-installed-runtime', '--check-only'])

    def test_uncommitted_source_cannot_launch_as_a_pinned_checkpoint(self):
        with patch.object(dentobot.handoff, 'collect', return_value={'dirty': True, 'sha': 'a' * 40}), \
             patch.object(dentobot.subprocess, 'run') as run, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(dentobot.main([*self.args, 'launch']), 2)
        run.assert_not_called()

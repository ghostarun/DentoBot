import argparse
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


class VisibleCaseCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / 'commands.json'
        dentobot.write_config(self.config, {'active_machine': 'B', 'machines': {
            'B': {'host': None, 'repo': '/active/repo'}, 'A': {'host': 'dentobot-a'}}})
        self.args = ['--config', str(self.config)]

    def test_parser_accepts_the_four_visible_case_subcommands(self):
        sha = 'a' * 40
        run_id = '20261008T122000Z'
        parser = dentobot.parser()
        run = parser.parse_args(['visible-case', 'run', '--case', 'Cases/a.dentocase', '--sha', sha,
                                 '--run-id', run_id, '--detach'])
        self.assertEqual((run.command, run.visible_case_command, run.detach), ('visible-case', 'run', True))
        status = parser.parse_args(['visible-case', 'status', '--run-id', run_id])
        self.assertEqual(status.visible_case_command, 'status')
        request = parser.parse_args(['visible-case', 'request', '--case', 'Cases/a.dentocase', '--repo', '/x',
                                     '--no-wait', '--poll-interval', '5', '--max-wait', '60'])
        self.assertEqual((request.repo, request.no_wait, request.poll_interval, request.max_wait),
                         ('/x', True, 5, 60))
        collect = parser.parse_args(['visible-case', 'collect', '--run-id', run_id, '--accept-incomplete'])
        self.assertTrue(collect.accept_incomplete)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            parser.parse_args(['visible-case', 'request', '--case', 'Cases/a.dentocase', '--sha', sha,
                               '--repo', '/x'])

    def test_main_routes_visible_case_to_the_module_handler(self):
        with patch.object(dentobot.visible_case, 'cmd_status', return_value=0) as handler:
            self.assertEqual(dentobot.main([*self.args, 'visible-case', 'status', '--run-id',
                                            '20261008T122000Z']), 0)
        handler.assert_called_once()
        self.assertEqual(handler.call_args.args[0].run_id, '20261008T122000Z')
        self.assertEqual(handler.call_args.kwargs['active'], 'B')

    def test_dispatch_selects_the_handler_for_each_subcommand(self):
        names = {'run': 'cmd_run', 'status': 'cmd_status', 'request': 'cmd_request', 'collect': 'cmd_collect'}
        for command, handler_name in names.items():
            with self.subTest(command=command), \
                 patch.object(dentobot.visible_case, handler_name, return_value=0) as handler:
                args = argparse.Namespace(visible_case_command=command)
                self.assertEqual(dentobot.visible_case.dispatch(args, active='B', machines={'B': {}}), 0)
                handler.assert_called_once()

    def test_request_and_collect_are_refused_on_b_before_any_ssh(self):
        for command in ('request', 'collect'):
            out = io.StringIO()
            argv = [*self.args, 'visible-case', command]
            argv += ['--case', 'Cases/a.dentocase'] if command == 'request' else ['--run-id', '20261008T122000Z']
            with self.subTest(command=command), contextlib.redirect_stdout(out), \
                 contextlib.redirect_stderr(io.StringIO()), \
                 patch.object(dentobot.visible_case, 'Remote') as remote:
                self.assertEqual(dentobot.main(argv), 2)
            remote.assert_not_called()
            self.assertIn('"error"', out.getvalue().strip().splitlines()[-1])

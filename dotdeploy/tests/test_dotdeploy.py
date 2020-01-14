import os
import sys

import unittest
import mock
import io
import copy

from dotdeploy.dotdeploy import DotDeploy

# pylint: disable=no-member


class TestingContext:
    class Mocks:
        """Mock Meta Class"""

    def __init__(self):

        # create structure to store mocks/patches
        self.mocks = self.Mocks()
        self.patches = []

        # add our mocks
        setattr(self.mocks, "sys_argv", ["./dotdeploy"])
        self.patches.append(
            mock.patch.object(sys, "argv", new=getattr(self.mocks, "sys_argv"))
        )

        self.mock_stdout = io.StringIO()
        self.mock_stderr = io.StringIO()

    def __enter__(self):

        for patch in self.patches:
            patch.start()

        sys.stdout = self.mock_stdout
        sys.stderr = self.mock_stderr

        return self

    def __exit__(self, _type, _value, _trace):

        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

        for patch in self.patches:
            patch.stop()

        return False


class BaseTestCase(unittest.TestCase):
    def setUp(self):
        # create a testing context
        self.test_context = TestingContext()

        with self.test_context:
            # Create an instance of the dotdeploy class (under the testing context)
            self.dotdeploy = DotDeploy()


class GlobalTestCase(BaseTestCase):
    def test_sys_argv_empty(self):
        """
        Ensure sys.argv is empty initially,
        except from the script name
        """
        with self.test_context:
            self.assertEqual(
                sys.argv, ["./dotdeploy"], "sys.argv did not match expected mock",
            )
            self.assertIsInstance(sys.argv, list)

    def test_sys_argv_extended(self):
        """
        Ensure sys.argv is populated correctly
        """

        self.test_context.mocks.sys_argv.extend(
            ["--option1", "arg1", "--option2", "arg2"]
        )

        with self.test_context:
            self.assertEqual(
                sys.argv,
                ["./dotdeploy", "--option1", "arg1", "--option2", "arg2"],
                "sys.argv did not match expected mock",
            )
            self.assertIsInstance(sys.argv, list)

    def test_no_args_exits(self):
        """
        Ensure no arguments cause exit(1)
        """

        with self.test_context, self.assertRaises(SystemExit) as exit_ex:
            self.dotdeploy.cli()

        self.assertEqual(exit_ex.exception.code, 1, "exit code was not 1")

        self.assertFalse(
            self.test_context.mock_stdout.getvalue(), "stdout is not empty"
        )
        self.assertIn(
            "usage:", self.test_context.mock_stderr.getvalue(), "usage: not in stderr"
        )

    def test_help_arg(self):
        """
        Ensure help arg (--help) exits 0 and shows usage
        """

        self.test_context.mocks.sys_argv.extend(["--help"])

        with self.test_context, self.assertRaises(SystemExit) as exit_ex:
            self.dotdeploy.cli()

        self.assertEqual(exit_ex.exception.code, 0, "exit code was not 0")

        self.assertFalse(
            self.test_context.mock_stderr.getvalue(), "stderr is not empty"
        )
        self.assertIn(
            "usage:", self.test_context.mock_stdout.getvalue(), "usage: not in stdout"
        )

    def test_version_arg(self):
        """
        Ensure version arg (--version) exits 0 and shows version
        """

        self.test_context.mocks.sys_argv.extend(["--version"])

        with self.test_context, self.assertRaises(SystemExit) as exit_ex:
            self.dotdeploy.cli()

        self.assertEqual(exit_ex.exception.code, 0, "exit code was not 0")

        self.assertFalse(
            self.test_context.mock_stderr.getvalue(), "stderr is not empty"
        )
        self.assertEqual(
            "{} {}\n".format(self.dotdeploy._parser.prog, self.dotdeploy.VERSION),
            self.test_context.mock_stdout.getvalue(),
        )

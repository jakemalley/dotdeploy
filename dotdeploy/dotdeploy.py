#!/usr/bin/env python3

import os
import sys
import copy
import shutil
import argparse
import configparser


class DotDeployException(Exception):
    """DotDeployException"""


class DotDeploy:

    NAME = "dotdeploy"
    VERSION = "0.1"

    def __init__(self):
        """
        initialise dotdeploy's argument and confiuration parsers
        """

        # initialise an empty config
        self._config = {}

        # initialise an argument parser
        self._parser = argparse.ArgumentParser()
        self._parser._positionals.title = "command"
        subparsers = self._parser.add_subparsers(dest="command")

        # global optional arguments
        self._parser.add_argument("-v", "--verbose", action="count", default=0)
        self._parser.add_argument(
            "-V",
            "--version",
            action="version",
            version="%(prog)s {version}".format(version=self.VERSION),
        )

        # validate command
        validate_command = subparsers.add_parser(
            "validate", help="validate a given profile"
        )
        validate_command.add_argument("profile", help="path to a profile.ini file")
        validate_command.add_argument(
            "-q",
            "--quiet",
            action="store_true",
            help="disable output to stdout, return only exit code 0 or 1",
        )

        # apply command
        apply_command = subparsers.add_parser("apply", help="apply a given profile")
        apply_command.add_argument("profile", help="path to a profile.ini file")

    def cli(self):
        """
        begin CLI - parse the arguments and run the required function
        """
        self._args = self._parser.parse_args()
        if not self._args.command:
            self.show_help()

        # call the command function, if it doesn't exit error
        if hasattr(self, "cmd_{}".format(self._args.command)):
            getattr(self, "cmd_{}".format(self._args.command))()
        else:
            self.error("command {} not implemented".format(self._args.command))

    def show_help(self):
        """
        show the argparse help text and exit(1)
        """
        self._parser.print_help(sys.stderr)
        sys.exit(1)

    def error(self, message, exit=True, exit_code=1):
        """
        output a given error to the console and optionally exit(1)
        """
        print("{}: error: {}".format(os.path.basename(self._parser.prog), message))
        if exit:
            sys.exit(exit_code)

    def load_profile(self, profile_file):
        """
        load a given profile into the config attribute
        """
        # ensure the profile is a valid file
        if not os.path.isfile(self._args.profile):
            self.error("no such file {}".format(self._args.profile))

        # initialise a config parser
        config_parser = configparser.ConfigParser(
            interpolation=configparser.ExtendedInterpolation()
        )

        # add a global section for value interpolation
        config_parser.add_section("global")
        config_parser.set("global", "home", os.path.expanduser("~"))

        # attempt to read the profile
        try:
            config_parser.read(profile_file)
        except configparser.ParsingError as ex:
            self.error(str(ex).replace("\n", ""))

        # if there are no default settings, create them
        if "settings" not in config_parser:
            config_parser.add_section("settings")
            config_parser.set("settings", "mode", "link")
            config_parser.set("settings", "backup", "false")

        # configure the base path and add to the global section
        if config_parser["settings"].get("groups_directory", None):
            base_path = os.path.abspath(config_parser["settings"]["groups_directory"])
        else:
            base_path = os.path.abspath(os.path.dirname(profile_file))

        config_parser.set("global", "base_path", base_path)

        # return as a dictionary as config._sections doesn't provide value interpolation
        try:
            self._config = {
                s: dict(config_parser.items(s)) for s in config_parser.sections()
            }
        except configparser.InterpolationError as ex:
            self.error(ex.message)
        else:
            return self._config

    def validate(self, quiet=True):
        """
        validate a given profile
        """

        def validate_error(error):
            """Only display errors if not in quiet mode, never exit"""
            if not quiet:
                self.error(error, exit=False)

        if not self._config:
            raise DotDeployException("cannot validate an empty profile configuration")

        # ensure the base path actually exists
        if not os.path.isdir(self._config["global"]["base_path"]):
            validate_error(
                "directory not found: no such directory: {}".format(
                    self._config["global"]["base_path"]
                )
            )
            return False

        groups = self.groups(self._config)
        if not groups:
            validate_error("no groups found in profile")
            return False

        # flag for validation
        valid = True

        # for each group ensure it exists, and then check the files
        for group in self.groups(self._config):

            group_path = os.path.join(self._config["global"]["base_path"], group)
            if not os.path.isdir(group_path):
                valid = False
                validate_error(
                    "groups directory not found: no such directory: {}".format(
                        group_path
                    )
                )
                # group doesn't exist check the next one
                continue

            # list of the files in this group
            files = self._config[group]
            for file_name, deploy_path in files.items():

                if os.path.isabs(file_name):
                    valid = False
                    validate_error(
                        "file name cannot be an absolute path: {}".format(file_name)
                    )
                    continue

                abs_file_name, abs_deploy_path = self.get_paths(
                    group, file_name, deploy_path
                )

                if not self.is_abspath_prefixed_by(
                    os.path.join(self._config["global"]["base_path"], group),
                    abs_file_name,
                ):
                    valid = False
                    validate_error(
                        "file name {} must be within group {}".format(file_name, group)
                    )
                    continue

                if abs_file_name == abs_deploy_path:
                    valid = False
                    validate_error(
                        "deployment path cannot be the same as original path"
                    )
                    continue

                if not os.path.isfile(abs_file_name):
                    valid = False
                    validate_error(
                        "no such file: {} in group: {}".format(file_name, group)
                    )

        return valid

    def groups(self, config):
        """
        return a list of groups to deploy (excludes settings and *.settings)
        """
        blacklisted_sections = ["DEFAULT", "global", "settings"]
        return [
            k
            for k in config
            if k not in blacklisted_sections and not k.endswith(".settings")
        ]

    def get_paths(self, group, file_name, deploy_path):
        """
        return the absolute file paths to the file and deployment
        location for files within a group
        """

        abs_file_name = os.path.abspath(
            os.path.join(self._config["global"]["base_path"], group, file_name)
        )

        abs_deploy_path = self.get_expanded_abspath(
            os.path.dirname(abs_file_name), deploy_path
        )

        return abs_file_name, abs_deploy_path

    def get_expanded_abspath(self, base_path, path):
        """
        return a absolute path to a given file expanding user
        """
        # return path if already absolute
        if os.path.isabs(path):
            return path
        # expand user path and check if absolute
        path = os.path.expanduser(path)
        if os.path.isabs(path):
            return path
        # return a absolute path of base and path
        return os.path.abspath(os.path.join(base_path, path))

    def is_abspath_prefixed_by(self, expected_base, path):
        """
        return whether a path begins with a given base,
        e.g. is /abc/def/ghi under the directory /abc
        """
        return path.startswith(expected_base)

    def backup(self, config, path):
        """
        backup a given file
        """
        backup_base_path = os.path.join(config["global"]["base_path"], "backup")
        if not os.path.isdir(backup_base_path):
            os.mkdir(backup_base_path)

        backup_filename = path.replace("/", "_")[1:]
        backup_path = os.path.join(backup_base_path, backup_filename)

        if os.path.isfile(path):
            shutil.copyfile(path, backup_path, follow_symlinks=True)

    def cmd_apply(self):
        """
        apply command: apply a profile's configuration
        """

        # load the profile and validate it
        config = self.load_profile(self._args.profile)
        if not self.validate(quiet=False):
            sys.exit(1)

        for group in self.groups(config):
            # update the settings with the group specific settings
            settings = copy.deepcopy(config["settings"])
            settings.update(config.get("{}.settings".format(group), {}))
            # list of the files we will deploy
            files = config[group]
            # iterate over the files and deploy them
            for file_name, deploy_path in files.items():

                abs_file_name, abs_deploy_path = self.get_paths(
                    group, file_name, deploy_path
                )

                print("=" * 80)
                print("OLD:", abs_file_name)
                print("NEW:", abs_deploy_path)
                print("=" * 80)

                # if settings.get("backup", "false").lower() in ["true", "yes"]:
                #     self.backup(config, abs_deploy_path)

                # if settings.get("mode", "link").lower() in ["copy", "cp"]:
                #     shutil.copyfile(abs_file_name, abs_deploy_path)
                # else:
                #     if os.path.isfile(abs_deploy_path):
                #         os.remove(abs_deploy_path)
                #     os.symlink(abs_file_name, abs_deploy_path)

    def cmd_validate(self):
        """
        validate command: validate a profile's configuration
        """
        # set the quiet argument, this can be overridden by verbose
        quiet = self._args.quiet and (self._args.verbose == 0)

        # load the profile and validate it
        config = self.load_profile(self._args.profile)
        valid = self.validate(quiet=quiet)

        # if the profile wasn't valid we exit(1)
        if not valid:
            if quiet:
                sys.exit(1)
            else:
                self.error("validation failed: one or more errors occured")

        if self._args.verbose > 0:
            print("validation success exiting 0")
        sys.exit(0)


def main():
    """Main Entrypoint"""
    try:
        DotDeploy().cli()
    except DotDeployException as ex:
        print("dotdeploy: error: an unexpected exception occured: {}".format(str(ex)))


if __name__ == "__main__":
    main()

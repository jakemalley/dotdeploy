#!/usr/bin/env python3

import os
import sys
import copy
import shutil
import filecmp
import argparse
import configparser


class DotDeployException(Exception):
    """DotDeployException"""


class Helpers:
    """
    namespace for helper functions to keep dotdeploy in a single
    file for portability, while maintaining organisation.
    """

    @staticmethod
    def get_abspath(base_path, *paths):
        """
        return the absolute path for a base path,
        joined with a number of additional paths
        """
        return os.path.abspath(os.path.join(base_path, *paths))

    @staticmethod
    def get_expanded_abspath(base_path, path):
        """
        return a absolute path to a given file,
        while expanding ~ and ~user constructions
        """
        # return path if already absolute
        if os.path.isabs(path):
            return path
        # expand user path and check if absolute
        path = os.path.expanduser(path)
        if os.path.isabs(path):
            return path
        # return a absolute path of base and path
        return Helpers.get_abspath(base_path, path)

    @staticmethod
    def is_abspath_prefixed_by(expected_base, path):
        """
        return whether a path begins with a given base,
        e.g. is /abc/def/ghi under the directory /abc
        """
        return path.startswith(expected_base)


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
        self._parser = argparse.ArgumentParser(prog=self.NAME)
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
        apply_command.add_argument(
            "--no-report",
            action="store_true",
            help="do not report the number of files changed",
        )
        apply_command.add_argument(
            "--dry-run",
            action="store_true",
            help="report without applying file changes",
        )

    def cli(self):
        """
        begin CLI - parse the arguments and run the required function
        """
        # parse command line arguments
        self._args = self._parser.parse_args()
        if not self._args.command:
            self.show_help()

        # call the command function, if it doesn't exit error
        if hasattr(self, "cmd_{}".format(self._args.command)):
            getattr(self, "cmd_{}".format(self._args.command))()
        else:
            self.error("command {} not implemented".format(self._args.command))

        # exit(0)
        sys.exit(0)

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

    def get_group_names(self):
        """
        return a list of groups to deploy (excludes settings and *.settings)
        """
        blacklisted_sections = ["DEFAULT", "global", "settings"]
        return [
            k
            for k in self._config
            if k not in blacklisted_sections and not k.endswith(".settings")
        ]

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

        groups = self.get_group_names()
        if not groups:
            validate_error("no groups found in profile")
            return False

        # flag for validation
        valid = True

        # for each group ensure it exists, and then check the files
        for group in self.get_group_names():

            group_path = Helpers.get_abspath(self._config["global"]["base_path"], group)
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

                if not Helpers.is_abspath_prefixed_by(
                    Helpers.get_abspath(self._config["global"]["base_path"], group),
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

    def get_paths(self, group, file_name, deploy_path):
        """
        return the absolute file paths to the file and deployment
        location for files within a group
        """

        abs_file_name = Helpers.get_abspath(
            self._config["global"]["base_path"], group, file_name
        )

        abs_deploy_path = Helpers.get_expanded_abspath(
            os.path.dirname(abs_file_name), deploy_path
        )

        return abs_file_name, abs_deploy_path

    def file_changed(self, mode, abs_file_path, abs_deploy_path):
        """
        return whether the deployed file should or be updated
        (to prevent us updating the same file with each run)
        """
        # if the file doesn't already exist it will need
        # to be updated.
        if not os.path.isfile(abs_deploy_path):
            return True

        # if mode=link and it currently is a link to
        # the correct file we don't update
        if (
            mode == "link"
            and os.path.islink(abs_deploy_path)
            and os.path.samefile(abs_file_path, abs_deploy_path)
        ):
            return False

        # if mode=copy and it is not a link and
        # they are the same we don't update
        if (
            mode == "copy"
            and not os.path.islink(abs_deploy_path)
            and filecmp.cmp(abs_file_path, abs_deploy_path)
        ):
            return False

        # we need to update the file
        return True

    def backup(self, path):
        """
        backup a given file
        """

        backup_base_path = Helpers.get_abspath(
            self._config["global"]["base_path"], "backup"
        )
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

        # reporting
        report = (
            not self._args.no_report or self._args.dry_run or (self._args.verbose > 0)
        )

        report_data = {"resources": 0, "changed": 0, "backed_up": 0}

        for group in self.get_group_names():
            # update the settings with the group specific settings
            settings = copy.deepcopy(config["settings"])
            settings.update(config.get("{}.settings".format(group), {}))
            # list of the files we will deploy
            files = config[group]
            # iterate over the files and deploy them
            for file_name, deploy_path in files.items():
                report_data["resources"] += 1

                # get the absolute paths to the file and file to deploy
                abs_file_name, abs_deploy_path = self.get_paths(
                    group, file_name, deploy_path
                )

                # get mode, default to 'link'
                mode = settings.get("mode", "link").lower()
                # has the file changed
                changed = self.file_changed(mode, abs_file_name, abs_deploy_path)

                if changed:
                    report_data["changed"] += 1

                    # if the file has changed take a backup.
                    if settings.get("backup", "false").lower() in ["true", "yes"]:
                        report_data["backed_up"] += 1
                        if not self._args.dry_run:
                            self.backup(abs_deploy_path)

                    if not self._args.dry_run:
                        # if we are changing and the file exists remove it.
                        if os.path.isfile(abs_deploy_path):
                            os.remove(abs_deploy_path)

                        # if we are copying use shutil.copyfile
                        if settings.get("mode", "link").lower() in ["copy", "cp"]:
                            shutil.copyfile(abs_file_name, abs_deploy_path)
                        # otherwise use os.symlink
                        else:
                            os.symlink(abs_file_name, abs_deploy_path)

        if report:
            report_text = (
                "file(s) would change" if self._args.dry_run else "files(s) changed"
            )
            print(
                "{} / {} {}, {} file(s) backed up".format(
                    report_data["changed"],
                    report_data["resources"],
                    report_text,
                    report_data["backed_up"],
                )
            )

    def cmd_validate(self):
        """
        validate command: validate a profile's configuration
        """
        # set the quiet argument, this can be overridden by verbose
        quiet = self._args.quiet and (self._args.verbose == 0)

        # load the profile and validate it
        self.load_profile(self._args.profile)
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

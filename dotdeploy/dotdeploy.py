#!/usr/bin/env python3

import os
import sys
import copy
import shutil
import argparse
import configparser


class DotDeploy:

    NAME = "dotdeploy"
    VERSION = "0.1"

    def __init__(self):
        """
        initialise dotdeploy's argument and confiuration parsers
        """

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

        # initialise a config parser
        self._config = configparser.ConfigParser(
            interpolation=configparser.ExtendedInterpolation()
        )

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

        # add a global section for value interpolation
        self._config.add_section("global")
        self._config.set("global", "home", os.path.expanduser("~"))

        # attempt to read the profile
        try:
            self._config.read(profile_file)
        except configparser.ParsingError as ex:
            self.error(str(ex).replace("\n", ""))

        # if there are no default settings, create them
        if "settings" not in self._config:
            self._config.add_section("settings")
            self._config.set("settings", "mode", "link")
            self._config.set("settings", "backup", "false")

        # configure the base path and add to the global section
        if self._config["settings"].get("groups_directory", None):
            base_path = os.path.abspath(self._config["settings"]["groups_directory"])
        else:
            base_path = os.path.abspath(os.path.dirname(profile_file))

        self._config.set("global", "base_path", base_path)

        # return as a dictionary as config._sections doesn't provide value interpolation
        return {s: dict(self._config.items(s)) for s in self._config.sections()}

    def validate(self, config, quiet=True):
        """
        validate a given profile
        """
        # ensure the base path actually exists
        if not os.path.isdir(config["global"]["base_path"]):
            if not quiet:
                self.error(
                    "directory not found: no such directory: {}".format(
                        config["global"]["base_path"]
                    ),
                    exit=False,
                )
            return False

        groups = self.groups(config)
        if not groups:
            if not quiet:
                self.error(
                    "no groups found in profile", exit=False,
                )
            return False

        # flag for validation
        valid = True

        # for each group ensure it exists, and then check the files
        for group in self.groups(config):

            group_path = os.path.join(config["global"]["base_path"], group)
            if not os.path.isdir(group_path):
                valid = False
                if not quiet:
                    self.error(
                        "groups directory not found: no such directory: {}".format(
                            group_path
                        ),
                        exit=False,
                    )
                # group doesn't exist check the next one
                continue

            # list of the files in this group
            files = config[group]
            for file_name, _ in files.items():
                abs_file_name = os.path.join(
                    config["global"]["base_path"], group, file_name
                )
                if not os.path.isfile(abs_file_name):
                    valid = False
                    if not quiet:
                        self.error(
                            "no such file: {} in group: {}".format(file_name, group),
                            exit=False,
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
        if not self.validate(config, quiet=False):
            sys.exit(1)

        for group in self.groups(config):
            # update the settings with the group specific settings
            settings = copy.deepcopy(config["settings"])
            settings.update(config.get("{}.settings".format(group), {}))
            # list of the files we will deploy
            files = config[group]
            # iterate over the files and deploy them
            for file_name, deploy_path in files.items():

                if os.path.isabs(file_name):
                    self.error(
                        "file name cannot be an absolute path: {}".format(file_name)
                    )
                abs_file_name = os.path.join(
                    config["global"]["base_path"], group, file_name
                )

                if os.path.isabs(deploy_path):
                    abs_deploy_path = deploy_path
                else:
                    abs_deploy_path = os.path.join(
                        config["global"]["base_path"], deploy_path
                    )

                if settings.get("backup", "false").lower() in ["true", "yes"]:
                    self.backup(config, abs_deploy_path)

                if settings.get("mode", "link").lower() in ["copy", "cp"]:
                    shutil.copyfile(abs_file_name, abs_deploy_path)
                else:
                    if os.path.isfile(abs_deploy_path):
                        os.remove(abs_deploy_path)
                    os.symlink(abs_file_name, abs_deploy_path)

    def cmd_validate(self):
        """
        validate command: validate a profile's configuration
        """
        # set the quiet argument, this can be overridden by verbose
        quiet = self._args.quiet and (self._args.verbose == 0)

        # load the profile and validate it
        config = self.load_profile(self._args.profile)
        valid = self.validate(config, quiet=quiet)

        # if the profile wasn't valid we exit(1)
        if not valid:
            if quiet:
                sys.exit(1)
            else:
                self.error("validation failed: one or more errors occured")

        if self._args.verbose > 0:
            print("validation success exiting 0")
        sys.exit(0)


if __name__ == "__main__":
    DotDeploy().cli()

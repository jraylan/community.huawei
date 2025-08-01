#
# (c) 2016 Red Hat Inc.
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
#
from __future__ import absolute_import, division, print_function


__metaclass__ = type

import json
import re

from ansible.errors import AnsibleConnectionFailure
from ansible.module_utils._text import to_bytes, to_text
from ansible.utils.display import Display
from ansible_collections.ansible.netcommon.plugins\
                        .plugin_utils.terminal_base import TerminalBase


display = Display()


class TerminalModule(TerminalBase):
    terminal_stdout_re = [
        re.compile(
            rb"[\r\n]?^[\w\+\-\.:\/\[\]]+(?:\(config+\))?(?:[>#]) ?$",
            re.M)
    ]

    terminal_stderr_re = [
        # Command error
        re.compile(
            rb"^(\{[^\}]+\}:$([\r\n]$)+^\s+Command:$\s+.*?$)?"
            rb"\s*[\^]([\r\n]+)"
            rb"\s+\% (.*), the error locates at '\^'([\r\n]+)",
            re.M
        ),
        # Pre-timeout warning
        # re.compile(
        #     rb"^([\r\n])+\s+"
        #     rb"Please check whether system data has been changed, and save "
        #     rb"data in time([\r\n]$)+",
        #     re.M
        # ),
        # Timeout
        re.compile(
            rb"^\s+Configuration console time out, please retry to log on$",
            re.M
        ),
        # Saving alert
        # re.compile(
        #     rb"^\s+It will take several minutes to save configuration file, "
        #     rb"please wait...$",
        #     re.M
        # ),
        # Saving success
        # re.compile(
        #     rb"^\s+ Configuration file had been saved successfully([\n\r]+)$",
        #     re.M
        # ),
        # Logging/Warnings
        # re.compile(
        #     rb"^\s+(\d+\s+\[[0-9\-\:\s\+Z]{19,}\]|Warning):(.*[\n\r]?)*?$",
        #     re.M
        # ),
        # re.compile(
        #     rb"---- More ( Press 'Q' to break ) ----",
        #     re.M
        # ),
        # re.compile(
        #     rb"^\s+It will take a long time if the content you search is "
        #     rb"too much or the string you input is too long, "
        #     rb"you can press CTRL_C to break\s+$[\n\r]",
        #     re.M
        # )
    ]

    terminal_initial_prompt = [
        rb"[\r\n]?^[\w\+\-\.:\/\[\]]+(?:\(config+\))?(?:[>#]) ?$",
    ]

    terminal_config_prompt = re.compile(r"^.+\(config\)#$")

    def get_privilege_level(self):
        prompt = self._get_prompt()
        return 1 + prompt.endswith(b"#") * 14

    def on_open_shell(self):
        self._exec_cli_command(b"undo smart")
        self._exec_cli_command(b"undo interactive")
        self._exec_cli_command(b"scroll")

    def on_become(self, passwd=None):
        if (
            self._get_prompt().endswith(b"#")
            and self.get_privilege_level() == 15
        ):
            return

        cmd = {"command": "enable"}
        if passwd:
            # Note: python-3.5 cannot combine u"" and r"" together.  Thus make
            # an r string and use to_text to ensure it's text on both py2
            # and py3.
            cmd["prompt"] = to_text(
                r"[\r\n]?(?:.*)?[Pp]assword: ?$",
                errors="surrogate_or_strict",
            )
            cmd["answer"] = passwd
            cmd["prompt_retry_check"] = True  # type: ignore
        try:
            self._exec_cli_command(
                to_bytes(json.dumps(cmd), errors="surrogate_or_strict"),
            )
            prompt = self._get_prompt()
            privilege_level = self.get_privilege_level()
        except AnsibleConnectionFailure as e:
            prompt = self._get_prompt()
            raise AnsibleConnectionFailure(
                "failed to elevate privilege to enable mode, "
                "at prompt [%s] with error: %s"
                % (prompt, e.message),
            )

        if (
            prompt is None
            or not prompt.endswith(b"#")
            or privilege_level != 15
        ):
            raise AnsibleConnectionFailure(
                "failed to elevate privilege to enable mode, still at level "
                "[%d] and prompt [%s]"
                % (privilege_level, prompt),
            )

    def on_unbecome(self):
        prompt = self._get_prompt()
        if prompt is None:
            # if prompt is None most likely the terminal is hung up at a prompt
            return

        if self.get_privilege_level() != 15:
            return

        if prompt.endswith(b"#"):
            self._exec_cli_command(b"disable")

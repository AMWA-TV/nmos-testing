# Copyright (C) 2026 Advanced Media Workflow Association
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import re
import shlex
import subprocess
from enum import IntEnum

from .GenericTest import NMOSTestException
from . import Config as CONFIG

# Tests that use an external tool fail when its version is older than the minimum, and are disabled when its
# version cannot be read. A version newer than the tested version is allowed, with a warning at start-up.
# The Dockerfile, testssl/README.md and docs/1.1. Installation - Local.md install the tested versions.
EXTERNAL_TOOLS = {
    "SDPoker": {
        "command": "sdpoker --version",
        "pattern": r"^v?(\d+)\.(\d+)\.(\d+)",
        "minimum": "0.3.0",
        "tested": "0.3.0"
    },
    "testssl.sh": {
        "command": "{bash} testssl/testssl.sh -v",
        "pattern": r"testssl\.sh\s+(?:version\s+)?(\d+)\.(\d+)(?:\.(\d+))?",
        "env": {"COLOR": "0"},
        "minimum": "3.0.7",
        "tested": "3.0.7"
    }
}


class ExternalToolStatus(IntEnum):
    OK = 0
    UNTESTED = 1
    TOO_OLD = 2
    UNREADABLE = 3
    UNAVAILABLE = 4


def get_external_tool_status(name):
    """Run an external tool from EXTERNAL_TOOLS to check its version, returning an ExternalToolStatus and a message"""
    tool = EXTERNAL_TOOLS[name]
    command = tool["command"].format(bash=shlex.quote(CONFIG.TEST_SSL_BASH))
    try:
        output = subprocess.check_output(command, stderr=subprocess.STDOUT, shell=True,
                                         env=dict(os.environ, **tool.get("env", {})))
    except subprocess.CalledProcessError:
        return ExternalToolStatus.UNAVAILABLE, ("{} may be unavailable on this system. Please see the README for "
                                                "installation instructions.".format(name))
    text = output.decode("utf-8", errors="replace")
    match = re.search(tool["pattern"], text, re.MULTILINE)
    if match is None:
        # Node prints warnings before SDPoker's output, so the last line is the most useful one to quote
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return ExternalToolStatus.UNREADABLE, ("{} version could not be read from the output of {!r}, which ends "
                                               "with {!r}. The tested version is {}."
                                               .format(name, command, lines[-1] if lines else "", tool["tested"]))
    found = ".".join(field for field in match.groups() if field is not None)
    version = tuple(int(field or 0) for field in match.groups())
    if version < tuple(int(field) for field in tool["minimum"].split(".")):
        return ExternalToolStatus.TOO_OLD, ("{} version {} is older than the minimum version {}. Please update to "
                                            "version {}.".format(name, found, tool["minimum"], tool["tested"]))
    if version > tuple(int(field) for field in tool["tested"].split(".")):
        return ExternalToolStatus.UNTESTED, ("{} version {} is newer than the tested version {}."
                                             .format(name, found, tool["tested"]))
    return ExternalToolStatus.OK, ""


def check_external_tool(test, name):
    """Raise an NMOSTestException if the tests that use an external tool from EXTERNAL_TOOLS cannot run"""
    status, message = get_external_tool_status(name)
    if status in (ExternalToolStatus.UNAVAILABLE, ExternalToolStatus.UNREADABLE):
        raise NMOSTestException(test.DISABLED(message))
    if status == ExternalToolStatus.TOO_OLD:
        raise NMOSTestException(test.FAIL(message))


def check_external_requirements():
    for tool_name in EXTERNAL_TOOLS:
        status, message = get_external_tool_status(tool_name)
        if status != ExternalToolStatus.OK:
            print(" * WARNING: {}".format(message))

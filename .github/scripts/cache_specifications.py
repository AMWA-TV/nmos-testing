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

"""Clone each repository in SPECIFICATIONS into the cache directory.

Each clone tracks the branches matching "<version>*" for its versions, so the
hourly pull at startup also fetches a "<version>.x" branch created after the
image was built.
"""

import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from nmostesting.Config import CACHE_PATH, SPECIFICATIONS  # noqa: E402


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


for repo_key, repo_data in SPECIFICATIONS.items():
    repo = repo_data["repo"]
    if repo is None:
        continue
    path = os.path.join(ROOT, CACHE_PATH, repo_key)
    url = "https://github.com/AMWA-TV/{}.git".format(repo)
    print("Cloning {} into {}".format(url, path), flush=True)
    git("clone", "--depth", "1", "--no-tags", url, path)

    versions = repo_data["versions"]
    git("-C", path, "remote", "set-branches", "origin", *[version + "*" for version in versions])
    git("-C", path, "fetch", "--no-tags", "--depth", "1", "origin")

    # GenericTest checks out the first of these branches that exists
    branches = git("-C", path, "branch", "-r").split()
    for version in versions:
        candidates = [version + ".x", version + "-dev", version]
        if not any("origin/" + candidate in branches for candidate in candidates):
            sys.exit("No branch for {} version {}: tried {}".format(repo, version, ", ".join(candidates)))

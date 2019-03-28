#!/usr/bin/python
#
# Copyright 2018 British Broadcasting Corporation
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

from __future__ import print_function
from setuptools import setup
import os


def check_packages(packages):
    failure = False
    for python_package, package_details in packages:
        try:
            __import__(python_package)
        except ImportError:
            failure = True
            print("Cannot find", python_package,)
            print("you need to install :", package_details)

    return not failure


def check_dependencies(packages):
    failure = False
    for python_package, dependency_filename, dependency_url in packages:
        try:
            __import__(python_package)
        except ImportError:
            failure = True
            print()
            print("Cannot find", python_package,)
            print("you need to install :", dependency_filename)
            print("... originally retrieved from", dependency_url)

    return not failure


def is_package(path):
    return (
        os.path.isdir(path) and
        os.path.isfile(os.path.join(path, '__init__.py'))
        )


def find_packages(path, base=""):
    """ Find all packages in path """
    packages = {}
    for item in os.listdir(path):
        dir = os.path.join(path, item)
        if is_package(dir):
            if base:
                module_name = "%(base)s.%(item)s" % vars()
            else:
                module_name = item
            packages[module_name] = dir
            packages.update(find_packages(dir, module_name))
    return packages


packages = find_packages(".")
package_names = packages.keys()

with open("requirements.txt") as requirements_file:
    packages_required = requirements_file.read().splitlines()

deps_required = []

setup(name="nmos-testing",
      version="0.1.1",
      description="NMOS Test Suite",
      url='https://github.com/bbc/nmos-testing',
      author='Andrew Bonney',
      author_email='andrew.bonney@bbc.co.uk',
      license='Apache 2',
      packages=package_names,
      package_dir=packages,
      install_requires=packages_required,
      dependency_links=deps_required,
      scripts=[],
      data_files=[],
      long_description="""
Automated testing suite for the AMWA NMOS APIs
""")

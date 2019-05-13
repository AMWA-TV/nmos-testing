# Copyright (C) 2019 Advanced Media Workflow Association
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


from is08.helperTools import getIOList
from is08.testConfig import globalConfig
from is08.calls import Call
from is08.outputs import getOutputList
from GenericTest import NMOSTestException


def getInputList():
    idList = getIOList("input")
    instanceList = []
    for id in idList:
        instanceList.append(ACMInput(id))
    return instanceList


class ACMInput:

    def __init__(self, inputID):
        self.id = inputID
        self.urlBase = globalConfig.apiUrl
        self.url = "{}inputs/{}".format(self.urlBase, self.id)
        self.test = globalConfig.test

    def assembleInputObject(self):
        """Create JSON representation of an Input"""
        toReturn = {}
        resourceList = [
            'parent',
            'channels',
            'caps',
            'properties'
        ]
        for resource in resourceList:
            url = "{}/{}".format(self.url, resource)
            call = Call(url)
            toReturn[resource] = call.get()
        return toReturn

    def getParent(self):
        return self.assembleInputObject()['parent']

    def getChannelList(self):
        return self.assembleInputObject()['channels']

    def getConstraints(self):
        return self.assembleInputObject()['caps']

    def getBlockSize(self):
        try:
            return self.getConstraints()['block_size']
        except KeyError:
            raise NMOSTestException(
                globalConfig.test.FAIL("Could not find `block_size` parameter in"
                                       " input caps for input {}".format(self.id))
            )

    def getReordering(self):
        try:
            return self.getConstraints()['reordering']
        except KeyError:
            raise NMOSTestException(
                globalConfig.test.FAIL("Could not find `reordering` parameter in"
                                       " input caps for input {}".format(self.id))
            )

    def getRoutableOutputs(self):
        routableOutputList = []
        for outputInstance in getOutputList():
            if self.getBlockSize() <= len(outputInstance.getChannelList()):
                if self.id in outputInstance.getRoutableInputList():
                    routableOutputList.append(outputInstance)
        return routableOutputList

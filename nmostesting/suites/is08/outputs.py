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


from .helperTools import getIOList
from ...GenericTest import NMOSTestException
from .testConfig import globalConfig
from .calls import Call


def getOutputList():
    outputList = getIOList("output")
    instanceList = []
    for outputId in outputList:
        instanceList.append(ACMOutput(outputId))
    return instanceList


class ACMOutput:

    def __init__(self, outputID):
        self.id = outputID
        self.url = "{}outputs/{}/".format(globalConfig.apiUrl, self.id)
        self.test = globalConfig.test

    def assembleOutputObject(self):
        """Create JSON representation of an output"""
        toReturn = {}
        resourceList = {
            'sourceid': 'source_id',
            'channels': 'channels',
            'caps': 'caps',
            'properties': 'properties'
        }
        for apiId, ioId in resourceList.items():
            url = "{}{}".format(self.url, apiId)
            call = Call(url)
            toReturn[ioId] = call.get()
        if toReturn['source_id'] == "null":
            toReturn['source_id'] = None
        return toReturn

    def getRoutableInputList(self):
        outputObject = self.assembleOutputObject()
        try:
            routableInputs = outputObject['caps']['routable_inputs']
        except KeyError:
            msg = 'Could not find caps routable_inputs parameter for Output {}'.format(self.id)
            raise NMOSTestException(self.test.FAIL(msg))
        if routableInputs is None:
            routableInputs = getIOList("input")
            routableInputs.append(None)
        return routableInputs

    def getChannelList(self):
        outputObject = self.assembleOutputObject()
        try:
            channelList = outputObject['channels']
        except KeyError:
            msg = 'Could not find channel list resource for Output {}'.format(self.id)
            raise NMOSTestException(self.test.FAIL(msg))
        return channelList

    def getSourceID(self):
        return self.assembleOutputObject()['source_id']

    def getCaps(self):
        return self.assembleOutputObject()['caps']

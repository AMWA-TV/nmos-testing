# Copyright (C) 2018 British Broadcasting Corporation
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

from is08.testConfig import globalConfig
from is08.inputs import ACMInput
from is08.calls import Call
from is08.outputs import ACMOutput, getOutputList
from is08.action import Action
from is08.activation import Activation
from GenericTest import NMOSTestException


class Active:

    def __init__(self):
        self.url = "{}map/active".format(globalConfig.apiUrl)
        self.test = globalConfig.test

    def buildJSONObject(self):
        call = Call(self.url)
        return call.get()

    def getInputChannelIndex(self, output, channelIndex):
        activeObject = self.buildJSONObject()
        try:
            inputID = activeObject['map'][output.id][str(channelIndex)]['channel_index']
        except KeyError:
            msg = self.test.FAIL("Could not find 'input' field in /active "
                                 "for Output {} Channel {}".format(output.id, channelIndex))
            raise NMOSTestException(msg)
        return inputID

    def getInputChannelName(self, output, channelIndex):
        activeObject = self.buildJSONObject()
        try:
            inputName = activeObject['map'][output.id][str(channelIndex)]['input']
        except KeyError:
            msg = self.test.FAIL("Could not find 'input' field in /active "
                                 "for Output {} Channel {}".format(output.id, channelIndex))
            raise NMOSTestException(msg)
        return inputName

    def getInput(self, output, channelIndex):
        activeObject = self.buildJSONObject()
        try:
            inputChannelID = activeObject['map'][output.id][str(channelIndex)]['input']
        except KeyError:
            msg = self.test.FAIL("Could not find 'input' field in /active "
                                 "for Output {} Channel {}".format(output.id, channelIndex))
            NMOSTestException(msg)
        return ACMInput(inputChannelID)

    def assertActionCompleted(self, action, retries=0):
        ouputChannelIndex = action.outputChannel
        output = ACMOutput(action.outputID)
        inputChannelIndex = self.getInputChannelIndex(output, action.outputChannel)
        input = self.getInput(output, ouputChannelIndex)

        failure = True
        while retries >= 0 and failure:
            channelFail = action.inputChannel != inputChannelIndex
            idFail = action.inputID != input.id
            failure = channelFail or idFail
            retries = retries - 1

        if idFail:
            msg = self.test.FAIL("Did not get expected input channel index in active"
                                 " map, expected {}, got {} for Output {}".format(
                                        action.inputChannel,
                                        inputChannelIndex,
                                        output.id
                                    ))
            raise NMOSTestException(msg)
        if channelFail:
            msg = self.test.FAIL("Did not get expected input channel ID in active"
                                 " map, expected {}, got {} for Output {}".format(
                                     action.inputID,
                                     input.id,
                                     output.id
                                 ))
            raise NMOSTestException(msg)            

    def unrouteAll(self):
        outputList = getOutputList()
        activation = Activation()
        for outputInstance in outputList:
            for channelID in range(0, len(outputInstance.getChannelList())):
                action = Action(None, outputInstance.id, None, channelID)
                activation.addAction(action)
        activation.fireActivation()

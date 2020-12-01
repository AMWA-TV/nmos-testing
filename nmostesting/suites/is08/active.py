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

from .testConfig import globalConfig
from .inputs import ACMInput
from .calls import Call
from .outputs import ACMOutput
from .action import Action
from ...GenericTest import NMOSTestException


class Active:

    def __init__(self):
        self.url = "{}map/active".format(globalConfig.apiUrl)
        self.test = globalConfig.test

    def buildJSONObject(self):
        call = Call(self.url)
        return call.get()

    def getOutputMap(self, output):
        activeObject = self.buildJSONObject()
        try:
            return activeObject['map'][output.id]
        except KeyError:
            res = self.test.FAIL("Could not find 'map' entry for Output {} in /active"
                                 .format(output.id))
            raise NMOSTestException(res)

    def getInputIDChannelIndex(self, output, outputChannelIndex):
        outputMap = self.getOutputMap(output)
        try:
            outputChannel = outputMap[str(outputChannelIndex)]
            inputID = outputChannel['input']
            inputChannelIndex = outputChannel['channel_index']
        except KeyError:
            res = self.test.FAIL("Could not find 'input' or 'channel_index' field in /active "
                                 "for Output {} channel {}".format(output.id, outputChannelIndex))
            raise NMOSTestException(res)
        return inputID, inputChannelIndex

    def getInput(self, output, outputChannelIndex):
        inputID, inputChannelIndex = self.getInputIDChannelIndex(output, outputChannelIndex)
        return ACMInput(inputID)

    def assertActionsCompleted(self, actions):
        for action in actions:
            outputChannelIndex = action.outputChannel
            output = ACMOutput(action.outputID)
            inputID, inputChannelIndex = self.getInputIDChannelIndex(output, action.outputChannel)
            input = self.getInput(output, outputChannelIndex)

            if action.inputID != input.id:
                res = self.test.FAIL("Did not get expected input channel index in active "
                                     "map, expected {}, got {} for Output {} channel {}"
                                     .format(
                                        action.inputChannel,
                                        inputChannelIndex,
                                        output.id,
                                        outputChannelIndex
                                     ))
                raise NMOSTestException(res)
            if action.inputChannel != inputChannelIndex:
                res = self.test.FAIL("Did not get expected input channel ID in active "
                                     "map, expected {}, got {} for Output {} channel {}"
                                     .format(
                                         action.inputID,
                                         input.id,
                                         output.id,
                                         outputChannelIndex
                                     ))
                raise NMOSTestException(res)

    def getUnrouteAllActionsForOutput(self, output):
        channels = len(output.getChannelList())
        return [Action(None, output.id, None, i) for i in range(0, channels)]

    def getRouteBlockActionsForInputOutput(self, input, output, blockNumber=0, reverse=False):
        if input.id is None:
            res = self.test.FAIL("Expected routable Input for Output {}, got null".format(output.id))
            raise NMOSTestException(res)
        channels = len(output.getChannelList())
        block = input.getBlockSize()
        # note, doesn't handle the case where channels is not a multiple of block
        offset = blockNumber * block
        if reverse:
            return [Action(input.id, output.id, offset + i % block, channels - i - 1) for i in range(0, channels)]
        else:
            return [Action(input.id, output.id, offset + i % block, i) for i in range(0, channels)]

    def getAcceptableActionsForOutput(self, output):
        """Find an acceptable set of actions that would change the Output's active map"""

        activeMap = self.getOutputMap(output)

        routableInputs = output.getRoutableInputList()

        # if unrouted channels are supported
        if None in routableInputs:
            # if any are currently routed, then unroute all
            for outputChannel in activeMap:
                if activeMap[outputChannel]['input'] is not None:
                    print(" * Unrouting Output {}".format(output.id))
                    return self.getUnrouteAllActionsForOutput(output)
            # otherwise, route the first block of the first routable input
            # (if the first one is null, the second shouldn't be)
            routableInput = routableInputs[0] or routableInputs[1]
            input = ACMInput(routableInput)
            print(" * Routing Input {} on Output {}".format(input.id, output.id))
            return self.getRouteBlockActionsForInputOutput(input, output)
        else:
            # if there is more than one routable input, route a different one
            activeInput = activeMap[str(0)]['input']
            for routableInput in routableInputs:
                if routableInput != activeInput:
                    input = ACMInput(routableInput)
                    print(" * Switching to Input {} on Output {}".format(input.id, output.id))
                    return self.getRouteBlockActionsForInputOutput(input, output)
            # otherwise, only a single input to work with...
            input = ACMInput(activeInput)
            blockSize = input.getBlockSize()
            if blockSize < len(input.getChannelList()):
                # if the input has more than one block, route a different one
                activeBlock = activeMap[str(0)]['channel_index'] / blockSize
                print(" * Switching channels of Input {} on Output {}".format(input.id, output.id))
                return self.getRouteBlockActionsForInputOutput(input, output, blockNumber=0 if activeBlock else 1)
            elif len(input.getChannelList()) > 1 and input.getReordering():
                # if the input supports reordering, do so
                activeChannel = activeMap[str(0)]['channel_index']
                print(" * Reordering channels of Input {} on Output {}".format(input.id, output.id))
                return self.getRouteBlockActionsForInputOutput(input, output, reverse=activeChannel == 0)
            else:
                res = self.test.UNCLEAR("This test cannot run automatically as the routing constraints "
                                        "for Output {} are not currently supported by the test suite"
                                        .format(output.id))
                raise NMOSTestException(res)

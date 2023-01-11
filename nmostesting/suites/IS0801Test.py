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

import time
import copy

from ..GenericTest import GenericTest, NMOSTestException
from ..TestHelper import compare_json
from ..IS05Utils import IS05Utils, SCHEDULED_ABSOLUTE_ACTIVATION, SCHEDULED_RELATIVE_ACTIVATION
from .is08.action import Action
from .is08.activation import Activation
from .is08.inputs import getInputList
from .is08.outputs import getOutputList
from .is08.active import Active
from .is08.io import IO
from .is08.testConfig import globalConfig


MAPPING_API_KEY = "channelmapping"


class IS0801Test(GenericTest):
    """
    Runs IS-08-01-Test
    """

    def __init__(self, apis):
        # Don't auto-test /map/active/{outputId} as the tests cannot find the {outputId}s automatically
        omit_paths = [
            "/map/active/{outputId}"
        ]
        GenericTest.__init__(self, apis, omit_paths)
        globalConfig.apiUrl = apis[MAPPING_API_KEY]['url']
        globalConfig.testSuite = self
        globalConfig.apiKey = MAPPING_API_KEY

    def test_01(self, test):
        """Content of the /io view matches resources elsewhere in the API"""
        globalConfig.test = test

        inputList = getInputList()
        outputList = getOutputList()
        ioInstance = IO()
        ioJSON = ioInstance.getIOAsJSON()

        mockIoResource = {"inputs": {}, "outputs": {}}

        for input in inputList:
            mockIoResource["inputs"][input.id] = input.assembleInputObject()

        for output in outputList:
            mockIoResource["outputs"][output.id] = output.assembleOutputObject()

        if compare_json(mockIoResource, ioJSON):
            return test.PASS()
        else:
            return test.FAIL("IO Resource does not correctly reflect the API resources")

    def test_02(self, test):
        """Immediate activation can be called on the API"""
        globalConfig.test = test

        outputList = getOutputList()
        if len(outputList) == 0:
            return test.UNCLEAR("Not tested. No resources found.")

        active = Active()

        activation = Activation()
        for output in outputList:
            activation.addActions(active.getAcceptableActionsForOutput(output))
        activation.fireActivation()

        active.assertActionsCompleted(activation.getActions())
        return test.PASS()

    def test_03(self, test):
        """Relative offset activations can be called on the API"""
        globalConfig.test = test

        self.check_delayed_activation(SCHEDULED_RELATIVE_ACTIVATION)

        return test.PASS()

    def test_04(self, test):
        """Absolute offset activations can be called on the API"""
        globalConfig.test = test

        self.check_delayed_activation(SCHEDULED_ABSOLUTE_ACTIVATION)

        return test.PASS()

    def test_05(self, test):
        """Activations can be deleted once created"""
        globalConfig.test = test

        outputList = getOutputList()
        if len(outputList) == 0:
            return test.UNCLEAR("Not tested. No resources found.")
        output = outputList[0]

        activation = Activation()
        activation.addActions(Active().getAcceptableActionsForOutput(output))
        activation.type = SCHEDULED_RELATIVE_ACTIVATION
        activation.activationTimestamp = "2:0"
        try:
            activation.fireActivation()
        except NMOSTestException as e:
            time.sleep(2)
            raise e

        time.sleep(1)

        activation.delete()

        return test.PASS()

    def test_06(self, test):
        """Attempting to change a locked route results in a 423 response"""
        globalConfig.test = test

        outputList = getOutputList()
        if len(outputList) == 0:
            return test.UNCLEAR("Not tested. No resources found.")
        output = outputList[0]

        activation = Activation()
        activation.addActions(Active().getAcceptableActionsForOutput(output))
        activation.type = SCHEDULED_RELATIVE_ACTIVATION
        activation.activationTimestamp = "5:0"
        activation.fireActivation()
        activation.checkLock()
        activation.delete()

        return test.PASS()

    def test_07(self, test):
        """Channels in the active resource where no input channel is routed have null
        set as the 'input' and 'channel_index'"""
        globalConfig.test = test

        active = Active()

        outputList = getOutputList()
        if len(outputList) == 0:
            return test.UNCLEAR("Not tested. No resources found.")

        for outputInstance in outputList:
            channelList = outputInstance.getChannelList()
            for channelIndex in range(0, len(channelList)):
                inputID, inputChannelIndex = active.getInputIDChannelIndex(
                    outputInstance,
                    channelIndex
                )
                if (inputID is None) != (inputChannelIndex is None):
                    msg = ("Both the input and channel index must be set "
                           "to null when a channel is not routed")
                    test.FAIL(msg)

        return test.PASS()

    def test_08(self, test):
        """If the device allows re-entrant  matrices, the constraints are set such that it
        is not possible to create a loop"""
        globalConfig.test = test

        forbiddenRoutes = []
        outputList = getOutputList()
        inputList = getInputList()
        if len(inputList) == 0 or len(outputList) == 0:
            return test.UNCLEAR("Not tested. No resources found.")

        for outputInstance in outputList:
            sourceID = outputInstance.getSourceID()
            for inputInstance in inputList:
                inputParent = inputInstance.getParent()
                if inputParent['type'] == "source" and sourceID == inputParent['id']:
                    route = {
                        "input": inputInstance,
                        "output": outputInstance
                    }
                    forbiddenRoutes.append(route)

        for route in forbiddenRoutes:
            outputCaps = route['output'].getCaps()
            msg = ("It is possible to create a loop using re-entrant matrices "
                   "between Input {} and Output {}".format(route['input'].id, route['output'].id))
            try:
                routableInputs = outputCaps['routable_inputs']
            except KeyError:
                return test.FAIL("Could not find 'routable_inputs' in /caps "
                                 "for Output {}".format(route['output'].id))
            if routableInputs is None or route['input'].id in routableInputs:
                return test.FAIL(msg)
        return test.PASS()

    def test_09(self, test):
        """Human readable name provided in the properties resource"""
        return test.MANUAL()

    def test_10(self, test):
        """Human readable description provided in the properties resource"""
        return test.MANUAL()

    def test_11(self, test):
        """Inputs have at least one channel represented in their channels resource"""
        globalConfig.test = test
        inputList = getInputList()
        if len(inputList) == 0:
            return test.UNCLEAR("Not tested. No resources found.")
        for inputInstance in inputList:
            channels = inputInstance.getChannelList()
            if len(channels) == 0:
                return test.FAIL("Inputs must have at least one channel")
        return test.PASS()

    def test_12(self, test):
        """Outputs have at least one channel represented in their channels resource"""
        globalConfig.test = test
        outputList = getOutputList()
        if len(outputList) == 0:
            return test.UNCLEAR("Not tested. No resources found.")
        for outputInstance in outputList:
            channels = outputInstance.getChannelList()
            if len(channels) == 0:
                return test.FAIL("Outputs must have at least one channel")
        return test.PASS()

    def test_13(self, test):
        """Attempting to violate routing constraints results in an HTTP 400 response"""
        globalConfig.test = test

        outputList = getOutputList()
        inputList = getInputList()

        if len(inputList) == 0 and len(outputList) == 0:
            return test.UNCLEAR("Not tested. No resources found.")

        constrainedOutputList = []
        for outputInstance in outputList:
            outputCaps = outputInstance.getCaps()
            try:
                routableInputs = outputCaps['routable_inputs']
            except KeyError:
                return test.FAIL("Could not find 'routable_inputs' in /caps "
                                 "for Output {}".format(outputInstance.id))
            if routableInputs is not None:
                constrainedOutputList.append(
                    {
                        "output": outputInstance,
                        "routableInputs": routableInputs
                    }
                )

        if len(constrainedOutputList) == 0:
            return test.UNCLEAR("Could not test - no outputs have routing constraints set.")

        inputIDList = [None]
        for inputInstance in inputList:
            inputIDList.append(inputInstance.id)

        for constrainedOutput in constrainedOutputList:
            forbiddenRoutes = copy.deepcopy(inputIDList)

            for routableInputID in constrainedOutput['routableInputs']:
                forbiddenRoutes.remove(routableInputID)

            if len(forbiddenRoutes) > 0:

                action = Action(forbiddenRoutes[0], constrainedOutput['output'].id)
                activation = Activation()
                activation.addAction(action)

                try:
                    activation.checkReject()
                    return test.PASS()
                except NMOSTestException:
                    msg = ("Was able to create a forbidden route between Input {} "
                           "and Output {} despite routing constraint."
                           .format(forbiddenRoutes[0], outputInstance.id))
                    return test.FAIL(msg)
        return test.UNCLEAR("Could not test - no route is forbidden.")

    def test_14(self, test):
        """It is not possible to re-order channels when re-ordering is set to false"""
        globalConfig.test = test

        inputList = getInputList()
        if len(inputList) == 0:
            return test.UNCLEAR("Not tested. No resources found.")

        constrainedInputs = []
        constraintSet = False
        for inputInstance in inputList:
            if not inputInstance.getReordering():
                constrainedInputs.append(inputInstance)
                constraintSet = True

        if not constraintSet:
            return test.UNCLEAR("No inputs prevent re-ordering.")

        # Filter out inputs where the constraint can't be tested because the
        # block size prevents re-ordering anyway
        filteredInputs = []
        for inputInstance in constrainedInputs:
            blockSize = inputInstance.getBlockSize()
            if len(inputInstance.getChannelList()) >= blockSize * 2:
                # Constraint makes no sense, can't re-order to to block size
                filteredInputs.append(inputInstance)

        # Filter out inputs where there is no output that channels could be
        # re-ordered into
        targetOutputList = {}
        testableInputs = []
        for inputInstance in filteredInputs:
            routableOutputList = inputInstance.getRoutableOutputs()
            for outputInstance in routableOutputList:
                if len(outputInstance.getChannelList()) >= inputInstance.getBlockSize() * 2:
                    targetOutputList[inputInstance.id] = outputInstance
            if inputInstance.id in targetOutputList.keys():
                testableInputs.append(inputInstance)

        # Cross over blocks one and two on an input and output
        # e.g for a block size of 2:
        # IN            OUT
        # 0 ____   ____ 0
        # 1 ___ \ / ___ 1
        #      \ X /
        #       X X
        # 2 ___/ X \___ 2
        # 3 ____/ \____ 3
        activation = Activation()
        for inputInstance in testableInputs:
            for inputChannelIndex in range(0, inputInstance.getBlockSize()):
                outputChannelIndex = inputChannelIndex + blockSize
                blockOneAction = Action(
                    inputInstance.id,
                    targetOutputList[inputInstance.id].id,
                    inputChannelIndex,
                    outputChannelIndex
                )
                blockTwoAction = Action(
                    inputInstance.id,
                    targetOutputList[inputInstance.id].id,
                    outputChannelIndex,
                    inputChannelIndex
                )
                activation.addAction(blockOneAction)
                activation.addAction(blockTwoAction)

        try:
            activation.fireActivation()
        except NMOSTestException:
            return test.PASS()

        return test.FAIL("Channels could be re-ordered despite re-ordering constraint.")

    def test_15(self, test):
        """It is not possible to make an out-of-block route when block_size
        is anything other than 1"""
        globalConfig.test = test

        inputList = getInputList()
        if len(inputList) == 0:
            return test.UNCLEAR("Not tested. No resources found.")

        constraintSet = False
        constrainedInputs = []
        for inputInstance in inputList:
            if inputInstance.getBlockSize() > 1:
                constraintSet = True
                constrainedInputs.append(inputInstance)

        if not constraintSet:
            return test.UNCLEAR("No inputs constrain by block.")

        chosenInput = constrainedInputs[0]
        output = chosenInput.getRoutableOutputs()
        actions = [
            Action(chosenInput.id, output[0].id, 0, 0),
            Action(chosenInput.id, output[0].id, 0, 1),
        ]
        activation = Activation()
        activation.addActions(actions)
        try:
            activation.fireActivation()
        except NMOSTestException:
            return test.PASS()

        return test.FAIL("Was able to break block size routing constraint")

    def check_delayed_activation(self, activationType):
        active = Active()
        preActivationState = active.buildJSONObject()

        outputList = getOutputList()
        if len(outputList) == 0:
            res = globalConfig.test.UNCLEAR("Not tested. No resources found.")
            raise NMOSTestException(res)
        output = outputList[0]

        active = Active()

        activation = Activation()
        for output in outputList:
            activation.addActions(active.getAcceptableActionsForOutput(output))

        activation.type = activationType
        if activationType == SCHEDULED_RELATIVE_ACTIVATION:
            activation.activationTimestamp = "2:0"
        elif activationType == SCHEDULED_ABSOLUTE_ACTIVATION:
            activation.activationTimestamp = IS05Utils.get_TAI_time(offset=2.0)
        try:
            activation.fireActivation()
        except NMOSTestException as e:
            time.sleep(3)
            raise e

        pendingState = active.buildJSONObject()
        if not compare_json(preActivationState, pendingState):
            res = globalConfig.test.FAIL("Scheduled Activation completed immediately")
            raise NMOSTestException(res)

        time.sleep(3)

        active.assertActionsCompleted(activation.getActions())

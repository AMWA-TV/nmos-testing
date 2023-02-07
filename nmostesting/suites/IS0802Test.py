# Copyright 2019 Advanced Media Workflow Association
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


from requests.compat import json

from ..GenericTest import GenericTest, NMOSTestException
from .is08.testConfig import globalConfig
from .is08.activation import Activation
from .is08.active import Active
from .is08.outputs import getOutputList
from .is08.inputs import getInputList
from ..NMOSUtils import NMOSUtils

MAPPING_API_KEY = "channelmapping"
NODE_API_KEY = "node"


class IS0802Test(GenericTest):
    """
    Runs Tests covering both IS-04 and IS-05
    """

    def __init__(self, apis, auths, **kwargs):
        # Don't auto-test /map/active/{outputId} as the tests cannot find the {outputId}s automatically
        omit_paths = [
            "/map/active/{outputId}"
        ]
        GenericTest.__init__(self, apis, omit_paths, auths=auths, **kwargs)
        globalConfig.apiUrl = apis[MAPPING_API_KEY]['url']
        globalConfig.testSuite = self
        globalConfig.apiKey = MAPPING_API_KEY
        self.is05_resources = {"senders": [], "receivers": [], "devices": [], "sources": [], "_requested": []}
        self.is04_resources = {"senders": [], "receivers": [], "devices": [], "sources": [], "_requested": []}
        self.node_url = self.apis[NODE_API_KEY]["url"]

    def test_01(self, test):
        """ Activations result in a Device version number increment"""
        globalConfig.test = test

        devicesWithAdvertisements = self.find_device_advertisement()

        versionNumbersBeforeActivation = []
        for device in devicesWithAdvertisements:
            versionNumbersBeforeActivation.append(device['version'])

        outputList = getOutputList()
        if len(outputList) == 0:
            res = globalConfig.test.UNCLEAR("Not tested. No resources found.")
            raise NMOSTestException(res)
        output = outputList[0]

        activation = Activation()
        activation.addActions(Active().getAcceptableActionsForOutput(output))
        activation.fireActivation()

        versionIncremented = False

        counter = 0

        devicesWithAdvertisements = self.find_device_advertisement()

        for device in devicesWithAdvertisements:
            if device['version'] != versionNumbersBeforeActivation[counter]:
                versionIncremented = True

        if versionIncremented:
            return test.PASS()
        else:
            return test.FAIL("No devices in the Node API incremented version number on activation.")

    def test_02(self, test):
        """ API is correctly advertised as a control endpoint"""
        globalConfig.test = test

        if len(self.find_device_advertisement()) > 0:
            return test.PASS()
        return test.FAIL("Could not find a Device advertisement for the Channel Mapping API")

    def test_03(self, test):
        """ All Output Source IDs match up to the IS-04 Node API"""
        globalConfig.test = test

        outputList = getOutputList()
        allSourcesRegistered = True
        for outputInstance in outputList:
            sourceRegistered = False
            sourceID = outputInstance.getSourceID()
            if sourceID is None:
                sourceRegistered = True
            else:
                sourceRegistered = self.findSourceID(sourceID)
            if not sourceRegistered:
                allSourcesRegistered = False

        if allSourcesRegistered:
            return test.PASS()
        else:
            return test.FAIL("Not all Output sources IDs were advertised in the Node API")

    def test_04(self, test):
        """All Input Source/Receiver IDs match up to the IS-04 Node API"""
        globalConfig.test = test

        inputList = getInputList()
        allIdsRegistered = True
        for inputInstance in inputList:
            idRegistered = False
            parent = inputInstance.getParent()
            if parent['type'] == "source":
                idRegistered = self.findSourceID(parent['id'])
            elif parent['type'] == "receiver":
                idRegistered = self.findReceiverID(parent['id'])
            else:
                idRegistered = True
            if not idRegistered:
                allIdsRegistered = False

        if allIdsRegistered:
            return test.PASS()
        else:
            return test.FAIL("Not all Input Sources/Receivers are present in the Node API.")

    def get_is04_resources(self, resource_type):
        """Retrieve all Senders or Receivers from a Node API, keeping hold of the returned objects"""
        assert resource_type in ["senders", "receivers", "devices", "sources"]

        # Prevent this being executed twice in one test run
        if resource_type in self.is04_resources["_requested"]:
            return True, ""

        valid, resources = self.do_request("GET", self.node_url + resource_type)
        if not valid:
            return False, "Node API did not respond as expected: {}".format(resources)

        try:
            for resource in resources.json():
                self.is04_resources[resource_type].append(resource)
            self.is04_resources["_requested"].append(resource_type)
        except json.JSONDecodeError:
            return False, "Non-JSON response returned from Node API"

        return True, ""

    def refresh_is04_resources(self, resource_type):
        """Force a re-retrieval of the IS-04 Senders, Receivers or Devices, bypassing the cache"""
        if resource_type in self.is04_resources["_requested"]:
            self.is04_resources["_requested"].remove(resource_type)
            self.is04_resources[resource_type] = []

        return self.get_is04_resources(resource_type)

    def find_device_advertisement(self):
        test = globalConfig.test

        valid, result = self.refresh_is04_resources("devices")
        if not valid:
            raise NMOSTestException(test.FAIL(result))

        devicesWithAdvertisements = []
        found_api_match = False
        for device in self.is04_resources["devices"]:
            for control in device['controls']:
                if control['type'] == "urn:x-nmos:control:cm-ctrl/v1.0":
                    if device not in devicesWithAdvertisements:
                        devicesWithAdvertisements.append(device)
                    if NMOSUtils.compare_urls(globalConfig.apiUrl, control["href"]) and \
                            self.authorization is control.get("authorization", False):
                        found_api_match = True

        if len(devicesWithAdvertisements) > 0 and not found_api_match:
            raise NMOSTestException(test.FAIL("Found one or more Device controls, but no href and authorization mode "
                                              "matched the Channel Mapping API under test"))

        return devicesWithAdvertisements

    def findSourceID(self, sourceID):
        if not self.get_is04_resources("sources"):
            raise NMOSTestException(globalConfig.test.FAIL("Could not get sources from Node API"))
        registrySources = self.is04_resources["sources"]
        for source in registrySources:
            if source['id'] == sourceID:
                return True
        return False

    def findReceiverID(self, receiverID):
        if not self.get_is04_resources("receivers"):
            raise NMOSTestException(globalConfig.test.FAIL("Could not get receivers from Node API"))
        registryReceivers = self.is04_resources["receivers"]
        for receiver in registryReceivers:
            if receiver['id'] == receiverID:
                return True
        return False

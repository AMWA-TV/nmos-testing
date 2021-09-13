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

from ..GenericTest import GenericTest
from ..IS11Utils import IS11Utils
from .. import Config as CONFIG

SINIK_MP_API_KEY = "sink-mp"


class IS1101Test(GenericTest):
    """
    Runs IS-11-01-Test
    """

    def __init__(self, apis):
        omit_paths = [
            "/sinks/{sinkId}/edid" # Does not have a schema
        ]
        GenericTest.__init__(self, apis, omit_paths)
        self.url = self.apis[SINIK_MP_API_KEY]["url"]
        self.is11_utils = IS11Utils(self.url)

    def set_up_tests(self):
        self.senders = self.is11_utils.get_senders()
        self.receivers = self.is11_utils.get_receivers()
        self.sinks = self.is11_utils.get_sinks()

    def test_01(self, test):
        """Senders Media Profile's SHOULD initially be empty"""

        if len(self.senders) <= 0:
            return test.UNCLEAR("Not tested. No resources found.")

        senders_not_empty = []
        for sender in self.senders:
            valid, media_profiles = self.is11_utils.get_media_profiles(sender)
            if not valid:
                return test.FAIL(media_profiles)
            if media_profiles != []:
                senders_not_empty.append(sender)

        if len(senders_not_empty) > 0:
            return test.WARNING("Some Senders presented a non-empty Media Profiles.")

        return test.PASS()

    def test_02(self, test):
        """Senders accept valid Media Profile"""

        if len(self.senders) <= 0:
            return test.UNCLEAR("Not tested. No resources found.")

        media_profile = {
            "frame_height": CONFIG.MEDIA_PROFILES_PREFERENCES["video_height"],
            "frame_width": CONFIG.MEDIA_PROFILES_PREFERENCES["video_width"],
            "grain_rate": CONFIG.MEDIA_PROFILES_PREFERENCES["video_exactframerate"],
            "interlace_mode": "interlaced_tff" if CONFIG.MEDIA_PROFILES_PREFERENCES["video_interlace"] else "progressive"
        }
        for sender in self.senders:
            valid, response = self.is11_utils.put_media_profiles(sender, data=[media_profile])
            if not valid:
                return test.FAIL("Sender {} rejected Media Profile: {}".format(sender, response))

        # Requires https://github.com/AMWA-TV/nmos-sink-metadata-processing/pull/25
        # schema = self.get_schema(SINIK_MP_API_KEY, "PUT", "/senders/{senderId}/media-profiles", response.status_code)
        # valid, message = self.check_response(schema, "PUT", response)
        # if not valid:
        #     return test.FAIL(message)
        # elif message:
        #     return test.WARNING(message)

        return test.PASS()

    def test_03(self, test):
        """Senders clears Media Profile on DELETE"""

        if len(self.senders) <= 0:
            return test.UNCLEAR("Not tested. No resources found.")

        for sender in self.senders:
            valid, response = self.is11_utils.delete_media_profiles(sender)
            if not valid:
                return test.FAIL("Sender {} failed to delete Media Profile: {}".format(sender, response))
            if response != []:
                return test.FAIL("Sender {} did not empty Media Profile: {}".format(sender, response))

            valid, media_profiles = self.is11_utils.get_media_profiles(sender)
            if not valid:
                return test.FAIL(media_profiles)
            if media_profiles != []:
                return test.FAIL("Sender {} did not empty Media Profile: {}".format(sender, response))

        return test.PASS()

    def test_04(self, test):
        """Receivers are associated to known Sinks"""

        if len(self.receivers) <= 0:
            return test.UNCLEAR("Not tested. No resources found.")

        missink_sink_resources = []
        for receiver in self.receivers:
            valid, sinks = self.is11_utils.get_associated_sinks(receiver)
            if not valid:
                return test.FAIL(sinks)
            for sink in sinks:
                if sink.rstrip("/") not in self.sinks:
                    missink_sink_resources.append(sink)

        if len(missink_sink_resources) > 0:
            return test.FAIL("Some associated Sinks were not present.")

        return test.PASS()

    def test_05(self, test):
        """Sinks expose a valid EDID"""
        # TODO: Possibly look into https://github.com/jojonas/pyedid

        return test.MANUAL()

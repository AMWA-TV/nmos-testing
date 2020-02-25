#!/usr/bin/env python3

# Copyright (C) 2020 Advanced Media Workflow Association
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

import argparse
import requests
from urllib.parse import urlparse
import re
import json
from pathlib import Path
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from gsheetsImport.resultsImporter import gsheets_import


SCOPES = ['https://spreadsheets.google.com/feeds',
          'https://www.googleapis.com/auth/drive']


def make_request(url):
    response = requests.get(url)

    if response.status_code not in [200]:
        print(f'Request: {url} response HTTP {response.status_code}')
        raise Exception

    return response


def parse_nmos_url(url):
    port = 80
    version = None
    selector = None

    try:
        result = urlparse(url)
        # Extract port from URL
        if result.port:
            port = result.port
        # Extract version from URL
        version = result.path.replace('/x-nmos/connection/', '').strip('/')
        urlPathSections = result.path.split('/')
        version = urlPathSections[3]
        selector = urlPathSections[4]

    except ValueError:
        print("URL could not be parsed: {}".format(url))
        return None, None

    return port, version, selector


def _split_version(version):
    major, minor = re.search('(\d+)\.(\d+)', version).groups()
    return int(major), int(minor)


def get_highest_version(data, key='version'):
    """Return the highest version in a list"""
    if not data:
        return None

    versions = (x[key] for x in data)
    highestVersion = max(versions, key=_split_version)

    data = next(item for item in data if item[key] == highestVersion)

    return data


def perform_test(test_suite_url, data):
    response = requests.post(test_suite_url + '/api', json=data)
    print(f'{data}')

    if response.status_code not in [200]:
        print(f'Request: {test_suite_url} response HTTP {response.status_code}')
        raise Exception

    return response.json()


def is_04_01_test(test_suite_url, node_ip, node_port, node_version, test_start_delay):
    """IS-04 Node API"""
    print(f'Running test IS-04-01:')
    print(f'    Node API {node_version} {node_ip}:{node_port}')

    if test_start_delay:
        data = {
            "DNS_SD_ADVERT_TIMEOUT": test_start_delay
        }
        response = requests.patch(test_suite_url + '/config', json=data)

        if response.status_code not in [200]:
            print(f'Request: {test_suite_url} response HTTP {response.status_code}')
            raise Exception

    body = {
        "suite": "IS-04-01",
        "host": [node_ip],
        "port": [node_port],
        "version": [node_version]
    }

    try:
        results = perform_test(test_suite_url, body)
        return results
    except Exception:
        print("ERROR: is_04_01_test failed")
        return None


def is_04_02_test(test_suite_url, reg_ip, reg_port, reg_version, query_ip, query_port, query_version):
    """IS-04 Registry API"""
    print(f'Running test IS-04-02:')
    print(f'    Registration API {reg_version} {reg_ip}:{reg_port}')
    print(f'    Query API {query_version} {query_ip}:{query_port}')

    body = {
        "suite": "IS-04-02",
        "host": [reg_ip, query_ip],
        "port": [reg_port, query_port],
        "version": [reg_version, query_version]
    }

    try:
        results = perform_test(test_suite_url, body)
        return results
    except Exception:
        print("ERROR: is_04_02_test failed")
        return None


def is_05_01_test(test_suite_url, connection_ip, connection_port, connection_version):
    """IS-05 Connection Management API"""
    print(f'Running test IS-05-01:')
    print(f'    Connection Management API {connection_version} {connection_ip}:{connection_port}')

    body = {
        "suite": "IS-05-01",
        "host": [connection_ip],
        "port": [connection_port],
        "version": [connection_version]
    }

    try:
        results = perform_test(test_suite_url, body)
        return results
    except Exception:
        print("ERROR: is_05_01_test failed")
        return None


def is_05_02_test(test_suite_url, node_ip, node_port, node_version, connection_ip, connection_port, connection_version):
    """IS-05 Interaction with IS-04"""
    print(f'Running test IS-05-02:')
    print(f'    Node API {node_version} {node_ip}:{node_port}')
    print(f'    Connection Management API {connection_version} {connection_ip}:{connection_port}')

    body = {
        "suite": "IS-05-02",
        "host": [node_ip, connection_ip],
        "port": [node_port, connection_port],
        "version": [node_version, connection_version]
    }

    try:
        results = perform_test(test_suite_url, body)
        return results
    except Exception:
        print("ERROR: is_05_02_test failed")
        return None


def is_08_01_test(test_suite_url, ch_map_ip, ch_map_port, ch_map_version, selector):
    """IS-08 Channel Mapping API"""
    print(f'Running test IS-08-01:')
    print(f'    Channel Mapping API {ch_map_version} {ch_map_ip}:{ch_map_port}  {selector}')

    body = {
        "suite": "IS-08-01",
        "host": [ch_map_ip],
        "port": [ch_map_port],
        "version": [ch_map_version],
        "selector": selector
    }

    try:
        results = perform_test(test_suite_url, body)
        return results
    except Exception:
        print("ERROR: is_08_01_test failed")
        return None


def is_08_02_test(test_suite_url, node_ip, node_port, node_version, ch_map_ip, ch_map_port, ch_map_version, selector):
    """IS-08 Interaction with IS-04"""
    print(f'Running test IS-08-02:')
    print(f'    Node API {node_version} {node_ip}:{node_port}')
    print(f'    Channel Mapping API {ch_map_version} {ch_map_ip}:{ch_map_port}  {selector}')

    body = {
        "suite": "IS-08-02",
        "host": [node_ip, ch_map_ip],
        "port": [node_port, ch_map_port],
        "version": [node_version, ch_map_port],
        "selector": selector
    }

    try:
        results = perform_test(test_suite_url, body)
        return results
    except Exception:
        print("ERROR: is_08_02_test failed")
        return None


def save_test_results_to_file(results, name, folder):
    """Save the JSON test results to the folder"""

    if not folder:
        print('ERROR: No folder specified')
        return
    if not results:
        print('ERROR: No results specified')
        return

    Path(folder).mkdir(parents=True, exist_ok=True)

    filename = f"{folder}{name}_{results.get('suite')}_{results.get('timestamp')}.json"

    with open(filename, 'w') as outfile:
        json.dump(results, outfile)


def upload_test_results(results, name, sheet, credentials):
    """Upload the test results to the the google sheet"""

    if not sheet:
        print('ERROR: No worksheet specified')
        return
    if not results:
        print('ERROR: No results specified')
        return

    credentials = ServiceAccountCredentials.from_json_keyfile_name(credentials, SCOPES)
    gcloud = gspread.authorize(credentials)

    spreadsheet = gcloud.open_by_url(sheet)

    try:
        worksheet = spreadsheet.worksheet(results["suite"])
    except gspread.exceptions.WorksheetNotFound:
        print(" * ERROR: Worksheet {} not found".format(results["suite"]))
        return

    filename = f"{name}_{results.get('suite')}_{results.get('timestamp')}.json"

    gsheets_import(results, worksheet, filename)


def run_all_tests(testSuiteUrl,
                  is04NodeData,
                  is04RegistryData,
                  is05Data,
                  is08Data,
                  deviceName=None,
                  resultsFolder=None,
                  resultsSheet=None,
                  credentials=None):

    # Find highest versions of each api
    is04NodeData = get_highest_version(is04NodeData)
    is04RegistryData = get_highest_version(is04RegistryData, key='reg-version')
    is05Data = get_highest_version(is05Data)
    is08Data = get_highest_version(is08Data)

    if is04NodeData:
        results = is_04_01_test(testSuiteUrl, is04NodeData['ip'], is04NodeData['port'], is04NodeData['version'],
                                is04NodeData['test-start-delay'])
        save_test_results_to_file(results, deviceName, resultsFolder)
        upload_test_results(results, deviceName, resultsSheet, credentials)
    if is05Data:
        results = is_05_01_test(testSuiteUrl, is05Data['ip'], is05Data['port'], is05Data['version'])
        save_test_results_to_file(results, deviceName, resultsFolder)
        upload_test_results(results, deviceName, resultsSheet, credentials)
    if is04NodeData and is05Data:
        results = is_05_02_test(testSuiteUrl, is04NodeData['ip'], is04NodeData['port'], is04NodeData['version'],
                                is05Data['ip'], is05Data['port'], is05Data['version'])
        save_test_results_to_file(results, deviceName, resultsFolder)
        upload_test_results(results, deviceName, resultsSheet, credentials)
    if is08Data:
        results = is_08_01_test(testSuiteUrl, is08Data['ip'], is08Data['port'], is08Data['version'],
                                is08Data.get('selector'))
        save_test_results_to_file(results, deviceName, resultsFolder)
        upload_test_results(results, deviceName, resultsSheet, credentials)
    if is04NodeData and is08Data:
        results = is_08_02_test(testSuiteUrl, is04NodeData['ip'], is04NodeData['port'], is04NodeData['version'],
                                is08Data['ip'], is08Data['port'], is08Data['version'], is08Data.get('selector'))
        save_test_results_to_file(results, deviceName, resultsFolder)
        upload_test_results(results, deviceName, resultsSheet, credentials)
    if is04RegistryData:
        results = is_04_02_test(testSuiteUrl, is04RegistryData['ip'], is04RegistryData['reg-port'],
                                is04RegistryData['reg-version'], is04RegistryData['ip'],
                                is04RegistryData['query-port'], is04RegistryData['query-version'],)
        save_test_results_to_file(results, deviceName, resultsFolder)
        upload_test_results(results, deviceName, resultsSheet, credentials)


def print_nmos_api_data(api_name, data):
    print(f"{api_name}:")
    for x in data:
        print(f"    Port: {x.get('port')}  Version: {x.get('version')} Selector: {x.get('selector')} "
              f"href: {x.get('href')}")


def automated_discovery(ip, port, version='v1.2'):
    is05Data = []
    is08Data = []

    base_url = f"http://{ip}:{port}/x-nmos/node/{version}/"

    # Devices. We assume that the same IP is used for all IS-05/08 instances
    url = base_url + "devices/"
    response = make_request(url)
    json_data = response.json()
    for device in json_data:
        for control in device["controls"]:
            if control["type"].startswith("urn:x-nmos:control:sr-ctrl"):
                port, version, selector = parse_nmos_url(control['href'])
                is05Data.append({
                    'ip': args.ip,
                    'port': port,
                    'version': version,
                    'href': control['href']
                })
            if control["type"].startswith("urn:x-nmos:control:cm-ctrl"):
                port, version, selector = parse_nmos_url(control["href"])
                is08Data.append({
                    'ip': args.ip,
                    'port': port,
                    'version': version,
                    'href': control['href'],
                    'selector': selector
                })

    return is05Data, is08Data


def parse_config_data(data):
    is05Data = []
    is08Data = []
    is04RegistryData = []

    if data.get('is05-port'):
        is05Data = [{
            'ip': data.get('node-ip'),
            'port': data.get('is05-port'),
            'version': data.get('is05-version', 'v1.0')
        }]

    if data.get('is08-port'):
        is08Data = [{
            'ip': data.get('node-ip'),
            'port': data.get('is08-port'),
            'version': data.get('is08-version', 'v1.0'),
            'selector': data.get('is08-selector')
        }]

    if data.get('is04-reg-port'):
        is04RegistryData = [{
            'ip': data.get('node-ip'),
            'reg-port': data.get('is04-reg-port'),
            'reg-version': data.get('is04-reg-version', 'v1.2'),
            'query-port': data.get('is04-query-port'),
            'query-version': data.get('is04-query-version', 'v1.2'),
        }]

    return is05Data, is08Data, is04RegistryData


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", required=True, help="URL of the testing tool, eg. http://localhost:5000")
    parser.add_argument("--ip", required=True, help="IP address or Hostname of the DuT")
    parser.add_argument("--port", type=int, default=80, help="Port number of IS-04 API of DuT")
    parser.add_argument("--version", default="v1.2", help="Version of IS-04 API of DuT")

    # Manual checking
    parser.add_argument("--config", help="JSON string of config, defines tests to be run, NMOS API ports and versions")

    args = parser.parse_args()

    nmosApis = []
    is04NodeData = [{
        'ip': args.ip,
        'port': args.port,
        'version': args.version,
        'test-start-delay': 31,
    }]
    is04RegistryData = []
    is05Data = []
    is08Data = []
    resultsFolder = "test/"
    resultsSheet = None
    deviceName = "TestDevice"
    credentials = None

    if args.config:
        print(args.config)
        config = json.loads(args.config)
        print(config)
        is05Data, is08Data, is04RegistryData = parse_config_data(config)

        is04NodeData[0]['test-start-delay'] = config.get('test-start-delay', 29)

        # If testing a registry, remove Node config
        if is04RegistryData:
            is04NodeData = []

        if config.get('results-sheet'):
            resultsSheet = config.get('results-sheet')
            print(f'Test results will be uploaded to {resultsSheet}')
        if config.get('results-folder'):
            resultsFolder = config.get('results-folder')
            print(f'Results files will be stored in: {resultsFolder}')
        if config.get('device-name'):
            deviceName = config.get('device-name')
            print(f'Device Name: {deviceName}')
        credentials = config.get('credentials', 'credentials.json')
    else:
        is05Data, is08Data = automated_discovery(is04NodeData[0]['ip'], is04NodeData[0]['port'],
                                                 is04NodeData[0]['version'])

    # Display Data
    print_nmos_api_data('IS-04', is04NodeData)
    print_nmos_api_data('IS-05', is05Data)
    print_nmos_api_data('IS-08', is08Data)

    run_all_tests(args.test, is04NodeData, is04RegistryData, is05Data, is08Data, deviceName, resultsFolder,
                  resultsSheet, credentials)

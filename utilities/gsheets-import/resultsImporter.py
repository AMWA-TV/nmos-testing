#!/usr/bin/python

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

import argparse
import gspread
import json
import sys

from oauth2client.service_account import ServiceAccountCredentials

GOOGLE_SHEET_URL = ""

SCOPES = ['https://spreadsheets.google.com/feeds',
          'https://www.googleapis.com/auth/drive']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True)
    args = parser.parse_args()

    credentials = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPES)
    gcloud = gspread.authorize(credentials)

    spreadsheet = gcloud.open_by_url(GOOGLE_SHEET_URL)

    with open(args.json) as json_file:
        test_results = json.load(json_file)

    try:
        worksheet = spreadsheet.worksheet(test_results["suite"])
    except gspread.exceptions.WorksheetNotFound:
        print(" * ERROR: Worksheet {} not found".format(test_results["suite"]))
        sys.exit(1)

    populated_rows = len(worksheet.get_all_values())
    current_row = populated_rows + 1

    # Test Names
    start_cell_addr = gspread.utils.rowcol_to_a1(1, 5)
    end_cell_addr = gspread.utils.rowcol_to_a1(1, 9+len(test_results["results"]))
    cell_list_names = worksheet.range("{}:{}".format(start_cell_addr, end_cell_addr))

    # Results
    start_cell_addr = gspread.utils.rowcol_to_a1(current_row, 5)
    end_cell_addr = gspread.utils.rowcol_to_a1(current_row, 9+len(test_results["results"]))
    cell_list_results = worksheet.range("{}:{}".format(start_cell_addr, end_cell_addr))

    # Col 1-4 reserved for device details
    current_index = 0
    cell_list_names[current_index].value = "Filename"
    cell_list_results[current_index].value = args.json
    current_index += 1
    cell_list_names[current_index].value = "URL Tested"
    cell_list_results[current_index].value = test_results["url"]
    current_index += 1
    cell_list_names[current_index].value = "Timestamp"
    cell_list_results[current_index].value = test_results["timestamp"]
    current_index += 1
    cell_list_names[current_index].value = "Test Suite"
    cell_list_results[current_index].value = test_results["suite"]

    current_index += 1

    for result in test_results["results"]:
        cell_contents = result["state"]
        if result["detail"] != "":
            cell_contents += " (" + result["detail"] + ")"
        cell_list_names[current_index].value = result["name"]
        cell_list_results[current_index].value = cell_contents
        current_index += 1

    worksheet.update_cells(cell_list_names)
    worksheet.update_cells(cell_list_results)


if __name__ == '__main__':
    main()

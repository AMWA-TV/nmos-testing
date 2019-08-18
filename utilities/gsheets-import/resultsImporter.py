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
from gspread import Cell
import json
import sys

from oauth2client.service_account import ServiceAccountCredentials

GOOGLE_SHEET_URL = ""

SCOPES = ['https://spreadsheets.google.com/feeds',
          'https://www.googleapis.com/auth/drive']

READ_ONLY_COL_OFFSET = 4
TEST_DATA_COL_OFFSET = READ_ONLY_COL_OFFSET + 4


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

    current_worksheet_data = worksheet.get_all_values()
    populated_rows = len(current_worksheet_data)
    current_row = populated_rows + 1

    if populated_rows < 2:
        # Blank spreadsheet
        current_number_columns = TEST_DATA_COL_OFFSET
        current_row = 3
    else:
        current_number_columns = len(current_worksheet_data[0])
        if current_number_columns < TEST_DATA_COL_OFFSET:
            current_number_columns = TEST_DATA_COL_OFFSET

    # Test Names
    start_cell_addr = gspread.utils.rowcol_to_a1(1, 1)
    end_cell_addr = gspread.utils.rowcol_to_a1(1, current_number_columns)
    cell_list_names = worksheet.range("{}:{}".format(start_cell_addr, end_cell_addr))

    # Results
    start_cell_addr = gspread.utils.rowcol_to_a1(current_row, 1)
    end_cell_addr = gspread.utils.rowcol_to_a1(current_row, current_number_columns)
    cell_list_results = worksheet.range("{}:{}".format(start_cell_addr, end_cell_addr))

    # Col 1-4 reserved for device details
    current_index = READ_ONLY_COL_OFFSET
    cell_list_names[current_index].value = "Filename"
    cell_list_results[current_index].value = args.json
    current_index += 1
    cell_list_names[current_index].value = "URLs Tested"
    urls_tested = []
    try:
        for endpoint in test_results["endpoints"]:
            urls_tested.append("{}:{} ({})".format(endpoint["host"], endpoint["port"], endpoint["version"]))
        cell_list_results[current_index].value = ", ".join(urls_tested)
    except Exception:
        print("JSON file does not support endpoints key")
        cell_list_results[current_index].value = test_results["url"]
    current_index += 1
    cell_list_names[current_index].value = "Timestamp"
    cell_list_results[current_index].value = test_results["timestamp"]
    current_index += 1
    cell_list_names[current_index].value = "Test Suite"
    cell_list_results[current_index].value = test_results["suite"]

    for result in test_results["results"]:
        cell_contents = result["state"]
        if result["detail"] != "":
            cell_contents += " (" + result["detail"] + ")"
        try:
            index = current_worksheet_data[0].index(result["name"])
            cell_list_results[index].value = cell_contents
        except (ValueError, IndexError):
            # Test name not found, add column
            current_number_columns += 1
            cell_list_names.append(Cell(1, current_number_columns, result["name"]))
            cell_list_results.append(Cell(current_row, current_number_columns, cell_contents))

    worksheet.update_cells(cell_list_names)
    worksheet.update_cells(cell_list_results)


if __name__ == '__main__':
    main()

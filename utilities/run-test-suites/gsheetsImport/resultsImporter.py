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
import datetime
import gspread
import json
import sys

from oauth2client.service_account import ServiceAccountCredentials

SCOPES = ['https://spreadsheets.google.com/feeds',
          'https://www.googleapis.com/auth/drive']


# Test states grouped by severity
TEST_STATES = ["Pass", "Fail", "Warning", "Not Implemented", "Test Disabled", "Could Not Test", "Manual",
               "Not Applicable"]


def gsheets_import(test_results, worksheet, filename, start_col=1):
    """Upload results data to spreadsheet"""

    worksheet_data = worksheet.get_all_values()
    populated_rows = len(worksheet_data)
    if populated_rows == 0:
        # Blank spreadsheet, row 1 will be for column titles
        current_row = 2
    else:
        current_row = populated_rows+1

    # Columns before start_col reserved for manually entered details
    start_col = max(1, start_col)

    # Columns for Filename, URLs Tested, Timestamp, Test Suite
    metadata_cols = 4
    # Columns for counts of Tests, and each Test Status
    state_cols = 1+len(TEST_STATES)

    # First results column
    results_col = start_col+metadata_cols+state_cols

    # Column after last results
    if populated_rows == 0:
        # Blank spreadsheet
        next_col = results_col
    else:
        next_col = max(results_col, len(worksheet_data[0])+1)

    # Test Names
    start_cell_addr = gspread.utils.rowcol_to_a1(1, 1)
    end_cell_addr = gspread.utils.rowcol_to_a1(1, next_col)
    cell_list_names = worksheet.range("{}:{}".format(start_cell_addr, end_cell_addr))[:-1]

    # Results
    start_cell_addr = gspread.utils.rowcol_to_a1(current_row, 1)
    end_cell_addr = gspread.utils.rowcol_to_a1(current_row, next_col)
    cell_list_results = worksheet.range("{}:{}".format(start_cell_addr, end_cell_addr))[:-1]

    # Columns for Filename, URLs Tested, Timestamp, Test Suite
    current_index = start_col-1  # list is 0-indexed whereas rows/cols are 1-indexed
    cell_list_names[current_index].value = "Filename"
    cell_list_results[current_index].value = filename
    current_index += 1
    cell_list_names[current_index].value = "URLs Tested"
    try:
        urls_tested = []
        for endpoint in test_results["endpoints"]:
            urls_tested.append("{}:{} ({})".format(endpoint["host"], endpoint["port"], endpoint["version"]))
        cell_list_results[current_index].value = ", ".join(urls_tested)
    except Exception:
        print(" * WARNING: JSON file does not include endpoints")
        cell_list_results[current_index].value = test_results["url"]
    current_index += 1
    cell_list_names[current_index].value = "Timestamp"
    cell_list_results[current_index].value = (datetime.datetime.utcfromtimestamp(test_results["timestamp"])
                                                               .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + 'Z')
    current_index += 1
    cell_list_names[current_index].value = "Test Suite"
    try:
        cell_list_results[current_index].value = "{} ({})".format(test_results["suite"],
                                                                  test_results["config"]["VERSION"])
    except Exception:
        print(" * WARNING: JSON file does not include test suite version")
        cell_list_results[current_index].value = test_results["suite"]

    # Columns for counts of Tests and each Test Status
    results_addr = "{}:{}".format(gspread.utils.rowcol_to_a1(current_row, results_col),
                                  gspread.utils.rowcol_to_a1(current_row, 1)[1:])

    current_index += 1
    cell_list_names[current_index].value = "Tests"
    # count non-empty cells on rest of this row
    cell_list_results[current_index].value = "=COUNTIF({}, \"?*\")".format(results_addr)
    for state in TEST_STATES:
        current_index += 1
        cell_list_names[current_index].value = state
        # count cells on the rest of this row that match this column's status
        current_col_addr = gspread.utils.rowcol_to_a1(1, cell_list_names[current_index].col)
        cell_list_results[current_index].value = "=COUNTIF({}, CONCAT({},\"*\"))" \
                                                 .format(results_addr, current_col_addr)

    # Columns for the Results
    for result in test_results["results"]:
        cell_contents = result["state"]
        if result["detail"] != "":
            cell_contents += " (" + result["detail"] + ")"
        col = next((cell.col for cell in cell_list_names if cell.value == result["name"]), None)
        if col:
            index = col-1  # list is 0-indexed whereas rows/cols are 1-indexed
            cell_list_results[index].value = cell_contents
        else:
            # Test name not found, append column (since gspread doesn't make it easy to insert one)
            col = cell_list_names[-1].col+1  # = cell_list_results[-1].col+1
            cell_list_names.append(gspread.Cell(1, col, result["name"]))
            cell_list_results.append(gspread.Cell(current_row, col, cell_contents))

    worksheet.update_cells(cell_list_names)
    # 'USER_ENTERED' allows formulae to be used
    worksheet.update_cells(cell_list_results, value_input_option='USER_ENTERED')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True)
    parser.add_argument("--sheet", required=True)
    parser.add_argument("--credentials", default="credentials.json")
    parser.add_argument("--start_col", default="1", type=int)
    args = parser.parse_args()

    credentials = ServiceAccountCredentials.from_json_keyfile_name(args.credentials, SCOPES)
    gcloud = gspread.authorize(credentials)

    spreadsheet = gcloud.open_by_url(args.sheet)

    with open(args.json) as json_file:
        test_results = json.load(json_file)

    try:
        worksheet = spreadsheet.worksheet(test_results["suite"])
    except gspread.exceptions.WorksheetNotFound:
        print(" * ERROR: Worksheet {} not found".format(test_results["suite"]))
        # could add_worksheet?
        sys.exit(1)

    gsheets_import(test_results, worksheet, args.json, args.start_col)


if __name__ == '__main__':
    main()

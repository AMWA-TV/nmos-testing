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
import copy

from oauth2client.service_account import ServiceAccountCredentials

SCOPES = ['https://spreadsheets.google.com/feeds',
          'https://www.googleapis.com/auth/drive']


# Test states grouped by severity
TEST_STATES = ["Pass", "Fail", "Warning", "Not Implemented", "Test Disabled", "Could Not Test", "Manual",
               "Not Applicable"]


def get_range(worksheet_data, start_row, start_col, end_row, end_col):
    result = []
    for row_no in range(start_row-1, end_row):
        row = worksheet_data[row_no] if row_no < len(worksheet_data) else []
        for col_no in range(start_col-1, end_col):
            result.append(gspread.Cell(row_no + 1, col_no + 1, row[col_no] if col_no < len(row) else ""))
    return result


def ranges_equal(first, second):
    if len(first) != len(second):
        return False
    for i in range(len(first)):
        if (first[i].row != second[i].row or
                first[i].col != second[i].col or
                first[i].value != second[i].value):
            return False
    return True


def insert_row(worksheet, data, row):
    data_values = [{
            "userEnteredValue": ({"formulaValue": x} if x.startswith("=") else {"stringValue": x})
        } for x in data]
    worksheet.spreadsheet.batch_update({
        'requests': [{
            'insertDimension': {
                'range': {
                    'sheetId': worksheet.id,
                    'dimension': 'ROWS',
                    'startIndex': row,
                    'endIndex': row + 1
                },
                'inheritFromBefore': False
            }
        }, {
            'updateCells': {
                'start': {
                    'sheetId': worksheet.id,
                    'rowIndex': row,
                    'columnIndex': 0,
                },
                'rows': [{
                    "values": data_values
                }],
                'fields': 'userEnteredValue'
            }
        }]
    })


def append_row(worksheet, data):
    worksheet.append_rows([data],
                          value_input_option='USER_ENTERED',
                          insert_data_option='INSERT_ROWS',
                          table_range="A1")


def gsheets_import(test_results, worksheet, filename, start_col=1, insert=False):
    """Upload results data to spreadsheet"""

    worksheet_data = worksheet.get_all_values()
    populated_rows = len(worksheet_data)
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
    cell_list_names = get_range(worksheet_data, 1, 1, 1, next_col-1)
    original_cell_list_names = copy.deepcopy(cell_list_names)

    # Results
    cell_list_results = [""] * len(cell_list_names)

    # Columns for Filename, URLs Tested, Timestamp, Test Suite
    current_index = start_col-1  # list is 0-indexed whereas rows/cols are 1-indexed
    cell_list_names[current_index].value = "Filename"
    cell_list_results[current_index] = filename
    current_index += 1
    cell_list_names[current_index].value = "URLs Tested"
    try:
        urls_tested = []
        for endpoint in test_results["endpoints"]:
            urls_tested.append("{}:{} ({})".format(endpoint["host"], endpoint["port"], endpoint["version"]))
        cell_list_results[current_index] = ", ".join(urls_tested)
    except Exception:
        print(" * WARNING: JSON file does not include endpoints")
        cell_list_results[current_index] = test_results["url"]
    current_index += 1
    cell_list_names[current_index].value = "Timestamp"
    cell_list_results[current_index] = (datetime.datetime.utcfromtimestamp(test_results["timestamp"])
                                        .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + 'Z')
    current_index += 1
    cell_list_names[current_index].value = "Test Suite"
    try:
        cell_list_results[current_index] = "{} ({})".format(test_results["suite"],
                                                            test_results["config"]["VERSION"])
    except Exception:
        print(" * WARNING: JSON file does not include test suite version")
        cell_list_results[current_index] = test_results["suite"]

    # Columns for counts of Tests and each Test Status
    result_col_name = gspread.utils.rowcol_to_a1(1, results_col)[0:-1]
    results_addr = 'INDIRECT("${}"&ROW()&":"&ROW())'.format(result_col_name)

    current_index += 1
    cell_list_names[current_index].value = "Tests"
    # count non-empty cells on rest of this row
    cell_list_results[current_index] = "=COUNTIF({}, \"?*\")".format(results_addr)
    for state in TEST_STATES:
        current_index += 1
        cell_list_names[current_index].value = state
        # count cells on the rest of this row that match this column's status
        current_col_name = gspread.utils.rowcol_to_a1(1, cell_list_names[current_index].col)[0:-1]
        cell_list_results[current_index] = "=COUNTIF({}, CONCAT({}$1,\"*\"))" \
            .format(results_addr, current_col_name)

    # Columns for the Results
    for result in test_results["results"]:
        cell_contents = result["state"]
        if result["detail"] != "":
            cell_contents += " (" + result["detail"] + ")"
        col = next((cell.col for cell in cell_list_names if cell.value == result["name"]), None)
        if col:
            index = col-1  # list is 0-indexed whereas rows/cols are 1-indexed
            cell_list_results[index] = cell_contents
        else:
            # Test name not found, append column (since gspread doesn't make it easy to insert one)
            col = cell_list_names[-1].col+1  # = cell_list_results[-1].col+1
            cell_list_names.append(gspread.Cell(1, col, result["name"]))
            cell_list_results.append(cell_contents)

    if not ranges_equal(original_cell_list_names, cell_list_names):
        worksheet.update_cells(cell_list_names)
    if insert:
        insert_row(worksheet, cell_list_results, 1)
    else:
        append_row(worksheet, cell_list_results)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True, nargs="+", help="json test results filename(s) to import")
    parser.add_argument("--sheet", required=True, help="spreadsheet url")
    parser.add_argument("--credentials", default="credentials.json", help="credentials filename")
    parser.add_argument("--start_col", default="1", type=int, help="reserve some columns for manually entered details")
    parser.add_argument("--insert", action="store_true", help="insert new results at the top rather than the bottom")
    args = parser.parse_args()

    credentials = ServiceAccountCredentials.from_json_keyfile_name(args.credentials, SCOPES)
    gcloud = gspread.authorize(credentials)

    spreadsheet = gcloud.open_by_url(args.sheet)

    worksheets = spreadsheet.worksheets()

    for json_file_name in args.json:
        with open(json_file_name) as json_file:
            test_results = json.load(json_file)

        try:
            worksheet = next(x for x in worksheets if x.title == test_results["suite"])
        except StopIteration:
            print(" * ERROR: Worksheet {} not found".format(test_results["suite"]))
            # could add_worksheet?
            sys.exit(1)

        gsheets_import(test_results, worksheet, json_file_name, args.start_col, args.insert)


if __name__ == '__main__':
    main()

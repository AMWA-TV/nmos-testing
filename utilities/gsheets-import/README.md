# Google Sheets Test Result Importer
Command line tool to import NMOS testing results into a Google spreadsheet.

## Installation

1. Install the dependencies, by running the following on a system with Python 3 and Pip installed:
```
pip3 install -r requirements.txt
```

2. Insert the spreadsheet URL into the `GOOGLE_SHEET_URL` variable
3. Provide access credentails
    * Place `credentials.json` file in the directory with the script, this grants permission to the script to make changes to the google sheet.  
    * Instructions on how to create this file can be found [here](https://gspread.readthedocs.io/en/latest/oauth2.html).  
4. **Make sure to grant the `client_email` in `credentials.json` access to the sheet.**

## Usage
First, ensure that the spreadsheet has a worksheet with the name of the 'suite', and add the URL of the spreadsheet to `GOOGLE_SHEET_URL` in the script.

To import a test results JSON file, run:

```
python3 resultsImporter.py --json <json-results-file-name>
```

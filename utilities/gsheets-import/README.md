# Google Sheets Test Result Importer
Command line tool to import NMOS testing results into a Google spreadsheet.

## Installation
To install the dependencies, run the following on a system with Python 3 and Pip installed:

```
pip3 install -r requirements.txt
```

## Usage
First, ensure that the spreadsheet has a worksheet with the name of the 'suite', and add the URL of the spreadsheet to `GOOGLE_SHEET_URL` in the script.

To import a test results JSON file, run:

```
python3 resultsImporter.py --json <json-results-file-name>
```

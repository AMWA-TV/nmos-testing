# Google Sheets Test Result Importer
Command line tool to import NMOS testing results into a Google spreadsheet.

## Installation

1. Install the dependencies, by running the following on a system with Python 3 and Pip installed:
```
pip3 install -r requirements.txt
```

2. Get an access credentials file
    * Instructions on how to create this file can be found [here](https://gspread.readthedocs.io/en/latest/oauth2.html).  
    **Make sure to grant the `client_email` in this file access to the sheet.**

3. Ensure that the spreadsheet has a worksheet with the name of the suite (e.g. 'IS-04-01').

## Usage

To import a test results JSON file, run:

```
python3 resultsImporter.py --json <json-results-file-name> --sheet <spreadsheet-url> --credentials <credentials-file-name>
```

To reserve some columns for manually entered details, specify the first column, e.g. `--start_col 4`.

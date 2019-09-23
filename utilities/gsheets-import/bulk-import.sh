#!/bin/bash
for filename in ~/Downloads/nmos-test-results/*.json; do
    printf "$filename\n"
    python3 resultsImporter.py --json "$filename" --sheet "$1"
done

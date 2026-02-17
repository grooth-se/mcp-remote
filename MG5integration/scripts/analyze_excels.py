#!/usr/bin/env python3
"""Analyze all Excel files in data/excel_exports/ and print schema info."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.excel_analyzer import analyze_all_exports, find_common_columns

folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      'data', 'excel_exports')

if len(sys.argv) > 1:
    folder = sys.argv[1]

print(f"Analyzing Excel files in: {folder}\n")
analysis = analyze_all_exports(folder)

for filename, info in analysis.items():
    print(f"=== {filename} ===")
    if 'error' in info:
        print(f"  ERROR: {info['error']}")
    else:
        print(f"  Rows: {info['row_count']}, Columns: {info['column_count']}")
        print(f"  Headers: {info['columns']}")
    print()

print("=== Common columns across files ===")
common = find_common_columns(analysis)
for col, count in common:
    if count > 1:
        print(f"  {col}: appears in {count} files")

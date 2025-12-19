#!/usr/bin/env python3
"""
Script to parse text files in a directory tree, extract percentage differences
between valid depth points and mask pixels, and display the results in a matrix format."""
import os
import re
import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def find_txt_files(root_dir):
    txt_files = []
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if file.endswith('.txt'):
                txt_files.append(os.path.join(root, file))
    return txt_files

def extract_info(filename):
    base = os.path.basename(filename)
    parts = base.split('_')
    # Distance is always the second part
    distance = parts[1]
    # Remove distance from filename for row index
    file_base = '_'.join(parts[:1] + parts[2:]).replace('.txt', '')
    # Add slash before underscores for LaTeX formatting
    file_base = file_base.replace('_', r'\_')
    return file_base, distance

def parse_file(filepath):
    diffs = []
    with open(filepath, 'r') as f:
        for line in f:
            m = re.search(r'Number of pixels in the mask: (\d+) Valid depth points: (\d+)', line)
            if m:
                mask = int(m.group(1))
                valid = int(m.group(2))
                if mask > 0:
                    diff = (abs(valid - mask) / mask) * 100.0
                    diffs.append(diff)
    # If no lines found, treat as all zeros
    if len(diffs) == 0:
        return 0.0, 0.0, 0.0
    return np.mean(diffs), np.min(diffs), np.max(diffs)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse depth image outlier text files and display results.")
    parser.add_argument('--root-dir', type=str, nargs='+', help='Root directories to search for text files (can specify multiple)')
    parser.add_argument('--tex', type=str, help='Export matrix to LaTeX file (provide filename)')
    parser.add_argument('--filter', action='store_true', help='Filter out rows where all mean values are 0')
    args = parser.parse_args()

    # Collect files from all root directories
    txt_files = []
    for root_dir in args.root_dir:
        if os.path.exists(root_dir):
            files_in_dir = find_txt_files(root_dir)
            txt_files.extend(files_in_dir)
            print(f"Found {len(files_in_dir)} text files in {root_dir}")
        else:
            print(f"Warning: Directory {root_dir} does not exist")
    
    print(f"Total: {len(txt_files)} text files across all directories.")


    records = []
    for filepath in txt_files:
        file_base, distance = extract_info(filepath)
        mean, min_, max_ = parse_file(filepath)
        records.append({
            'test': file_base,
            'distance': distance,
            'mean_pct': mean,
            'min_pct': min_,
            'max_pct': max_
        })
    df = pd.DataFrame(records)
    # Pivot table
    pivot = df.pivot(index='test', columns='distance', values=['mean_pct', 'min_pct', 'max_pct'])
    # Build formatted cell matrix
    cell_matrix = pd.DataFrame(index=pivot.index, columns=pivot.columns.levels[1])
    for row in pivot.index:
        for col in pivot.columns.levels[1]:
            try:
                mean = pivot.loc[row, ('mean_pct', col)]
                min_ = pivot.loc[row, ('min_pct', col)]
                max_ = pivot.loc[row, ('max_pct', col)]
                cell_matrix.loc[row, col] = f"{mean:.2f}\%\n{min_:.2f}\%\n{max_:.2f}\%"
            except KeyError:
                cell_matrix.loc[row, col] = "N/A"

    print("Matrix of mean, min, max % difference (Valid vs Mask) per File/Distance:")
    print(cell_matrix)

        # Apply filter if requested
    if args.filter:
        # Filter rows where at least one mean value is not 0
        rows_to_keep = []
        for row in pivot.index:
            has_non_zero_mean = False
            for col in pivot.columns.levels[1]:
                try:
                    mean = pivot.loc[row, ('mean_pct', col)]
                    if mean > 0:
                        has_non_zero_mean = True
                        break
                except KeyError:
                    continue
            if has_non_zero_mean:
                rows_to_keep.append(row)
        
        # Filter the cell_matrix to only include rows with non-zero means
        cell_matrix = cell_matrix.loc[rows_to_keep]
        print(f"\nFiltered matrix (rows with at least one non-zero mean):")
        print(cell_matrix)

    # Export to LaTeX if requested
    if args.tex:
        # Add a label column for mean/min/max
        label_col = []
        for row in cell_matrix.index:
            label_col.append(r"\makecell{mean\\min\\max}")
        cell_matrix.insert(0, "Stats", label_col)

        # Format each cell for makecell (three lines per cell, no trailing \\)
        for row in cell_matrix.index:
            for col in cell_matrix.columns:
                val = cell_matrix.loc[row, col]
                if val != "N/A" and val is not None and col != "Stats":
                    vals = val.replace('%', '').split('\n')
                    cell_matrix.loc[row, col] = r"\makecell{" + r"\".join([v.strip() for v in vals]) + "}"
                elif col != "Stats":
                    cell_matrix.loc[row, col] = "N/A"

        # Export to LaTeX with midrule between each test
        latex_str = cell_matrix.to_latex(escape=False, na_rep="N/A", column_format="l" + "c" * (len(cell_matrix.columns)-1))
        # Insert \midrule between each row (after each test)
        lines = latex_str.splitlines()
        header_end = None
        for i, line in enumerate(lines):
            if r'\toprule' in line or r'\midrule' in line:
                header_end = i
        # Insert \midrule after each data row
        new_lines = lines[:header_end+1]
        for i, line in enumerate(lines[header_end+1:]):
            new_lines.append(line)
            # Only insert midrule after data rows, not at the end
            if i < len(cell_matrix.index)-1:
                new_lines.append(r'\midrule')
        latex_str = '\n'.join(new_lines)

        with open(args.tex, "w") as f:
            f.write(latex_str)
        print(f"LaTeX table exported to {args.tex}")
#!/usr/bin/env python3

"""
@brief This file is used to obtain the error in depth estimation along different distances of the object.
The error can be evaluated among different metrics and evaluated for different cameras and modes.
"""

import os
import re
import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from collections import defaultdict
from pathlib import Path

FILENAME_PATTERN = re.compile(r'(?P<camera>\w+)_(?P<distance>\d{4})_(?P<mode>[a-z_]+)\.txt')


def _normalize_folders(folders):
    """Normalize folder inputs.

    Args:
        folders: either a dict-like {path: test_name} or an iterable of paths.

    Returns:
        list[tuple[str, str]]: (path, test_name)
    """
    if hasattr(folders, "items"):
        return [(str(path), str(name)) for path, name in folders.items()]
    return [(str(path), Path(str(path)).name) for path in folders]


def build_stats_dataframe(folders, min_dist=None, max_dist=None, outlier_threshold=None):
    """
    Parse logs, compute errors, prepare data and statistics in one step.
    Returns:
        pd.DataFrame with the same structure as compute_statistics().
    """

    # Regex patterns for parsing
    pattern_both = re.compile(r"Depth map Average z \[m\]:\s*([0-9.e-]+)\s+Pointcloud Average z:\s*([0-9.e-]+)")
    pattern_depth = re.compile(r"Depth map Average z \[m\]:\s*([0-9.e-]+)")
    pattern_rms_depth = re.compile(r"Depth map RMS z \[m\]:\s*([0-9.e-]+)")
    pattern_rmse = re.compile(r"RMSE of the depth map \[m\]:\s*([0-9.e-]+)")

    stats_list = []

    folder_items = _normalize_folders(folders)
    for i, (path, test_name) in enumerate(folder_items):
        print(f"Processing folder {i}: {path} → {test_name}")
        
        for dirpath, _, filenames in os.walk(path):
            for filename in filenames:
                match = FILENAME_PATTERN.match(filename)
                if not match:
                    continue
                camera = match['camera']
                distance = int(match['distance'])
                mode = match['mode']
                # remove all the text after the last underscore
                mode = mode.rsplit('_', 1)[0]
                # Remove test name from filename
                filepath = os.path.join(dirpath, filename)

                # --- Parse log file ---
                depth_vals, depth_rms_vals, rmse_vals = [], [], []
                with open(filepath, 'r') as f:
                    for line in f:
                        match_both = pattern_both.search(line)
                        if match_both:
                            depth_vals.append(float(match_both.group(1)))
                        else:
                            match_depth = pattern_depth.search(line)
                            if match_depth:
                                depth_vals.append(float(match_depth.group(1)))

                        match_rms_depth = pattern_rms_depth.search(line)
                        if match_rms_depth:
                            depth_rms_vals.append(float(match_rms_depth.group(1)))

                        match_rmse = pattern_rmse.search(line)
                        if match_rmse:
                            rmse_vals.append(float(match_rmse.group(1)))

                # --- Compute errors ---
                gt = distance / 1000.0  # mm → meters
                err_avg = np.array(depth_vals) - gt
                err_rms = np.array(depth_rms_vals) - gt
                rmse = np.array(rmse_vals)

                if (min_dist and gt < min_dist) or (max_dist and gt > max_dist):
                    continue

                to_process = True

                # Skip if empty
                if err_avg.size == 0:
                    print(f"Warning: No valid depth average data for camera {camera} " +
                          f"mode {mode} at distance {distance}mm for test {test_name}.")
                    to_process = False
                if err_rms.size == 0:
                    print(f"Warning: No valid depth RMS data for camera {camera} " +
                          f"mode {mode} at distance {distance}mm for test {test_name}.")
                    to_process = False
                if rmse.size == 0:
                    print(f"Warning: No valid RMSE data for camera {camera} " +
                            f"mode {mode} at distance {distance}mm for test {test_name}.")
                    to_process = False

                if to_process:
                    # --- Statistics for Avg ---
                    mean_avg = np.mean(err_avg)
                    median_avg = np.median(err_avg)
                    std_avg = np.std(err_avg)
                    q25_avg, q75_avg = np.percentile(err_avg, [25, 75])
                    iqr_avg = q75_avg - q25_avg
                    if outlier_threshold is not None:
                        thresh_outliers_avg = err_avg[np.abs(err_avg) > outlier_threshold]
                        inliers_avg = err_avg[np.abs(err_avg) <= outlier_threshold]
                    else:
                        thresh_outliers_avg = np.array([])
                        inliers_avg = err_avg
                    lower_iqr_outliers_avg = err_avg[err_avg < q25_avg - 1.5*iqr_avg]
                    upper_iqr_outliers_avg = err_avg[err_avg > q75_avg + 1.5*iqr_avg]
                    if outlier_threshold is not None:
                        lower_iqr_outliers_avg = np.setdiff1d(lower_iqr_outliers_avg, thresh_outliers_avg)
                        upper_iqr_outliers_avg = np.setdiff1d(upper_iqr_outliers_avg, thresh_outliers_avg)

                    # --- Statistics for RMS ---
                    mean_rms = np.mean(err_rms)
                    median_rms = np.median(err_rms)
                    std_rms = np.std(err_rms)
                    q25_rms, q75_rms = np.percentile(err_rms, [25, 75])
                    iqr_rms = q75_rms - q25_rms
                    if outlier_threshold is not None:
                        thresh_outliers_rms = err_rms[np.abs(err_rms) > outlier_threshold]
                        inliers_rms = err_rms[np.abs(err_rms) <= outlier_threshold]
                    else:
                        thresh_outliers_rms = np.array([])
                        inliers_rms = err_rms
                    lower_iqr_outliers_rms = err_rms[err_rms < q25_rms - 1.5*iqr_rms]
                    upper_iqr_outliers_rms = err_rms[err_rms > q75_rms + 1.5*iqr_rms]
                    if outlier_threshold is not None:
                        lower_iqr_outliers_rms = np.setdiff1d(lower_iqr_outliers_rms, thresh_outliers_rms)
                        upper_iqr_outliers_rms = np.setdiff1d(upper_iqr_outliers_rms, thresh_outliers_rms)

                    # --- Matching RMSE values for inliers of avg ---
                    # inliers_avg is a mask on err_avg, so get indices
                    if outlier_threshold is not None:
                        inliers_avg_indices = np.where(np.abs(err_avg) <= outlier_threshold)[0]
                        matching_rmse_inliers_avg = rmse[inliers_avg_indices].tolist()
                    else:
                        matching_rmse_inliers_avg = rmse.tolist()

                # --- Append row ---
                stats_list.append({
                    "Camera": camera,
                    "Mode": mode,
                    "Test": test_name,  # Use the properly assigned test name
                    "Distance": gt,
                    "Total_Avg": len(err_avg) if to_process else 0,
                    "Avg_Values": err_avg.tolist() if to_process else [],
                    "Inliers_List_Avg": inliers_avg.tolist() if to_process else [],
                    "Matching_RMSE_Inliers_Avg": matching_rmse_inliers_avg if to_process else [],
                    "Treshold_Outliers_Avg_Count": len(thresh_outliers_avg) if to_process else 0,
                    "IQR_Lower_Outliers_Avg_Count": len(lower_iqr_outliers_avg) if to_process else 0,
                    "IQR_Upper_Outliers_Avg_Count": len(upper_iqr_outliers_avg) if to_process else 0,
                    "Treshold_Outliers_Avg_Values": thresh_outliers_avg.tolist() if to_process else [],
                    "IQR_Lower_Outliers_Avg_Values": lower_iqr_outliers_avg.tolist() if to_process else [],
                    "IQR_Upper_Outliers_Avg_Values": upper_iqr_outliers_avg.tolist() if to_process else [],
                    "Total_RMS": len(err_rms) if to_process else 0,
                    "RMS_Values": err_rms.tolist() if to_process else [],
                    "Inliers_List_RMS": inliers_rms.tolist() if to_process else [],
                    "Treshold_Outliers_RMS_Count": len(thresh_outliers_rms) if to_process else 0,
                    "IQR_Lower_Outliers_RMS_Count": len(lower_iqr_outliers_rms) if to_process else 0,
                    "IQR_Upper_Outliers_RMS_Count": len(upper_iqr_outliers_rms) if to_process else 0,
                    "Treshold_Outliers_RMS_Values": thresh_outliers_rms.tolist() if to_process else [],
                    "IQR_Lower_Outliers_RMS_Values": lower_iqr_outliers_rms.tolist() if to_process else [],
                    "IQR_Upper_Outliers_RMS_Values": upper_iqr_outliers_rms.tolist() if to_process else [],
                    "RMSES": rmse.tolist() if to_process else [],
                })
    
    # Create DataFrame
    return pd.DataFrame(stats_list)

def filter_dataframe(df):
    """
    Remove rows where both Treshold_Outliers_Avg_Count and Treshold_Outliers_RMS_Count are 0.
    
    Args:
        df (pd.DataFrame): Input dataframe
        
    Returns:
        pd.DataFrame: Filtered dataframe with rows removed
    """
    # Keep rows where at least one threshold outlier count is > 0
    filtered_df = df[~((df['Treshold_Outliers_Avg_Count'] == 0) & 
                       (df['Treshold_Outliers_RMS_Count'] == 0) & 
                       (df['Total_Avg'] == 300) & 
                       (df['Total_RMS'] == 300))]
    
    # Reset index to maintain clean indexing
    filtered_df = filtered_df.reset_index(drop=True)
    
    print(f"Original rows: {len(df)}")
    print(f"Filtered rows: {len(filtered_df)}")
    print(f"Removed rows: {len(df) - len(filtered_df)}")
    
    return filtered_df


def export_outliers_latex(stats_df, filename="outliers_table.tex", no_iqr=False, filter_df=False):
    """
    Export a LaTeX table of outliers and statistics with improved formatting.
    
    Args:
        stats_df: DataFrame with statistics
        filename: Output LaTeX file name
        no_iqr: If True, exclude IQR columns from the table
    """
    from collections import defaultdict

    # Optionally filter the DataFrame
    if filter_df:
        filtered_df = filter_dataframe(stats_df)
    else:
        filtered_df = stats_df.copy()
    
    # Group data as camera_mode > test > distances
    tree = defaultdict(lambda: defaultdict(list))
    for _, row in filtered_df.iterrows():
        camera = row["Camera"]
        mode = row["Mode"]
        test = row["Test"]
        dist = row["Distance"]
        total_avg = row["Total_Avg"]
        thresh_out_avg_count = row["Treshold_Outliers_Avg_Count"]
        iqr_lower_avg_count = row["IQR_Lower_Outliers_Avg_Count"]
        iqr_upper_avg_count = row["IQR_Upper_Outliers_Avg_Count"]
        total_rms = row["Total_RMS"]
        thresh_out_rms_count = row["Treshold_Outliers_RMS_Count"]
        iqr_lower_rms_count = row["IQR_Lower_Outliers_RMS_Count"]
        iqr_upper_rms_count = row["IQR_Upper_Outliers_RMS_Count"]

        # Format with percentages
        def fmt(count, total):
            if total > 0 and count > 0:
                return f"{count} ({count/total*100:.1f}\\%)"
            elif count > 0:
                return str(count)
            return "-"

        if no_iqr:
            # Store only total and threshold values
            tree[f"{camera}\\\\{mode}"][test].append(
                (dist, str(total_avg),
                 fmt(thresh_out_avg_count, total_avg),
                 str(total_rms),
                 fmt(thresh_out_rms_count, total_rms))
            )
        else:
            # Store all values including IQR
            tree[f"{camera}\\\\{mode}"][test].append(
                (dist, str(total_avg),
                 fmt(thresh_out_avg_count, total_avg),
                 fmt(iqr_lower_avg_count, total_avg),
                 fmt(iqr_upper_avg_count, total_avg),
                 str(total_rms),
                 fmt(thresh_out_rms_count, total_rms),
                 fmt(iqr_lower_rms_count, total_rms),
                 fmt(iqr_upper_rms_count, total_rms))
            )

    with open(filename, "w") as f:
        f.write("% Requires: \\usepackage{array,makecell,multirow,booktabs,longtable}\n")
        f.write("\\renewcommand\\theadalign{cc}\n")
        f.write("\\renewcommand\\theadfont{\\bfseries}\n")
        f.write("\\renewcommand\\cellalign{cc}\n")
        
        # Table column specification depends on no_iqr setting
        if no_iqr:
            f.write("\\begin{longtable}{\n")
            f.write("  >{\\centering\\arraybackslash}m{2.5cm}  % Camera / Mode\n")
            f.write("  >{\\centering\\arraybackslash}m{2.5cm}  % Test\n")
            f.write("  >{\\centering\\arraybackslash}m{2cm}    % Distance\n")
            f.write("  >{\\centering\\arraybackslash}m{1.2cm}  % Total Avg\n")
            f.write("  >{\\centering\\arraybackslash}m{1.5cm}  % Thresh Avg\n")
            f.write("  >{\\centering\\arraybackslash}m{1.2cm}  % Total RMS\n")
            f.write("  >{\\centering\\arraybackslash}m{1.5cm}  % Thresh RMS\n")
            f.write("}\n")
            num_cols = 7
        else:
            f.write("\\begin{longtable}{\n")
            f.write("  >{\\centering\\arraybackslash}m{2cm}  % Camera / Mode\n")
            f.write("  >{\\centering\\arraybackslash}m{2cm}  % Test\n")
            f.write("  >{\\centering\\arraybackslash}m{1.5cm}  % Distance\n")
            f.write("  >{\\centering\\arraybackslash}m{0.7cm}  % Total Avg\n")
            f.write("  >{\\centering\\arraybackslash}m{1cm}    % Thresh Avg\n")
            f.write("  >{\\centering\\arraybackslash}m{1cm}    % IQR Lower Avg\n")
            f.write("  >{\\centering\\arraybackslash}m{1cm}    % IQR Upper Avg\n")
            f.write("  >{\\centering\\arraybackslash}m{0.7cm}  % Total RMS\n")
            f.write("  >{\\centering\\arraybackslash}m{1cm}    % Thresh RMS\n")
            f.write("  >{\\centering\\arraybackslash}m{1cm}    % IQR Lower RMS\n")
            f.write("  >{\\centering\\arraybackslash}m{1cm}    % IQR Upper RMS\n")
            f.write("}\n")
            num_cols = 11
            
        f.write("\\caption{Outliers and statistics}\n")
        f.write("\\label{tab:outliers-stats} \\\\\n")
        f.write("\\toprule\n")
        
        # Header depends on no_iqr setting
        if no_iqr:
            f.write("Camera Mode & Test & Distance [m] & "
                    "\\multicolumn{2}{c}{\\makecell{Average \\\\ Error}} & "
                    "\\multicolumn{2}{c}{\\makecell{RMS \\\\ Error}} \\\\\n")
            f.write("\\cmidrule(lr){4-5} \\cmidrule(lr){6-7}\n")
            f.write(" & & & Total & Thresh & Total & Thresh \\\\\n")
        else:
            f.write("\\makecell{Camera \\\\ Mode} & Test & Distance [m] & "
                    "\\multicolumn{4}{c}{\\makecell{Average \\\\ Error}} & "
                    "\\multicolumn{4}{c}{\\makecell{RMS \\\\ Error}} \\\\\n")
            f.write("\\cmidrule(lr){4-7} \\cmidrule(lr){8-11}\n")
            f.write(" & & & Total & Thresh & IQR Lower & IQR Upper "
                    "& Total & Thresh & IQR Lower & IQR Upper \\\\\n")
            
        f.write("\\midrule\n")
        f.write("\\endfirsthead\n\n")
        
        # Repeat header for continuation pages
        f.write("\\toprule\n")
        if no_iqr:
            f.write("Camera Mode & Test & Distance [m] & "
                    "\\multicolumn{2}{c}{\\makecell{Average \\\\ Error}} & "
                    "\\multicolumn{2}{c}{\\makecell{RMS \\\\ Error}} \\\\\n")
            f.write("\\cmidrule(lr){4-5} \\cmidrule(lr){6-7}\n")
            f.write(" & & & Total & Thresh & Total & Thresh \\\\\n")
        else:
            f.write("\\makecell{Camera \\\\ Mode} & Test & Distance [m] & "
                    "\\multicolumn{4}{c}{\\makecell{Average \\\\ Error}} & "
                    "\\multicolumn{4}{c}{\\makecell{RMS \\\\ Error}} \\\\\n")
            f.write("\\cmidrule(lr){4-7} \\cmidrule(lr){8-11}\n")
            f.write(" & & & Total & Thresh & IQR Lower & IQR Upper "
                    "& Total & Thresh & IQR Lower & IQR Upper \\\\\n")
            
        f.write("\\midrule\n")
        f.write("\\endhead\n\n")
        f.write("\\midrule\n")
        f.write(f"\\multicolumn{{{num_cols}}}{{r}}{{{{Continued on next page}}}} \\\\\n")
        f.write("\\midrule\n")
        f.write("\\endfoot\n\n")
        f.write("\\bottomrule\n")
        f.write("\\endlastfoot\n\n")

        for cam_mode_idx, (cam_mode, tests) in enumerate(tree.items()):
            if no_iqr:
                # When no IQR, camera mode can be on single line
                cam_mode_rows = sum(len(tests[test]) for test in tests)
                cam_mode_written = False
                for test_idx, (test, distances) in enumerate(tests.items()):
                    test_rows = len(distances)
                    test_written = False
                    for i, (dist, *vals) in enumerate(sorted(distances)):
                        # Clean camera mode for LaTeX
                        cam_mode_clean = cam_mode.replace("_", "\\_").replace("\\\\", " ")
                        cm = f"\\multirow{{{cam_mode_rows}}}{{*}}{{{cam_mode_clean}}}" if not cam_mode_written else ""
                        cam_mode_written = True
                        t = f"\\multirow{{{test_rows}}}{{*}}{{{test}}}" if not test_written else ""
                        test_written = True
                        if i > 0:
                            cm, t = "", ""

                        row = [cm, t, f"{dist:.2f}"] + list(vals)

                        # use \\* for intermediate rows, \\ for last
                        endline = "\\\\*" if i < test_rows-1 else "\\\\"
                        f.write(" & ".join(row) + f" {endline}\n")

                    if test_idx == len(tests)-1 and cam_mode_idx != len(tree)-1:
                        f.write(f"\\cmidrule(lr){{1-{num_cols}}}\n")
                    else:
                        f.write(f"\\cmidrule(lr){{2-{num_cols}}}\n")
            else:
                # Original behavior with IQR - camera mode on two lines
                cam_mode_rows = sum(len(tests[test]) for test in tests)
                cam_mode_written = False
                for test_idx, (test, distances) in enumerate(tests.items()):
                    test_rows = len(distances)
                    test_written = False
                    for i, (dist, *vals) in enumerate(sorted(distances)):
                        # Add backslash for LaTeX
                        cam_mode_clean = cam_mode.replace("_", "\\_") if "_" in cam_mode else cam_mode
                        cm = f"\\multirow{{{cam_mode_rows}}}{{*}}{{\\makecell{{{cam_mode_clean}}}}}" if not cam_mode_written else ""
                        cam_mode_written = True
                        t = f"\\multirow{{{test_rows}}}{{*}}{{{test}}}" if not test_written else ""
                        test_written = True
                        if i > 0:
                            cm, t = "", ""

                        row = [cm, t, f"{dist:.2f}"] + list(vals)

                        # use \\* for intermediate rows, \\ for last
                        endline = "\\\\*" if i < test_rows-1 else "\\\\"
                        f.write(" & ".join(row) + f" {endline}\n")

                    if test_idx == len(tests)-1 and cam_mode_idx != len(tree)-1:
                        f.write(f"\\cmidrule(lr){{1-{num_cols}}}\n")
                    else:
                        f.write(f"\\cmidrule(lr){{2-{num_cols}}}\n")
                        
        f.write("\\end{longtable}\n")
    print(f"LaTeX table written to {filename}")
    return tree


def plot_errors(df, camera_filter, mode_filter, min_dist=None, max_dist=None,
                output_folder=None):
    """
    Plot violin plots showing depth errors from the DataFrame.
    
    Data Organization in DataFrame:
    - Each row represents one (Camera, Mode, Test, Distance) combination
    - 'Inliers_List_Avg': list of average depth error values (after outlier filtering)
    - 'Matching_RMSE_Inliers_Avg': list of RMSE values corresponding to avg inliers
    
    Plotting Order per Distance (Depth Errors):
    For each distance value, violins are positioned as:
    1. HD - Natural Light Average (leftmost)
    2. SD - Natural Light Average
    3. HD - Artificial Light Average
    4. SD - Artificial Light Average (rightmost)
    
    RMSE and Scatter plots remain unchanged.
    """
    all_plot_tuples = []  # Store all plots for final saving/showing
    save_plots = output_folder is not None

    # Handle 'all' mode filter
    if mode_filter is not None:
        if isinstance(mode_filter, str) and mode_filter.lower() == 'all':
            mode_filter = None
        elif hasattr(mode_filter, '__iter__') and any(str(m).lower() == 'all' for m in mode_filter):
            mode_filter = None

    # ====== FILTER DATAFRAME BY CAMERA AND MODE ======
    print("=== Filtering DataFrame ===")
    filtered_df = df.copy()

    # plot all available cameras/modes if no filter provided
    print(f"Camera modes before filtering:")
    print(filtered_df[["Camera", "Mode"]].drop_duplicates().to_string(index=False))

    # Apply camera filter
    if camera_filter:
        filtered_df = filtered_df[filtered_df["Camera"].isin(camera_filter)]
        print(f"Filtered by cameras: {camera_filter}")
    
    # Apply mode filter
    if mode_filter:
        filtered_df = filtered_df[filtered_df["Mode"].isin(mode_filter)]
        print(f"Filtered by modes: {mode_filter}")
    
    # Apply distance range filter
    if min_dist is not None:
        filtered_df = filtered_df[filtered_df["Distance"] >= min_dist]
        print(f"Filtered by min distance: {min_dist}m")
    if max_dist is not None:
        filtered_df = filtered_df[filtered_df["Distance"] <= max_dist]
        print(f"Filtered by max distance: {max_dist}m")
    
    if filtered_df.empty:
        print("No data remaining after filtering!")
        return
    
    print(f"Filtered DataFrame contains {len(filtered_df)} rows")
    unique_cameras = filtered_df["Camera"].unique()
    unique_modes = filtered_df["Mode"].unique()
    print(f"Cameras to plot: {list(unique_cameras)}")
    print(f"Modes to plot: {list(unique_modes)}")
    
    # ====== ADD RESOLUTION CATEGORY (HD/SD) AND BASE MODE ======
    def categorize_resolution(mode_str):
        """Categorize mode as HD or SD based on prefix"""
        mode_lower = mode_str.lower()
        if mode_lower.startswith('hd'):
            return 'HD'
        elif mode_lower.startswith('sd'):
            return 'SD'
        else:
            return 'Unknown'
    
    def get_base_mode(mode_str):
        """Extract base mode name without hd/sd prefix"""
        mode_lower = mode_str.lower()
        if mode_lower.startswith('hd_') or mode_lower.startswith('sd_'):
            # Remove hd_ or sd_ prefix
            return mode_lower[3:]
        elif mode_lower in ['hd', 'sd']:
            # Just hd or sd without suffix - use 'default' as base mode
            return 'default'
        else:
            return mode_lower
    
    filtered_df['Resolution'] = filtered_df['Mode'].apply(categorize_resolution)
    filtered_df['BaseMode'] = filtered_df['Mode'].apply(get_base_mode)
    print(f"\nResolution and base mode categories:")
    print(filtered_df[["Camera", "Mode", "Resolution", "BaseMode"]].drop_duplicates().to_string(index=False))

    # ====== COMPUTE GLOBAL Y-LIMITS FOR CONSISTENT SCALING ======
    print("\n=== Computing Global Y-Limits ===")
    all_depth_values = []
    all_rmse_values = []
    
    # Extract all values from the filtered DataFrame
    for _, row in filtered_df.iterrows():
        # Collect depth errors (only avg, no more rms)
        avg_vals = np.array(row["Inliers_List_Avg"])
        rmse_vals = np.array(row["Matching_RMSE_Inliers_Avg"])
        
        if len(avg_vals) > 0:
            all_depth_values.extend(avg_vals.flatten())
        if len(rmse_vals) > 0:
            all_rmse_values.extend(rmse_vals.flatten())
    
    # Calculate y-limits for depth errors (violin plots)
    if all_depth_values:
        depth_min = min(all_depth_values)
        depth_max = max(all_depth_values)
        # Ensure zero line is always visible
        depth_min = min(depth_min, 0)
        depth_max = max(depth_max, 0)
        # Add 5% padding
        depth_range = depth_max - depth_min
        padding = depth_range * 0.05 if depth_range > 0 else 0.01  # minimum padding
        depth_ylim = (depth_min - padding, depth_max + padding)
        print(f"Global depth error y-limits: [{depth_ylim[0]:.4f}, {depth_ylim[1]:.4f}]")
    else:
        depth_ylim = (-0.1, 0.1)  # fallback
        print("No depth data found, using fallback y-limits")
    
    # Calculate y-limits for RMSE plots
    if all_rmse_values:
        rmse_min = min(all_rmse_values)
        rmse_max = max(all_rmse_values)
        # RMSE is always >= 0, but ensure zero line is visible
        rmse_min = min(rmse_min, 0)
        rmse_max = max(rmse_max, 0)
        # Add 5% padding
        rmse_range = rmse_max - rmse_min
        padding = rmse_range * 0.05 if rmse_range > 0 else 0.01
        rmse_ylim = (rmse_min - padding, rmse_max + padding)
        print(f"Global RMSE y-limits: [{rmse_ylim[0]:.4f}, {rmse_ylim[1]:.4f}]")
    else:
        rmse_ylim = (0, 0.1)  # fallback
        print("No RMSE data found, using fallback y-limits")

    # ====== ITERATE THROUGH CAMERA/MODE COMBINATIONS ======
    print("\n=== Processing Camera/Mode Combinations ===")
    
    # Process each camera/mode combination separately (grouping HD and SD together)
    for (camera, base_mode), mode_group in filtered_df.groupby(["Camera", "BaseMode"]):

        color_palette = sns.color_palette("tab20", n_colors=20)
        
        print(f"\n=== Processing {camera.upper()} - {base_mode} ===")

        # Extract data organized by resolution, test, and distance
        # Structure: {(resolution, test): {distance: {'avg': [...], 'rmse': [...]}}}
        combo_data = {}
        available_distances = set()
        
        for _, row in mode_group.iterrows():
            resolution = row["Resolution"]
            test_name = row["Test"]
            distance = row["Distance"]
            combo_key = (resolution, test_name)
            
            if combo_key not in combo_data:
                combo_data[combo_key] = {}
            
            combo_data[combo_key][distance] = {
                'avg_errors': np.array(row["Inliers_List_Avg"]),
                'rmse_values': np.array(row["Matching_RMSE_Inliers_Avg"])
            }
            available_distances.add(distance)

        # Sort distances for consistent x-axis
        sorted_distances = sorted(available_distances)
        print(f"Available distances: {sorted_distances}")
        print(f"Available combinations: {list(combo_data.keys())}")

        # Define explicit plotting order and colors for depth errors
        # Order: SD-Natural, SD-Artificial, HD-Natural, HD-Artificial
        plot_config = [
            {"resolution": "SD", "test": "Natural Light", "label": "SD - Natural Light", "color": color_palette[0], "position_offset": -1.5},
            {"resolution": "HD", "test": "Natural Light", "label": "HD - Natural Light", "color": color_palette[1], "position_offset": -0.5},
            {"resolution": "SD", "test": "Artificial Light", "label": "SD - Artificial Light", "color": color_palette[2], "position_offset": 0.5},
            {"resolution": "HD", "test": "Artificial Light", "label": "HD - Artificial Light", "color": color_palette[3], "position_offset": 1.5}
        ]

        # ====== DEPTH ERRORS VIOLIN PLOT (AVERAGE ONLY) ======
        fig1, ax1 = plt.subplots(figsize=(12, 7))
        legend_handles = []
        legend_labels = []
        
        # Base positions for each distance on x-axis
        base_positions = np.arange(len(sorted_distances))
        violin_width = 0.2
        
        print(f"\n--- Plotting Depth Errors (Average only) ---")
        
        for config in plot_config:
            resolution = config["resolution"]
            test_name = config["test"]
            label = config["label"]
            color = config["color"]
            position_offset = config["position_offset"]
            combo_key = (resolution, test_name)
            
            # Skip if this combination is not available in the data
            if combo_key not in combo_data:
                print(f"Skipping {label}: combination {combo_key} not found in data")
                continue
                
            # Collect data for this resolution/test combination
            violin_data = []
            violin_positions = []
            
            for i, distance in enumerate(sorted_distances):
                if distance in combo_data[combo_key]:
                    values = combo_data[combo_key][distance]['avg_errors']
                    
                    # Only plot if we have data
                    if len(values) > 0:
                        violin_data.append(values)
                        violin_positions.append(base_positions[i] + position_offset * violin_width)
                        print(f"  {label} at {distance:.2f}m: {len(values)} data points")
                    else:
                        print(f"  {label} at {distance:.2f}m: NO DATA")
                else:
                    print(f"  {label} at {distance:.2f}m: MISSING DISTANCE")
            
            # Plot violins if we have any data
            if violin_data:
                vp = ax1.violinplot(violin_data, positions=violin_positions, widths=violin_width, showmedians=True)
                
                # Style the violins
                for pc in vp['bodies']:
                    pc.set_facecolor(color)
                    pc.set_edgecolor('black')
                    pc.set_alpha(0.6)
                for partname in ['cbars','cmins','cmaxes','cmedians']:
                    vp[partname].set_color(color)

                # Add to legend
                legend_handles.append(plt.Line2D([0], [0], color=color, lw=6))
                legend_labels.append(label)
                print(f"  Successfully plotted {len(violin_data)} violins for {label}")
            else:
                print(f"  No data to plot for {label}")

        # Finalize depth errors plot
        ax1.axhline(y=0, color='red', linestyle='--', alpha=0.7, label='Zero Error')
        ax1.set_xticks(base_positions)
        ax1.set_xticklabels([f"{d:.2f}m" for d in sorted_distances])
        ax1.set_xlabel(r'Distances (ground truth) [m]', fontsize=22)
        ax1.set_ylabel(r'$\epsilon_{avg}$ [m]', fontsize=22)
        # ax1.set_title(f"{camera.upper()} - Depth Errors Comparison", fontsize=14)
        ax1.grid(True, alpha=1, which='major', linestyle='--', linewidth=2)
        ax1.grid(True, alpha=0.5, which='minor', linestyle=':', linewidth=1.5, axis='y')
        ax1.tick_params(axis='both', which='major', labelsize=20)
        # ax1.set_yticks(np.arange(-0.2, 0.3, 0.05), minor=True)
        
        # Apply automatic y-limits for depth errors
        ax1.set_ylim(depth_ylim)
        print(f"Applied global depth error y-limits: {depth_ylim}")
        
        if legend_handles:
            ax1.legend(legend_handles, legend_labels, loc='best', fontsize=22)
        
        plt.tight_layout()
        if save_plots:
            if not os.path.exists(f"{output_folder}/depth/"):
                os.makedirs(f"{output_folder}/depth/")
            all_plot_tuples.append((fig1, f"{output_folder}/depth/{camera}_{base_mode}_depth_errors.png"))

        # ====== RMSE VIOLIN PLOT (Split by HD/SD and Test) ======
        fig2, ax2 = plt.subplots(figsize=(12, 7))
        legend_handles_rmse = []
        legend_labels_rmse = []
        
        print(f"\n--- Plotting RMSE (HD/SD split) ---")
               
        for config in plot_config:
            resolution = config["resolution"]
            test_name = config["test"]
            label = config["label"]
            color = config["color"]
            position_offset = config["position_offset"]
            combo_key = (resolution, test_name)
            
            # Skip if this combination is not available in the data
            if combo_key not in combo_data:
                print(f"Skipping {label}: combination {combo_key} not found in data")
                continue
                
            # Collect RMSE data for this resolution/test combination
            violin_data = []
            violin_positions = []
            
            for i, distance in enumerate(sorted_distances):
                if distance in combo_data[combo_key]:
                    rmse_values = combo_data[combo_key][distance]['rmse_values']
                    
                    # Only plot if we have data
                    if len(rmse_values) > 0:
                        violin_data.append(rmse_values)
                        violin_positions.append(base_positions[i] + position_offset * violin_width)
                        print(f"  {label} at {distance:.2f}m: {len(rmse_values)} RMSE values")
                    else:
                        print(f"  {label} at {distance:.2f}m: NO RMSE DATA")
                else:
                    print(f"  {label} at {distance:.2f}m: MISSING DISTANCE")
            
            # Plot RMSE violins if we have any data
            if violin_data:
                vp = ax2.violinplot(violin_data, positions=violin_positions, widths=violin_width, showmedians=True)
                
                # Style the violins
                for pc in vp['bodies']:
                    pc.set_facecolor(color)
                    pc.set_edgecolor('black')
                    pc.set_alpha(0.6)
                for partname in ['cbars','cmins','cmaxes','cmedians']:
                    vp[partname].set_color(color)

                # Add to legend
                legend_handles_rmse.append(plt.Line2D([0], [0], color=color, lw=6))
                legend_labels_rmse.append(label)
                print(f"  Successfully plotted {len(violin_data)} RMSE violins for {label}")
            else:
                print(f"  No RMSE data to plot for {label}")

        # Finalize RMSE plot
        ax2.axhline(y=0, color='red', linestyle='--', alpha=0.7, label='Zero RMSE')
        ax2.set_xticks(base_positions)
        ax2.set_xticklabels([f"{d:.2f}m" for d in sorted_distances])
        ax2.set_xlabel(r'$\epsilon_{avg}$ [m]', fontsize=22)
        ax2.set_ylabel(r'RMSE [m]', fontsize=22)
        # ax2.set_title(f"{camera.upper()} - {mode} - RMSE Comparison", fontsize=14)
        ax2.grid(True, alpha=1, which='major', linestyle='--', linewidth=2)
        ax2.grid(True, alpha=0.5, which='minor', linestyle=':', linewidth=1.5, axis='y')
        ax2.tick_params(axis='both', which='major', labelsize=20)
        #ax2.set_yticks(np.arange(-0.05, 0.75, 0.05), minor=True)

        # Apply automatic y-limits for RMSE
        # ax2.set_ylim(rmse_ylim)
        print(f"Applied global RMSE y-limits: {rmse_ylim}")
        
        if legend_handles_rmse:
            ax2.legend(legend_handles_rmse, legend_labels_rmse, loc='best', fontsize=22)
        
        plt.tight_layout()
        if save_plots:
            if not os.path.exists(f"{output_folder}/rmse/"):
                os.makedirs(f"{output_folder}/rmse/")
            all_plot_tuples.append((fig2, f"{output_folder}/rmse/{camera}_{base_mode}_rmse.png"))

        # ====== SCATTER PLOTS: Average Error vs RMSE (Separate for HD and SD) ======
        print(f"\n--- Plotting Scatter: Average Error vs RMSE (HD and SD separate) ---")
        
        # Create two scatter plots - one for HD, one for SD
        for resolution in ['SD', 'HD']:
            fig_scatter, ax_scatter = plt.subplots(figsize=(12, 7))
            legend_handles_scatter = []
            legend_labels_scatter = []
            color_index = 0
            
            print(f"\n--- Plotting {resolution} Scatter ---")
            
            # Plot for each distance and test combination
            for distance in sorted_distances:
                for test_name in ["Natural Light", "Artificial Light"]:
                    combo_key = (resolution, test_name)
                    
                    # Skip if this combination is not available in the data
                    if combo_key not in combo_data or distance not in combo_data[combo_key]:
                        print(f"Skipping {resolution} scatter for {test_name} at {distance:.2f}m: no data")
                        continue
                    
                    # Extract data for this specific resolution/distance/test combination
                    avg_errs = combo_data[combo_key][distance]['avg_errors']
                    rmse_vals = combo_data[combo_key][distance]['rmse_values']
                    
                    if len(avg_errs) == 0 or len(rmse_vals) == 0:
                        print(f"Skipping {resolution} scatter for {test_name} at {distance:.2f}m: empty data")
                        continue
                    
                    x_values = np.array(avg_errs)  # Average depth errors (inliers)
                    y_values = np.array(rmse_vals)  # Corresponding RMSE values
                    
                    # Ensure x and y have same length (should be true by design)
                    if len(x_values) != len(y_values):
                        min_len = min(len(x_values), len(y_values))
                        x_values = x_values[:min_len]
                        y_values = y_values[:min_len]
                        print(f"Warning: Trimmed {resolution} data for {test_name} at {distance:.2f}m to {min_len} points")
                    
                    # Plot scatter points
                    color = color_palette[color_index % len(color_palette)]
                    label = f"{distance:.2f}m - {test_name}"
                    
                    ax_scatter.scatter(x_values, y_values, 
                               facecolors='none',
                               edgecolors=color,
                               alpha=0.6, 
                               s=30, 
                               label=label,
                               linewidths=1.5)
                    
                    # Add to legend
                    legend_handles_scatter.append(plt.Line2D([], [], 
                                                           marker='o', 
                                                           color='w', 
                                                           markerfacecolor='none', 
                                                           markersize=8, 
                                                           markeredgecolor=color,
                                                           markeredgewidth=2))
                    legend_labels_scatter.append(label)
                    
                    print(f"  Plotted {len(x_values)} points for {resolution} {test_name} at {distance:.2f}m")
                    color_index += 1
            
            # Finalize scatter plot
            ax_scatter.axvline(x=0, color='red', linestyle='--', alpha=0.7, label='Zero Avg Error')
            ax_scatter.axhline(y=0, color='red', linestyle=':', alpha=0.7, label='Zero RMSE')
            ax_scatter.set_xlabel(r'$\epsilon_{avg}$ [m]', fontsize=22)
            ax_scatter.set_ylabel(r'RMSE [m]', fontsize=22)
            # ax_scatter.set_title(f"{camera.upper()} - {base_mode} - {resolution} - Average Error vs RMSE", fontsize=14)
            ax_scatter.grid(True, alpha=0.5, which='both', linestyle='--', linewidth=1)
            ax_scatter.tick_params(axis='both', which='major', labelsize=20)
            ax_scatter.set_ylim(rmse_ylim)  # Use same limits as RMSE plot
            ax_scatter.set_xlim(depth_ylim)  # Use same limits as depth error plot
            
            if legend_handles_scatter:
                # Split legend into two columns if too many entries
                ncol = 2 if len(legend_handles_scatter) > 6 else 1
                ax_scatter.legend(legend_handles_scatter, legend_labels_scatter, 
                          title="Distance - Test", 
                          loc='best', 
                          ncol=ncol,
                          fontsize=18)
            
            plt.tight_layout()
            if save_plots:
                if not os.path.exists(f"{output_folder}/scatter/"):
                    os.makedirs(f"{output_folder}/scatter/")
                all_plot_tuples.append((fig_scatter, f"{output_folder}/scatter/{camera}_{base_mode}_{resolution}_avg_vs_rmse.png"))

        print(f"=== Finished processing {camera.upper()} - {base_mode} ===\n")

        # ====== SAVE OR SHOW ALL PLOTS ======
        
        # Save figures if requested
        if save_plots:
            for fig, filename in all_plot_tuples:
                fig.savefig(filename, dpi=300, bbox_inches='tight')
                plt.close(fig)
        else:
            # Press 'escape' to close all plots
            def on_key(event):
                if event.key == 'escape':
                    plt.close('all')
            for fig_num in plt.get_fignums():
                fig = plt.figure(fig_num)
                fig.canvas.mpl_connect('key_press_event', on_key)
            plt.show()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plot depth/pointcloud/angle/area errors from logs")
    parser.add_argument("--camera", type=str, nargs='*', choices=["rsi", "rsf", "zedx", "zedxm"], help="Filter by one or more camera names")
    parser.add_argument("--mode", type=str, nargs='*', help="Filter by one or more mode names (insert 'all' for no filter)")
    parser.add_argument("--min-dist", type=float, help="Minimum distance [m] to display in plots")
    parser.add_argument("--max-dist", type=float, help="Maximum distance [m] to display in plots")
    parser.add_argument("--root-folder", type=str, default="CameraComparisonDataset", help="Root folder containing log file subfolders")
    parser.add_argument("--output-folder", type=str, default=None, help="Output folder for saving plots")
    parser.add_argument("--outlier-threshold", type=float, default=None, help="Outlier threshold in meters (default: None)")
    args = parser.parse_args()

    # Define folders to process
    folders = {
        os.path.join(args.root_folder, "natural"): "Natural Light",
        os.path.join(args.root_folder, "artificial"): "Artificial Light"
    }

    stats_df = build_stats_dataframe(folders, min_dist=args.min_dist, max_dist=args.max_dist,
                                     outlier_threshold=args.outlier_threshold)
    export_outliers_latex(stats_df, filename="outliers_table_filtered.tex", no_iqr=True, filter_df=True)

    # Sanity check for output folder
    output_folder = None
    if args.output_folder:
        print(f"Saving plots to folder: {args.output_folder}")
        output_folder = args.output_folder
        if not os.path.exists(output_folder):
            os.makedirs(output_folder, exist_ok=True)

        plot_errors(stats_df, args.camera, args.mode, args.min_dist, args.max_dist, output_folder)

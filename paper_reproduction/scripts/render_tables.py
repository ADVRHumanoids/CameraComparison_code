"""Generate the seven computed LaTeX tables using the active manuscript layouts.

Called by scripts.render with complete derived CSV tables; no reference files read.
Inputs: exclusions, invalid-count extrema, contextual bias, plane table values.
Outputs: seven CSV/LaTeX pairs.
Templates preserve formatting/captions, while every result cell is computed anew.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from .render_plots import LABEL, MODE

DISTANCES = [.4, .6, .8, 1., 1.4, 1.8, 2.2, 2.6, 3.]


def printed(value):
    """Keep two-decimal scientific table rounding without negative rounded zero."""
    return f"{0. if abs(value) < .005 else value:.2f}"


def table_rows(name, data):
    """Preserve explicit camera/mode order and HD-first/SD-second cell meaning."""
    rows = []
    if name == "app_outliers":
        for (camera, distance, resolution, light, mode), group in data.groupby(["camera", "distance_m", "resolution", "lighting", "mode"]):
            rows.append(" & ".join([LABEL[camera], f"{distance:.1f}", resolution.upper(), light.capitalize(), MODE[mode],
                                    str(len(group)), ", ".join(map(str, sorted(group.frame.astype(int))))]) + r" \\")
    elif name == "app_invalid_pixels":
        for (camera, resolution, light), group in data.groupby(["camera", "resolution", "lighting"]):
            title = r"\makecell{" + LABEL[camera] + " " + resolution.upper() + r"\\" + light.capitalize() + "}"
            for kind in ("min", "max"):
                cells = []
                for distance in DISTANCES:
                    current = group[group.distance_m == distance]
                    if current.empty:
                        cells.append("--")
                    else:
                        row = current.iloc[0]
                        cells.append(str(int(row[f"count_{kind}"])) + " [" + f'{row[f"percent_at_count_{kind}"]:.2f}' + r"\%]")
                rows.append((r"\multirow{2}{*}{" + title + "}" if kind == "min" else "") + " & " + kind.capitalize() + " & " + " & ".join(cells) + r" \\")
            rows.append(r"\midrule")
        rows = rows[:-1]
    elif name == "manufacturer_context":
        for camera in LABEL:
            cells = [LABEL[camera].replace(" ", "~")]
            for distance in (1.8, 2.2):
                row = data[data.camera.eq(camera) & data.distance_m.eq(distance)]
                if len(row) != 1:
                    raise ValueError("Context table needs one HD/natural value per camera/distance")
                cells.extend([f"{row.iloc[0].bias_mm:.2f}", f"{row.iloc[0].absolute_bias_percent:.2f}"])
            rows.append(" & ".join(cells) + r"\\")
    else:
        letter = name[-1]; light = "natural" if letter in "ac" else "artificial"
        groups = [(camera, "stereo") for camera in ("rsi", "rsf")] if letter in "ab" else [
            (camera, mode) for camera in ("zedx", "zedxm") for mode in ("neural_light", "neural", "neural_plus")]
        lookup = data.set_index(["camera", "mode", "lighting", "distance_m", "resolution"])
        quantities = [("S_mm", r"$S$ (mm)"), ("S_pl_mm", r"$S_{\mathrm{pl}}$ (mm)"),
                      ("theta_h_deg", r"$\theta_h$ ($^\circ$)"), ("theta_v_deg", r"$\theta_v$ ($^\circ$)")]
        for camera, mode in groups:
            title = LABEL[camera] + (r"\\ " + mode.replace("_", " ").upper() if mode != "stereo" else "")
            for index, (metric, tex) in enumerate(quantities):
                cells = []
                for distance in DISTANCES:
                    pair = [lookup.loc[(camera, mode, light, distance, res), metric] for res in ("hd", "sd")]
                    if not np.isfinite(pair).all():
                        raise ValueError("Nonfinite plane table value")
                    cells.append("$" + " / ".join(printed(value) for value in pair) + "$")
                label = r"\multirow{4}{*}{\shortstack[l]{" + title + "}}" if index == 0 else ""
                rows.append(label + " & " + tex + " & " + " & ".join(cells) + r" \\")
            rows.append(r"\addlinespace")
    return "\n".join(rows)


def render_tables(source, destination):
    """Generate editable table inputs from the complete derived tables."""
    destination.mkdir(parents=True, exist_ok=True)
    for name in TEMPLATES:
        filename = {"app_outliers": "frame_exclusions", "app_invalid_pixels": "invalid_pixel_extrema",
                    "manufacturer_context": "manufacturer_context"}.get(name, "plane_table_values")
        data = pd.read_csv(source / f"{filename}.csv")
        if name.startswith("appendix_d_table_"):
            light = "natural" if name[-1] in "ac" else "artificial"
            family = data.camera.isin(["rsi", "rsf"]) if name[-1] in "ab" else data.camera.str.startswith("zed")
            data = data[family & data.lighting.eq(light)]
        data.to_csv(destination / f"{name}.csv", index=False)
        (destination / f"{name}.tex").write_text(TEMPLATES[name].replace("@ROWS@", table_rows(name, data)))

TEMPLATES = {
    'app_outliers': '\\begin{table}[htbp]\n\\centering\n\\caption{Excluded frames under the target-ID and mean-error criteria.}\n\\label{tab:excluded_frames}\n\\small\n\\setlength{\\tabcolsep}{4pt}\n\\begin{adjustbox}{max width=\\linewidth}\n\\begin{tabular}{llllllll}\n\\toprule\nCamera & Distance (m) & Resolution & Illumination & Mode & $n$ & Frame indices \\\\\n\\midrule\n@ROWS@\n\\bottomrule\n\\end{tabular}\n\\end{adjustbox}\n\\end{table}\n',
    'app_invalid_pixels': '\\begin{table*}[htbp]\n\\centering\n\\caption{Minimum and maximum invalid-pixel counts among affected accepted frames. Brackets give the percentage of the ROI in the frame attaining the displayed count; ties use the earliest frame.}\n\\label{tab:invalid_pixel_counts}\n\\footnotesize\n\\setlength{\\tabcolsep}{2pt}\n\\begin{adjustbox}{max width=\\textwidth}\n\\begin{tabular}{@{}cc*{9}{c}@{}}\n\\toprule\n\\multirow{2}{*}{Configuration} & & \\multicolumn{9}{c}{Reference distance (m)}\\\\\n\\cmidrule(lr){3-11}\n & & 0.4 & 0.6 & 0.8 & 1.0 & 1.4 & 1.8 & 2.2 & 2.6 & 3.0 \\\\\n\\midrule\n@ROWS@\n\\bottomrule\n\\end{tabular}\n\\end{adjustbox}\n\\end{table*}\n',
    'manufacturer_context': '\\begin{table}[h]\n\\centering\n\\caption{Signed regional bias and its absolute percentage of nominal reference distance around 2\\,m; HD/natural illumination, with ZED in \\textit{NEURAL PLUS}.}\n\\label{tab:near_spec}\n\\small\n\\begin{tabular}{lrrrr}\n\\toprule\nCamera & $\\overline b_{1.8}$ (mm) & $|\\overline b_{1.8}|/g$ (\\%) & $\\overline b_{2.2}$ (mm) & $|\\overline b_{2.2}|/g$ (\\%)\\\\\n\\midrule\n@ROWS@\n\\bottomrule\n\\end{tabular}\n\\end{table}\n',
    'appendix_d_table_a': '\\begin{table}\n\\centering\n\\caption{Fitted-plane analysis of the \\realsense cameras under natural illumination. Within-ROI spatial SDV ($S$) and fitted-plane residual SDV ($S_{\\mathrm{pl}}$) are expressed in millimetres, while signed horizontal and vertical inclinations ($\\theta_h$, $\\theta_v$) are expressed in degrees. Columns represent reference distances in metres, with each cell reporting HD / SD values.}\n\\label{tab:appendix-d-a}\n\\small\n\\setlength{\\tabcolsep}{2.5pt}\n\\renewcommand{\\arraystretch}{1.05}\n\\begin{adjustbox}{max width=\\linewidth}\n\\begin{tabular}{ll*{9}{c}}\n\\toprule\n\\multirow{2}{*}{\\shortstack[c]{Camera /\\\\ mode}}\n& \\multirow{2}{*}{Quantity}\n& \\multicolumn{9}{c}{Reference distance (m)} \\\\\n\\cmidrule(lr){3-11}\n& & 0.4 & 0.6 & 0.8 & 1.0 & 1.4 & 1.8 & 2.2 & 2.6 & 3.0 \\\\\n\\midrule\n@ROWS@\n\\bottomrule\n\\end{tabular}\n\\end{adjustbox}\n\\end{table}\n',
    'appendix_d_table_b': '\\begin{table}\n\\centering\n\\caption{Fitted-plane analysis of the \\realsense cameras under artificial illumination. Within-ROI spatial SDV ($S$) and fitted-plane residual SDV ($S_{\\mathrm{pl}}$) are expressed in millimetres, while signed horizontal and vertical inclinations ($\\theta_h$, $\\theta_v$) are expressed in degrees. Columns represent reference distances in metres, with each cell reporting HD / SD values.}\n\\label{tab:appendix-d-b}\n\\small\n\\setlength{\\tabcolsep}{2.5pt}\n\\renewcommand{\\arraystretch}{1.05}\n\\begin{adjustbox}{max width=\\linewidth}\n\\begin{tabular}{ll*{9}{c}}\n\\toprule\n\\multirow{2}{*}{\\shortstack[c]{Camera /\\\\ mode}}\n& \\multirow{2}{*}{Quantity}\n& \\multicolumn{9}{c}{Reference distance (m)} \\\\\n\\cmidrule(lr){3-11}\n& & 0.4 & 0.6 & 0.8 & 1.0 & 1.4 & 1.8 & 2.2 & 2.6 & 3.0 \\\\\n\\midrule\n@ROWS@\n\\bottomrule\n\\end{tabular}\n\\end{adjustbox}\n\\end{table}\n',
    'appendix_d_table_c': '\\begin{table}\n\\centering\n\\caption{Fitted-plane analysis of the ZED cameras under natural illumination. Within-ROI spatial SDV ($S$) and fitted-plane residual SDV ($S_{\\mathrm{pl}}$) are expressed in millimetres, while signed horizontal and vertical inclinations ($\\theta_h$, $\\theta_v$) are expressed in degrees. Columns represent reference distances in metres, with each cell reporting HD / SD values.}\n\\label{tab:appendix-d-c}\n\\small\n\\setlength{\\tabcolsep}{2.5pt}\n\\renewcommand{\\arraystretch}{1.05}\n\\begin{adjustbox}{max width=\\linewidth}\n\\begin{tabular}{ll*{9}{c}}\n\\toprule\n\\multirow{2}{*}{\\shortstack[c]{Camera /\\\\ mode}}\n& \\multirow{2}{*}{Quantity}\n& \\multicolumn{9}{c}{Reference distance (m)} \\\\\n\\cmidrule(lr){3-11}\n& & 0.4 & 0.6 & 0.8 & 1.0 & 1.4 & 1.8 & 2.2 & 2.6 & 3.0 \\\\\n\\midrule\n@ROWS@\n\\bottomrule\n\\end{tabular}\n\\end{adjustbox}\n\\end{table}\n',
    'appendix_d_table_d': '\\begin{table}\n\\centering\n\\caption{Fitted-plane analysis of the ZED cameras under artificial illumination. Within-ROI spatial SDV ($S$) and fitted-plane residual SDV ($S_{\\mathrm{pl}}$) are expressed in millimetres, while signed horizontal and vertical inclinations ($\\theta_h$, $\\theta_v$) are expressed in degrees. Columns represent reference distances in metres, with each cell reporting HD / SD values.}\n\\label{tab:appendix-d-d}\n\\small\n\\setlength{\\tabcolsep}{2.5pt}\n\\renewcommand{\\arraystretch}{1.05}\n\\begin{adjustbox}{max width=\\linewidth}\n\\begin{tabular}{ll*{9}{c}}\n\\toprule\n\\multirow{2}{*}{\\shortstack[c]{Camera /\\\\ mode}}\n& \\multirow{2}{*}{Quantity}\n& \\multicolumn{9}{c}{Reference distance (m)} \\\\\n\\cmidrule(lr){3-11}\n& & 0.4 & 0.6 & 0.8 & 1.0 & 1.4 & 1.8 & 2.2 & 2.6 & 3.0 \\\\\n\\midrule\n@ROWS@\n\\bottomrule\n\\end{tabular}\n\\end{adjustbox}\n\\end{table}\n',
}

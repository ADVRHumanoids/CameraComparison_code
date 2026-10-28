"""Paper plotting functions, adapted from the original renderers.

Called by scripts.render, with already validated CSV/NPZ data only.
Returns Matplotlib figures; no raw bags, logs, reference images or network access.
Units, fonts, dimensions, palette, limits and selected frames follow MainSensors.tex.
"""

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
from matplotlib.ticker import MaxNLocator
import numpy as np

from .analysis_math import marker_grid, transitions


LABEL = {"rsi": "D435i", "rsf": "D435f", "zedx": "ZED X", "zedxm": "ZED X Mini"}
MODE = {"stereo": "--", "neural_light": "LIGHT", "neural": "NEURAL", "neural_plus": "PLUS"}
PALETTE = plt.get_cmap("tab20").colors
COLOUR = {"rsf": PALETTE[0], "rsi": PALETTE[2], "zedx": PALETTE[4], "zedxm": PALETTE[6]}
STYLE = {"font.family": "serif", "font.serif": ["Liberation Serif", "DejaVu Serif"],
         "font.size": 9, "axes.titlesize": 10, "legend.fontsize": 8, "axes.labelsize": 9}


def recording_name(camera, distance=1800, mode="neural_plus"):
    """Identify the paper's HD/natural examples explicitly."""
    return f"{camera}_{distance:04d}_hd" + ("_" + mode if camera.startswith("zed") else "") + "_natural"


def limits(values):
    """Include zero and five-percent padding, matching the original plot scaling."""
    low, high = min(0., float(values.min())), max(0., float(values.max()))
    padding = .05 * (high - low) if high > low else .01
    return low - padding, high + padding


def distribution(frames, camera, mode, span, resolution=None):
    """Reproduce an active bias violin or bias/RMSE scatter, without extra plot families."""
    low, high = (.4, 1.) if span == "short" else (1.4, 3.)
    population = frames[frames.distance_m.between(low, high)]
    depth_limits = limits(population.bias_m)
    data = population[population.camera.eq(camera) & population["mode"].eq(mode)]
    if data.empty:
        raise ValueError("Missing distribution inputs")
    rmse_limits = limits(data.rmse_m)
    distances = sorted(data.distance_m.unique())
    fig, ax = plt.subplots(figsize=(12, 7))
    handles, labels = [], []
    if resolution is None:
        configurations = [("sd", "natural", -1.5), ("hd", "natural", -.5),
                          ("sd", "artificial", .5), ("hd", "artificial", 1.5)]
        for colour, (res, light, offset) in zip(PALETTE, configurations):
            values, positions = [], []
            for index, distance in enumerate(distances):
                subset = data[data.resolution.eq(res) & data.lighting.eq(light) & data.distance_m.eq(distance)]
                if len(subset):
                    values.append(subset.bias_m.to_numpy()); positions.append(index + offset * .2)
            if not values:
                continue
            violin = ax.violinplot(values, positions=positions, widths=.2, showmedians=True)
            for body in violin["bodies"]:
                body.set_facecolor(colour); body.set_edgecolor("black"); body.set_alpha(.6); body.set_linewidth(.6)
            for part in ("cbars", "cmins", "cmaxes", "cmedians"):
                violin[part].set_color(colour); violin[part].set_linewidth(.8)
            handles.append(plt.Line2D([0], [0], color=colour, lw=6))
            labels.append(res.upper() + " - " + light.capitalize() + " Light")
        ax.axhline(y=0, color="red", linestyle="--", alpha=.7, label="Zero Error")
        ax.set_xticks(np.arange(len(distances)), [f"{distance:.2f}m" for distance in distances])
        ax.set_xlabel(r"Distances (ground truth) [m]", fontsize=22)
        ax.set_ylabel(r"$b_t$ [m]", fontsize=22)
        ax.set_axisbelow(True); ax.minorticks_on()
        ax.grid(True, which="major", color="#b0b0b0", linestyle="--", linewidth=2, alpha=1)
        ax.grid(True, which="minor", axis="y", color="#b0b0b0", linestyle=":", linewidth=1.5, alpha=.5)
        ax.set_ylim(depth_limits)
        ax.legend(handles, labels, loc="best", fontsize=22)
    else:
        index = 0
        for distance in distances:
            for light in ("natural", "artificial"):
                subset = data[data.resolution.eq(resolution) & data.lighting.eq(light) & data.distance_m.eq(distance)]
                if subset.empty:
                    continue
                colour = PALETTE[index % len(PALETTE)]
                ax.scatter(subset.bias_m.to_numpy(), subset.rmse_m.to_numpy(), facecolors="none", edgecolors=colour,
                           alpha=.6, s=30, label=f"{distance:.2f}m - {light.capitalize()} Light", linewidths=1.5)
                handles.append(plt.Line2D([], [], marker="o", color="w", markerfacecolor="none",
                                          markersize=8, markeredgecolor=colour, markeredgewidth=2))
                labels.append(f"{distance:.2f}m - {light.capitalize()} Light"); index += 1
        ax.axvline(x=0, color="red", linestyle="--", alpha=.7, label="Zero Avg Error")
        ax.axhline(y=0, color="red", linestyle=":", alpha=.7, label="Zero RMSE")
        ax.set_xlabel(r"$b_t$ [m]", fontsize=22); ax.set_ylabel(r"$r_t$ [m]", fontsize=22)
        ax.grid(True, alpha=.5, which="both", linestyle="--", linewidth=1)
        ax.set_ylim(rmse_limits); ax.set_xlim(depth_limits)
        ax.legend(handles, labels, title="Distance - Test", loc="best", ncol=2 if len(handles) > 6 else 1, fontsize=18)
    ax.tick_params(axis="both", which="major", labelsize=20)
    fig.tight_layout()
    return fig


def summary_plot(summary, name):
    """Render the paper's bias grid or equally weighted configuration envelopes."""
    baseline = summary[summary.camera.isin(["rsi", "rsf"]) | summary["mode"].eq("neural_plus")]
    if name == "bias_conditions":
        fig, axes = plt.subplots(2, 2, figsize=(7.1, 4.8), layout="constrained")
        for ax, (res, light) in zip(axes.flat, [("hd", "natural"), ("hd", "artificial"), ("sd", "natural"), ("sd", "artificial")]):
            data = baseline[baseline.resolution.eq(res) & baseline.lighting.eq(light)]
            for camera, group in data.groupby("camera", sort=False):
                group = group.sort_values("distance_m"); complete = group[group.bag_frames == 300]
                ax.plot(group.distance_m, group.bias_m * 1000, "-", lw=1, color=COLOUR[camera], label=LABEL[camera])
                ax.scatter(complete.distance_m, complete.bias_m * 1000, s=9, color=COLOUR[camera])
                partial = group[group.bag_frames < 300]
                ax.scatter(partial.distance_m, partial.bias_m * 1000, s=30, facecolors="none", edgecolors=COLOUR[camera], zorder=4)
            ax.set_xlabel("Reference distance (m)"); ax.grid(alpha=.2)
            ax.axhline(0, color="gray", lw=.6); ax.set(title=f"{res.upper()}, {light} light", ylabel=r"$\overline{b}$ [mm]")
        axes[0, 0].legend(ncol=2)
        return fig
    modes = name == "zed_mode_envelope"
    metrics = [("absolute_bias_m", r"$|\overline{b}|$ [mm]"), ("spatial_sd_m", r"$S$ [mm]"),
               ("rmse_m", r"$R$ [mm]"), ("pixel_temporal_rms_m", r"$T_{\mathrm{px}}$ [mm]")]
    if modes:
        data = summary[summary.camera.isin(["zedx", "zedxm"])]
        fig, axes = plt.subplots(2, 2, figsize=(7.1, 5), layout="constrained")
        groups = [(camera, mode) for camera in ("zedx", "zedxm") for mode in ("neural_light", "neural", "neural_plus")]
    else:
        data = baseline; metrics = metrics[1:]
        fig, axes = plt.subplots(1, 3, figsize=(8.6, 3), layout="constrained")
        groups = [(camera, "neural_plus" if camera.startswith("zed") else "stereo") for camera in LABEL]
    for ax, (metric, ylabel) in zip(axes.flat, metrics):
        for camera, mode in groups:
            subset = data[data.camera.eq(camera) & data["mode"].eq(mode)]
            values = subset.groupby("distance_m")[metric].agg(["min", "median", "max"]) * 1000
            if len(values) != 9 or not subset.groupby("distance_m").size().eq(4).all():
                raise ValueError("Envelope needs all nine distances and four configurations")
            colour = np.array(matplotlib.colors.to_rgb(COLOUR[camera])); linestyle = "-"; marker = "o"; label = LABEL[camera]
            if modes:
                label += " " + MODE[mode]
                if mode == "neural_light": colour = .65 * colour + .35; linestyle = ":"; marker = "s"
                elif mode == "neural_plus": colour = .65 * colour; linestyle = "--"; marker = "^"
            else:
                ax.fill_between(values.index, values["min"], values["max"], color=colour, alpha=.12, linewidth=0)
            ax.plot(values.index, values["median"], color=colour, linestyle=linestyle, marker=marker, lw=1.2, ms=3, label=label)
        ax.set(xlabel="Reference distance (m)", ylabel=ylabel, ylim=(0, None), xticks=[.4, 1., 1.8, 2.6, 3.])
        ax.grid(alpha=.25, linewidth=.5); ax.set_axisbelow(True)
    axes.flat[0].legend(fontsize=7 if modes else 8, ncol=2, loc="upper left")
    return fig


def temporal_maps(pixels):
    """Keep four common-scale maps and the two unchanged ZED expanded-scale maps."""
    heats = {}
    for camera in LABEL:
        p = pixels[recording_name(camera)]
        v, u = p["rows"], p["cols"]; keep = p["count"] >= .9 * int(p["evaluated_frames"])
        values = p["temporal_sd_m"][keep] * 1000
        if not len(values) or not np.isfinite(values).all() or (camera.startswith("zed") and values.max() > .8):
            raise ValueError("Invalid/clipped temporal map")
        heat = np.full((int(v.max() - v.min() + 1), int(u.max() - u.min() + 1)), np.nan)
        heat[v[keep] - v.min(), u[keep] - u.min()] = values; heats[camera] = heat
    fig, axes = plt.subplots(2, 3, figsize=(8.6, 4.9), layout="constrained")
    for ax, camera in zip(axes[:, :2].flat, LABEL):
        common = ax.imshow(heats[camera], vmin=0, vmax=60., cmap="magma", interpolation="nearest")
        ax.set(title=LABEL[camera], xticks=[], yticks=[])
    for ax, camera in zip(axes[:, 2], ("zedx", "zedxm")):
        zoom = ax.imshow(heats[camera], vmin=0, vmax=.8, cmap="magma", interpolation="nearest")
        ax.set(title=LABEL[camera] + " (expanded scale)", xticks=[], yticks=[])
    fig.colorbar(common, ax=list(axes[:, :2].flat), label="Temporal SDV (mm)", shrink=.8)
    fig.colorbar(zoom, ax=list(axes[:, 2]), label="Temporal SDV (mm)", shrink=.8)
    return fig


def boundary_example(pixels, reference):
    """Use the original context crop and nominal transition overlay for LIGHT/PLUS."""
    fig, axes = plt.subplots(1, 3, figsize=(7.1, 2.4), layout="constrained")
    for index, mode in enumerate(("neural_light", "neural_plus")):
        name = recording_name("zedxm", mode=mode); p = pixels[name]; first = reference[name]
        polygon = first["polygon_xy"].astype(np.float32)
        transform = cv2.getPerspectiveTransform(polygon, np.array([[0, 0], [6, 0], [6, 6], [0, 6]], np.float32))
        segments = transitions(marker_grid(int(first["marker_id"])))
        if index == 0:
            axes[0].imshow(cv2.cvtColor(first["rgb"], cv2.COLOR_BGR2RGB)); axes[0].set(xticks=[], yticks=[], title="RGB reference")
            for edge in segments:
                xy = cv2.perspectiveTransform(edge.astype(np.float32).reshape(-1, 1, 2), np.linalg.inv(transform)).reshape(-1, 2) - first["origin_uv"]
                axes[0].plot(xy[:, 0], xy[:, 1], color="cyan", lw=.6)
        v, u = p["rows"], p["cols"]; keep = p["count"] >= .9 * int(p["evaluated_frames"])
        shape = (int(v.max() - v.min() + 1), int(u.max() - u.min() + 1))
        heat, distance = np.full(shape, np.nan), np.full(shape, np.nan)
        heat[v[keep] - v.min(), u[keep] - u.min()] = p["temporal_sd_m"][keep] * 1000
        from .analysis_math import edge_distance
        points = cv2.perspectiveTransform(np.column_stack([u, v]).astype(np.float32).reshape(-1, 1, 2), transform).reshape(-1, 2)
        distance[v - v.min(), u - u.min()] = edge_distance(points, segments)
        im = axes[index + 1].imshow(heat, cmap="magma", vmin=0, vmax=2.5)
        axes[index + 1].contour(distance, levels=[.15], colors="cyan", linewidths=.4)
        axes[index + 1].set(title=mode.replace("_", " ").upper(), xticks=[], yticks=[])
    fig.colorbar(im, ax=list(axes[1:]), label="Temporal SDV (mm)", shrink=.8)
    return fig


def mask_edges(mask, origin_uv):
    """Trace the exact rasterized ROI at half-integer pixel edges."""
    u0, v0 = origin_uv; padded = np.pad(np.asarray(mask, dtype=np.int8), 1)
    rows, cols = np.nonzero(np.diff(padded, axis=0)[:, 1:-1])
    horizontal = np.stack([np.column_stack([cols + u0 - .5, rows + v0 - .5]),
                           np.column_stack([cols + u0 + .5, rows + v0 - .5])], axis=1)
    rows, cols = np.nonzero(np.diff(padded, axis=1)[1:-1, :])
    vertical = np.stack([np.column_stack([cols + u0 - .5, rows + v0 - .5]),
                         np.column_stack([cols + u0 - .5, rows + v0 + .5])], axis=1)
    return np.concatenate([horizontal, vertical])


def residual_maps(maps):
    """Preserve the paper's native coordinates, raster outlines and separate family scales."""
    cmap = plt.get_cmap("RdBu_r").copy(); cmap.set_bad("white")
    fig, axes = plt.subplots(2, 2, figsize=(6.6, 6.), layout="constrained")
    for row, (family, cameras) in enumerate([("RealSense", ["rsi", "rsf"]), ("ZED", ["zedx", "zedxm"])]):
        maximum = max(float(np.nanmax(np.abs(maps[camera]["residual_mm"]))) for camera in cameras)
        if maximum <= 0 or not np.isfinite(maximum):
            raise ValueError("Residual colour range must be finite and positive")
        step = 10**np.floor(np.log10(maximum)) / 2; limit = float(np.ceil(maximum / step) * step)
        norm = Normalize(vmin=-limit, vmax=limit)
        for ax, camera in zip(axes[row], cameras):
            data = maps[camera]; heat = data["residual_mm"]; u0, v0 = data["origin_uv"]; height, width = heat.shape
            if int(data["frame"]) != 150 or np.any(np.isfinite(heat) & ~data["roi_mask"].astype(bool)):
                raise ValueError("Invalid frame-150 residual mask")
            ax.imshow(heat, cmap=cmap, norm=norm, interpolation="nearest", origin="upper",
                      extent=(u0 - .5, u0 + width - .5, v0 + height - .5, v0 - .5), aspect="equal")
            ax.add_collection(LineCollection(mask_edges(data["roi_mask"], data["origin_uv"]), colors="0.25", linewidths=.5))
            ax.set(title=LABEL[camera], xlabel="Image column u (px)", ylabel="Image row v (px)")
            ax.xaxis.set_major_locator(MaxNLocator(nbins=4, integer=True)); ax.yaxis.set_major_locator(MaxNLocator(nbins=4, integer=True))
        fig.colorbar(ScalarMappable(norm=norm, cmap=cmap), ax=list(axes[row]), label=f"{family}: signed residual (mm)",
                     ticks=np.linspace(-limit, limit, 5), shrink=.9, fraction=.045, pad=.03)
    return fig


def point_cloud(clouds, name):
    """Use shared limits from both clouds and the original view/physical axis units."""
    bounds = []
    for key in ("x_mm", "y_mm", "z_reference_mm"):
        values = np.concatenate([cloud[key] for cloud in clouds.values()]); pad = .05 * np.ptp(values)
        bounds.append((values.min() - pad, values.max() + pad))
    cloud = clouds[name]
    fig = plt.figure(figsize=(5, 4)); ax = fig.add_subplot(projection="3d")
    ax.scatter(cloud["x_mm"], cloud["y_mm"], cloud["z_reference_mm"], c=cloud["rgb"], s=1, rasterized=True)
    ax.set(xlabel="X (mm)", ylabel="Y (mm)", xlim=bounds[0], ylim=bounds[1], zlim=bounds[2])
    fig.text(.88, .61, "Z (mm)", rotation=90, va="center", fontsize=9)
    ax.view_init(elev=30, azim=-65); ax.set_box_aspect((1, 1, .4)); fig.subplots_adjust(left=0, right=.82, bottom=.1, top=.85)
    return fig


def boundary_ratio_distance(recordings):
    """Combine distance-resolved observations and marginal histograms in eight panels."""
    good=recordings[recordings.primary_eligible].copy()
    assert not good.recording.duplicated().any()
    assert np.isfinite(good[['distance_m','edge_interior_ratio']].to_numpy()).all()
    q=good.edge_interior_ratio.to_numpy()
    edges=np.arange(np.floor(min(q.min(),1.)*10),np.ceil(max(q.max(),1.)*10)+1)/10
    groups=[('rsi','stereo'),* [('zedx',mode) for mode in ['neural_light','neural','neural_plus']],
            ('rsf','stereo'),* [('zedxm',mode) for mode in ['neural_light','neural','neural_plus']]]
    conditions=[('sd','natural'),('hd','natural'),('sd','artificial'),('hd','artificial')]
    fig=plt.figure(figsize=(12,5.8),layout='constrained')
    grid=fig.add_gridspec(2,4);summaries=[];plotted=[];histograms=[]
    count_max=max(np.histogram(g.edge_interior_ratio,bins=edges)[0].max()
                  for _,g in good.groupby(['camera','mode']))
    for index,(camera,mode) in enumerate(groups):
        inner=grid[index//4,index%4].subgridspec(1,2,width_ratios=[4,1],wspace=.04)
        ax=fig.add_subplot(inner[0]);hist=fig.add_subplot(inner[1],sharey=ax)
        group=good[(good.camera==camera)&(good['mode']==mode)];color=COLOUR[camera]
        assert len(group)>0
        for resolution,lighting in conditions:
            subset=group[(group.resolution==resolution)&(group.lighting==lighting)]
            ax.scatter(subset.distance_m,subset.edge_interior_ratio,s=22,
                       marker='o' if resolution=='sd' else '^',
                       facecolors=color if lighting=='natural' else 'none',edgecolors=color,linewidths=.8)
            plotted.extend(subset.recording.tolist())
        for distance,subset in group.groupby('distance_m'):
            values=subset.edge_interior_ratio
            ax.plot(distance,values.median(),marker='_',ms=10,color='black',ls='none',mew=1.3)
            summaries.append(dict(camera=camera,mode=mode,distance_m=distance,recordings=len(subset),
                                  median_q=values.median(),min_q=values.min(),max_q=values.max()))
        counts,_=np.histogram(group.edge_interior_ratio,bins=edges)
        assert counts.sum()==len(group)
        hist.stairs(counts,edges,orientation='horizontal',color=color,fill=True,alpha=.25,linewidth=.8)
        histograms.extend(dict(camera=camera,mode=mode,q_low=low,q_high=high,count=int(count))
                          for low,high,count in zip(edges[:-1],edges[1:],counts))
        title=LABEL[camera]+('' if mode=='stereo' else ' / '+MODE[mode])
        ax.set(title=title,xlabel='Distance (m)',xlim=(.25,3.15),ylim=(edges[0],edges[-1]),
               xticks=[.4,1.,1.8,2.6],yticks=[.5,.75,1.,1.25])
        ax.set_title(title,fontsize=12)
        ax.text(.04,.95,f'n = {len(group)}',transform=ax.transAxes,va='top',fontsize=10)
        if index%4==0:ax.set_ylabel(r'$Q$')
        ax.grid(alpha=.2,linewidth=.5);ax.set_axisbelow(True)
        hist.set(xlim=(0,count_max*1.15),xlabel='Count',xticks=[0,10])
        hist.tick_params(axis='y',left=False,labelleft=False)
        for axis in [ax,hist]:
            axis.axhline(1,color='.4',ls='--',lw=.7)
            axis.tick_params(axis='both',labelsize=10.5)
            axis.xaxis.label.set_fontsize(11)
            axis.yaxis.label.set_fontsize(11)
    assert len(plotted)==len(good) and set(plotted)==set(good.recording)
    handles=[matplotlib.lines.Line2D([],[],marker='o' if res=='sd' else '^',ls='none',
             markerfacecolor='.35' if light=='natural' else 'none',markeredgecolor='.35',
             label=res.upper()+' / '+light) for res,light in conditions]
    handles.append(matplotlib.lines.Line2D([],[],marker='_',color='black',ls='none',ms=10,label='Distance median'))
    fig.legend(handles=handles,loc='outside lower center',ncol=5,fontsize=10.5,frameon=False)
    return fig

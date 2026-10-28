#!/usr/bin/env python3
"""Standalone paper reproduction entry point.

Usage: python main.py {download,extract,analyze,render,all,incremental_download,incremental_all}
Inputs: existing ROS 2 bags, or Dataverse release 1.0 for explicit downloads.
Outputs: compact extraction artifacts under analysis/; downloads under dataset/.
Status: complete pipeline; downloading remains a separate explicit command.
"""

import argparse
from pathlib import Path
from tarfile import TarError


def main():
    """Dispatch explicitly requested work, resolving defaults beside this file."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    download = commands.add_parser("download", help="Download and extract bags, excluding logs")
    download.add_argument("--dataset", type=Path, default=Path(__file__).resolve().parent / "dataset")
    download.add_argument("--stream", action="store_true", help="Verify/extract network streams without storing compressed archives")
    download.add_argument("--workers", type=int, default=1, help="Concurrent archive transfers (default: 1)")
    extract = commands.add_parser("extract", help="Read existing bags without acquisition logs")
    extract.add_argument("--dataset", type=Path, default=Path(__file__).resolve().parent / "dataset")
    extract.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "analysis")
    extract.add_argument("--recording", help="Process just one recording, retaining the full inventory")
    analyze = commands.add_parser("analyze", help="Derive tables, planes, profiles and boundary statistics")
    analyze.add_argument("--dataset", type=Path, default=Path(__file__).resolve().parent / "dataset")
    analyze.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "analysis",
                         help="Existing extraction root; derived files go into its derived/ subfolder")
    analyze.add_argument("--recording", help="Analyze one extracted recording without exporting global tables")
    render = commands.add_parser("render", help="Render paper figures/tables from cached analysis only")
    render.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "analysis",
                        help="Existing extraction/analysis root")
    render.add_argument("--destination", type=Path, default=Path(__file__).resolve().parent,
                        help="Parent folder for figures/ and tables/")
    render.add_argument("--figure", nargs="+", help="Explicit figure paths, e.g. revision/temporal_maps; omit for all figures/tables")
    all_stages = commands.add_parser("all", help="Download if needed, then extract, analyze and render the complete dataset")
    all_stages.add_argument("--dataset", type=Path, default=Path(__file__).resolve().parent / "dataset")
    all_stages.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "analysis")
    all_stages.add_argument("--destination", type=Path, default=Path(__file__).resolve().parent)
    for name in ("incremental_download", "incremental_all"):
        incremental = commands.add_parser(name, help="Incremental download/analysis/cleanup" + (" and rendering" if name == "incremental_all" else " without rendering"))
        incremental.add_argument("--cache", type=Path, default=Path(__file__).resolve().parent / "incremental_cache",
                                 help="New dedicated raw-download cache; analyzed raw files are deleted here")
        incremental.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "incremental_results/analysis")
        incremental.add_argument("--destination", type=Path, default=Path(__file__).resolve().parent / "incremental_results")
    args = parser.parse_args()
    try:
        if args.command == "download":
            from scripts.download_dataset import download_dataset
            download_dataset(args.dataset, stream=args.stream, workers=args.workers)
        elif args.command == "extract":
            from scripts.extract import extract_dataset
            extract_dataset(args.dataset, args.output, args.recording)
        elif args.command == "analyze":
            from scripts.analyze import analyze_dataset
            analyze_dataset(args.dataset, args.output, args.recording)
        elif args.command == "render":
            from scripts.render import render_paper
            render_paper(args.output, args.destination, args.figure)
        elif args.command in ("incremental_download", "incremental_all"):
            from scripts.incremental import incremental_download, incremental_all
            runner = incremental_all if args.command == "incremental_all" else incremental_download
            runner(args.cache, args.output, args.destination)
        else:
            if not args.dataset.expanduser().is_dir():
                from scripts.download_dataset import download_dataset
                download_dataset(args.dataset, stream=True, workers=4)
            from scripts.extract import extract_dataset
            from scripts.analyze import analyze_dataset
            from scripts.render import render_paper
            extract_dataset(args.dataset, args.output)
            analyze_dataset(args.dataset, args.output)
            render_paper(args.output, args.destination)
    except (OSError, ValueError, RuntimeError, TarError, KeyError) as error:
        parser.exit(1, f"{args.command.capitalize()} failed: {error}\n")


if __name__ == "__main__":
    main()

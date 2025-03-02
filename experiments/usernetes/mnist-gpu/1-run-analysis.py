#!/usr/bin/env python3

import argparse
import collections
import json
import os
import re
import sys

import matplotlib.pylab as plt
import pandas
import seaborn as sns

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)

import performance_study as ps

sns.set_theme(style="whitegrid", palette="muted")


def get_parser():
    parser = argparse.ArgumentParser(
        description="Analyze Compute Engine (Usernetes) vs. GKE",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--root",
        help="root directory with experiments",
        default=here,
    )
    parser.add_argument(
        "--out",
        help="directory to save parsed results",
        default=os.path.join(here, "results"),
    )
    return parser


def main():
    """
    Find application result files to parse.
    """
    parser = get_parser()
    args, _ = parser.parse_known_args()

    # Output images and data
    outdir = os.path.abspath(args.out)
    indir = os.path.abspath(args.root)
    if not os.path.exists(outdir):
        os.makedirs(outdir)

    # Find input directories (anything with data)
    files = ps.find_inputs(indir, "data")
    files = [
        x
        for x in files
        if ".terraform" not in x and x.endswith("/data") and "docker/data" not in x
    ]
    if not files:
        raise ValueError(f"There are no input files in {indir}")

    # Saves raw data to file
    df = parse_data(indir, outdir, files)
    plot_results(df, outdir)


def parse_timestamp(timestamp):
    minutes = 0
    # First check for milliseconds, if reported in ms there aren't seconds or minutes
    if "ms" in timestamp:
        return float(timestamp.replace("ms", "", 1)) / 1000
    if "m" in timestamp:
        minutes, rest = timestamp.split("m", 1)
        minutes = int(minutes)
        timestamp = rest
    seconds = float(timestamp.rstrip("s"))
    return (minutes * 60) + seconds


def parse_data(indir, outdir, files):
    """
    Parse filepaths for environment, etc., and results files for data.
    """
    # metrics here will be wall time and wrapped time
    p = ps.ResultParser("usernetes-vs-kubernetes")

    # It's important to just parse raw data once, and then use intermediate
    for dirname in files:
        exp = ps.ExperimentNameParser(dirname, indir)

        # Calculate number of gpus from nodes
        number_gpus = exp.size

        # Set the parsing context for the result data frame
        p.set_context(exp.cloud, exp.env, exp.env_type, exp.size, gpu_count=number_gpus)
        exp.show()

        # Now we can read each result file to get metrics.
        results = list(ps.get_outfiles(dirname))

        # We drop the first iteration - we had to pull containers
        results = [x for x in results if "iter-1-" not in x]
        for result in results:

            # Basename that start with underscore are test or otherwise should not be included
            item = ps.read_file(result)

            # Real runtime
            runtime = [x for x in item.split("\n") if "real" in x][0]
            runtime = parse_timestamp(runtime.split("\t")[-1])
            p.add_result("time_seconds", runtime)

            # Epoch stats
            for i, line in enumerate(
                [x for x in item.split("\n") if "metricName" in x]
            ):
                for metric in line.split("     ")[-1].split(";"):
                    metric_name = metric.split(",")[0].split(":")[-1].strip()
                    metric_value = float(
                        metric.split(",")[-1].split(":")[-1].strip().replace("}", "")
                    )
                    p.add_result(f"epoch_{i}_{metric_name}", metric_value)

    print("Done parsing study data")
    # Generate a usernetes vs. kubernetes column
    setup = []
    for x in p.df.env.values:
        if x == "gke":
            setup.append("kubernetes")
        else:
            setup.append("usernetes")
    p.df["setup"] = setup
    p.df.to_csv(os.path.join(outdir, "results.csv"))
    return p.df


def plot_results(df, outdir):
    """
    Plot analysis results
    """
    img_outdir = os.path.join(outdir, "img")
    if not os.path.exists(img_outdir):
        os.makedirs(img_outdir)

    # Within a setup, compare between experiments for GPU and cpu
    for metric in df.metric.unique():
        subset = df[df.metric == metric]
        title = " ".join([x.capitalize() for x in metric.split("_")])
        if metric == "time_seconds":
            y_label = "Time (Seconds)"
        else:
            y_label = title
        ps.make_plot(
            subset,
            title=f"Kubernetes vs Usernetes MNIST (GPU)",
            ydimension="value",
            plotname=f"user-vs-kuber-netes-{metric}-gpu",
            xdimension="gpu_count",
            outdir=img_outdir,
            hue="setup",
            xlabel="GPU Count",
            ylabel=y_label,
            do_round=False,
        )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3

import argparse
import os
import sys
import re
import pandas

import matplotlib.pylab as plt
import seaborn as sns

here = os.path.dirname(os.path.abspath(__file__))
analysis_root = os.path.dirname(here)
root = os.path.dirname(analysis_root)
sys.path.insert(0, analysis_root)

import performance_study as ps

sns.set_theme(style="whitegrid", palette="muted")

# These are files I found erroneous - no result, or incomplete result
# Details included with each, and more exploration is likely needed to quantify
# error types
errors = []
error_regex = "(%s)" % "|".join(errors)


def get_parser():
    parser = argparse.ArgumentParser(
        description="Run analysis",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--root",
        help="root directory with experiments",
        default=os.path.join(root, "experiments"),
    )
    parser.add_argument(
        "--non-anon",
        help="Generate non-anon",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--out",
        help="directory to save parsed results",
        default=os.path.join(here, "data"),
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

    # We absolutely want on premises results here
    if not os.path.exists(outdir):
        os.makedirs(outdir)

    # Find input files (skip anything with test)
    files = ps.find_inputs(indir, "RTT.csv")
    if not files:
        raise ValueError(f"There are no input files in {indir}")

    parse_data(indir, outdir, files)


def parse_data(indir, outdir, files):
    """
    Parse filepaths for environment, etc., and results files for data.
    """
    # metrics here will be figures of merit, and seconds runtime
    p = ps.ProblemSizeParser("netmark")

    # For flux we can save jobspecs and other event data
    data = {}
    img_outdir = os.path.join(outdir, "img")
    if not os.path.exists(img_outdir):
        os.makedirs(img_outdir)

    # It's important to just parse raw data once, and then use intermediate
    for filename in files:
        exp = ps.ExperimentNameParser(filename, indir)
        if exp.prefix not in data:
            data[exp.prefix] = []
        exp.show()

        hosts_file = os.path.join(os.path.dirname(filename), "hosts.csv")
        hosts = list(pandas.read_csv(hosts_file))
        df = pandas.read_csv(filename, header=None, names=hosts)
        df.index = hosts

        plt.figure(figsize=(20, 18))
        sns.heatmap(df, vmin=0, vmax=70, cmap="crest")
        plt.title(
            f"                 Netmark Latency Google Kubernetes Size {exp.size}",
            fontsize=16,
        )
        plt.tight_layout()
        plt.savefig(os.path.join(img_outdir, f"netmark-size-{exp.size}-heatmap.svg"))
        plt.savefig(os.path.join(img_outdir, f"netmark-size-{exp.size}-heatmap.png"))

        plt.close()
        plt.clf()
        sns.clustermap(df, cmap="crest")
        plt.savefig(os.path.join(img_outdir, f"netmark-size-{exp.size}-cluster.svg"))
        plt.savefig(os.path.join(img_outdir, f"netmark-size-{exp.size}-cluster.png"))
        plt.close()
        plt.clf()

    print("Done parsing netmark results!")


if __name__ == "__main__":
    main()

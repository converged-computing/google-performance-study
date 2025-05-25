#!/usr/bin/env python3

import argparse
import os
import sys
import re

import matplotlib.pylab as plt
import seaborn as sns

here = os.path.dirname(os.path.abspath(__file__))
analysis_root = os.path.dirname(here)
root = os.path.dirname(analysis_root)
sys.path.insert(0, analysis_root)

import performance_study as ps

sns.set_theme(style="whitegrid", palette="muted")

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
    files = ps.find_inputs(indir, "cfdscope")
    if not files:
        raise ValueError(f"There are no input files in {indir}")

    # Saves raw data to file
    df = parse_data(indir, outdir, files)
    plot_results(df, outdir, args.non_anon)

def parse_data(indir, outdir, files):
    """
    Parse filepaths for environment, etc., and results files for data.
    """
    # metrics here will be figures of merit, and seconds runtime
    p = ps.ProblemSizeParser("cfdscope")

    # It's important to just parse raw data once, and then use intermediate
    for filename in files:
        if "connection-lost" in filename or "slower" in filename:
            continue
        exp = ps.ExperimentNameParser(filename, indir)

        # Set the parsing context for the result data frame
        p.set_context(exp.cloud, exp.env, exp.env_type, exp.size)
        
        # Sanity check the files we found
        print(filename)
        exp.show()
         
        item = ps.read_file(filename)
        threads = int(filename.split('threads-')[-1].replace('.out', ''))
        jobs = ps.parse_flux_jobs(item)
        for job, metadata in jobs.items():
            # Parse the FOM from the item - I see three.
            # This needs to throw an error if we can't find it - indicates the result file is wonky
            # Figure of Merit (FOM): nnz_AP / (Setup Phase Time + 3 * Solve Phase Time) 1.148604e+09
            simulation_seconds = float(metadata['log'].split('\n')[-1].split(' ')[-2]) 
            p.add_result("simulation_seconds", simulation_seconds, threads)
            p.add_result("duration", metadata['duration'], threads)

    print("Done parsing cfdscope results!")

    # Save stuff to file first
    p.df.to_csv(os.path.join(outdir, "cfdscope-results.csv"))
    ps.write_json(jobs, os.path.join(outdir, "flux-jobs-and-events.json"))
    return p.df


def plot_results(df, outdir, non_anon=False):
    """
    Plot analysis results
    """
    # Let's get some shoes! Err, plots.
    # Make an image outdir
    img_outdir = os.path.join(outdir, "img")
    if not os.path.exists(img_outdir):
        os.makedirs(img_outdir)
    
    # We are going to put the plots together, and the colors need to match!
    cloud_colors = {}
    for cloud in df.experiment.unique():
        cloud_colors[cloud] = ps.match_color(cloud)

    # Within a setup, compare between experiments for GPU and cpu
    frames = {}
    for env in df.env_type.unique():
        subset = df[df.env_type == env]

        # Make a plot for seconds runtime, and each FOM set.
        # We can look at the metric across sizes, colored by experiment
        for metric in subset.metric.unique():
            metric_df = subset[subset.metric == metric]
            frames[metric] = metric_df

    # Figure for paper
    fig = plt.figure(figsize=(5, 3))
    gs = plt.GridSpec(1, 1, width_ratios=[1])
    axes = []
    axes.append(fig.add_subplot(gs[0, 0]))
    
    sns.set_style("whitegrid")
    sns.barplot(
        frames['simulation_seconds'],
        ax=axes[0],
        # This is threads
        x="problem_size",
        y="value",
        hue="experiment",
        err_kws={"color": "darkred"},
        order=[11, 22, 44, 88],
        palette=cloud_colors,
    )
    axes[0].set_title(f"Simulation Duration", fontsize=12)
    axes[0].set_ylabel("Seconds", fontsize=12)
    axes[0].set_xlabel("Threads", fontsize=12)
    for ax in axes:
       legend = ax.get_legend()
       if legend:
           legend.remove()
    plt.tight_layout()
    plt.savefig(os.path.join(img_outdir, f"cfdscope-paper.svg"))
    plt.savefig(os.path.join(img_outdir, f"cfdscope-paper.png"))
    plt.clf()

    print(f'Total number of CPU datum: {frames["simulation_seconds"].shape[0]}')


if __name__ == "__main__":
    main()

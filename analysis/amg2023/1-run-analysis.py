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
    files = ps.find_inputs(indir, "amg")
    if not files:
        raise ValueError(f"There are no input files in {indir}")

    # Saves raw data to file
    df = parse_data(indir, outdir, files)
    plot_results(df, outdir, args.non_anon)


def get_fom_line(item, name):
    """
    Get a figure of merit based on the name
    """
    line = [x for x in item.split("\n") if name in x][0]
    return float(line.rsplit(" ", 1)[-1])


def parse_data(indir, outdir, files):
    """
    Parse filepaths for environment, etc., and results files for data.
    """
    # metrics here will be figures of merit, and seconds runtime
    p = ps.ProblemSizeParser("amg2023")

    # For flux we can save jobspecs and other event data
    data = {}

    # It's important to just parse raw data once, and then use intermediate
    for filename in files:
        exp = ps.ExperimentNameParser(filename, indir)
        if "compute-engine" in filename:
            continue
        mpi = "openmpi"
        if "intel" in filename:
            mpi = "intel"
        if exp.prefix not in data:
            data[exp.prefix] = []

        # Set the parsing context for the result data frame
        p.set_context(exp.cloud, exp.env, exp.env_type, exp.size)
        
        # Sanity check the files we found
        print(filename)
        exp.show()
         
        item = ps.read_file(filename)
        
        # amg started to error at size 64
        if "MPI_ERR" in item:
            continue

        jobs = ps.parse_flux_jobs(item)
        for job, metadata in jobs.items():
            if "log" not in metadata:
                print(filename)
                continue
            # Parse the FOM from the item - I see three.
            # This needs to throw an error if we can't find it - indicates the result file is wonky
            # Figure of Merit (FOM): nnz_AP / (Setup Phase Time + 3 * Solve Phase Time) 1.148604e+09
            fom_overall = get_fom_line(metadata['log'], "Figure of Merit (FOM)")
            p.add_result("fom_overall", fom_overall, mpi)
            if "duration" in metadata:
                p.add_result("duration", metadata['duration'], mpi)
            else:
                print(filename)

    print("Done parsing amg2023 results!")

    # Save stuff to file first
    p.df.to_csv(os.path.join(outdir, "amg2023-results.csv"))
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

    # TODO do we want to do this?
    # ps.print_experiment_cost(df, outdir)
    
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
            title = " ".join([x.capitalize() for x in metric.split("_")])
            title = title.replace("Fom", "FOM")
            frames[metric] = {'cpu': metric_df}

    for metric, data_frames in frames.items():
        # We only have one for now :)
        fig = plt.figure(figsize=(4, 2))
        gs = plt.GridSpec(1, 1)
        axes = []
        axes.append(fig.add_subplot(gs[0, 0]))

        # These are all ubuntu openmpi, the intel spack build was using it
        sns.set_style("whitegrid")
        sns.barplot(
            data_frames["cpu"],
            ax=axes[0],
            x="nodes",
            y="value",
            hue="experiment",
            err_kws={"color": "darkred"},
            palette=cloud_colors,
            order=[4, 8, 16, 32],
        )
        if metric == "duration":        
            duration_df = data_frames["cpu"]
            axes[0].set_title("AMG2023 Duration (CPU)", fontsize=12)
            axes[0].set_ylabel("Seconds", fontsize=12)
        else:
            fom_df = data_frames["cpu"]        
            axes[0].set_title("FOM Overall (CPU)", fontsize=12)
            axes[0].set_ylabel("FOM Overall", fontsize=12)
        axes[0].set_xlabel("Nodes", fontsize=12)        
        axes[0].get_legend().remove()
        
        plt.tight_layout()
        plt.savefig(os.path.join(img_outdir, f"amg-{metric}-cpu.svg"))
        plt.savefig(os.path.join(img_outdir, f"amg-{metric}-cpu.png"))
        plt.clf()

        # Print the total number of data points
        print(f'Total number of CPU datum for {metric}: {data_frames["cpu"].shape[0]}')

    # Figure for paper - include duration and FOM
    fig = plt.figure(figsize=(9, 3))
    gs = plt.GridSpec(1, 2, width_ratios=[1, 1])
    axes = []
    axes.append(fig.add_subplot(gs[0, 0]))
    axes.append(fig.add_subplot(gs[0, 1]))

    sns.set_style("whitegrid")
    sns.barplot(
        duration_df,
        ax=axes[0],
        x="nodes",
        y="value",
        hue="experiment",
        err_kws={"color": "darkred"},
        order=[4, 8, 16, 32],
        palette=cloud_colors,
    )
    axes[0].set_title(f"AMG2023 Duration", fontsize=12)
    axes[0].set_ylabel("Seconds", fontsize=12)
    axes[0].set_xlabel("", fontsize=12)
    sns.barplot(
        fom_df,
        ax=axes[1],
        x="nodes",
        y="value",
        hue="experiment",
        err_kws={"color": "darkred"},
        order=[4, 8, 16, 32],
        palette=cloud_colors,
    )
    axes[1].set_title("FOM Overall (CPU)", fontsize=12)
    axes[1].set_ylabel("FOM Overall", fontsize=12)
    axes[1].set_xlabel("Nodes", fontsize=14)
    for ax in axes[0:2]:
        ax.get_legend().remove()

    plt.tight_layout()
    plt.savefig(os.path.join(img_outdir, f"amg-paper.svg"))
    plt.savefig(os.path.join(img_outdir, f"amg-paper.png"))
    plt.clf()



if __name__ == "__main__":
    main()

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
    files = ps.find_inputs(indir, "lammps")
    if not files:
        raise ValueError(f"There are no input files in {indir}")

    # Saves raw data to file
    df = parse_data(indir, outdir, files)
    plot_results(df, outdir, args.non_anon)


def parse_matom_steps(item):
    """
    Parse matom steps

    We separated this into a function because cyclecloud submits have
    two problem sizes in one file.
    """
    # Add in Matom steps - what is considered the LAMMPS FOM
    # https://asc.llnl.gov/sites/asc/files/2020-09/CORAL2_Benchmark_Summary_LAMMPS.pdf
    # Not parsed by metrics operator so we find the line here
    line = [x for x in item.split("\n") if "Matom-step/s" in x][0]
    return float(line.split(",")[-1].strip().split(" ")[0])


def parse_data(indir, outdir, files):
    """
    Parse filepaths for environment, etc., and results files for data.
    """
    # metrics here will be figures of merit, and seconds runtime
    p = ps.ProblemSizeParser("lammps")

    # For flux we can save jobspecs and other event data
    data = {}

    # It's important to just parse raw data once, and then use intermediate
    for filename in files:
        if (
            "compute-engine" in filename
            or "lammps-gpu-mpich.out" in filename
            or "lammps-rocky8-mpich" in filename
            or "ebpf" in filename
        ):
            continue
        exp = ps.ExperimentNameParser(filename, indir)
        if exp.prefix not in data:
            data[exp.prefix] = []
        if exp.size == 2:
            continue

        basename = os.path.basename(filename)
        if basename == "lammps.out":
            env_name = "Ubuntu OpenMPI"
        elif basename in ["lammps-rocky8-intel-mpi-interactive.out", "lammps-rocky8-intel-mpi.out"]:
            continue
        elif basename == "lammps-rocky8-openmpi.out":
            env_name = "Rocky OpenMPI"
        elif basename == "lammps-ubuntu-mpich.out":
            env_name = "Ubuntu Mpich"
        elif basename == "lammps-ubuntu-mpi-gpu.out":
            env_name = "Ubuntu OpenMPI GPU"
        else:
            print(filename)
            raise ValueError(f"Unexpected basename: {basename}")

        # Set the parsing context for the result data frame
        p.set_context(exp.cloud, exp.env, exp.env_type, exp.size)

        # Sanity check the files we found
        print(filename)
        exp.show()

        item = ps.read_file(filename)
        jobs = ps.parse_flux_jobs(item)
        for job, metadata in jobs.items():
            p.add_result(
                "matom_steps_per_second", parse_matom_steps(metadata["log"]), env_name
            )
            wall_time = [
                ps.convert_walltime_to_seconds(x.rsplit(" ", 1)[-1])
                for x in metadata["log"].split("\n")
                if "Total wall time" in x
            ][0]
            p.add_result("wall-time", wall_time, env_name)
            p.add_result("duration", metadata["duration"], env_name)
            p.add_result("hookup-time", metadata["duration"] - wall_time, env_name)

    print("Done parsing lammps results!")

    # Save stuff to file first
    p.df.to_csv(os.path.join(outdir, "lammps-results.csv"))
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

    frames = {}
    # Make a plot for seconds runtime, and each FOM set.
    # We can look at the metric across sizes, colored by experiment
    for metric in df.metric.unique():
        metric_df = df[df.metric == metric]
        title = " ".join([x.capitalize() for x in metric.split("_")])
        frames[metric] = {"cpu": metric_df}

    for metric, data_frames in frames.items():
        # We only have one for now :)
        fig = plt.figure(figsize=(9, 3.3))
        gs = plt.GridSpec(1, 2, width_ratios=[2, 1])
        axes = []
        axes.append(fig.add_subplot(gs[0, 0]))
        axes.append(fig.add_subplot(gs[0, 1]))

        sns.set_style("whitegrid")
        sns.barplot(
            data_frames["cpu"],
            ax=axes[0],
            x="nodes",
            y="value",
            hue="problem_size",
            err_kws={"color": "darkred"},
            # palette=cloud_colors,
            order=[4, 8, 16, 32, 64, 128],
        )
        if metric == "duration":
            duration_df = data_frames["cpu"]
        if metric in ["duration", "wall-time", "hookup-time"]:
            axes[0].set_title(f"LAMMPS {metric.capitalize()}", fontsize=14)
            axes[0].set_ylabel("Seconds", fontsize=14)
        else:
            fom_df = data_frames["cpu"]
            axes[0].set_title("LAMMPS M/Atom Steps per Second", fontsize=14)
            axes[0].set_ylabel("M/Atom Steps Per Second", fontsize=14)
        axes[0].set_xlabel("Nodes", fontsize=14)

        handles, labels = axes[0].get_legend_handles_labels()
        labels = ["/".join(x.split("/")[0:2]) for x in labels]
        axes[1].legend(
            handles,
            labels,
            loc="center left",
            bbox_to_anchor=(-0.1, 0.5),
            frameon=False,
        )
        for ax in axes[0:1]:
            ax.get_legend().remove()
        axes[1].axis("off")

        plt.tight_layout()
        plt.savefig(os.path.join(img_outdir, f"lammps-{metric}.svg"))
        plt.savefig(os.path.join(img_outdir, f"lammps-{metric}.png"))
        plt.clf()

        # Print the total number of data points
        print(f'Total number of datum: {data_frames["cpu"].shape[0]}')

    # Figure for paper - include duration and FOM
    fig = plt.figure(figsize=(9, 3))
    gs = plt.GridSpec(1, 3, width_ratios=[3, 3, 1])
    axes = []
    axes.append(fig.add_subplot(gs[0, 0]))
    axes.append(fig.add_subplot(gs[0, 1]))
    axes.append(fig.add_subplot(gs[0, 2]))

    sns.set_style("whitegrid")
    sns.barplot(
        duration_df,
        ax=axes[0],
        x="nodes",
        y="value",
        hue="env_type",
        err_kws={"color": "darkred"},
        order=[4, 8, 16, 32, 64, 128],
        # palette=cloud_colors,
    )
    axes[0].set_title(f"LAMMPS Duration", fontsize=12)
    axes[0].set_ylabel("Seconds", fontsize=12)
    axes[0].set_xlabel("", fontsize=12)
    sns.barplot(
        fom_df,
        ax=axes[1],
        x="nodes",
        y="value",
        hue="env_type",
        err_kws={"color": "darkred"},
        order=[4, 8, 16, 32, 64, 128],
        #palette=cloud_colors,
    )
    axes[1].set_title("LAMMPS M/Atom Steps per Second", fontsize=12)
    axes[1].set_ylabel("M/Atom Steps Per Second", fontsize=12)
    axes[1].set_xlabel("Nodes", fontsize=12)

    handles, labels = axes[0].get_legend_handles_labels()
    labels = ["/".join(x.split("/")[0:2]) for x in labels]
    axes[2].legend(
        handles,
        labels,
        loc="center left",
        bbox_to_anchor=(-0.1, 0.5),
        frameon=False,
    )
    for ax in axes[0:2]:
        ax.get_legend().remove()
    axes[2].axis("off")

    plt.tight_layout()
    plt.savefig(os.path.join(img_outdir, f"lammps-single-app-paper.svg"))
    plt.savefig(os.path.join(img_outdir, f"lammps-single-app-paper.png"))
    plt.clf()


if __name__ == "__main__":
    main()

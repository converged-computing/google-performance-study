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
    files = find_inputs(indir, "nccl-tests.out")
    if not files:
        raise ValueError(f"There are no input files in {indir}")

    # Saves raw data to file
    df = parse_data(indir, outdir, files)
    plot_results(df, outdir, args.non_anon)


def find_inputs(input_dir, pattern="*.*"):
    """
    Find inputs (times results files)
    """
    files = []
    for filename in ps.recursive_find_files(input_dir, pattern):
        if "OLD" in filename or "_logs" in filename:
            continue
        files.append(filename)
    return files

def parse_data(indir, outdir, files):
    """
    Parse filepaths for environment, etc., and results files for data.
    """
    # metrics here will be figures of merit, and seconds runtime
    p = ps.ProblemSizeParser("nccl-tests")

    # For flux we can save jobspecs and other event data
    data = {}

    # It's important to just parse raw data once, and then use intermediate
    for filename in files:
        exp = ps.ExperimentNameParser(filename, indir)
        if exp.prefix not in data:
            data[exp.prefix] = []

        # Set the parsing context for the result data frame
        p.set_context(exp.cloud, exp.env, exp.env_type, exp.size)
        
        # Sanity check the files we found
        print(filename)
        exp.show()
         
        item = ps.read_file(filename)
        jobs = ps.parse_flux_jobs(item)

        for job, metadata in jobs.items():
            log = metadata['log']
            lines = [x.strip() for x in log.split('\n') if x.strip() and not x.startswith('#')]
            for line in lines:
                # size, count, typ, redop, root, time_out_of_place, algbw_out_of_place, busbw_out_of_place out_of_place, wrong, in_place_time, in_place_algbw, in_place_busbw, in_place_wrong
                parts = line.split()
                message_size = int(parts[0])
                # These are GB/s
                busbw_out_of_place = (parts[7])
                busbw_in_place = float(parts[11])
                p.add_result("out_of_place_bandwidth", busbw_out_of_place, message_size)   
                p.add_result("in_place_bandwidth", busbw_in_place, message_size)   
            p.add_result("duration", metadata['duration'], "all")

    print("Done parsing nccl-tests results!")

    p.df.to_csv(os.path.join(outdir, "nccl-tests-results.csv"))
    ps.write_json(jobs, os.path.join(outdir, "flux-jobs-and-events.json"))
    return p.df

def plot_results(df, outdir, non_anon=False):
    """
    Plot analysis results
    """
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
            title = " ".join([x.capitalize() for x in metric.split("_")])
            frames[metric] = {'gpu': metric_df}

    for metric, data_frames in frames.items():
        fig = plt.figure(figsize=(9, 3.3))
        gs = plt.GridSpec(1, 2, width_ratios=[2, 1])
        axes = []
        axes.append(fig.add_subplot(gs[0, 0]))
        axes.append(fig.add_subplot(gs[0, 1]))
        sns.set_style("whitegrid")
        if metric == "duration":        
            sns.barplot(
                data_frames["gpu"],
                ax=axes[0],
                x="nodes",
                y="value",
                hue="experiment",
                err_kws={"color": "darkred"},
                hue_order=["google/gke/gpu",],
                palette=cloud_colors,
                order=[4, 8, 16, 32],
                # order=[4, 8, 16, 32, 64, 128],
            )
        else:
            sns.lineplot(
                data_frames["gpu"],
                ax=axes[0],
                hue="experiment",
                x="problem_size",
                y="value",
                markers=True,
                palette=cloud_colors,
                dashes=True,
                errorbar=("ci", 95),
            )

        if metric in ["duration"]:        
            axes[0].set_title(f"NCCL Tests {metric.capitalize()} (GPU)", fontsize=14)
            axes[0].set_ylabel("Seconds", fontsize=14)
            axes[0].set_xlabel("Nodes (1GPU/Node)", fontsize=14)
        else:
            metric = " ".join([x.capitalize() for x in metric.split('_')])
            axes[0].set_title(f"NCCL Tests {metric} (GPU)", fontsize=14)
            axes[0].set_xlabel("Message Size (bytes)", fontsize=14)
            axes[0].set_ylabel(metric + " MB/s", fontsize=14)
            axes[0].set_xscale("log")
            axes[0].set_yscale("log")

        handles, labels = axes[0].get_legend_handles_labels()
        labels = ["/".join(x.split("/")[0:2]) for x in labels]
        axes[1].legend(
            handles, labels, loc="center left", bbox_to_anchor=(-0.1, 0.5), frameon=False
        )
        for ax in axes[0:1]:
            ax.get_legend().remove()
        axes[1].axis("off")
    
        plt.tight_layout()
        plt.savefig(os.path.join(img_outdir, f"nccl-tests-{metric}-gpu.svg"))
        plt.savefig(os.path.join(img_outdir, f"nccl-tests-{metric}-gpu.png"))
        plt.clf()

        # Print the total number of data points
        print(f'Total number of GPU datum: {data_frames["gpu"].shape[0]}')
    

if __name__ == "__main__":
    main()

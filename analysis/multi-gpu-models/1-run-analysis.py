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
    files = ps.find_inputs(indir, "multi-gpu-models")
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
    p = ps.ProblemSizeParser("multi-gpu-models")

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

        # All had the same problem size
        problem_size = "16384x16384"
        for job, metadata in jobs.items():
            # problem size consistent across node counts
            # 16384x16384: 1 GPU:  33.4489 s, 4 GPUs:  14.7966 s, speedup:     2.26, efficiency:    56.51
            log = metadata['log']
            line = log.strip().split('\n')[-1]
            print(line)
            speedup = float(line.split('speedup:')[-1].split(',')[0].strip())
            efficiency = float(line.split('efficiency:')[-1].strip())
            p.add_result("speedup", speedup, problem_size)   
            p.add_result("efficiency", efficiency, problem_size)   
            p.add_result("duration", metadata['duration'], problem_size)

    print("Done parsing multi-gpu-models results!")

    # Save stuff to file first
    p.df.to_csv(os.path.join(outdir, "multi-gpu-models-results.csv"))
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
            frames[metric] = {'cpu': metric_df}

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
            hue="experiment",
            err_kws={"color": "darkred"},
            hue_order=[
                "google/gke/gpu",
            ],
            palette=cloud_colors,
            order=[4, 8, 16, 32, 64],
            # order=[4, 8, 16, 32, 64, 128],
        )
        if metric in ["duration"]:        
            axes[0].set_title(f"Multi-GPU-Models {metric.capitalize()} (GPU)", fontsize=14)
            axes[0].set_ylabel("Seconds", fontsize=14)
        else:
            axes[0].set_title(f"Multi-GPU-Models {metric.capitalize()} (GPU)", fontsize=14)
            axes[0].set_ylabel(metric.capitalize(), fontsize=14)
        axes[0].set_xlabel("Nodes (1GPU/Node)", fontsize=14)

        handles, labels = axes[0].get_legend_handles_labels()
        labels = ["/".join(x.split("/")[0:2]) for x in labels]
        axes[1].legend(
            handles, labels, loc="center left", bbox_to_anchor=(-0.1, 0.5), frameon=False
        )
        for ax in axes[0:1]:
            ax.get_legend().remove()
        axes[1].axis("off")
    
        plt.tight_layout()
        plt.savefig(os.path.join(img_outdir, f"multi-gpu-models-{metric}-gpu.svg"))
        plt.savefig(os.path.join(img_outdir, f"multi-gpu-models-{metric}-gpu.png"))
        plt.clf()

        # Print the total number of data points
        print(f'Total number of GPU datum: {data_frames["cpu"].shape[0]}')
    

if __name__ == "__main__":
    main()

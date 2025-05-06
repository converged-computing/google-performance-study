#!/usr/bin/env python3

import argparse
import os
import sys
import re
import json

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
    files = ps.find_inputs(indir, "fio")
    if not files:
        raise ValueError(f"There are no input files in {indir}")

    # Saves raw data to file
    outfile = os.path.join(outdir, "fio-results.csv")
    if os.path.exists(outfile):
        df = pandas.read_csv(outfile, index_col=0)
    else:
        df = parse_data(indir, outdir, files)
    plot_results(df, outdir, args.non_anon)



def parse_data(indir, outdir, files):
    """
    Parse filepaths for environment, etc., and results files for data.
    """
    # metrics here will be figures of merit, and seconds runtime
    p = ps.ResultParser("fio")
    data = {}
    
    # It's important to just parse raw data once, and then use intermediate
    for filename in files:
        exp = ps.ExperimentNameParser(filename, indir)
        if exp.prefix not in data:
            data[exp.prefix] = []

        # Skip size 2: testing
        if exp.size == 2:
            continue

        # Set the parsing context for the result data frame
        p.set_context(exp.cloud, exp.env, exp.env_type, exp.size)
        
        # Sanity check the files we found
        print(filename)
        exp.show()
         
        item = ps.read_file(filename)
        jobs = parse_flux_jobs(item)

        for job, metadata in jobs.items():
            for i, run in metadata["runs"].items():
                outlines = ' '.join(run['log'])
                nodes = []
                parts = outlines.split('} {')
                for i, part in enumerate(parts):
                    try:
                        if i == 0:
                            nodes.append(json.loads(part + '}'))
                        elif i == len(parts) - 1:
                            nodes.append(json.loads(part))                    
                        else:
                            nodes.append(json.loads('{' + part + '}'))
                        # A subset of the sample json doesn't parse
                    except:
                            pass

                    for node in nodes:
                        # We want to make quartile plots for read/write
                        # bw_mean is the mean across iterations
                        # bw_dev is the standard deviation across iterations
                        job = node['jobs'][0]                        
                        p.add_result("read_bandwidth", job['read']['bw'])
                        p.add_result("write_bandwidth", job['write']['bw'])

    print("Done parsing fio results!")

    # Save stuff to file first
    p.df.to_csv(os.path.join(outdir, "fio-results.csv"))
    ps.write_json(jobs, os.path.join(outdir, "flux-jobs-and-events.json"))
    return p.df

def parse_flux_jobs(item):
    """
    Parse flux jobs. We first find output, then logs and events
    """
    jobs = {}
    current_job = []
    jobid = None
    lines = item.split("\n")
    while lines:
        line = lines.pop(0)

        # Here, study id is job id above (e.g. amg2023-iter-1)
        if "FLUX-JOB START" in line and "echo" not in line:
            jobid, study_id = line.split(" ")[-2:]
            # There was a "null" run, not sure why, skip
            if study_id == "null":
                continue
            if "-node-" in study_id:
                study_id = study_id.split('-node-')[0]                
            if study_id not in jobs:
                jobs[study_id] = {}
            if "runs" not in jobs[study_id]:
                jobs[study_id]["runs"] = {}
            jobs[study_id]["runs"][jobid] = {}
            jobspec, lines = ps.find_section(lines, "FLUX-JOB-JOBSPEC")
            jobs[study_id]["runs"][jobid]["jobspec"] = jobspec
            log, lines = ps.find_section(lines, "FLUX-JOB-LOG")
            jobs[study_id]["runs"][jobid]["log"] = log
            resources, lines = ps.find_section(lines, "FLUX-JOB-RESOURCES")
            jobs[study_id]["runs"][jobid]["resources"] = resources
            events, lines = ps.find_section(lines, "FLUX-JOB-EVENTLOG")
            jobs[study_id]["runs"][jobid]["events"] = events

            # Calculate duration
            start = [x for x in events if x["name"] == "shell.start"][0]["timestamp"]
            done = [x for x in events if x["name"] == "done"][0]["timestamp"]
            jobs[study_id]["runs"][jobid]["duration"] = done - start

            assert "FLUX-JOB END" in lines[0]
            lines.pop(0)

        # Note that flux job stats are at the end, we don't parse
 
    return jobs


def plot_results(df, outdir, non_anon=False):
    """
    Plot analysis results
    """
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
                "google/gke/cpu",
            ],
            palette=cloud_colors,
            order=[4, 8, 16, 32, 64],
            # order=[4, 8, 16, 32, 64, 128],
        )
        title = " ".join([x.capitalize() for x in metric.split("_")])        
        axes[0].set_title(f"FIO {title} (CPU)", fontsize=14)
        axes[0].set_ylabel("Bandwidth", fontsize=14)
        axes[0].set_xlabel("Nodes", fontsize=14)
        handles, labels = axes[0].get_legend_handles_labels()
        labels = ["/".join(x.split("/")[0:2]) for x in labels]
        axes[1].legend(
            handles, labels, loc="center left", bbox_to_anchor=(-0.1, 0.5), frameon=False
        )
        for ax in axes[0:1]:
            ax.get_legend().remove()
        axes[1].axis("off")
    
        plt.tight_layout()
        plt.savefig(os.path.join(img_outdir, f"fio-{metric}-cpu.svg"))
        plt.savefig(os.path.join(img_outdir, f"fio-{metric}-cpu.png"))
        plt.clf()

        # Print the total number of data points
        print(f'Total number of CPU datum: {data_frames["cpu"].shape[0]}')

        # Print the total number of data points
        print(f'Total number of CPU datum: {data_frames["cpu"].shape[0]}')


    fig = plt.figure(figsize=(9, 3.3))
    gs = plt.GridSpec(1, 2, width_ratios=[2, 1])
    axes = []
    axes.append(fig.add_subplot(gs[0, 0]))
    axes.append(fig.add_subplot(gs[0, 1]))

    sns.set_style("whitegrid")
    sns.barplot(
        df,
        ax=axes[0],
        x="nodes",
        y="value",
        hue="metric",
        err_kws={"color": "darkred"},
        order=[4, 8, 16, 32, 64])
    axes[0].set_title(f"FIO Bandwidth (CPU)", fontsize=14)
    axes[0].set_ylabel("Bandwidth", fontsize=14)
    axes[0].set_xlabel("Nodes", fontsize=14)
    handles, labels = axes[0].get_legend_handles_labels()
    labels = ["/".join(x.split("/")[0:2]) for x in labels]
    axes[1].legend(handles, labels, loc="center left", bbox_to_anchor=(-0.1, 0.5), frameon=False)
    for ax in axes[0:1]:
        ax.get_legend().remove()
    axes[1].axis("off")
    
    plt.tight_layout()
    plt.savefig(os.path.join(img_outdir, f"fio-bandwidth-cpu.svg"))
    plt.savefig(os.path.join(img_outdir, f"fio-bandwidth-cpu.png"))
    plt.clf()

if __name__ == "__main__":
    main()

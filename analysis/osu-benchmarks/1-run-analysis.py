#!/usr/bin/env python3

import argparse
import os
import re
import sys

# import plotly.graph_objects as go
from matplotlib.font_manager import FontProperties
import matplotlib.pylab as plt
import pandas
import seaborn as sns
from metricsoperator.metrics.network.osu_benchmark import parse_multi_section

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

    # If flag is added, also parse on premises data
    if not os.path.exists(outdir):
        os.makedirs(outdir)

    # Find input directories
    files = ps.find_inputs(indir, "osu")
    if not files:
        raise ValueError(f"There are no input files in {indir}")

    # Saves raw data to file
    parsed = parse_data(indir, outdir, files)
    plot_results(parsed, outdir)


def split_combined_file(item, host_prefix="flux-sample"):
    """
    split combinations of OSU
    """
    # Remove lines with flux sample prints.
    # We could use this somewhere to derive pairs, but it's too hard
    # a parse for this first level analysis
    lines = [x for x in item.split("\n") if host_prefix not in x]

    # Each section has a last entry for size 4194304
    sections = []
    section = []
    last_line = None
    while lines:
        line = lines.pop(0)
        if not line.strip():
            continue

        # Get rid of these labels, not helpful
        if "Allreduce iteration" in line:
            continue
        # This is the start of an error and we need to stop parsing
        if "failed" in line:
            break
        section.append(line)

        # This is cyclecloud - ends with 1048576 or 4096 or 262144
        # These are likely incomplete runs
        if (
            line.startswith("#")
            and last_line
            and re.search("(1048576|4096|262144)", last_line)
        ):
            section.pop()
            sections.append(section)
            section = [line]

        # Reset when we get to the end
        if re.search("4194304", line) and section:
            sections.append(section)
            section = []
        last_line = line

    # Last hanging section, often has partial data
    if section:
        sections.append(section)
    return sections


def remove_cuda_line(item):
    """
    Remove the cuda metadata line for now.

    Ideally we should use it to validate, but we also know from
    commands what we ran and can come back to this.
    """
    idx = None
    for i, line in enumerate(item):
        if "Send Buffer" in line:
            idx = i
    if idx is not None:
        item.pop(idx)


def find_osu_command(metadata):
    """
    Find the osu command, meaning the line with the osu executable. This
    can be confused with the singularity container, etc.
    """
    command = metadata["jobspec"]["tasks"][0]["command"]
    for line in command:
        # Be pedantic
        if re.search("(osu_latency|osu_bw|osu_allreduce)$", line):
            return os.path.basename(line)
    raise ValueError(f"Cannot find osu command in {command}")


def clean_cyclecloud(item):
    """
    CycleCloud is different because it has:

    1. Loading messages for modules
    2. time wrappers
    3. Iterations counts
    """
    lines = [x for x in item.split("\n") if not re.search("(Loading|hpcx)", x)]
    # Time wrappers show up sometimes
    lines = [x for x in lines if not re.search("^(real|user|sys) ", x)]
    return "\n".join(lines)


def split_combined_file_on_premises(item, host_prefix):
    """
    split combinations of OSU
    """
    # Job info
    skip_regex = "(PST|PDT|JobID|Hosts)"
    lines = [
        x
        for x in item.split("\n")
        if x and host_prefix not in x and not re.search(skip_regex, x)
    ]

    # Each section has a last entry for size 4194304
    sections = []
    section = []
    last_line = None
    while lines:
        line = lines.pop(0)
        if not line.strip():
            continue

        # Get rid of these labels, not helpful
        if "Allreduce iteration" in line:
            continue
        # This is the start of an error and we need to stop parsing
        if "failed" in line:
            break
        section.append(line)

        if (
            line.startswith("#")
            and last_line
            and re.search("(1048576|4096|262144)", last_line)
        ):
            section.pop()
            sections.append(section)
            section = [line]

        # Reset when we get to the end (largest size)
        if re.search("4194304", line) and section:
            sections.append(section)
            section = []
        last_line = line

    # Last hanging section, often has partial data
    if section:
        sections.append(section)
    return sections


def parse_flux_jobs(item):
    """
    Parse flux jobs. We first find output, then logs and events
    """
    jobs = {}
    current_job = None
    jobid = None
    lines = item.split('\n')
    while lines:
        line = lines.pop(0)

        # This is the start of a job
        if "FLUX-RUN START" in line and "echo" not in line:
            jobid = line.split(' ')[-2]
            current_job = []
            if jobid not in jobs:
                jobs[jobid] = {'log': []}
        # This is the end of a job
        elif "FLUX-RUN END" in line and "echo" not in line:
            jobs[jobid]['log'].append("\n".join(current_job))
            jobid = None
        elif jobid is not None:
            current_job.append(line)
            continue

    lines = item.split('\n')
    while lines:
        line = lines.pop(0)

        # Here, study id is job id above (e.g. amg2023-iter-1)
        if "FLUX-JOB START" in line and "echo" not in line:
            jobid, study_id = line.split(' ')[-2:]
            # There was a "null" run, not sure why, skip
            if study_id == "null":
                continue
            # OSU is different - we have iterations within each
            if "runs" not in jobs[study_id]:
                jobs[study_id]["runs"] = {}
            jobs[study_id]['runs'][jobid] = {}
            jobspec, lines = ps.find_section(lines, "FLUX-JOB-JOBSPEC")
            jobs[study_id]['runs'][jobid]['jobspec'] = jobspec
            resources, lines = ps.find_section(lines, "FLUX-JOB-RESOURCES")
            jobs[study_id]['runs'][jobid]['resources'] = resources
            events, lines = ps.find_section(lines, "FLUX-JOB-EVENTLOG")
            jobs[study_id]['runs'][jobid]['events'] = events

            # Calculate duration
            start = [x for x in events if x["name"] == "shell.start"][0]["timestamp"]
            done = [x for x in events if x["name"] == "done"][0]["timestamp"]
            jobs[study_id]['runs'][jobid]['duration'] = done - start

            assert "FLUX-JOB END" in lines[0]
            lines.pop(0)

        # Note that flux job stats are at the end, we don't parse
 
    return jobs


def parse_data(indir, outdir, files):
    """
    Parse filepaths for environment, etc., and results files for data.
    """
    # For flux we can save jobspecs and other event data
    data = {}
    parsed = []
    result_count = set()

    # It's important to just parse raw data once, and then use intermediate
    for filename in files:
        exp = ps.ExperimentNameParser(filename, indir)
        if exp.prefix not in data:
            data[exp.prefix] = []

        exp.show()

        # Now we can read each result file to get metrics.
        item = ps.read_file(filename)

        # These were run in pairs mode - there was a bug in the identifier
        # can still parse OK
        print(filename)
        try:
            jobs = parse_flux_jobs(item)
            for job, metadata in jobs.items():
                for i, run in enumerate(metadata['runs']):            
                    outlines = metadata['log'][i].strip().split('\n')

                    # osu_latency, osu_bw, osu_allreduce
                    command = find_osu_command(metadata['runs'][run])
                    matrix = parse_multi_section([command] + outlines)
                    matrix["context"] = [exp.cloud, exp.env, exp.env_type, exp.size]
                    parsed.append(matrix)
        except:
            # All reduce run in normal mode
            jobs = ps.parse_flux_jobs(item)
            for job, metadata in jobs.items():
                outlines = metadata['log'].strip().split('\n')
                command = find_osu_command(metadata)
                matrix = parse_multi_section([command] + outlines)
                matrix["context"] = [exp.cloud, exp.env, exp.env_type, exp.size]
                parsed.append(matrix)

    print(f"Done parsing OSU {len(result_count)} results!")
    ps.write_json(parsed, os.path.join(outdir, "osu-parsed.json"))
    ps.write_json(jobs, os.path.join(outdir, "flux-jobspec-events.json"))
    return parsed


def get_columns(command):
    """
    Get columns for data frame depending on command
    """
    # Size       Avg Latency(us)
    if "allreduce" in command:
        return ["size", "avg_latency_us"]
    # Size          Latency (us)
    elif "latency" in command:
        return ["size", "latency_us"]
    # Size      Bandwidth (MB/s)
    return ["size", "bandwidth_mb_s"]


def get_osu_title(slug):
    if slug == "osu_bw":
        title = "OSU Bandwidth"
    elif slug == "osu_latency":
        title = "OSU Latency"
    elif slug == "osu_allreduce":
        title = "OSU AllReduce"
    return title


def plot_results(results, outdir, non_anon=False):
    """
    Plot result images to file
    """
    # Make consistent color schemes across plots
    clouds = set()

    img_outdir = os.path.join(outdir, "img")
    if not os.path.exists(img_outdir):
        os.makedirs(img_outdir)

    # Create a data frame for each result type, also lookup by size
    # For osu latency we will combine into one size (2 nodes)
    dfs_cpu = {}
    idxs_cpu = {}

    # lookup for x and y values for each
    lookup_cpu = {}
    for entry in results:
        # The source of truth is the command
        command = entry["command"]
        title = command
        if title not in dfs_cpu:
            dfs_cpu[title] = {}
            idxs_cpu[title] = {}
            lookup_cpu[title] = {}

        size = entry["context"][-1]

        columns = get_columns(title) + [
            "experiment",
            "cloud",
            "env",
            "env_type",
            "nodes",
        ]

        experiment = os.sep.join(entry["context"][:-1] + [command])
        # E.g., azure/aks. We don't want to include cpu/gpu or the command
        clouds.add(experiment)
        if size not in dfs_cpu[title]:
            dfs_cpu[title][size] = pandas.DataFrame(columns=columns)
            idxs_cpu[title][size] = 0
            lookup_cpu[title][size] = {"x": columns[0], "y": columns[1]}

        # Add command to experiment id since it includes unique command
        for datum in entry["matrix"]:
            dfs_cpu[title][size].loc[idxs_cpu[title][size], :] = (
                datum + [experiment] + entry["context"]
            )
            idxs_cpu[title][size] += 1

    # We are going to put the plots together, and the colors need to match!
    cloud_colors = {}
    for cloud in clouds:
        cloud_colors[cloud] = ps.match_color(cloud)

    # Make an output directory for plots by size
    plots_by_size = os.path.join(img_outdir, "by_size")
    if not os.path.exists(plots_by_size):
        os.makedirs(plots_by_size)

    fig = plt.figure(figsize=(18, 3))
    gs = plt.GridSpec(1, 4, width_ratios=[2, 2, 2, 0.8])
    axes = []
    axes.append(fig.add_subplot(gs[0, 0]))
    axes.append(fig.add_subplot(gs[0, 1]))
    axes.append(fig.add_subplot(gs[0, 2]))
    axes.append(fig.add_subplot(gs[0, 3]))
    i = 0

    # Save each completed data frame to file and plot!
    slugs = ["osu_latency", "osu_allreduce", "osu_bw"]
    for slug in slugs:
        sizes = dfs_cpu[slug]
        for size, subset in sizes.items():

            # We are doing size 256 for the paper
            if size != 64:
                continue
            print(f"Preparing plot for {slug} size {size}")

            # Save entire (unsplit) data frame to file
            # subset.to_csv(os.path.join(outdir, f"{slug}-{size}-cpu-dataframe.csv"))

            # Separate x and y - latency (y) is a function of size (x)
            xlabel = "Message size in bytes"
            x = lookup_cpu[slug][size]["x"]
            y = lookup_cpu[slug][size]["y"]

            # for sty in plt.style.available:
            sns.lineplot(
                data=subset,
                ax=axes[i],
                hue="experiment",
                x=x,
                y=y,
                markers=True,
                palette=cloud_colors,
                dashes=True,
                errorbar=("ci", 95),
            )

            axes[i].set_title(get_osu_title(slug), fontsize=12)
            axes[i].set_xticklabels(axes[i].get_xmajorticklabels(), fontsize=10)
            axes[i].set_yticklabels(axes[i].get_yticks(), fontsize=12)
            y_label = y.replace("_", " ")
            axes[i].set_xlabel("", fontsize=12)
            axes[i].set_ylabel(y_label + " (logscale)", fontsize=12)
            axes[i].set_xscale("log")
            axes[i].set_yscale("log")
            i += 1

    font_prop = FontProperties(size=14)
    fig.text(
        0.50,
        0.01,
        xlabel + " (logscale)",
        horizontalalignment="center",
        wrap=True,
        fontproperties=font_prop,
    )
    handles, labels = axes[0].get_legend_handles_labels()

    # Tweak the label to anonymize
    if not non_anon:
        labels = ["/".join(x.split("/")[0:3]) for x in labels]
        labels = [x.replace("/dane/", "/a/") for x in labels]

    axes[3].legend(
        handles, labels, loc="center left", bbox_to_anchor=(-0.25, 0.5), frameon=False
    )
    for ax in axes[0:3]:
        ax.get_legend().remove()
    axes[3].axis("off")
    plt.xscale("log")
    plt.yscale("log")
    plt.subplots_adjust(bottom=0.15)
    plt.tight_layout()
    plt.savefig(os.path.join(plots_by_size, "osu-latency-bw-reduce-cpu.svg"))
    plt.savefig(os.path.join(plots_by_size, "osu-latency-bw-reduce-cpu.png"))
    plt.clf()
    plt.close()


if __name__ == "__main__":
    main()

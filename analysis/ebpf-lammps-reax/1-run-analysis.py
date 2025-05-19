#!/usr/bin/env python3

import argparse
import os
import sys
import re
import pandas
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
    dirs = list(ps.recursive_find(indir, "ebpf"))
    if not dirs:
        raise ValueError(f"There are no input files in {indir}")
    files = []
    for dirname in dirs:
        files += ps.find_inputs(dirname, "lammps")

    # Get original runs without ebpf
    files += [x for x in ps.find_inputs(indir, "lammps") if "ebpf" not in x]

    # Saves raw data to file
    df, ebpfs = parse_data(indir, outdir, files)
    plot_results(df, ebpfs, outdir, args.non_anon)


def get_environment_context(filename):
    if "lammps-ubuntu-openmpi" in filename:
        env_name = "Ubuntu OpenMPI"
        exp_name = "ubuntu-openmpi"
    # These were rocky 8 and incorrectly named
    elif "lammps-rocky9-openmpi" in filename:
        env_name = "Rocky OpenMPI"
        exp_name = "rocky-openmpi"
    elif "lammps-rocky8-openmpi" in filename:
        env_name = "Rocky OpenMPI"
        exp_name = "rocky-openmpi"
    elif "lammps-ubuntu-mpich" in filename:
        env_name = "Ubuntu Mpich"
        exp_name = "ubuntu-mpich"
    elif "lammps-mpich-ubuntu" in filename:
        env_name = "Ubuntu Mpich"
        exp_name = "ubuntu-mpich"
    elif "lammps-ubuntu-mpi-gpu" in filename:
        env_name = "Ubuntu OpenMPI GPU"
        exp_name = "ubuntu-openmpi-gpu"        
    # Initial run of lammps, used the ubuntu openmpi
    elif "logs/lammps.out" in filename:
        env_name = "Ubuntu OpenMPI"
        exp_name = "ubuntu-openmpi"
        print(filename)
    else:
        raise ValueError(f"Unexpected filename: {filename}")
    return env_name, exp_name


def add_lammps_result(p, indir, filename, ebpf=None, gpu=False):
    """
    Add a new lammps result
    """
    exp = ps.ExperimentNameParser(filename, indir)
    if exp.size == 2:
        return p
    env_name, _ = get_environment_context(filename)
    if ebpf is not None: 
        env_name = f"{env_name} eBPF {ebpf.capitalize()}"    

    # Set the parsing context for the result data frame
    p.set_context(exp.cloud, exp.env, exp.env_type, exp.size)

    # Sanity check the files we found
    print(filename)
    exp.show()

    item = ps.read_file(filename)
    jobs = ps.parse_flux_jobs(item)
    for _, metadata in jobs.items():
        if not metadata:
            continue
        step, seconds = parse_matom_steps(metadata["log"])
        p.add_result(step, seconds, env_name)
        wall_time = [
            ps.convert_walltime_to_seconds(x.rsplit(" ", 1)[-1])
            for x in metadata["log"].split("\n")
            if "Total wall time" in x
        ][0]
        # This is a percentage
        cpu_use = float([x for x in item.split('\n') if "CPU use" in x][0].split('%')[0])
        p.add_result("cpu-usage", cpu_use, env_name)
        p.add_result("wall-time", wall_time, env_name)
        p.add_result("duration", metadata["duration"], env_name)
        p.add_result("hookup-time", metadata["duration"] - wall_time, env_name)
    return p


def parse_matom_steps(item):
    """
    Parse matom steps

    We separated this into a function because cyclecloud submits have
    two problem sizes in one file.
    """
    # Add in Matom steps - what is considered the LAMMPS FOM
    # https://asc.llnl.gov/sites/asc/files/2020-09/CORAL2_Benchmark_Summary_LAMMPS.pdf
    # Not parsed by metrics operator so we find the line here
    try:
        step = "matom_steps_per_second"
        line = [x for x in item.split("\n") if "Matom-step/s" in x][0]
    except:
        step = "katom_steps_per_second"
        line = [x for x in item.split("\n") if "katom-step" in x][0]
    return step, float(line.split(",")[-1].strip().split(" ")[0])


def add_ebpf_result(lookup, indir, filename):
    """
    Add an ebpf result
    """
    env_name, exp_name = get_environment_context(filename)
    analysis = os.path.basename(os.path.dirname(filename))
    exp = ps.ExperimentNameParser(filename, indir)
    if analysis not in lookup:
        lookup[analysis] = ps.ProblemSizeParser(analysis)
    p = lookup[analysis]
    p.set_context(exp_name, exp.env, exp.env_type, exp.size)

    item = ps.read_file(filename)
    if analysis == "shmem":
        parse_shmem(p, item)
    elif analysis == "tcp-socket":
        return lookup
    elif analysis == "tcp-model":
        parse_tcp(p, item)
    elif analysis == "futex-model":
        parse_futex(p, item)
    elif analysis == "open-close":
        parse_io(p, item, exp_name)
    elif analysis == "cpu-model":
        parse_cpu(p, item)
    lookup[analysis] = p
    return lookup


def parse_cpu(p, item):
    """
    Parse TCP
    """
    item = item.split("Cleaning up BPF resources")[-1]
    lines = [x for x in item.split("\n") if x and "Possibly lost" not in x][1:-1]
    item = "\n".join(lines)
    models = json.loads(item.split("Initiating cleanup sequence...")[-1])
    for model_type, model_names in models.items():
        for model in model_names:
            # E.g,. migration/22, kworker/88:2
            command = model["comm"].split("/")[0]
            # Add the median for now
            time_waiting_q = model["runq_latency_stats_ns"]["median"]
            if time_waiting_q is not None:
                p.add_result("cpu_waiting_ns", time_waiting_q, command)
            time_running = model["on_cpu_stats_ns"]["median"]
            if time_running is not None:
                p.add_result("cpu_running_ns", time_running, command)


def parse_tcp(p, item):
    """
    Parse TCP
    """
    item = item.split("--- FINAL AGGREGATED STATISTICS (JSON) ---")[-1]
    lines = [x for x in item.split("\n") if x][:-1]
    item = "\n".join(lines)
    models = json.loads(item)

    pattern = r"TGID\((?P<tgid>.*?)\)_COMM\((?P<command>.*?)\)_EVT\((?P<event>.*?)\)"
    bucket_pattern = r"TGID\((?P<tgid>.*?)\)_COMM\((?P<command>.*?)\)_EVT\((?P<event>.*?)\)_BUCKET\((?P<bucket>.*?)\)"
    for model_type, model_names in models.items():
        for model_name, model in model_names.items():
            if model_type == "overall_byte_stats":
                meta = re.search(pattern, model_name).groupdict()
                event = f"{meta['command']}-{meta['event'].lower()}"
                p.add_result("mean_bytes", model["mean"], event)
            elif "BUCKET" in model_name:
                meta = re.search(bucket_pattern, model_name).groupdict()
                bucket = meta["bucket"]
                event = f"{meta['command']}-{meta['event'].lower()}"
                p.add_result(f"duration_ns_{bucket}", model["p95"], event)
            else:
                meta = re.search(pattern, model_name).groupdict()
                event = f"{meta['command']}-{meta['event'].lower()}"
                # Just save median of duration ns to start
                p.add_result("duration_ns", model["duration_stats"]["p95"], event)


def parse_io(p, item, experiment):
    """
    Parse IO. This is more qualitiative.
    """
    if not hasattr(p, "counts"):
        p.counts = {}

    for line in item.split("\n"):
        if line.startswith("{"):
            datum = json.loads(line)
            command = datum["command"]
            # Just counting files for now - we could also time things
            if datum["event"] == "CLOSE":
                continue
            if experiment not in p.counts:
                p.counts[experiment] = {}
            if command not in p.counts[experiment]:
                p.counts[experiment][command] = {}
            filename = datum["filename"]
            if filename not in p.counts[experiment][command]:
                p.counts[experiment][command][filename] = 0
            p.counts[experiment][command][datum["filename"]] += 1


# {'event': 'OPEN',
# 'command': 'kubelet',
# 'retval': 33,
# 'ts_sec': 1857.259043102,
# 'tgid': 1701734764,
# 'tid': 3792,
# 'ppid': 13411,
# 'cgroup_id': 7237126475108805679,
# 'filename': '/var/log/pods/default_lammps-0-f6vcz_f27a413b-4d60-44d9-b282-c6cd399424e8/bcc-monitor'}


def parse_futex(p, item):
    """
    Futex parsing
    """
    item = item.split("Cleaning up BPF resources")[-1]
    lines = [x for x in item.split("\n") if x][1:-1]
    item = "\n".join(lines)
    models = json.loads(item)

    # {'tgid': 3592,
    # 'comm': 'containerd',
    # 'cgroup_id': 6520,
    # 'wait_duration_stats_ns': {'count': 1693.0,
    #  'sum': 224436362166.99985,
    #  'mean': 132567254.67631415,
    #  'median': 221633.7996235165,
    #  'min': 812,
    #  'max': 25489918732,
    #  'variance_ns2': 9.336119483708768e+17,
    #  'iqr_ns': 97748409.18476921,
    #  'q1_ns': 65205.02079568948,
    #  'q3_ns': 97813614.2055649},
    # 'futex_op_counts': {'128': 1693},
    # 'first_seen_ts_ns': 1941370732957,
    # 'last_seen_ts_ns': 1975537850634}

    for model_type, model_names in models.items():
        for model in model_names:
            # Add the median for now
            p.add_result(
                "median_futex_wait",
                model["wait_duration_stats_ns"]["median"],
                model["comm"],
            )


def parse_shmem(p, item):
    """
    Shared memory parsing
    """
    sections = item.split("Shared Memory Stats Summary")[1:]
    for timepoint, section in enumerate(sections):
        # Just get to the last timepoint
        continue

    for line in section.split("\n"):
        if not line.startswith("{"):
            continue
        datum = json.loads(line)

        # The munmap seems to change, the rest don't.
        p.add_result("get_mb", datum["get_mb"], datum["comm"])
        p.add_result("mmap_sh", datum["mmap_sh"], datum["comm"])
        p.add_result("munmap", datum["munmap"], datum["comm"])
        p.add_result("mmap_sh_mb", datum["mmap_sh_mb"], datum["comm"])

# {'tgid': 28139,
# 'comm': 'lmp',
# 'shmget': 1,
# 'shmat': 1,
# 'shmdt': 1,
# 'rmid': 1,
# 'get_mb': 0.00390625,
# 'shmopen': 0,
# 'unlink': 0,
# 'mmap_sh': 88,
# 'munmap': 35,
# 'mmap_sh_mb': 352.00067138671875}


def parse_data(indir, outdir, files):
    """
    Parse filepaths for environment, etc., and results files for data.
    """
    p = ps.ProblemSizeParser("lammps")
    ebpf_p = {}

    # Sanity check groups at end
    checks = {"multiple": [], "sample": [], "no-ebpf": [], "no-ebpf-gpu": []}

    # It's important to just parse raw data once, and then use intermediate
    for filename in files:
        if (
            "compute-engine" in filename
            or "lammps-gpu-mpich.out" in filename
            or "lammps-rocky8-mpich" in filename
            # Initial serial runs
            or "ebpf-serial" in filename
            or "tcp-socket" in filename
            # These are lammps without gvnic, only a subset of sizes
            # the times look the same, but I don't want to add extra
            #(slightly different) data.
            or "no-gvnic" in filename
        ):
            continue

        basename = os.path.basename(filename)

        # These are initial lammps output, without ebpf
        if basename in [
            "lammps-ubuntu-openmpi.out",
            "lammps-rocky9-openmpi.out",
            "lammps-rocky8-openmpi.out",
            "lammps-ubuntu-mpich.out",
        ]:
            checks['no-ebpf'].append(filename)
            p = add_lammps_result(p, indir, filename, ebpf=None)

        # GPu runs
        elif basename in [
            "lammps-ubuntu-mpi-gpu.out",
        ]:
            checks['no-ebpf-gpu'].append(filename)
            p = add_lammps_result(p, indir, filename, ebpf=None, gpu=True)

        # First original run
        elif "logs/lammps.out" in filename:
            checks['no-ebpf'].append(filename)
            p = add_lammps_result(p, indir, filename, ebpf=None) 

        elif "ebpf-multiple" in filename and "lammps.out" in filename:
            checks['multiple'].append(filename)
            p = add_lammps_result(p, indir, filename, ebpf="multiple") 

        # Single pod with randomly selected ebpf program
        elif "ebpf-sample" in filename and "lammps.out" in filename:
            checks['sample'].append(filename)
            p = add_lammps_result(p, indir, filename, ebpf="sample") 

        else:
            continue
            ebpf_p = add_ebpf_result(ebpf_p, indir, filename)

    print("Done parsing lammps results!")
    print("Please check groupings")
    print(json.dumps(checks, indent=4))

    # Save stuff to file first
    p.df.to_csv(os.path.join(outdir, "lammps-results.csv"))
    return p.df, ebpf_p


def plot_results(df, ebpfs, outdir, non_anon=False):
    """
    Plot analysis results
    """
    img_outdir = os.path.join(outdir, "img")
    if not os.path.exists(img_outdir):
        os.makedirs(img_outdir)

    plot_lammps(df, img_outdir, non_anon)
    # plot_ebpfs(ebpfs, img_outdir, non_anon)


def plot_open_close(counts, outdir):
    """
    Plot counts of open and close for each application
    """
    # Note might need to add nodes here
    df = pandas.DataFrame(columns=["experiment", "command", "path", "count"])
    idx = 0

    # First generate summary stats for each experiment and command to add to df
    for experiment, commands in counts.items():
        for command, opened in commands.items():
            # Count cgroups as one
            updated = {}

            def update_path(path):
                if path not in updated:
                    updated[path] = 0
                updated[path] += 1

            for filename, count in opened.items():

                # Kubelet pod activity
                if filename.startswith("/var/lib/kubelet/pods"):
                    update_path("/var/lib/kubelet/pods")

                # cgroup checking
                elif filename.startswith("/sys/fs/cgroup"):
                    update_path("/sys/fs/cgroup")

                # pod logging
                elif filename.startswith("/var/log/pods"):
                    update_path("/var/log/pods")

                # Manifests
                elif filename.startswith("/etc/kubernetes"):
                    update_path("/etc/kubernetes")

                # processes
                elif filename.startswith("/proc"):
                    update_path("/proc")
                else:
                    update_path(filename)
        for path, count in updated.items():
            df.loc[idx, :] = [experiment, command, path, count]
            idx += 1

    for command in df.command.unique():
        print(command)        
        img_outdir = os.path.join(outdir, "open-close", command)
        if not os.path.exists(img_outdir):
            os.makedirs(img_outdir)

        # Make sorted histogram of counts > 1
        subset = df[df.command == command]
        subset = subset[subset["count"] > 1]
        df_sorted = subset.sort_values(by="count", ascending=False).reset_index(drop=True)
        plt.figure(figsize=(12, 8))
        bar = sns.barplot(
            x="path",
            y="count",
            hue="experiment",
            data=df_sorted,
            order=df_sorted["path"],
        )
        plt.xlabel("File Path / Identifier")
        plt.ylabel("Count")
        plt.title(f"Open Counts by Path for {command.capitalize()} >1")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        plt.savefig(os.path.join(img_outdir, f"lammps-open-close.svg"))
        plt.savefig(os.path.join(img_outdir, f"lammps-open-close.png"))
        plt.clf()

def plot_ebpfs(ebpfs, outdir, non_anon):
    """
    Plot ebpf result
    """
    for analysis, p in ebpfs.items():
        if analysis == "open-close":
            plot_open_close(p.counts, outdir)
            continue
        if p.df.shape[0] == 0:
            continue
        df = p.df
        df.experiment = [x.replace("/gke/", "-") for x in df.experiment]
        img_outdir = os.path.join(outdir, analysis)
        if not os.path.exists(img_outdir):
            os.makedirs(img_outdir)

        import IPython
        IPython.embed()
        # problem size corresponding to application or context
        if analysis in ["cpu-model", "futex-model", "tcp-model", "shmem"]:
            for command in df.problem_size.unique():
                img_outdir = os.path.join(outdir, analysis, command)
                if not os.path.exists(img_outdir):
                    os.makedirs(img_outdir)
                command_df = df[df.problem_size == command]
                for metric in command_df.metric.unique():
                    metric_df = command_df[command_df.metric == metric]
                    fig = plt.figure(figsize=(10, 3.3))
                    gs = plt.GridSpec(1, 2, width_ratios=[2, 1])
                    axes = []
                    axes.append(fig.add_subplot(gs[0, 0]))
                    axes.append(fig.add_subplot(gs[0, 1]))
                    sns.set_style("whitegrid")
                    sns.barplot(
                        metric_df,
                        ax=axes[0],
                        x="nodes",
                        y="value",
                        hue="experiment",
                        err_kws={"color": "darkred"},
                        # palette=cloud_colors,
                    )
                    axes[0].set_title(f"LAMMPS ({command}) {metric}", fontsize=14)
                    if "futex" in metric or "cpu" in metric:
                        axes[0].set_ylabel("Nanoseconds", fontsize=14)
                    else:
                        axes[0].set_ylabel("Seconds", fontsize=14)
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

        elif analysis == "shmemm":
            df.experiment = [x.replace("/gke/", "-") for x in df.experiment]
            print(df.experiment.unique())
            for metric in df.metric.unique():
                metric_df = df[df.metric == metric]
                fig = plt.figure(figsize=(9, 3.3))
                gs = plt.GridSpec(1, 2, width_ratios=[2, 1])
                axes = []
                axes.append(fig.add_subplot(gs[0, 0]))
                axes.append(fig.add_subplot(gs[0, 1]))

                sns.set_style("whitegrid")
                sns.barplot(
                    metric_df,
                    ax=axes[0],
                    # This will eventually be nodes
                    x="problem_size",
                    y="value",
                    hue="experiment",
                    err_kws={"color": "darkred"},
                    # palette=cloud_colors,
                )
                axes[0].set_title(f"LAMMPS {metric}", fontsize=14)
                axes[0].set_ylabel(metric, fontsize=14)
                axes[0].set_xlabel("Timepoints", fontsize=14)
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

        else:
            raise ValueError(f"Not parsing metric {analysis}")


def plot_lammps(df, img_outdir, non_anon):
    """
    Plot lammps result. The goal here is to show the different environment setups.
    """
    frames = {}
    # Make a plot for seconds runtime, and each FOM set.
    # We can look at the metric across sizes, colored by experiment
    for metric in df.metric.unique():
        metric_df = df[df.metric == metric]
        frames[metric] = {"cpu": metric_df}

    order = [
             'Ubuntu Mpich eBPF Sample', 
             'Ubuntu Mpich',
             'Ubuntu Mpich eBPF Multiple',
             'Ubuntu OpenMPI eBPF Sample',
             'Ubuntu OpenMPI',
             'Ubuntu OpenMPI eBPF Multiple',
             'Rocky OpenMPI eBPF Sample', 
             'Rocky OpenMPI',
             'Rocky OpenMPI eBPF Multiple',
             'Ubuntu OpenMPI GPU', 
    ]

    colors = {
             'Ubuntu Mpich eBPF Sample': "#6495ed",
             'Ubuntu Mpich eBPF Multiple': "#0047ab",
             'Ubuntu Mpich': "#758fa9", 
             'Ubuntu OpenMPI eBPF Sample': "#e79aff",
             'Ubuntu OpenMPI eBPF Multiple': "#691883",
             'Ubuntu OpenMPI': "#b148d2",
             'Rocky OpenMPI eBPF Sample': "#c9df8a", 
             'Rocky OpenMPI eBPF Multiple': "#36802d",
             'Rocky OpenMPI': "#77ab59",
             'Ubuntu OpenMPI GPU': "#973348"
    }

    for metric, data_frames in frames.items():
        # We only have one for now :)
        fig = plt.figure(figsize=(10, 3.3))
        axes = []
        gs = plt.GridSpec(1, 2, width_ratios=[2, 1])
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
            palette=colors,
            hue_order=order,
        )
        if metric in ["duration", "wall-time", "hookup-time"]:
            axes[0].set_title(f"LAMMPS {metric.capitalize()}", fontsize=14)
            axes[0].set_ylabel("Seconds", fontsize=14)
        elif "cpu" in metric:
            axes[0].set_title("LAMMPS CPU Usage", fontsize=14)
            axes[0].set_ylabel("% CPU usage", fontsize=14)
        elif "katom" in metric:
            axes[0].set_title("LAMMPS K/Atom Steps per Second", fontsize=14)
            axes[0].set_ylabel("M/Atom Steps Per Second", fontsize=14)
        else:
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

        # Keep a variable with paper figure plots
        if "duration" in metric:
            duration_df = data_frames['cpu']
        elif "matom" in metric:
            matom_df = data_frames['cpu']

    # PAPER FIGURE
    # Two figures and one legend
    fig = plt.figure(figsize=(6, 6))
    axes = []
    gs = plt.GridSpec(3, 1, height_ratios=[2, 2, 1])
    axes.append(fig.add_subplot(gs[0, 0]))
    axes.append(fig.add_subplot(gs[1, 0]))
    axes.append(fig.add_subplot(gs[2, 0]))

    # Duration
    sns.set_style("whitegrid")
    sns.barplot(
        duration_df,
        ax=axes[0],
        x="nodes",
        y="value",
        hue="problem_size",
        err_kws={"color": "darkred"},
        palette=colors,
        hue_order=order,
    )
    axes[0].set_title(f"LAMMPS Duration", fontsize=12)
    axes[0].set_ylabel("Seconds", fontsize=12)
    axes[0].set_xlabel("", fontsize=12)


    # Matom steps per second
    sns.barplot(
        matom_df,
        ax=axes[1],
        x="nodes",
        y="value",
        hue="problem_size",
        err_kws={"color": "darkred"},
        palette=colors,
        hue_order=order,
    )
    axes[1].set_title("LAMMPS M/Atom Steps per Second", fontsize=12)
    axes[1].set_ylabel("M/Atom Steps Per Second", fontsize=12)
    axes[1].set_xlabel("Nodes", fontsize=12)

    # These labels are the same for axes 0 and 1
    handles, labels = axes[0].get_legend_handles_labels()

    # Shorten labels
    updated = []
    for label in labels:
        label = label.replace("Ubuntu", "U")  
        label = label.replace("Rocky", "R")  
        updated.append(label)

    axes[2].legend(
        handles,
        labels,
        ncols=2,
        fontsize=10,
        loc="center left",
        bbox_to_anchor=(-0.1, 0.5),
        frameon=False,
    )

    for ax in axes[0:2]:
        ax.get_legend().remove()
    # The legend will go here
    axes[2].axis("off")
    plt.tight_layout()
    plt.savefig(os.path.join(img_outdir, f"lammps-paper.svg"))
    plt.savefig(os.path.join(img_outdir, f"lammps-paper.png"))
    plt.clf()




if __name__ == "__main__":
    main()

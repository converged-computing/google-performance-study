#!/usr/bin/env python3

import argparse
import os
import sys
import pandas
import json
import numpy as np

import matplotlib.pylab as plt
import seaborn as sns

here = os.path.dirname(os.path.abspath(__file__))
analysis_root = os.path.dirname(here)
root = os.path.dirname(analysis_root)
sys.path.insert(0, analysis_root)

# Import the original library
import performance_study as ps

sns.set_theme(style="whitegrid", palette="muted")


class ProblemSizeParser(ps.ResultParser):
    """
    Extended ResultParser that includes problem size and eBPF status.
    It inherits from the base ResultParser to reuse its context-setting logic.
    """

    def init_df(self):
        self.df = pandas.DataFrame(
            columns=[
                "experiment",
                "cloud",
                "env",
                "env_type",
                "nodes",
                "application",
                "problem_size",
                "metric",
                "value",
                "gpu_count",
                "ebpf_status",
                "ebpf_type",
            ]
        )

    def add_result(self, metric, value, problem_size, ebpf_status, ebpf_type):
        experiment = os.path.join(self.cloud, self.env, self.env_type)
        if self.qualifier is not None:
            experiment = os.path.join(experiment, self.qualifier)
        self.df.loc[self.idx, :] = [
            experiment,
            self.cloud,
            self.env,
            self.env_type,
            self.size,
            self.app,
            problem_size,
            metric,
            value,
            self.gpu_count,
            ebpf_status,
            ebpf_type,
        ]
        self.idx += 1


def get_parser():
    parser = argparse.ArgumentParser(
        description="Run analysis", formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--root",
        help="root directory with experiments",
        default=os.path.join(root, "experiments"),
    )
    parser.add_argument(
        "--out",
        help="directory to save parsed results",
        default=os.path.join(here, "data"),
    )
    return parser


def main():
    parser = get_parser()
    args, _ = parser.parse_known_args()
    outdir = os.path.abspath(args.out)
    indir = os.path.abspath(args.root)
    if not os.path.exists(outdir):
        os.makedirs(outdir)
    dirs = list(ps.recursive_find(indir, "ebpf"))
    if not dirs:
        raise ValueError(f"There are no input files in {indir}")
    files = []
    for dirname in dirs:
        files += ps.find_inputs(dirname, "lammps")
    files += [x for x in ps.find_inputs(indir, "lammps") if "ebpf" not in x]

    raw_df = parse_data(indir, outdir, files)
    overhead_df = calculate_overhead_bootstrap(raw_df)
    overhead_df.to_csv(os.path.join(outdir, "lammps-overhead-results.csv"))

    img_outdir = os.path.join(outdir, "img")
    if not os.path.exists(img_outdir):
        os.makedirs(img_outdir)
    plot_overhead(overhead_df, img_outdir)


def get_environment_context(filename):
    if "ubuntu-openmpi" in filename or "logs/lammps.out" in filename:
        return "Ubuntu", "OpenMPI"
    elif "rocky9-openmpi" in filename or "rocky8-openmpi" in filename:
        return "Rocky", "OpenMPI"
    elif "ubuntu-mpich" in filename or "mpich-ubuntu" in filename:
        return "Ubuntu", "Mpich"
    elif "ubuntu-mpi-gpu" in filename:
        return "Ubuntu", "OpenMPI"
    else:
        print(f"Warning: Could not determine context for {filename}")
        return "Unknown", "Unknown"


def add_lammps_result(p, indir, filename, ebpf_type, gpu=False):
    exp = ps.ExperimentNameParser(filename, indir)
    if exp.size == 2:
        return p
    container_base, mpi_variant = get_environment_context(filename)
    config_name = f"{container_base} {mpi_variant}"
    if gpu:
        config_name += " GPU"
    ebpf_status = "Enabled" if ebpf_type else "Disabled"
    ebpf_type_str = ebpf_type if ebpf_type else "None"
    p.set_context(exp.cloud, exp.env, exp.env_type, exp.size, gpu_count=1 if gpu else 0)
    item = ps.read_file(filename)
    jobs = ps.parse_flux_jobs(item)
    for _, metadata in jobs.items():
        if not metadata:
            continue
        try:
            step, seconds = parse_matom_steps(metadata["log"])
        except:
            print(f"Skipping {filename} - no result present")
            continue
        p.add_result(step, seconds, config_name, ebpf_status, ebpf_type_str)
        wall_time = [
            ps.convert_walltime_to_seconds(x.rsplit(" ", 1)[-1])
            for x in metadata["log"].split("\n")
            if "Total wall time" in x
        ][0]
        cpu_use = float(
            [x for x in item.split("\n") if "CPU use" in x][0].split("%")[0]
        )
        p.add_result("cpu-usage", cpu_use, config_name, ebpf_status, ebpf_type_str)
        p.add_result("wall-time", wall_time, config_name, ebpf_status, ebpf_type_str)
        p.add_result(
            "duration", metadata["duration"], config_name, ebpf_status, ebpf_type_str
        )
        p.add_result(
            "hookup-time",
            metadata["duration"] - wall_time,
            config_name,
            ebpf_status,
            ebpf_type_str,
        )
    return p


def parse_matom_steps(item):
    try:
        step = "matom_steps_per_second"
        line = [x for x in item.split("\n") if "Matom-step/s" in x][0]
    except:
        step = "katom_steps_per_second"
        line = [x for x in item.split("\n") if "katom-step" in x][0]
    return step, float(line.split(",")[-1].strip().split(" ")[0])


def parse_data(indir, outdir, files):
    p = ProblemSizeParser("lammps")
    for filename in files:
        if (
            "compute-engine" in filename
            or "lammps-gpu-mpich.out" in filename
            or "lammps-rocky8-intel-mpi-interactive" in filename
            or "lammps-rocky8-mpich" in filename
            or "ebpf-serial" in filename
            or "tcp-socket" in filename
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
            add_lammps_result(p, indir, filename, ebpf_type=None, gpu=False)

        # GPU without ebpf
        elif "gpu" in filename and "noebpf" in filename and basename == "lammps.out":
            add_lammps_result(p, indir, filename, ebpf_type=None, gpu=True)

        elif "gpu" in filename and "ebpf" in filename and basename == "lammps.out":
            add_lammps_result(p, indir, filename, ebpf_type="Sample", gpu=True)

        # original GPU runs
        elif basename in ["lammps-ubuntu-mpi-gpu.out"]:
            add_lammps_result(p, indir, filename, ebpf_type=None, gpu=True)

        # First original run
        elif "logs/lammps.out" in filename:
            add_lammps_result(p, indir, filename, ebpf_type=None, gpu=False)

        elif "ebpf-multiple" in filename and "lammps.out" in filename:
            add_lammps_result(p, indir, filename, ebpf_type="Multiple", gpu=False)

        # Single pod with randomly selected ebpf program
        elif "ebpf-sample" in filename and "lammps.out" in filename:
            add_lammps_result(p, indir, filename, ebpf_type="Sample", gpu=False)

    print("Done parsing lammps results!")
    df = p.df
    df.to_csv(os.path.join(outdir, "lammps-results-raw-extended.csv"))
    return df


def calculate_overhead_bootstrap(df, n_bootstrap=5000):
    """
    Calculates overhead by correctly pairing eBPF runs with their baselines
    using a common 'base_config' key.
    """
    overhead_results = []

    # Create a 'base_config' column for reliable pairing by stripping eBPF type.
    df["base_config"] = df["problem_size"]

    # Separate the dataframes based on the 'ebpf_status' column from the parser.
    baseline_df = df[df["ebpf_status"] == "Disabled"].copy()
    ebpf_df = df[df["ebpf_status"] == "Enabled"].copy()

    # The group columns for an eBPF run.
    group_cols = ["problem_size", "nodes", "metric", "ebpf_type"]

    print(f"\n--- Starting Overhead Calculation ---")

    for i, (name, group_a) in enumerate(ebpf_df.groupby(group_cols)):
        config = dict(zip(group_cols, name))
        print(f"  Analyzing: {config}")

        # Determine the baseline config name to search for
        base_config_name = config["problem_size"].replace(f" {config['ebpf_type']}", "")

        # Query the baseline_df using the constructed base config name
        group_b = baseline_df.query(
            f"problem_size == '{base_config_name}' & "
            f"nodes == {config['nodes']} & "
            f"metric == '{config['metric']}'"
        )

        if group_b.empty:
            print(
                f"    -> WARNING: No matching baseline ('{base_config_name}') found. Skipping."
            )
            continue

        values_a = group_a["value"].values
        values_b = group_b["value"].values

        bootstrap_diffs = [
            np.mean(np.random.choice(values_a, len(values_a), True))
            - np.mean(np.random.choice(values_b, len(values_b), True))
            for _ in range(n_bootstrap)
        ]

        # We need to add the base_config to the results for plotting
        result = config.copy()
        result.update(
            {
                "base_config": base_config_name,
                "overhead": np.median(bootstrap_diffs),
                "ci_lower": np.percentile(bootstrap_diffs, 2.5),
                "ci_upper": np.percentile(bootstrap_diffs, 97.5),
                "mean_with_ebpf": np.mean(values_a),
                "mean_without_ebpf": np.mean(values_b),
            }
        )
        overhead_results.append(result)

    return pandas.DataFrame(overhead_results)


def plot_overhead(df, img_outdir):
    """
    Plots the calculated overhead with 95% confidence intervals.
    - Creates one figure per metric, showing CPU and GPU results together.
    - Has side-by-side subplots for 'Multiple' and 'Sample' eBPF setups.
    """
    # consistent colors
    colors = list(plt.cm.get_cmap("viridis", 4).colors)
    print(colors)
    palette = {}
    for env_type in df.problem_size.unique():
        palette[env_type] = list(colors.pop(0))

    def plot_single_setup(ax, data, title):
        nodes = sorted(data["nodes"].unique())
        # Use 'base_config' for the hue to distinguish CPU and GPU runs
        base_configs = sorted(data["base_config"].unique())
        n_configs = len(base_configs)
        total_group_width = 0.8
        bar_width = total_group_width / n_configs

        for i, config in enumerate(base_configs):
            # Filter by the 'base_config'
            config_data = data[data["base_config"] == config].sort_values("nodes")
            if config_data.empty:
                continue

            node_indices = [nodes.index(n) for n in config_data["nodes"]]
            positions = [
                idx - (total_group_width / 2) + (i + 0.5) * bar_width
                for idx in node_indices
            ]

            err_lower = config_data["overhead_pct"] - (
                config_data["ci_lower"] / config_data["mean_without_ebpf"] * 100
            )
            err_upper = (
                config_data["ci_upper"] / config_data["mean_without_ebpf"] * 100
            ) - config_data["overhead_pct"]
            y_err_config = [err_lower.tolist(), err_upper.tolist()]

            ax.bar(
                x=positions,
                height=config_data["overhead_pct"],
                width=bar_width,
                label=config,
                color=palette[config],
            )
            ax.errorbar(
                x=positions,
                y=config_data["overhead_pct"],
                yerr=y_err_config,
                fmt="none",
                c="black",
                capsize=3,
            )

        ax.axhline(0, color="red", linestyle="--", linewidth=1.5)
        ax.set_title(title, fontsize=14)
        ax.set_xlabel("Number of Nodes", fontsize=12)
        ax.set_xticks(range(len(nodes)))
        ax.set_xticklabels(nodes)
        ax.grid(True, which="major", linestyle=":", linewidth="0.6", color="grey")
        ax.set_axisbelow(True)

    for metric in df["metric"].unique():
        metric_df = df[df["metric"] == metric].copy()
        if metric_df.empty:
            continue

        metric_df["overhead_pct"] = (
            metric_df["overhead"] / metric_df["mean_without_ebpf"]
        ) * 100
        multiple_df = metric_df[metric_df["ebpf_type"] == "Multiple"]
        sample_df = metric_df[metric_df["ebpf_type"] == "Sample"]

        if multiple_df.empty and sample_df.empty:
            continue

        fig, axes = plt.subplots(1, 2, figsize=(20, 8), sharey=True, facecolor="w")
        plt.style.use("seaborn-v0_8-whitegrid")

        plot_single_setup(axes[0], multiple_df, "Multiple Programs")
        plot_single_setup(axes[1], sample_df, "Sampled Single Program")

        title_metric = metric.replace("_", " ").title()
        fig.suptitle(f"eBPF Performance Overhead for {title_metric}", fontsize=18)

        ylabel = "Performance Change (%) [95% CI]"
        axes[0].set_ylabel(ylabel, fontsize=12)

        # IMPORTANT: GPU is only in axis 1, we need this one.
        handles, labels = axes[1].get_legend_handles_labels()
        if not handles:
            handles, labels = axes[1].get_legend_handles_labels()

        if not any("Baseline" in label for label in labels):
            handles.append(
                plt.Line2D(
                    [0],
                    [0],
                    color="red",
                    linestyle="--",
                    label="Baseline (No Overhead)",
                )
            )
            labels.append("Baseline (No Overhead)")

        fig.legend(
            handles,
            labels,
            title="Base Configuration",
            bbox_to_anchor=(0.86, 0.85),
            loc="upper left",
        )

        fig.tight_layout(pad=1.0, rect=[0, 0, 0.85, 0.95])

        plt.savefig(os.path.join(img_outdir, f"lammps-overhead-{metric}.svg"))
        plt.savefig(os.path.join(img_outdir, f"lammps-overhead-{metric}.png"))
        plt.close(fig)


if __name__ == "__main__":
    main()

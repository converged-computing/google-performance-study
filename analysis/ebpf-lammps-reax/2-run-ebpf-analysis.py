#!/usr/bin/env python3

import argparse
import os
import sys

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
    db_file = os.path.join(outdir, "ebpf-data.sqlite")

    # We absolutely want on premises results here
    if not os.path.exists(db_file):
        sys.exit(f"Database file {db_file} does not exist.")

    db = ps.Database(db_file)
    plot_ebpfs(db, outdir)


def plot_open_close(db, outdir):
    """
    Plot counts of open and close for each application
    """
    # Get data frame of values
    query = "SELECT * FROM performance_data WHERE analysis_name = ?"
    df = db.query_to_dataframe(query, params=("open-close",))
    sizes = [int(x) for x in df.nodes.unique()]
    sizes.sort()
    sizes = [str(x) for x in sizes]
    df.nodes = df.nodes.astype(int)

    # Let's choose one middle size.
    df = df[df.nodes == 64]

    # Create a column that combines experiment and environment
    df["experiment"] = df["environment"] + "-" + df["environment_type"]

    def get_unique_paths(pathset):
        """
        Get unique paths and a lookup for a set
        """
        lookup = {}
        _paths = set(pathset.metric_name.unique().tolist())
        paths = set()
        for path in _paths:
            if ".so" not in path:
                paths.add(path)
            else:
                # Normalize for version
                if ".so." in path:
                    path = path.split(".so.")[0] + ".so"
                basename = os.path.basename(path)
                if basename in lookup:
                    print(lookup[basename])
                    print(path)
                    print(f"Warning: .so {basename} is found in two places")
                    lookup[basename] = basename
                else:
                    lookup[basename] = path
                paths.add(basename)
        return paths, lookup

    def get_shared_paths(A, B):
        """
        Get shared paths and counts for two sets.

        Note sure what to do with this info.
        """
        _paths_A = set(A.metric_name.unique().tolist())
        _paths_B = set(B.metric_name.unique().tolist())
        shared = _paths_A.intersection(_paths_B)
        A = A[A.metric_name.isin(shared)]
        B = B[B.metric_name.isin(shared)]
        diffs = {}
        for path in shared:
            diffs[path] = (
                A[A.metric_name == path].metric_value.tolist()[0]
                - B[B.metric_name == path].metric_value.tolist()[0]
            )
        return diffs

    # Let's look at differences between GPU and CPU for each command
    # and then differences between experiments
    results = {}
    for command in df.context.unique():

        # Make sorted histogram of counts > 1
        subset = df[df.context == command]

        # Break into ubuntu-openmpi with and without GPU
        # We need to filter out install prefix of .so files
        with_gpu = subset[subset.experiment == "ubuntu-openmpi-gpu"]
        without_gpu = subset[subset.experiment == "ubuntu-openmpi-cpu"]
        with_gpu_paths, with_gpu_lookup = get_unique_paths(with_gpu)
        without_gpu_paths, without_gpu_lookup = get_unique_paths(without_gpu)

        # Take the set differences
        in_gpu_not_cpu = set(with_gpu_paths) - set(without_gpu_paths)
        in_cpu_not_gpu = set(without_gpu_paths) - set(with_gpu_paths)

        # Assemble back into full paths and save
        in_cpu_not_gpu = {without_gpu_lookup.get(x) or x for x in in_cpu_not_gpu}
        in_gpu_not_cpu = {with_gpu_lookup.get(x) or x for x in in_gpu_not_cpu}
        results[command] = {
            "in_gpu_not_cpu": sorted(list(in_gpu_not_cpu)),
            "in_cpu_not_gpu": sorted(list(in_cpu_not_gpu)),
        }

        # For those that are the same, look at difference in count of opens?
        # Now look at cpu experiments
        rocky_openmpi = subset[subset.experiment == "rocky-openmpi-cpu"]
        ubuntu_openmpi = subset[subset.experiment == "ubuntu-openmpi-cpu"]
        ubuntu_mpich = subset[subset.experiment == "ubuntu-mpich-cpu"]
        rocky_openmpi_paths, rocky_openmpi_lookup = get_unique_paths(rocky_openmpi)
        ubuntu_openmpi_paths, ubuntu_openmpi_lookup = get_unique_paths(ubuntu_openmpi)
        ubuntu_mpich_paths, ubuntu_mpich_lookup = get_unique_paths(ubuntu_mpich)

        in_ubuntu_not_rocky = set(ubuntu_openmpi_paths) - set(rocky_openmpi_paths)
        in_rocky_not_ubuntu = set(rocky_openmpi_paths) - set(ubuntu_openmpi_paths)
        in_openmpi_not_mpich = set(ubuntu_openmpi_paths) - set(ubuntu_mpich_paths)
        in_mpich_not_openmpi = set(ubuntu_mpich_paths) - set(ubuntu_openmpi_paths)

        in_ubuntu_not_rocky = {
            ubuntu_openmpi_lookup.get(x) or x for x in in_ubuntu_not_rocky
        }
        in_rocky_not_ubuntu = {
            rocky_openmpi_lookup.get(x) or x for x in in_rocky_not_ubuntu
        }
        in_openmpi_not_mpich = {
            ubuntu_openmpi_lookup.get(x) or x for x in in_openmpi_not_mpich
        }
        in_mpich_not_openmpi = {
            ubuntu_mpich_lookup.get(x) or x for x in in_mpich_not_openmpi
        }
        results[command]["in_ubuntu_not_rocky"] = sorted(list(in_ubuntu_not_rocky))
        results[command]["in_rocky_not_ubuntu"] = sorted(list(in_rocky_not_ubuntu))
        results[command]["in_openmpi_not_mpich"] = sorted(list(in_openmpi_not_mpich))
        results[command]["in_mpich_not_openmpi"] = sorted(list(in_mpich_not_openmpi))

    print(outdir)
    ps.write_json(results, os.path.join(outdir, "file-access-differences.json"))


def plot_ebpfs(db, outdir):
    """
    Plot ebpf result
    """
    analyses = db.query("Select distinct analysis_name from performance_data;")
    print(f"Found analysis: {analyses}")

    img_outdir = os.path.join(outdir, "img")
    if not os.path.exists(img_outdir):
        os.makedirs(img_outdir)

    # plot open close
    plot_open_close(db, outdir)
    sys.exit()

    # NEED TO REDO BELOW, carefully
    for analysis, p in ebpfs.items():
        if analysis == "open_close" and hasattr(p, "counts"):
            plot_open_close(p.counts, outdir)
            continue
        if p.df.shape[0] == 0:
            continue
        df = p.df
        df.experiment = [x.replace("/gke/", "-") for x in df.experiment]
        img_outdir = os.path.join(outdir, analysis)
        if not os.path.exists(img_outdir):
            os.makedirs(img_outdir)

        # problem size corresponding to application or context
        if analysis in ["cpu", "futex", "tcp", "shmem"]:
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
                        order=[4, 8, 16, 32, 64, 128],
                        # palette=cloud_colors,
                    )
                    axes[0].set_title(f"LAMMPS ({command}) {metric}", fontsize=14)
                    if analysis == "shmem":
                        axes[0].set_ylabel("Count", fontsize=14)
                    else:
                        axes[0].set_ylabel("Nanoseconds", fontsize=14)
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

        elif analysis == "shmem":
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
                    order=[4, 8, 16, 32, 64, 128],
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


if __name__ == "__main__":
    main()

#!/usr/bin/env python3

# Shared functions to use across analyses.

import json
import os
import re

from matplotlib.ticker import FormatStrFormatter
import matplotlib.pylab as plt
import pandas
import seaborn as sns
import yaml

sns.set_theme(style="whitegrid", palette="muted")
sns.set_style("whitegrid", {"legend.frameon": True})


def read_yaml(filename):
    with open(filename, "r") as fd:
        content = yaml.safe_load(fd)
    return content


def read_json(filename):
    with open(filename, "r") as fd:
        content = json.loads(fd.read())
    return content


def recursive_find(base, pattern="*.*"):
    """
    Recursively find and yield directories matching a glob pattern.
    """
    for root, dirnames, filenames in os.walk(base):
        for dirname in dirnames:
            if not re.search(pattern, dirname):
                continue
            yield os.path.join(root, dirname)


def recursive_find_files(base, pattern="*.*"):
    """
    Recursively find and yield directories matching a glob pattern.
    """
    for root, _, filenames in os.walk(base):
        for filename in filenames:
            if not re.search(pattern, filename):
                continue
            yield os.path.join(root, filename)


def find_inputs(input_dir, pattern="*.*", include_on_premises=False):
    """
    Find inputs (times results files)
    """
    files = []
    for filename in recursive_find(input_dir, pattern):
        # We only have data for small
        if not include_on_premises and "on-premises" in filename:
            continue
        files.append(filename)
    return files


def get_outfiles(base, pattern="[.]out"):
    """
    Recursively find and yield directories matching a glob pattern.
    """
    for root, _, filenames in os.walk(base):
        for filename in filenames:
            if not re.search(pattern, filename):
                continue
            yield os.path.join(root, filename)


def read_file(filename):
    with open(filename, "r") as fd:
        content = fd.read()
    return content


def write_json(obj, filename):
    with open(filename, "w") as fd:
        fd.write(json.dumps(obj, indent=4))


def write_file(text, filename):
    with open(filename, "w") as fd:
        fd.write(text)


class ExperimentNameParser:
    """
    Shared parser to convert directory path into components.
    """

    def __init__(self, filename, indir):
        self.filename = filename
        self.indir = indir
        self.parse()

    def show(self):
        print(self.cloud, self.env, self.env_type, self.size)

    def parse(self):
        parts = self.filename.replace(self.indir + os.sep, "").split(os.sep)
        # These are consistent across studies
        self.cloud = "google"
        self.env = parts.pop(0)
        self.env_type = "gpu"
        size = parts.pop(0)

        # Experiment is the plot label
        self.experiment = os.path.join(self.cloud, self.env, self.env_type)

        # Prefix is an identifier for parsed flux metadata, jobspec and events
        self.prefix = os.path.join(self.experiment, size)
        self.size = int(size.replace("size-", ""))


class ResultParser:
    """
    Helper class to parse results into a data frame.
    """

    def __init__(self, app):
        self.init_df()
        self.idx = 0
        self.app = app

    def init_df(self):
        """
        Initialize an empty data frame for the application
        """
        self.df = pandas.DataFrame(
            columns=[
                "experiment",
                "cloud",
                "env",
                "env_type",
                "nodes",
                "application",
                "metric",
                "value",
                "gpu_count",
            ]
        )

    def set_context(self, cloud, env, env_type, size, qualifier=None, gpu_count=0):
        """
        Set the context for the next stream of results.

        These are just fields to add to the data frame.
        """
        self.cloud = cloud
        self.env = env
        self.env_type = env_type
        self.size = size
        # Extra metadata to add to experiment name
        self.qualifier = qualifier
        self.gpu_count = gpu_count

    def add_result(self, metric, value):
        """
        Add a result to the table
        """
        # Unique identifier for the experiment plot
        # is everything except for size
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
            metric,
            value,
            self.gpu_count,
        ]
        self.idx += 1


def set_group_color_properties(plot_name, color_code, label):
    # https://www.geeksforgeeks.org/how-to-create-boxplots-by-group-in-matplotlib/
    for k, v in plot_name.items():
        plt.setp(plot_name.get(k), color=color_code)

    # use plot function to draw a small line to name the legend.
    plt.plot([], c=color_code, label=label)
    plt.legend()


def make_plot(
    df,
    title,
    ydimension,
    xdimension,
    xlabel,
    ylabel,
    ext="png",
    plotname="lammps",
    hue=None,
    outdir="img",
    log_scale=False,
    do_round=False,
    round_by=3,
):
    """
    Helper function to make common plots.

    This also adds the normalized version

    Speedup: typically we do it in a way that takes into account serial/parallel.
    Speedup definition - normalize by performance at smallest size tested.
      This means taking each value and dividing by result at smallest test size (relative speed up)
      to see if conveys information better.
    """
    ext = ext.strip(".")
    plt.figure(figsize=(7, 6))
    sns.set_style("whitegrid")
    ax = sns.boxplot(
        x=xdimension,
        y=ydimension,
        hue=hue,
        data=df,
        linewidth=0.8,
        whis=[5, 95],
        dodge=True,
    )
    plt.title(title, fontsize=16)
    ax.set_xlabel(xlabel, fontsize=16)
    ax.set_ylabel(ylabel, fontsize=16)
    if log_scale is True:
        plt.gca().yaxis.set_major_formatter(
            plt.ScalarFormatter(useOffset=True, useMathText=True)
        )

    if do_round is True:
        ax.yaxis.set_major_formatter(FormatStrFormatter(f"%.{round_by}f"))
    plt.legend(facecolor="white")

    plt.tight_layout()
    plt.savefig(os.path.join(outdir, f"{plotname}.{ext}"))
    plt.clf()

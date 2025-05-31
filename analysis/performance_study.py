#!/usr/bin/env python3

# Shared functions to use across analyses.

import sqlite3
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

insert_query = """INSERT INTO performance_data (cloud, analysis_name, environment, environment_type,
nodes, metric_name, metric_value, context) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""

# Manually created color palette
cloud_prefixes = [
    "azure/aks",
    "aws/eks",
    "google/gke",
    "google/compute-engine",
    "aws/parallel-cluster",
    "on-premises/dane",
    "azure/cyclecloud",
    "on-premises/lassen",
]

cloud_prefixes.sort()

# colors = sns.color_palette("muted", len(cloud_prefixes))
# hexcolors = colors.as_hex()
# colors = {}
# for cloud in cloud_prefixes:
#    colors[cloud] = hexcolors.pop(0)
colors = {
    "azure/aks": "#004589",
    "aws/parallel-cluster": "#FF9900",
    "aws/eks": "#CC5500",
    "google/gke": "#FBBC04",
    "google/compute-engine": "#EA4335",
    "on-premises/a": "gray",
    "on-premises/dane": "gray",
    "azure/cyclecloud": "#0080ff",
    "on-premises/lassen": "gray",
    "on-premises/b": "gray",
}


def match_color(cloud):
    """
    Match the color for an environment
    """
    if "lassen" in cloud:
        cloud = "on-premises/b"
    if "dane" in cloud:
        cloud = "on-premises/a"
    # We assume the environ name (e.g., azure/aks) is shorter than
    # the one provided (e.g., azure/aks/cpu)
    for environ, color in colors.items():
        if environ in cloud:
            return color
    raise ValueError(f"Did not find color for {cloud}")


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


def find_inputs(input_dir, pattern="*.*"):
    """
    Find inputs (times results files)
    """
    files = []
    for filename in recursive_find_files(input_dir, pattern):
        if "test" in filename or "OLD" in filename or "_logs" in filename:
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


class Database:
    def __init__(self, db_path):
        self.db_path = db_path
        self.cursor = None
        self.conn = None
        self.create_table()
        self.count = 0

    def query_to_dataframe(self, query, params=None):
        """
        Queries the SQLite database for all data of a specific metric type
        and loads the results into a Pandas DataFrame.
        """
        params = params or ()
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            df = pandas.read_sql_query(query, conn, params=params)
            conn.close()
            return df
        except sqlite3.Error as e:
            print(f"Database error: {e}")
        except Exception as e:
            print(f"An error occurred: {e}")

    def query(self, query, params=None):
        """
        Queries the SQLite database.
        """
        params = params or ()
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            # query = "SELECT metric_value FROM performance_data WHERE metric_name = ?"
            cursor.execute(query, params)
            results = [row[0] if len(row) == 1 else row for row in cursor.fetchall()]
            conn.close()
            return results
        except Exception as e:
            print(f"An error occurred: {e}")

    def create_table(self):
        """
        Creates the performance data eBPF table in an SQLite database.

        I started parsing with pandas and realized it took a LONG time
        to process.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
          CREATE TABLE IF NOT EXISTS performance_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cloud TEXT NOT NULL,
            analysis_name TEXT NOT NULL,
            environment TEXT NOT NULL,
            environment_type TEXT NOT NULL,
            nodes TEXT,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            context TEXT
          )
        """
        )
        conn.commit()
        conn.close()
        print(f"Table 'performance_data' created (or already exists) in {self.db_path}")

    def close(self):
        self.conn.commit()
        self.conn.close()

    def ensure_open(self):
        if self.conn is None or self.cursor is None:
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()

    def add_result(
        self,
        cloud,
        analysis,
        environ,
        env_type,
        nodes,
        metric_name,
        metric_value,
        context=None,
        command=None,
    ):
        """
        Add a new result
        """
        # Special parsing of command, if provided
        if command and "lmp" in command:
            command = "lmp"
        if command and "flux-broker" in command:
            command = "flux-broker"
        if command and ":" in command:
            command = command.split(':')[0]
        if command:
            command = re.sub('([(]|[)])', '', command)

        self.ensure_open()
        try:
            self.cursor.execute(
                insert_query,
                (
                    cloud,
                    analysis,
                    environ,
                    env_type,
                    nodes,
                    metric_name,
                    metric_value,
                    context or command,
                ),
            )
            self.count += 1
        except Exception as e:
            print(f"Error processing entry: {e}")


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
        self.env_type = parts.pop(0)
        size = parts.pop(0)

        # Experiment is the plot label
        self.experiment = os.path.join(self.cloud, self.env, self.env_type)

        # Prefix is an identifier for parsed flux metadata, jobspec and events
        self.prefix = os.path.join(self.experiment, size)

        # If these are in the size, they are additional identifiers to indicate the
        # environment type. Add to it instead of the size. I could skip some of these
        # but I want to see the differences.
        if "-" in size:
            _, size = size.split("-", 1)
        self.size = int(size.replace("size", ""))


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


class ProblemSizeParser(ResultParser):
    """
    Extended ResultParser that includes a problem size.
    """

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
                "problem_size",
                "metric",
                "value",
                "gpu_count",
            ]
        )

    def add_result(self, metric, value, problem_size):
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
            problem_size,
            metric,
            value,
            self.gpu_count,
        ]
        self.idx += 1


def find_section(lines, key):
    """
    Find sections based on wrapping lines
    """
    # This is inefficient in that we just get the one at the top,
    # but we return to a context with the job id (which we need)
    start_idx = [i for i, x in enumerate(lines) if f"{key} START" in x][0]
    end_idx = [i for i, x in enumerate(lines) if f"{key} END" in x][0]
    section = lines[start_idx + 1 : end_idx]

    # Jobspec and resources are single lines of json
    if "JOBSPEC" in key or "RESOURCES" in key:
        assert len(section) == 1
        section = json.loads(section[0])

    # Event line has one json object per line
    elif "EVENTLOG" in key:
        events = []
        for line in section:
            if not line:
                continue
            events.append(json.loads(line))
        section = events

    # update lines to remove section
    lines = lines[end_idx + 1 :]
    return section, lines


def parse_flux_jobs(item):
    """
    Parse flux jobs. We first find output, then logs and events
    """
    jobs = {}
    current_job = None
    jobid = None
    lines = item.split("\n")
    while lines:
        line = lines.pop(0)

        # This is the start of a job
        if "FLUX-RUN START" in line and "echo" not in line:
            jobid = line.split(" ")[-1]
            current_job = []
            jobs[jobid] = {}
        # This is the end of a job
        elif "FLUX-RUN END" in line and "echo" not in line:
            jobs[jobid]["log"] = "\n".join(current_job)
            jobid = None
        elif jobid is not None:
            current_job.append(line)
            continue

    lines = item.split("\n")
    while lines:
        line = lines.pop(0)

        # Here, study id is job id above (e.g. amg2023-iter-1)
        if "FLUX-JOB START" in line and "echo" not in line:
            jobid, study_id = line.split(" ")[-2:]
            # I shelled in and ran hostname for osu, oops
            if study_id == "null":
                find_section(lines, "FLUX-JOB-JOBSPEC")
                find_section(lines, "FLUX-JOB-RESOURCES")
                find_section(lines, "FLUX-JOB-EVENTLOG")
                continue
            jobs[study_id]["fluxid"] = jobid
            jobspec, lines = find_section(lines, "FLUX-JOB-JOBSPEC")
            jobs[study_id]["jobspec"] = jobspec
            resources, lines = find_section(lines, "FLUX-JOB-RESOURCES")
            jobs[study_id]["resources"] = resources
            events, lines = find_section(lines, "FLUX-JOB-EVENTLOG")
            jobs[study_id]["events"] = events

            # Calculate duration
            start = [x for x in events if x["name"] == "shell.start"][0]["timestamp"]
            done = [x for x in events if x["name"] == "done"][0]["timestamp"]
            jobs[study_id]["duration"] = done - start

            assert "FLUX-JOB END" in lines[0]
            lines.pop(0)

        # Note that flux job stats are at the end, we don't parse

    return jobs


def parse_slurm_duration(item):
    """
    Get the start and end time from the slurm output.

    We want this to throwup if it is missing from the output.
    """
    start = int(
        [x for x in item.split("\n") if "Start time" in x][0].rsplit(" ", 1)[-1]
    )
    done = int([x for x in item.split("\n") if "End time" in x][0].rsplit(" ", 1)[-1])
    return done - start


def remove_slurm_duration(item):
    """
    Remove the start and end time from the slurm output.
    """
    keepers = [x for x in item.split("\n") if not re.search("^(Start|End) time", x)]
    return "\n".join(keepers)


def skip_result(dirname, filename):
    """
    Return true if we should skip the result path.
    """
    # I don't know if these are results or testing, skipping for now
    # They are from aws parallel-cluster CPU
    if os.path.join("experiment", "data") in filename:
        return True

    if "compute-toolkit" in filename:
        return True
    # These are OK
    if "aks/cpu/size" in filename and "kripke" in filename:
        return False

    # These were redone with a placement group
    if (
        "aks/cpu/size" in filename
        and "placement" not in filename
        and "256" not in filename
        and "128" not in filename
    ):
        return True

    return (
        dirname.startswith("_")
        or "configs" in filename
        or "no-add" in filename
        or "noefa" in filename
        or "attempt-1" in filename
        or "no-placement" in filename
        or "shared-memory" in filename
    )


def set_group_color_properties(plot_name, color_code, label):
    # https://www.geeksforgeeks.org/how-to-create-boxplots-by-group-in-matplotlib/
    for k, v in plot_name.items():
        plt.setp(plot_name.get(k), color=color_code)

    # use plot function to draw a small line to name the legend.
    plt.plot([], c=color_code, label=label)
    plt.legend()


def print_experiment_cost(df, outdir, duration_field="duration"):
    """
    Based on costs of instances, calculate the cost for runs
    """
    # Lookup for prices.
    # This is not saying on-premises costs nothing, but rather that
    # we cannot share / disclose (and we aren't entirely sure)
    instance_costs = {
        "google/gke/cpu": 5.06,
        "google/gke/gpu": 23.36,
        "google/compute-engine/cpu": 5.06,
        "google/compute-engine/gpu": 23.36,
        "aws/eks/cpu": 2.88,
        "aws/eks/gpu": 34.33,
        "on-premises/a/cpu": None,
        "on-premises/b/gpu": None,
        "on-premises/dane/cpu": None,
        "on-premises/lassen/gpu": None,
        "aws/parallel-cluster/cpu": 2.88,
        "azure/cyclecloud/cpu": 3.60,
        "azure/cyclecloud/gpu": 22.03,
        "azure/aks/cpu": 3.60,
        "azure/aks/gpu": 22.03,
    }

    cost_df = pandas.DataFrame(columns=["experiment", "cost", "size"])
    idx = 0

    # This is OK to use node and discount the on prem GPU counts, we
    # aren't calculating on prem costs because we can't
    for size in df.nodes.unique():
        subset = df[(df.metric == "duration") & (df.nodes == size)]
        subset["cost_per_hour"] = [instance_costs[x] for x in subset.experiment.values]

        # This converts seconds to hours
        hourly_cost_node = (subset["value"] / 60 / 60) * subset["cost_per_hour"]

        # Multiply by number of nodes
        subset["cost"] = hourly_cost_node * size
        for idx, row in subset.iterrows():
            cost_df.loc[idx, :] = [row.experiment, row.cost, row.nodes]
            idx += 1

    print(cost_df.groupby(["experiment"]).cost.sum().sort_values())
    cost_df.to_csv(os.path.join(outdir, "cost-by-environment.csv"))


def convert_walltime_to_seconds(walltime):
    """
    This is from flux and the function could be shared
    """
    # An integer or float was provided
    if isinstance(walltime, int) or isinstance(walltime, float):
        return int(float(walltime) * 60.0)

    # A string was provided that will convert to numeric
    elif isinstance(walltime, str) and walltime.isnumeric():
        return int(float(walltime) * 60.0)

    # A string was provided that needs to be parsed
    elif ":" in walltime:
        seconds = 0.0
        for i, value in enumerate(walltime.split(":")[::-1]):
            seconds += float(value) * (60.0**i)
        return seconds

    # Don't set a wall time
    elif not walltime or (isinstance(walltime, str) and walltime == "inf"):
        return 0

    # If we get here, we have an error
    msg = (
        f"Walltime value '{walltime}' is not an integer or colon-" f"separated string."
    )
    raise ValueError(msg)


def make_plot(
    df,
    title,
    ydimension,
    xdimension,
    xlabel,
    ylabel,
    palette=None,
    ext="png",
    plotname="lammps",
    hue=None,
    outdir="img",
    order=None,
    log_scale=False,
    do_round=False,
    no_legend=False,
    hue_order=None,
    bottom_legend=False,
    round_by=3,
    width=12,
    height=6,
):
    """
    Helper function to make common plots.

    This is largely not used. I was too worried to have the generalized function
    not work for a specific plot so I just redid them all manually. Ug.

    Speedup: typically we do it in a way that takes into account serial/parallel.
    Speedup definition - normalize by performance at smallest size tested.
      This means taking each value and dividing by result at smallest test size (relative speed up)
      to see if conveys information better.
    """
    # Replace the initial value of interest with the speedup (this gets thrown away after plot)
    plt.figure(figsize=(width, height))
    sns.set_style("whitegrid")
    ax = sns.barplot(
        df,
        x=xdimension,
        y=ydimension,
        hue=hue,
        hue_order=hue_order,
        palette=palette,
        order=order,
        err_kws={"color": "darkred"},
    )
    plt.title(title, fontsize=14)
    ax.set_xlabel(xlabel, fontsize=14)
    ax.set_ylabel(ylabel, fontsize=14)
    if log_scale is True:
        plt.gca().yaxis.set_major_formatter(
            plt.ScalarFormatter(useOffset=True, useMathText=True)
        )

    if do_round is True:
        ax.yaxis.set_major_formatter(FormatStrFormatter(f"%.{round_by}f"))
    if bottom_legend:
        # Get the current x-axis label
        xlabel = ax.get_xlabel()
        x_min, x_max = ax.get_xlim()
        x_pos = x_min + 0.2
        # Remove the default x-axis label
        ax.set_xlabel("")
        # Add the new x-axis label at the desired position
        ax.text(x_pos, ax.get_ylim()[0] - 30, xlabel, ha="left", va="top")
        plt.legend(loc="lower center", bbox_to_anchor=(0.5, -0.2), ncol=3)
    elif no_legend:
        plt.legend().remove()
    else:
        plt.legend(facecolor="white")
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, f"{plotname}-speedup-scaled.svg"))
    plt.clf()

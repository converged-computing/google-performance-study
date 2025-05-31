#!/usr/bin/env python3

import argparse
import sys
import re
import json
import sqlite3
import os

here = os.path.dirname(os.path.abspath(__file__))
analysis_root = os.path.dirname(here)
root = os.path.dirname(analysis_root)
sys.path.insert(0, analysis_root)

import performance_study as ps

db = None
insert_query = """INSERT INTO performance_data (cloud, analysis_name, environment, environment_type,
nodes, metric_name, metric_value, context) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""


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
        "--out",
        help="directory to save parsed results",
        default=os.path.join(here, "data"),
    )
    return parser


def main():
    """
    Find application result files to parse.
    """
    global db
    parser = get_parser()
    args, _ = parser.parse_known_args()

    # Output images and data
    outdir = os.path.abspath(args.out)
    indir = os.path.abspath(args.root)

    # We absolutely want on premises results here
    if not os.path.exists(outdir):
        os.makedirs(outdir)

    # Database path
    db_path = os.path.join(outdir, "ebpf-data.sqlite")
    db = Database(db_path)

    # Find input files (skip anything with test)
    dirs = list(ps.recursive_find(indir, "ebpf"))
    if not dirs:
        raise ValueError(f"There are no input files in {indir}")
    files = []
    for dirname in dirs:
        files += ps.find_inputs(dirname, "lammps")

    original_runs = [
        "shmem",
        "tcp",
        "open_close",
        "futex",
        "tcp-socket",
        "open-close",
        "futex-model",
        "tcp-model",
        "cpu-model",
    ]
    regex = "(%s)" % "|".join(original_runs)
    files = [
        x
        for x in files
        if "ebpf-multiple" not in x and "/size-2/" not in x and not re.search(regex, x)
    ]
    parse_data(indir, outdir, files, db_path)


class Database:
    def __init__(self, db_path):
        self.db_path = db_path
        self.cursor = None
        self.conn = None
        self.create_table()
        self.count = 0

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


def add_ebpf_result(indir, filename, io_counts):
    """
    Add an ebpf result
    """
    global db
    env_name, exp_name = get_environment_context(filename)
    exp = ps.ExperimentNameParser(filename, indir)

    item = ps.read_file(filename)
    if "PROGRAM" not in item:
        return

    analysis = [x for x in item.split("\n") if "PROGRAM" in x][0].split(":")[-1].strip()
    if analysis == "shmem":
        for name, value, command in parse_shmem(item):
            db.add_result(
                exp.cloud,
                analysis,
                env_name,
                exp.env_type,
                exp.size,
                name,
                value,
                command=command,
            )
    elif analysis == "tcp-socket":
        return
    elif analysis == "tcp":
        for name, value, context in parse_tcp(item):
            db.add_result(
                exp.cloud,
                analysis,
                env_name,
                exp.env_type,
                exp.size,
                name,
                value,
                context=context,
            )
    elif analysis == "futex":
        for name, value, command in parse_futex(item):
            db.add_result(
                exp.cloud,
                analysis,
                env_name,
                exp.env_type,
                exp.size,
                name,
                value,
                command=command,
            )
    elif analysis == "open_close":
        io_counts = parse_io(item, exp_name, exp, io_counts, filename)
    elif analysis == "cpu":
        for name, value, command in parse_cpu(item):
            db.add_result(
                exp.cloud,
                analysis,
                env_name,
                exp.env_type,
                exp.size,
                name,
                value,
                command=command,
            )
    else:
        raise ValueError(analysis)


def parse_cpu(item):
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
            time_waiting_q = model["runq_latency_stats_ns"]["median_ns"]
            if time_waiting_q is not None:
                yield "cpu_waiting_ns", time_waiting_q, command
            time_running = model["on_cpu_stats_ns"]["median_ns"]
            if time_running is not None:
                yield "cpu_running_ns", time_running, command


def parse_tcp(item):
    """
    Parse TCP
    """
    item = item.split("--- FINAL AGGREGATED STATISTICS (JSON) ---")[-1]
    lines = [x for x in item.split("\n") if x][:-1]
    item = "\n".join(lines)
    models = json.loads(item)

    pattern = r"TGID\((?P<tgid>.*?)\)_COMM\((?P<command>.*?)\)_EVT\((?P<event>.*?)\)"
    bucket_pattern = r"TGID\((?P<tgid>.*?)\)_COMM\((?P<command>.*?)\)_EVT\((?P<event>.*?)\)_BUCKET\((?P<bucket>.*?)\)"

    def update_meta(meta):
        if "lmp" in meta["command"]:
            meta["command"] = "lmp"
        if "flux-broker" in meta["command"]:
            meta["command"] = "flux-broker"
        if " " in meta["command"]:
            meta["command"] = meta["command"].split(" ")[0]
        return meta

    for model_type, model_names in models.items():
        for model_name, model in model_names.items():
            if model_type == "overall_byte_stats":
                meta = re.search(pattern, model_name).groupdict()
                meta = update_meta(meta)
                event = f"{meta['command']}-{meta['event'].lower()}"
                yield "mean_bytes", model["mean"], event
            elif "BUCKET" in model_name:
                meta = re.search(bucket_pattern, model_name).groupdict()
                meta = update_meta(meta)
                bucket = meta["bucket"]
                event = f"{meta['command']}-{meta['event'].lower()}"
                yield f"duration_ns_{bucket}", model["p95"], event
            else:
                meta = re.search(pattern, model_name).groupdict()
                meta = update_meta(meta)
                event = f"{meta['command']}-{meta['event'].lower()}"

                # Just save median of duration ns to start
                yield "duration_ns", model["duration_stats"]["p95"], event


def parse_io(item, experiment, exp, counts, filename):
    """
    Parse IO. This is more qualitiative.
    """
    if experiment not in counts:
        counts[experiment] = {}

    if exp.size not in counts[experiment]:
        counts[experiment][exp.size] = {}

    if exp.env_type not in counts[experiment][exp.size]:
        counts[experiment][exp.size][exp.env_type] = {}

    # Split on start of list
    try:
        items = json.loads(item.split("proceeding to print.", 1)[1])
    except:
        print(f"Issue parsing {filename}")
        return counts
    for d in items:
        if d["command"] not in counts[experiment][exp.size][exp.env_type]:
            counts[experiment][exp.size][exp.env_type][d["command"]] = {}
        if (
            d["filename"]
            not in counts[experiment][exp.size][exp.env_type][d["command"]]
        ):
            counts[experiment][exp.size][exp.env_type][d["command"]][d["filename"]] = 0
        counts[experiment][exp.size][exp.env_type][d["command"]][d["filename"]] += d[
            "open_count"
        ]
    return counts


# {'event': 'OPEN',
# 'command': 'kubelet',
# 'retval': 33,
# 'ts_sec': 1857.259043102,
# 'tgid': 1701734764,
# 'tid': 3792,
# 'ppid': 13411,
# 'cgroup_id': 7237126475108805679,
# 'filename': '/var/log/pods/default_lammps-0-f6vcz_f27a413b-4d60-44d9-b282-c6cd399424e8/bcc-monitor'}


def parse_futex(item):
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
            # Add the median for now...
            median = model["wait_duration_stats_ns"]["median"]
            yield "median_futex_wait", median, model["comm"]


def parse_shmem(item):
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
        yield "get_mb", datum["get_mb"], datum["comm"]
        yield "mmap_sh", datum["mmap_sh"], datum["comm"]
        yield "munmap", datum["munmap"], datum["comm"]
        yield "mmap_sh_mb", datum["mmap_sh_mb"], datum["comm"]


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


def parse_data(indir, outdir, files, db_path):
    """
    Parse filepaths for environment, etc., and results files for data.
    """
    global db
    io_counts = {}

    # It's important to just parse raw data once, and then use intermediate
    total = len(files) - 1
    for i, filename in enumerate(files):
        print(f"{i}/{total}", end="\r")
        if (
            "compute-engine" in filename
            or "lammps-gpu-mpich.out" in filename
            or "lammps-rocky8-mpich" in filename
            # Initial serial runs
            or "ebpf-serial" in filename
            or "tcp-socket" in filename
            or "interactive" in filename
            or "logs/lammps-rocky8-intel-mpi.out" in filename
            # These are lammps without gvnic, only a subset of sizes
            # the times look the same, but I don't want to add extra
            # (slightly different) data.
            or "no-gvnic" in filename
        ):
            continue

        if "ebpf-multiple" in filename:
            continue
        basename = os.path.basename(filename)

        # These are initial lammps output, without ebpf
        if basename in [
            "lammps-ubuntu-openmpi.out",
            "lammps-rocky9-openmpi.out",
            "lammps-rocky8-openmpi.out",
            "lammps-ubuntu-mpich.out",
        ]:
            continue

        # GPU without ebpf
        elif "gpu" in filename and "noebpf" in filename and basename == "lammps.out":
            continue

        elif "gpu" in filename and "ebpf" in filename and basename == "lammps.out":
            continue

        # original GPU runs
        elif basename in ["lammps-ubuntu-mpi-gpu.out"]:
            continue

        # First original run
        elif "logs/lammps.out" in filename:
            continue

        elif "ebpf-multiple" in filename and "lammps.out" in filename:
            continue

        # Single pod with randomly selected ebpf program
        elif "ebpf-sample" in filename and "lammps.out" in filename:
            continue

        else:
            add_ebpf_result(indir, filename, io_counts)

    # save counts...
    for experiment, sizes in io_counts.items():
        for size, env_types in sizes.items():
            for env_type, commands in env_types.items():
                for command, filepaths in commands.items():
                    for filepath, count in filepaths.items():
                        db.add_result(
                            "google",
                            "open-close",
                            experiment,
                            env_type,
                            size,
                            filepath,
                            count,
                            command=command,
                        )

    db.close()
    print("Done parsing lammps eBPF results!")


if __name__ == "__main__":
    main()

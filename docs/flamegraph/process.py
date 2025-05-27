# generate_manifest.py
import os
import json
from glob import glob
from collections import Counter

SVG_DIR = os.getcwd()
FOLDED_STACKS_DIR = os.getcwd()
OUTPUT_MANIFEST_FILE = "manifest.json"

# If CALCULATE_SIMILARITY is True, which TGID to use as the reference for similarity scores.
# If None, the first found TGID will be used.
REFERENCE_TGID_FOR_SIMILARITY = None


def parse_folded_stacks(filepath):
    """Parses a .folded file and returns a set of unique stack;frame strings."""
    stacks = set()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(" ")
                if len(parts) > 1:  # Should be stack string and count
                    stacks.add(parts[0])  # Just the stack string
    except FileNotFoundError:
        print(f"Warning: Folded stack file not found {filepath}")
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
    return stacks


def calculate_jaccard_similarity(set1, set2):
    if not set1 and not set2:  # Both empty
        return 1.0
    if not set1 or not set2:  # One empty
        return 0.0
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union != 0 else 0


def main():
    processes_data = []
    tgid_to_stacks = {}

    if not os.path.isdir(SVG_DIR):
        sys.exit(
            f"Error: SVG directory '{SVG_DIR}' not found. Please create it and add your SVGs."
        )

    svg_files = glob(os.path.join(SVG_DIR, "*.svg"))
    if not svg_files:
        sys.exit(f"No SVG files found in {SVG_DIR}")

    # --- Step 1: Discover SVGs and parse folded stacks (if enabled) ---
    for svg_path in svg_files:
        basename = os.path.basename(svg_path)
        tgid = int(basename.split("_")[-1].replace(".svg", ""))
        process_info = {
            "tgid": tgid,
            "svgPath": basename,
            "similarityScore": None,
            "order": 0,
        }
        folded_file_path = os.path.join(
            FOLDED_STACKS_DIR, f"flamegraph_lmp_rank_{tgid}.folded"
        )
        if os.path.exists(folded_file_path):
            tgid_to_stacks[tgid] = parse_folded_stacks(folded_file_path)
        else:
            print(
                f"Warning: No folded stack file found for TGID {tgid} at {folded_file_path}"
            )
            tgid_to_stacks[tgid] = set()  # Empty set if no data for this TGID

        processes_data.append(process_info)

    if not processes_data:
        print("No process data collected (perhaps TGIDs couldn't be parsed).")
        return

    # Sort by TGID initially for consistent ordering
    processes_data.sort(key=lambda p: str(p["tgid"]))  # Sort as strings for consistency
    for i, proc_data in enumerate(processes_data):
        proc_data["order"] = i

    # --- Step 2: Calculate Similarity (if enabled) ---
    if tgid_to_stacks:
        # Determine the reference TGID
        ref_tgid = REFERENCE_TGID_FOR_SIMILARITY
        if ref_tgid not in tgid_to_stacks:
            if (
                processes_data
            ):  # Pick the first one if no specific reference or reference not found
                ref_tgid = processes_data[0]["tgid"]
                print(
                    f"Using TGID {ref_tgid} as reference for similarity (first available)."
                )
            else:
                ref_tgid = None  # No processes to reference

        reference_stacks = tgid_to_stacks.get(ref_tgid)

        if (
            reference_stacks is not None
        ):  # Might be None if ref_tgid had no .folded file
            for proc_data in processes_data:
                current_tgid = proc_data["tgid"]
                current_stacks = tgid_to_stacks.get(current_tgid)
                if (
                    current_stacks is not None
                ):  # Can be None if this tgid had no .folded
                    similarity = calculate_jaccard_similarity(
                        reference_stacks, current_stacks
                    )
                    proc_data["similarityScore"] = round(similarity, 3)
        else:
            print(
                f"Warning: Reference stacks for TGID {ref_tgid} not available. Cannot calculate similarity."
            )

    # --- Step 3: Output Manifest ---
    manifest_content = {"processes": processes_data}
    try:
        with open(OUTPUT_MANIFEST_FILE, "w", encoding="utf-8") as f:
            json.dump(manifest_content, f, indent=4)
        print(f"Manifest written to {OUTPUT_MANIFEST_FILE}")
    except IOError as e:
        print(f"Error writing manifest file: {e}")


if __name__ == "__main__":
    main()

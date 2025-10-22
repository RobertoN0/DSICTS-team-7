#!/usr/bin/env python3
import argparse
import os, glob
import pandas as pd

CANONICAL_MEM_UNIT = "MiB"   # or "MB"
PROFILES_ORDER = ['baseline', 'c1-only','c2-only', 'heap', 'interpret', 'low-threshold', 'double-thread']

from .io_utils import average_csv_files, merge_dataframes
from .plot_single import generate_single_experiment_plots
from .plot_overlays import generate_experiment_overlays

def main():
    ap = argparse.ArgumentParser(description='Generate plots from JITLab experiment runs')
    ap.add_argument("--runs-dir", default="./results_h264gpu",
                    help="Root directory containing experiments like h264-cpu, h264-gpu, ...")
    ap.add_argument("--output-dir", default="./plots",
                    help="Output directory for plots")
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)


    experiment_dirs = [d for d in glob.glob(os.path.join(args.runs_dir, '*')) if os.path.isdir(d)]
    if not experiment_dirs:
        print(f"Error: No experiment directories found in {args.runs_dir}")
        return
    print(f"Found {len(experiment_dirs)} experiment directories")

    experiments_map = {}

    # Iterate over each experiment
    for exp_path in experiment_dirs:
        exp_name = os.path.basename(exp_path)
        exp_out_dir = os.path.join(args.output_dir, exp_name)
        os.makedirs(exp_out_dir, exist_ok=True)
        print(f"\n>>> Processing experiment: {exp_name} ...")

        profile_dirs = [d for d in glob.glob(os.path.join(exp_path, '*')) if os.path.isdir(d)]
        if not profile_dirs:
            print(f"  No profiles found in {exp_name}")
            continue

        experiments_map[exp_name] = {}

        # Iterate over each profile within the experiment
        for prof_dir in profile_dirs:
            prof_dirname = os.path.basename(prof_dir) 
            prof_key = prof_dirname.split('_')[0].lower() 

            if prof_key not in PROFILES_ORDER:
                print(f"  - Skipping non-standard profile folder: {prof_dirname}")
                continue

            print(f"  - Profile: {prof_dirname} (key={prof_key})")

            cpu_files = glob.glob(os.path.join(prof_dir, '**', 'monitor_iter.csv'), recursive=True)
            gpu_files = glob.glob(os.path.join(prof_dir, '**', 'gpu_monitor_iter.csv'), recursive=True)

            try:
                if cpu_files and gpu_files:
                    # GPU experiment
                    avg_cpu_df = average_csv_files(cpu_files, file_type='CPU')
                    avg_gpu_df = average_csv_files(gpu_files, file_type='GPU')
                    merged_df = merge_dataframes(avg_cpu_df, avg_gpu_df, prof_key)
                else:
                    print(f"    --> SKIP: no CSV files found for {prof_dirname}")
                    continue

                # Plots for each single profile
                #generate_single_experiment_plots(
                #    merged_df,
                #    avg_cpu_df,
                #    avg_gpu_df if not avg_gpu_df.empty else None,
                #    f"{exp_name} - {prof_dirname}",
                #    os.path.join(exp_out_dir, prof_dirname),
                #    CANONICAL_MEM_UNIT
                #)

                # Save for overlay & subsequent comparisons
                experiments_map[exp_name][prof_key] = (
                    merged_df,
                    avg_cpu_df,
                    (avg_gpu_df if not avg_gpu_df.empty else None)
                )

            except Exception as e:
                print(f"    Error in profile {prof_dirname}: {e}")
                continue

        # Overlay for profiles in the same experiment
        generate_experiment_overlays(
            exp_name, experiments_map[exp_name], exp_out_dir,
            PROFILES_ORDER, CANONICAL_MEM_UNIT
        )

    print("\nAll plots generated successfully!")

if __name__ == "__main__":
    main()

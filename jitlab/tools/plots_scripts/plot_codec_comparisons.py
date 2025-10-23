import os
import matplotlib.pyplot as plt
from .io_utils import (
    to_datetime_series,
    unify_memory_units_cpu,
    unify_memory_units_gpu,
    get_cpu_mem_col,
    get_gpu_mem_col,
)


def _extract_codec_and_hw(exp_name):
    """Split experiment name into codec and hardware (cpu/gpu)."""
    if "-" not in exp_name:
        return None, None
    codec, hw = exp_name.split("-", 1)
    return codec.lower(), hw.lower()


def _ensure_datetime_and_rel_seconds(df, ts_column="ts"):
    """Convert timestamp column to datetime and add elapsed time in seconds."""
    df = df.copy()
    df[ts_column] = to_datetime_series(df[ts_column])
    df["time_s"] = (df[ts_column] - df[ts_column].min()).dt.total_seconds()
    return df


def generate_cross_codec_comparisons(experiments_map, output_dir, canonical_mem_unit, target_profile="baseline"):
    """
    Generate comparison plots across codecs (H264/HEVC/AV1) using the same profile.

    For GPU experiments:
        - Average power breakdown (CPU/GPU/Total)
        - Total energy breakdown (CPU/GPU/Total)
        - GPU-only energy (single bar)
        - GPU memory over time

    For CPU-only experiments:
        - Average power
        - Total energy
        - CPU memory over time
    """
    comp_dir = os.path.join(output_dir, "_codec_comparisons")
    os.makedirs(comp_dir, exist_ok=True)

    codec_cpu_map = {}
    codec_gpu_map = {}

    for exp_name, profiles in experiments_map.items():
        codec, hw = _extract_codec_and_hw(exp_name)
        if not codec or target_profile not in profiles:
            print(f"  - Skipping experiment {exp_name} for cross-codec comparison.")
            continue
        if hw == "cpu":
            print(f"  - Found CPU experiment for codec: {codec}")
            codec_cpu_map[codec] = exp_name
        elif hw == "gpu":
            print(f"  - Found GPU experiment for codec: {codec}")
            codec_gpu_map[codec] = exp_name

    print(">>> Generating GPU codec comparison plots...")
    _plot_gpu_codec_comparison(codec_gpu_map, experiments_map, comp_dir, canonical_mem_unit, target_profile)
    print(">>> Generating CPU codec comparison plots...")
    _plot_cpu_codec_comparison(codec_cpu_map, experiments_map, comp_dir, canonical_mem_unit, target_profile)


def _plot_gpu_codec_comparison(codec_gpu_map, experiments_map, comp_dir, canonical_mem_unit, target_profile):
    if not codec_gpu_map:
        return

    codecs = sorted(codec_gpu_map.keys())
    avg_cpu_powers, avg_gpu_powers, avg_tot_powers = [], [], []
    total_cpu_energy, total_gpu_energy, total_energy = [], [], []

    for codec in codecs:
        merged_df, _, gpu_df = experiments_map[codec_gpu_map[codec]].get(target_profile, (None, None, None))
        if merged_df is None:
            avg_cpu_powers.append(float("nan"))
            avg_gpu_powers.append(float("nan"))
            avg_tot_powers.append(float("nan"))
            total_cpu_energy.append(float("nan"))
            total_gpu_energy.append(float("nan"))
            total_energy.append(float("nan"))
            continue

        avg_cpu_powers.append(merged_df["power_w_cpu"].mean() if "power_w_cpu" in merged_df.columns else float("nan"))
        avg_gpu_powers.append(merged_df["power_w_gpu"].mean() if "power_w_gpu" in merged_df.columns else float("nan"))
        avg_tot_powers.append(merged_df["total_power_w"].mean() if "total_power_w" in merged_df.columns else float("nan"))

        cpu_e = merged_df["energy_j_total_cpu"].iloc[-1] if "energy_j_total_cpu" in merged_df.columns else 0
        gpu_e = merged_df["energy_j_total_gpu"].iloc[-1] if "energy_j_total_gpu" in merged_df.columns else 0
        total_cpu_energy.append(cpu_e)
        total_gpu_energy.append(gpu_e)
        total_energy.append(cpu_e + gpu_e)

    # --- Power comparison
    _plot_bar_triplets(
        codecs,
        avg_cpu_powers,
        avg_gpu_powers,
        avg_tot_powers,
        "Average Power (W)",
        "Average Power Across Codecs (GPU Experiments)",
        os.path.join(comp_dir, "codec_comparison_gpu_power.png"),
    )

    # --- Energy comparison (CPU + GPU + Total)
    _plot_bar_triplets(
        codecs,
        total_cpu_energy,
        total_gpu_energy,
        total_energy,
        "Total Energy (J)",
        "Total Energy Across Codecs (GPU Experiments)",
        os.path.join(comp_dir, "codec_comparison_gpu_energy.png"),
    )

    if any(total_gpu_energy):
        colors = ["#4C72B0", "#55A868", "#C44E52", "#8172B2", "#CCB974", "#64B5CD"]
        fig, ax = plt.subplots(figsize=(10, 7))  

        bars = ax.bar(
            [c.upper() for c in codecs],
            total_gpu_energy,
            color=colors[:len(codecs)],
            alpha=0.9,
            edgecolor="black",
            linewidth=1.2,
        )

        y_offset = max(total_gpu_energy) * 0.05 
        for bar, val in zip(bars, total_gpu_energy):
            height = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                height + y_offset,
                f"{val:.0f} J",
                ha="center",
                va="bottom",
                fontsize=13,
                weight="bold"
            )

        ax.set_title("GPU Energy Consumption Across Codecs (Baseline)", fontsize=14, pad=15)
        ax.set_ylabel("Total Energy (J)", fontsize=12)
        ax.set_xlabel("Codec", fontsize=12)
        ax.set_ylim(0, max(total_gpu_energy) * 1.25)  
        ax.grid(axis="y", alpha=0.3)
        plt.tight_layout()
        plt.savefig(os.path.join(comp_dir, "codec_comparison_gpu_energy_only.png"), dpi=200)
        plt.close()


    # --- GPU Memory over time
    plt.figure(figsize=(12, 6))
    for codec in codecs:
        _, _, gpu_df = experiments_map[codec_gpu_map[codec]].get(target_profile, (None, None, None))
        if gpu_df is None or gpu_df.empty:
            continue
        gpu_df = unify_memory_units_gpu(gpu_df, canonical_mem_unit)
        gpu_df = _ensure_datetime_and_rel_seconds(gpu_df)
        mem_col, _ = get_gpu_mem_col(gpu_df, canonical_mem_unit)
        if mem_col:
            plt.plot(gpu_df["time_s"], gpu_df[mem_col], label=codec.upper(), linewidth=2)

    unit_label = canonical_mem_unit if canonical_mem_unit.lower() in ("mib", "mb") else "MB/MiB"
    plt.title("GPU Memory Usage Over Time (Baseline, GPU Experiments)")
    plt.xlabel("Time (seconds)")
    plt.ylabel(f"Memory ({unit_label})")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(comp_dir, "codec_comparison_gpu_memory.png"), dpi=150)
    plt.close()


def _plot_cpu_codec_comparison(codec_cpu_map, experiments_map, comp_dir, canonical_mem_unit, target_profile):
    if not codec_cpu_map:
        return

    codecs = sorted(codec_cpu_map.keys())
    avg_powers, total_energy, avg_mem = [], [], []

    for codec in codecs:
        merged_df, cpu_df, _ = experiments_map[codec_cpu_map[codec]].get(target_profile, (None, None, None))
        if merged_df is None or cpu_df is None:
            avg_powers.append(float("nan"))
            total_energy.append(float("nan"))
            avg_mem.append(float("nan"))
            continue

        avg_powers.append(merged_df["power_w_cpu"].mean() if "power_w_cpu" in merged_df.columns else float("nan"))
        cpu_e = merged_df["energy_j_total_cpu"].iloc[-1] if "energy_j_total_cpu" in merged_df.columns else 0
        total_energy.append(cpu_e)

        cpu_df = unify_memory_units_cpu(cpu_df, canonical_mem_unit)
        mem_col, _ = get_cpu_mem_col(cpu_df, canonical_mem_unit)
        avg_mem.append(cpu_df[mem_col].mean() if mem_col and mem_col in cpu_df.columns else float("nan"))

    _plot_single_bar(
        codecs,
        avg_powers,
        "Average Power (W)",
        "Average Power Across Codecs (CPU-only Experiments)",
        os.path.join(comp_dir, "codec_comparison_cpu_power.png"),
        value_fmt="{:.1f} W",
    )

    _plot_single_bar(
        codecs,
        total_energy,
        "Total Energy (J)",
        "Total Energy Across Codecs (CPU-only Experiments)",
        os.path.join(comp_dir, "codec_comparison_cpu_energy.png"),
        value_fmt="{:.0f} J",
    )

    plt.figure(figsize=(12, 6))
    for codec in codecs:
        merged_df, cpu_df, _ = experiments_map[codec_cpu_map[codec]].get(target_profile, (None, None, None))
        if cpu_df is None:
            continue
        cpu_df = unify_memory_units_cpu(cpu_df, canonical_mem_unit)
        cpu_df = _ensure_datetime_and_rel_seconds(cpu_df)
        mem_col, _ = get_cpu_mem_col(cpu_df, canonical_mem_unit)
        if mem_col:
            plt.plot(cpu_df["time_s"], cpu_df[mem_col], label=codec.upper(), linewidth=2)

    unit_label = canonical_mem_unit if canonical_mem_unit.lower() in ("mib", "mb") else "MB/MiB"
    plt.title("CPU Memory Usage Over Time (Baseline, CPU-only Experiments)")
    plt.xlabel("Time (seconds)")
    plt.ylabel(f"Memory ({unit_label})")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(comp_dir, "codec_comparison_cpu_memory.png"), dpi=150)
    plt.close()


def _plot_bar_triplets(codecs, series_a, series_b, series_c, ylabel, title, output_path):
    """Helper to plot grouped bar charts with three series."""
    x = range(len(codecs))
    width = 0.25

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar([i - width for i in x], series_a, width, label="CPU")
    ax.bar([i for i in x], series_b, width, label="GPU")
    ax.bar([i + width for i in x], series_c, width, label="Total")

    ax.set_xticks(list(x))
    ax.set_xticklabels([c.upper() for c in codecs])
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


def _plot_single_bar(codecs, values, ylabel, title, output_path, value_fmt="{:.1f}"):
    """Helper to plot single-series bar charts with value labels."""
    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar([c.upper() for c in codecs], values, alpha=0.85)

    for bar, value in zip(bars, values):
        if value == value:  
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), value_fmt.format(value),
                    ha="center", va="bottom", fontsize=10)

    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()

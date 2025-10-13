import os
import matplotlib.pyplot as plt
from .io_utils import (
    to_datetime_series,
    unify_memory_units_cpu,
    unify_memory_units_gpu,
    get_cpu_mem_col,
    get_gpu_mem_col,
)

def generate_cross_codec_comparisons(experiments_map, output_dir, canonical_mem_unit):
    """
    Comparisons between codecs (H264/HEVC/AV1), same logic:
        - GPU part: CPU, GPU, Total (baseline)
        - CPU-only part: (baseline)
        - Memory over time as line plot (GPU and CPU-only separate)
    """
    comp_dir = os.path.join(output_dir, "_codec_comparisons")
    os.makedirs(comp_dir, exist_ok=True)

    codec_cpu_map = {}
    codec_gpu_map = {}
    for exp_name in experiments_map.keys():
        if '-' not in exp_name:
            continue
        codec, hw = exp_name.split('-', 1)
        if hw == 'cpu': codec_cpu_map[codec] = exp_name
        if hw == 'gpu': codec_gpu_map[codec] = exp_name

    target_profile = 'baseline'

    # --- GPU experiments (CPU+GPU breakdown)
    if codec_gpu_map:
        codecs = sorted(codec_gpu_map.keys())
        avg_cpu_powers, avg_gpu_powers, avg_tot_powers = [], [], []
        total_cpu_energy, total_gpu_energy, total_energy = [], [], []

        for codec in codecs:
            exp = codec_gpu_map[codec]
            if target_profile not in experiments_map[exp]:
                continue
            merged_df, _, _ = experiments_map[exp][target_profile]
            avg_cpu_powers.append(merged_df['power_w_cpu'].mean() if 'power_w_cpu' in merged_df.columns else float('nan'))
            avg_gpu_powers.append(merged_df['power_w_gpu'].mean() if 'power_w_gpu' in merged_df.columns else float('nan'))
            avg_tot_powers.append(merged_df['total_power_w'].mean() if 'total_power_w' in merged_df.columns else float('nan'))
            cpu_e = merged_df['energy_j_total_cpu'].iloc[-1] if 'energy_j_total_cpu' in merged_df.columns else 0
            gpu_e = merged_df['energy_j_total_gpu'].iloc[-1] if 'energy_j_total_gpu' in merged_df.columns else 0
            total_cpu_energy.append(cpu_e); total_gpu_energy.append(gpu_e); total_energy.append(cpu_e + gpu_e)

        x = range(len(codecs)); w = 0.25
        # Power
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.bar([i - w for i in x], avg_cpu_powers, w, label='CPU')
        ax.bar([i for i in x],     avg_gpu_powers, w, label='GPU')
        ax.bar([i + w for i in x], avg_tot_powers, w, label='Total')
        ax.set_xticks(list(x)); ax.set_xticklabels([c.upper() for c in codecs])
        ax.set_ylabel("Average Power (W)")
        ax.set_title("Average Power Across Codecs (GPU Experiments)")
        ax.legend(); ax.grid(axis='y', alpha=0.3)
        plt.tight_layout(); plt.savefig(os.path.join(comp_dir, "codec_comparison_gpu_power.png"), dpi=150); plt.close()

        # Energy
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.bar([i - w for i in x], total_cpu_energy, w, label='CPU')
        ax.bar([i for i in x],     total_gpu_energy, w, label='GPU')
        ax.bar([i + w for i in x], total_energy,     w, label='Total')
        ax.set_xticks(list(x)); ax.set_xticklabels([c.upper() for c in codecs])
        ax.set_ylabel("Total Energy (J)")
        ax.set_title("Total Energy Across Codecs (GPU Experiments)")
        ax.legend(); ax.grid(axis='y', alpha=0.3)
        plt.tight_layout(); plt.savefig(os.path.join(comp_dir, "codec_comparison_gpu_energy.png"), dpi=150); plt.close()

        # GPU Memory over time (baseline)
        plt.figure(figsize=(12, 6))
        for codec in codecs:
            exp = codec_gpu_map[codec]
            if target_profile not in experiments_map[exp]:
                continue
            _, _, gpu_df = experiments_map[exp][target_profile]
            if gpu_df is None or gpu_df.empty:
                continue
            gpu_df = unify_memory_units_gpu(gpu_df, canonical_mem_unit)
            gpu_df['ts'] = to_datetime_series(gpu_df['ts'])
            gpu_df['time_s'] = (gpu_df['ts'] - gpu_df['ts'].min()).dt.total_seconds()
            mem_col, _ = get_gpu_mem_col(gpu_df, canonical_mem_unit)
            if mem_col:
                plt.plot(gpu_df['time_s'], gpu_df[mem_col], label=codec.upper(), linewidth=2)
        unit_label = canonical_mem_unit if canonical_mem_unit.lower() in ("mib", "mb") else "MB/MiB"
        plt.title("GPU Memory Usage Over Time (Baseline, GPU Experiments)")
        plt.xlabel("Time (seconds)"); plt.ylabel(f"Memory ({unit_label})")
        plt.legend(); plt.grid(True, alpha=0.3)
        plt.tight_layout(); plt.savefig(os.path.join(comp_dir, "codec_comparison_gpu_memory.png"), dpi=150); plt.close()

    # --- CPU-only experiments (baseline)
    if codec_cpu_map:
        codecs = sorted(codec_cpu_map.keys())
        avg_powers, total_energy, avg_mem = [], [], []

        for codec in codecs:
            exp = codec_cpu_map[codec]
            if target_profile not in experiments_map[exp]:
                continue
            merged_df, cpu_df, _ = experiments_map[exp][target_profile]
            avg_powers.append(merged_df['power_w_cpu'].mean() if 'power_w_cpu' in merged_df.columns else float('nan'))
            cpu_e = merged_df['energy_j_total_cpu'].iloc[-1] if 'energy_j_total_cpu' in merged_df.columns else 0
            total_energy.append(cpu_e)
            cpu_df = unify_memory_units_cpu(cpu_df, canonical_mem_unit)
            mem_col, _ = get_cpu_mem_col(cpu_df, canonical_mem_unit)
            avg_mem.append(cpu_df[mem_col].mean() if mem_col and mem_col in cpu_df.columns else float('nan'))

        # Power
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.bar([c.upper() for c in codecs], avg_powers, alpha=0.85)
        for i, v in enumerate(avg_powers):
            ax.text(i, v, f"{v:.1f} W", ha='center', va='bottom', fontsize=10)
        ax.set_title("Average Power Across Codecs (CPU-only Experiments)")
        ax.set_ylabel("Average Power (W)")
        ax.grid(axis='y', alpha=0.3)
        plt.tight_layout(); plt.savefig(os.path.join(comp_dir, "codec_comparison_cpu_power.png"), dpi=150); plt.close()

        # Energy
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.bar([c.upper() for c in codecs], total_energy, alpha=0.85)
        for i, v in enumerate(total_energy):
            ax.text(i, v, f"{v:.0f} J", ha='center', va='bottom', fontsize=10)
        ax.set_title("Total Energy Across Codecs (CPU-only Experiments)")
        ax.set_ylabel("Total Energy (J)")
        ax.grid(axis='y', alpha=0.3)
        plt.tight_layout(); plt.savefig(os.path.join(comp_dir, "codec_comparison_cpu_energy.png"), dpi=150); plt.close()

        # CPU Memory over time (baseline)
        plt.figure(figsize=(12, 6))
        for codec in codecs:
            exp = codec_cpu_map[codec]
            if target_profile not in experiments_map[exp]:
                continue
            _, cpu_df, _ = experiments_map[exp][target_profile]
            cpu_df = unify_memory_units_cpu(cpu_df, canonical_mem_unit)
            cpu_df['ts'] = to_datetime_series(cpu_df['ts'])
            cpu_df['time_s'] = (cpu_df['ts'] - cpu_df['ts'].min()).dt.total_seconds()
            mem_col, _ = get_cpu_mem_col(cpu_df, canonical_mem_unit)
            if mem_col:
                plt.plot(cpu_df['time_s'], cpu_df[mem_col], label=codec.upper(), linewidth=2)
        unit_label = canonical_mem_unit if canonical_mem_unit.lower() in ("mib", "mb") else "MB/MiB"
        plt.title("CPU Memory Usage Over Time (Baseline, CPU-only Experiments)")
        plt.xlabel("Time (seconds)"); plt.ylabel(f"Memory ({unit_label})")
        plt.legend(); plt.grid(True, alpha=0.3)
        plt.tight_layout(); plt.savefig(os.path.join(comp_dir, "codec_comparison_cpu_memory.png"), dpi=150); plt.close()

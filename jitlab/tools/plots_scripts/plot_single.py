import numpy as np
import matplotlib.pyplot as plt
from .io_utils import (
    to_datetime_series,
    unify_memory_units_cpu,
    unify_memory_units_gpu,
    get_cpu_mem_col,
    get_gpu_mem_col,
)

def generate_single_experiment_plots(merged_df, cpu_df, gpu_df, title, output_prefix, canonical_mem_unit):
    """
    Plots for single profile:
      1) Power over time (CPU, GPU, Total)
      2) Total Energy (bar)
      3) Memory over time (CPU RAM + GPU VRAM overlay)
      4) Summary table adaptive
    """
    merged_df = merged_df.copy()
    cpu_df = unify_memory_units_cpu(cpu_df.copy(), canonical_mem_unit)

    gpu_available = (gpu_df is not None) and (not gpu_df.empty)
    if gpu_available:
        gpu_df = unify_memory_units_gpu(gpu_df.copy(), canonical_mem_unit)

    # Prepare time axis
    merged_df['ts'] = to_datetime_series(merged_df['ts'])
    merged_df['time_s'] = (merged_df['ts'] - merged_df['ts'].min()).dt.total_seconds()

    has_cpu_power = 'power_w_cpu' in merged_df.columns
    has_gpu_power = 'power_w_gpu' in merged_df.columns
    has_total     = 'total_power_w' in merged_df.columns

    # 1) Power over time
    plt.figure(figsize=(12, 6))
    if has_cpu_power:
        plt.plot(merged_df['time_s'], merged_df['power_w_cpu'], label='CPU Power (W)', linewidth=2)
        plt.axhline(merged_df['power_w_cpu'].mean(), linestyle='--', alpha=0.7,
                    label=f'Avg CPU: {merged_df["power_w_cpu"].mean():.1f} W')
    if has_gpu_power:
        plt.plot(merged_df['time_s'], merged_df['power_w_gpu'], label='GPU Power (W)', linewidth=2)
        plt.axhline(merged_df['power_w_gpu'].mean(), linestyle='--', alpha=0.7,
                    label=f'Avg GPU: {merged_df["power_w_gpu"].mean():.1f} W')
    if has_total:
        plt.plot(merged_df['time_s'], merged_df['total_power_w'], label='Total Power (W)', linewidth=2)
        plt.axhline(merged_df['total_power_w'].mean(), linestyle='--', alpha=0.7,
                    label=f'Avg Total: {merged_df["total_power_w"].mean():.1f} W')
    plt.title(f'{title} - Power Usage Over Time')
    plt.xlabel('Time (seconds)'); plt.ylabel('Power (W)'); plt.xlim(left=0)
    plt.legend(); plt.grid(True, alpha=0.3); plt.tight_layout()
    plt.savefig(f'{output_prefix}_1_power_usage_line.png', dpi=150); plt.close()

    # 2) Total Energy (bar)
    fig, ax = plt.subplots(figsize=(8, 6))
    cats, vals = [], []
    if 'energy_j_total_cpu' in merged_df.columns:
        cats.append('CPU'); vals.append(float(merged_df['energy_j_total_cpu'].iloc[-1]))
    if 'energy_j_total_gpu' in merged_df.columns:
        cats.append('GPU'); vals.append(float(merged_df['energy_j_total_gpu'].iloc[-1]))
    if ('energy_j_total_cpu' in merged_df.columns) and ('energy_j_total_gpu' in merged_df.columns):
        cats.append('Total'); vals.append(vals[0] + vals[1])
    bars = ax.bar(cats, vals, alpha=0.85)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width()/2., v, f'{v:.1f} J\n({v/3600:.4f} Wh)',
                ha='center', va='bottom', fontsize=10)
    ax.set_ylabel('Total Energy (J)'); ax.set_title(f'{title} - Total Energy Consumption')
    ax.grid(axis='y', alpha=0.3); plt.tight_layout()
    plt.savefig(f'{output_prefix}_2_total_energy_bar.png', dpi=150); plt.close()

    # 3) Memory over time (overlay)
    plt.figure(figsize=(12, 6))
    if 'ts' in cpu_df.columns:
        cpu_df = cpu_df.copy()
        cpu_df['ts'] = to_datetime_series(cpu_df['ts'])
        t0 = cpu_df['ts'].min()
        mem_col, mem_label = get_cpu_mem_col(cpu_df, canonical_mem_unit)
        if mem_col and mem_col in cpu_df.columns:
            plt.plot((cpu_df['ts'] - t0).dt.total_seconds(), cpu_df[mem_col], label=mem_label, linewidth=2)

    if gpu_available and 'ts' in gpu_df.columns:
        gpu_df = gpu_df.copy()
        gpu_df['ts'] = to_datetime_series(gpu_df['ts'])
        t0g = gpu_df['ts'].min()
        gmem_col, gmem_label = get_gpu_mem_col(gpu_df, canonical_mem_unit)
        if gmem_col and gmem_col in gpu_df.columns:
            plt.plot((gpu_df['ts'] - t0g).dt.total_seconds(), gpu_df[gmem_col], label=gmem_label, linewidth=2)

    unit_label = canonical_mem_unit if canonical_mem_unit.lower() in ("mib", "mb") else "MB/MiB"
    plt.title(f'{title} - Memory Usage Over Time')
    plt.xlabel('Time (seconds)'); plt.ylabel(f'Memory ({unit_label})'); plt.xlim(left=0)
    plt.legend(); plt.grid(True, alpha=0.3); plt.tight_layout()
    plt.savefig(f'{output_prefix}_5_memory_usage.png', dpi=150); plt.close()

    # 4) Summary table
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.axis('tight'); ax.axis('off')

    has_cpu_energy = 'energy_j_total_cpu' in merged_df.columns
    has_gpu_energy = 'energy_j_total_gpu' in merged_df.columns

    cpu_avg_p = merged_df['power_w_cpu'].mean() if has_cpu_power else np.nan
    cpu_max_p = merged_df['power_w_cpu'].max() if has_cpu_power else np.nan
    gpu_avg_p = merged_df['power_w_gpu'].mean() if has_gpu_power else np.nan
    gpu_max_p = merged_df['power_w_gpu'].max() if has_gpu_power else np.nan
    tot_avg_p = merged_df['total_power_w'].mean() if has_total else (cpu_avg_p if has_cpu_power else np.nan)
    tot_max_p = merged_df['total_power_w'].max() if has_total else (cpu_max_p if has_cpu_power else np.nan)

    cpu_e = merged_df['energy_j_total_cpu'].iloc[-1] if has_cpu_energy else np.nan
    gpu_e = merged_df['energy_j_total_gpu'].iloc[-1] if has_gpu_energy else np.nan
    tot_e = (cpu_e + gpu_e) if (has_cpu_energy and has_gpu_energy) else (cpu_e if has_cpu_energy else np.nan)

    cpu_util_avg = merged_df['cpu_percent'].mean() if 'cpu_percent' in merged_df.columns else np.nan
    cpu_util_max = merged_df['cpu_percent'].max() if 'cpu_percent' in merged_df.columns else np.nan
    gpu_util_avg = merged_df['gpu_util_percent'].mean() if 'gpu_util_percent' in merged_df.columns else np.nan
    gpu_util_max = merged_df['gpu_util_percent'].max() if 'gpu_util_percent' in merged_df.columns else np.nan

    cmem_col, _ = get_cpu_mem_col(cpu_df, canonical_mem_unit)
    gmem_col, _ = (get_gpu_mem_col(gpu_df, canonical_mem_unit) if gpu_available else (None, None))
    cmem_avg = cpu_df[cmem_col].mean() if cmem_col and cmem_col in cpu_df.columns else np.nan
    cmem_max = cpu_df[cmem_col].max() if cmem_col and cmem_col in cpu_df.columns else np.nan
    gmem_avg = gpu_df[gmem_col].mean() if (gpu_available and gmem_col and gmem_col in gpu_df.columns) else np.nan
    gmem_max = gpu_df[gmem_col].max() if (gpu_available and gmem_col and gmem_col in gpu_df.columns) else np.nan

    duration_s = (merged_df['ts'].max() - merged_df['ts'].min()).total_seconds()

    header = ['Metric', 'CPU']
    if gpu_available:
        header += ['GPU', 'Total']
    rows = [header]

    if gpu_available:
        rows += [
            ['Average Power (W)', f"{cpu_avg_p:.2f}", f"{gpu_avg_p:.2f}", f"{tot_avg_p:.2f}"],
            ['Peak Power (W)',    f"{cpu_max_p:.2f}", f"{gpu_max_p:.2f}", f"{tot_max_p:.2f}"],
            ['Total Energy (J)',  f"{cpu_e:.2f}",     f"{gpu_e:.2f}",     f"{tot_e:.2f}"],
            ['Total Energy (Wh)', f"{cpu_e/3600:.4f}", f"{gpu_e/3600:.4f}", f"{tot_e/3600:.4f}"],
            ['Avg Utilization (%)',  f"{cpu_util_avg:.1f}", f"{gpu_util_avg:.1f}", 'N/A'],
            ['Peak Utilization (%)', f"{cpu_util_max:.1f}", f"{gpu_util_max:.1f}", 'N/A'],
        ]
    else:
        rows += [
            ['Average Power (W)', f"{cpu_avg_p:.2f}"],
            ['Peak Power (W)',    f"{cpu_max_p:.2f}"],
            ['Total Energy (J)',  f"{cpu_e:.2f}"],
            ['Total Energy (Wh)', f"{cpu_e/3600:.4f}"],
        ]
        if not np.isnan(cpu_util_avg): rows.append(['Avg Utilization (%)',  f"{cpu_util_avg:.1f}"])
        if not np.isnan(cpu_util_max): rows.append(['Peak Utilization (%)', f"{cpu_util_max:.1f}"])

    mem_unit = canonical_mem_unit if canonical_mem_unit.lower() in ("mib", "mb") else "MB/MiB"
    if gpu_available:
        rows += [
            [f'Avg Memory ({mem_unit})',  f"{cmem_avg:.1f}", f"{gmem_avg:.1f}", 'N/A'],
            [f'Peak Memory ({mem_unit})', f"{cmem_max:.1f}", f"{gmem_max:.1f}", 'N/A'],
            ['Duration (s)', f"{duration_s:.1f}", '', '']
        ]
    else:
        rows += [
            [f'Avg Memory ({mem_unit})',  f"{cmem_avg:.1f}"],
            [f'Peak Memory ({mem_unit})', f"{cmem_max:.1f}"],
            ['Duration (s)', f"{duration_s:.1f}"]
        ]

    table = ax.table(cellText=rows, cellLoc='center', loc='center',
                     colWidths=[0.35] + [0.65/(len(header)-1)]*(len(header)-1))
    table.auto_set_font_size(False); table.set_fontsize(9); table.scale(1, 2)
    for j in range(len(header)):
        table[(0, j)].set_facecolor('#34495e'); table[(0, j)].set_text_props(weight='bold', color='white')
    for i in range(1, len(rows)):
        if i % 2 == 0:
            for j in range(len(header)):
                table[(i, j)].set_facecolor('#ecf0f1')

    plt.title(f'{title} - Summary Statistics', fontsize=14, weight='bold', pad=20)
    plt.tight_layout()
    plt.savefig(f'{output_prefix}_6_summary_statistics.png', dpi=150, bbox_inches='tight')
    plt.close()

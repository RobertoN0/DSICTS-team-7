import os
import matplotlib.pyplot as plt
from .io_utils import (
    to_datetime_series,
    unify_memory_units_cpu,
    unify_memory_units_gpu,
    get_cpu_mem_col,
    get_gpu_mem_col,
)

def generate_experiment_overlays(exp_name, profiles_map, exp_out_dir, profiles_order, canonical_mem_unit):
    """
    Overlays between the 4 profiles of the same experiment:
      - CPU Power
      - GPU Power (if GPU experiment)
      - Total Power (if GPU experiment)
      - CPU RAM (all profiles)
      - GPU VRAM (if GPU experiment)
      - Summary table
    """
    ordered_profiles = [p for p in profiles_order if p in profiles_map]
    if not ordered_profiles:
        return

    is_gpu = any('power_w_gpu' in profiles_map[p][0].columns for p in ordered_profiles)

    # CPU Power overlay
    plt.figure(figsize=(12, 7))
    for p in ordered_profiles:
        merged_df = profiles_map[p][0].copy()
        merged_df['ts'] = to_datetime_series(merged_df['ts'])
        t0 = merged_df['ts'].min()
        merged_df['time_s'] = (merged_df['ts'] - t0).dt.total_seconds()
        if 'power_w_cpu' in merged_df.columns:
            plt.plot(merged_df['time_s'], merged_df['power_w_cpu'], label=p, linewidth=2)
    plt.title(f'{exp_name} - CPU Power Over Time (All Profiles)')
    plt.xlabel('Time (seconds)'); plt.ylabel('Power (W)'); plt.xlim(left=0)
    plt.legend(); plt.grid(True, alpha=0.3); plt.tight_layout()
    plt.savefig(os.path.join(exp_out_dir, f'{exp_name}_overlay_cpu_power.png'), dpi=150)
    plt.close()

    # GPU Power overlay
    if is_gpu:
        plt.figure(figsize=(12, 7))
        for p in ordered_profiles:
            merged_df = profiles_map[p][0].copy()
            merged_df['ts'] = to_datetime_series(merged_df['ts'])
            t0 = merged_df['ts'].min()
            merged_df['time_s'] = (merged_df['ts'] - t0).dt.total_seconds()
            if 'power_w_gpu' in merged_df.columns:
                plt.plot(merged_df['time_s'], merged_df['power_w_gpu'], label=p, linewidth=2)
        plt.title(f'{exp_name} - GPU Power Over Time (All Profiles)')
        plt.xlabel('Time (seconds)'); plt.ylabel('Power (W)'); plt.xlim(left=0)
        plt.legend(); plt.grid(True, alpha=0.3); plt.tight_layout()
        plt.savefig(os.path.join(exp_out_dir, f'{exp_name}_overlay_gpu_power.png'), dpi=150)
        plt.close()

        # Total Power overlay
        plt.figure(figsize=(12, 7))
        for p in ordered_profiles:
            merged_df = profiles_map[p][0].copy()
            merged_df['ts'] = to_datetime_series(merged_df['ts'])
            t0 = merged_df['ts'].min()
            merged_df['time_s'] = (merged_df['ts'] - t0).dt.total_seconds()
            if 'total_power_w' in merged_df.columns:
                plt.plot(merged_df['time_s'], merged_df['total_power_w'], label=p, linewidth=2)
        plt.title(f'{exp_name} - Total Power Over Time (All Profiles)')
        plt.xlabel('Time (seconds)'); plt.ylabel('Power (W)'); plt.xlim(left=0)
        plt.legend(); plt.grid(True, alpha=0.3); plt.tight_layout()
        plt.savefig(os.path.join(exp_out_dir, f'{exp_name}_overlay_total_power.png'), dpi=150)
        plt.close()

    # CPU memory overlay
    plt.figure(figsize=(12, 7))
    for p in ordered_profiles:
        cpu_df = unify_memory_units_cpu(profiles_map[p][1].copy(), canonical_mem_unit)
        if 'ts' in cpu_df.columns:
            cpu_df['ts'] = to_datetime_series(cpu_df['ts'])
            t0 = cpu_df['ts'].min()
            mem_col, mem_label = get_cpu_mem_col(cpu_df, canonical_mem_unit)
            if mem_col and mem_col in cpu_df.columns:
                plt.plot((cpu_df['ts'] - t0).dt.total_seconds(), cpu_df[mem_col], label=p, linewidth=2)
    unit_label = canonical_mem_unit if canonical_mem_unit.lower() in ("mib", "mb") else "MB/MiB"
    plt.title(f'{exp_name} - CPU Memory Over Time (All Profiles)')
    plt.xlabel('Time (seconds)'); plt.ylabel(f'Memory ({unit_label})'); plt.xlim(left=0)
    plt.legend(); plt.grid(True, alpha=0.3); plt.tight_layout()
    plt.savefig(os.path.join(exp_out_dir, f'{exp_name}_overlay_memory_cpu.png'), dpi=150)
    plt.close()

    # GPU memory overlay
    if is_gpu:
        plt.figure(figsize=(12, 7))
        for p in ordered_profiles:
            gpu_df = profiles_map[p][2]
            if gpu_df is None or gpu_df.empty:
                continue
            gpu_df = unify_memory_units_gpu(gpu_df.copy(), canonical_mem_unit)
            if 'ts' in gpu_df.columns:
                gpu_df['ts'] = to_datetime_series(gpu_df['ts'])
                t0g = gpu_df['ts'].min()
                gmem_col, gmem_label = get_gpu_mem_col(gpu_df, canonical_mem_unit)
                if gmem_col and gmem_col in gpu_df.columns:
                    plt.plot((gpu_df['ts'] - t0g).dt.total_seconds(), gpu_df[gmem_col], label=p, linewidth=2)
        unit_label = canonical_mem_unit if canonical_mem_unit.lower() in ("mib", "mb") else "MB/MiB"
        plt.title(f'{exp_name} - GPU Memory Over Time (All Profiles)')
        plt.xlabel('Time (seconds)'); plt.ylabel(f'Memory ({unit_label})'); plt.xlim(left=0)
        plt.legend(); plt.grid(True, alpha=0.3); plt.tight_layout()
        plt.savefig(os.path.join(exp_out_dir, f'{exp_name}_overlay_memory_gpu.png'), dpi=150)
        plt.close()

    # Summary table for all profiles
    import numpy as np
    fig, ax = plt.subplots(figsize=(14, 8))
    ax.axis('tight'); ax.axis('off')

    header = ['Metric'] + ordered_profiles
    table_data = [header]

    tot_energy = []; cpu_energy = []; gpu_energy = []
    avg_total_power = []; avg_cpu_power = []; avg_gpu_power = []
    avg_cpu_mem = []; avg_gpu_mem = []

    for p in ordered_profiles:
        mdf, cdf, gdf = profiles_map[p]
        cdf = unify_memory_units_cpu(cdf.copy(), canonical_mem_unit)
        if gdf is not None and not gdf.empty:
            gdf = unify_memory_units_gpu(gdf.copy(), canonical_mem_unit)

        e_cpu = mdf['energy_j_total_cpu'].iloc[-1] if 'energy_j_total_cpu' in mdf.columns else np.nan
        e_gpu = mdf['energy_j_total_gpu'].iloc[-1] if 'energy_j_total_gpu' in mdf.columns else np.nan
        e_tot = (e_cpu + e_gpu) if (not np.isnan(e_cpu) and not np.isnan(e_gpu)) else e_cpu

        cpu_energy.append(e_cpu); gpu_energy.append(e_gpu); tot_energy.append(e_tot)

        avg_cpu_power.append(mdf['power_w_cpu'].mean() if 'power_w_cpu' in mdf.columns else np.nan)
        avg_gpu_power.append(mdf['power_w_gpu'].mean() if 'power_w_gpu' in mdf.columns else np.nan)
        avg_total_power.append(mdf['total_power_w'].mean() if 'total_power_w' in mdf.columns else avg_cpu_power[-1])

        cmem_col, _ = get_cpu_mem_col(cdf, canonical_mem_unit)
        avg_cpu_mem.append(cdf[cmem_col].mean() if cmem_col and cmem_col in cdf.columns else np.nan)
        if gdf is not None and not gdf.empty:
            gmem_col, _ = get_gpu_mem_col(gdf, canonical_mem_unit)
            avg_gpu_mem.append(gdf[gmem_col].mean() if gmem_col and gmem_col in gdf.columns else np.nan)
        else:
            avg_gpu_mem.append(np.nan)

    mem_unit = canonical_mem_unit if canonical_mem_unit.lower() in ("mib", "mb") else "MB/MiB"
    table_data.append(['Total Energy (J)'] + [f"{x:.1f}" if not np.isnan(x) else '-' for x in tot_energy])
    table_data.append(['CPU Energy (J)']   + [f"{x:.1f}" if not np.isnan(x) else '-' for x in cpu_energy])
    table_data.append(['GPU Energy (J)']   + [f"{x:.1f}" if not np.isnan(x) else '-' for x in gpu_energy])
    table_data.append(['Avg Total Power (W)'] + [f"{x:.2f}" if not np.isnan(x) else '-' for x in avg_total_power])
    table_data.append(['Avg CPU Power (W)']   + [f"{x:.2f}" if not np.isnan(x) else '-' for x in avg_cpu_power])
    table_data.append(['Avg GPU Power (W)']   + [f"{x:.2f}" if not np.isnan(x) else '-' for x in avg_gpu_power])
    table_data.append([f'Avg CPU Mem ({mem_unit})'] + [f"{x:.1f}" if not np.isnan(x) else '-' for x in avg_cpu_mem])
    table_data.append([f'Avg GPU Mem ({mem_unit})'] + [f"{x:.1f}" if not np.isnan(x) else '-' for x in avg_gpu_mem])

    tbl = ax.table(cellText=table_data, cellLoc='center', loc='center',
                   colWidths=[0.25] + [0.75/len(ordered_profiles)]*len(ordered_profiles))
    tbl.auto_set_font_size(False); tbl.set_fontsize(9); tbl.scale(1, 2)
    for j in range(len(header)):
        tbl[(0, j)].set_facecolor('#34495e'); tbl[(0, j)].set_text_props(weight='bold', color='white')
    for i in range(1, len(table_data)):
        if i % 2 == 0:
            for j in range(len(header)):
                tbl[(i, j)].set_facecolor('#ecf0f1')

    plt.title(f'{exp_name} - Experiment Summary (All Profiles)', fontsize=14, weight='bold', pad=20)
    plt.tight_layout()
    plt.savefig(os.path.join(exp_out_dir, f'{exp_name}_experiment_summary_table.png'), dpi=150, bbox_inches='tight')
    plt.close()

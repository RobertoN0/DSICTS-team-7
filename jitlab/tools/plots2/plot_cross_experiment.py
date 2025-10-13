import os
import numpy as np
import matplotlib.pyplot as plt
from .io_utils import (
    unify_memory_units_cpu,
    unify_memory_units_gpu,
    get_cpu_mem_col,
    get_gpu_mem_col,
)

def generate_cross_experiment_plots(experiments_map, output_dir, profiles_order, canonical_mem_unit):
    """
    Comparisons between CPU-only vs GPU for THE SAME codec (same logic as original).
    Output in: <output_dir>/_comparisons/<codec>_*.png
    """
    comp_dir = os.path.join(output_dir, "_comparisons")
    os.makedirs(comp_dir, exist_ok=True)

    by_codec = {}
    for exp_name in experiments_map.keys():
        if '-' not in exp_name:
            continue
        codec, hw = exp_name.split('-', 1)
        by_codec.setdefault(codec, {})[hw] = exp_name

    for codec, d in by_codec.items():
        if 'cpu' not in d or 'gpu' not in d:
            continue
        cpu_exp = d['cpu']
        gpu_exp = d['gpu']

        cpu_profiles = experiments_map[cpu_exp]
        gpu_profiles = experiments_map[gpu_exp]

        profiles = [p for p in profiles_order if p in cpu_profiles and p in gpu_profiles]
        if not profiles:
            continue

        x = np.arange(len(profiles)); width = 0.2
        e_cpu_only = []; e_cpu_gpu = []; e_gpu = []; e_total = []
        p_cpu_only = []; p_cpu_gpu = []; p_gpu = []; p_total = []
        mem_cpu_only = []; mem_cpu_gpu = []; mem_gpu = []; mem_total = []

        for p in profiles:
            m_cpu, c_cpu, _     = cpu_profiles[p]
            m_gpu, c_gpu, g_gpu = gpu_profiles[p]

            # Energy
            e1 = m_cpu['energy_j_total_cpu'].iloc[-1] if 'energy_j_total_cpu' in m_cpu.columns else np.nan
            ec = m_gpu['energy_j_total_cpu'].iloc[-1] if 'energy_j_total_cpu' in m_gpu.columns else np.nan
            eg = m_gpu['energy_j_total_gpu'].iloc[-1] if 'energy_j_total_gpu' in m_gpu.columns else np.nan
            et = (ec + eg) if (not np.isnan(ec) and not np.isnan(eg)) else ec
            e_cpu_only.append(e1); e_cpu_gpu.append(ec); e_gpu.append(eg); e_total.append(et)

            # Power
            pc1 = m_cpu['power_w_cpu'].mean() if 'power_w_cpu' in m_cpu.columns else np.nan
            pcc = m_gpu['power_w_cpu'].mean() if 'power_w_cpu' in m_gpu.columns else np.nan
            pg  = m_gpu['power_w_gpu'].mean() if 'power_w_gpu' in m_gpu.columns else np.nan
            pt  = m_gpu['total_power_w'].mean() if 'total_power_w' in m_gpu.columns else pcc
            p_cpu_only.append(pc1); p_cpu_gpu.append(pcc); p_gpu.append(pg); p_total.append(pt)

            # Memory (mean)
            c_cpu = unify_memory_units_cpu(c_cpu.copy(), canonical_mem_unit)
            memc_col, _ = get_cpu_mem_col(c_cpu, canonical_mem_unit)
            mco = c_cpu[memc_col].mean() if memc_col and memc_col in c_cpu.columns else np.nan
            mem_cpu_only.append(mco)

            c_gpu = unify_memory_units_cpu(c_gpu.copy(), canonical_mem_unit)
            memcg_col, _ = get_cpu_mem_col(c_gpu, canonical_mem_unit)
            mcg = c_gpu[memcg_col].mean() if memcg_col and memcg_col in c_gpu.columns else np.nan
            mem_cpu_gpu.append(mcg)

            if g_gpu is not None and not g_gpu.empty:
                g_gpu = unify_memory_units_gpu(g_gpu.copy(), canonical_mem_unit)
                memg_col, _ = get_gpu_mem_col(g_gpu, canonical_mem_unit)
                mg = g_gpu[memg_col].mean() if memg_col and memg_col in g_gpu.columns else np.nan
            else:
                mg = np.nan
            mem_gpu.append(mg)
            mem_total.append((mcg if not np.isnan(mcg) else 0.0) + (mg if not np.isnan(mg) else 0.0))

        # Energy
        fig, ax = plt.subplots(figsize=(14, 7))
        ax.bar(x - 1.5*width, e_cpu_only, width, label='CPU-only (CPU exp)')
        ax.bar(x - 0.5*width, e_cpu_gpu,  width, label='CPU (GPU exp)')
        ax.bar(x + 0.5*width, e_gpu,      width, label='GPU (GPU exp)')
        ax.bar(x + 1.5*width, e_total,    width, label='CPU+GPU Total (GPU exp)')
        ax.set_xticks(x); ax.set_xticklabels(profiles)
        ax.set_ylabel('Energy (J)'); ax.set_title(f'{codec.upper()} - Energy by Profile (CPU vs GPU experiments)')
        ax.grid(axis='y', alpha=0.3); ax.legend()
        for i, v in enumerate(e_total):
            if not np.isnan(v):
                ax.text(x[i] + 1.5*width, v, f'{v:.0f}J', ha='center', va='bottom', fontsize=8)
        plt.tight_layout(); plt.savefig(os.path.join(comp_dir, f'{codec}_energy_comparison.png'), dpi=150); plt.close()

        # Avg Power
        fig, ax = plt.subplots(figsize=(14, 7))
        ax.bar(x - 1.5*width, p_cpu_only, width, label='CPU-only (CPU exp)')
        ax.bar(x - 0.5*width, p_cpu_gpu,  width, label='CPU (GPU exp)')
        ax.bar(x + 0.5*width, p_gpu,      width, label='GPU (GPU exp)')
        ax.bar(x + 1.5*width, p_total,    width, label='CPU+GPU Total (GPU exp)')
        ax.set_xticks(x); ax.set_xticklabels(profiles)
        ax.set_ylabel('Average Power (W)'); ax.set_title(f'{codec.upper()} - Avg Power by Profile (CPU vs GPU experiments)')
        ax.grid(axis='y', alpha=0.3); ax.legend()
        plt.tight_layout(); plt.savefig(os.path.join(comp_dir, f'{codec}_avg_power_comparison.png'), dpi=150); plt.close()

        # Memory (stacked per CPU+GPU)
        fig, ax = plt.subplots(figsize=(14, 7))
        ax.bar(x - 1.5*width, mem_cpu_only, width, label='CPU-only RAM (CPU exp)')
        ax.bar(x - 0.5*width, mem_cpu_gpu,  width, label='CPU RAM (GPU exp)')
        ax.bar(x + 0.5*width, mem_gpu,      width, label='GPU VRAM (GPU exp)')
        ax.bar(x + 1.5*width, mem_cpu_gpu,  width, label='CPU RAM (stacked)', alpha=0.7)
        ax.bar(x + 1.5*width, mem_gpu,      width, bottom=[mcg if not np.isnan(mcg) else 0.0 for mcg in mem_cpu_gpu],
               label='GPU VRAM (stacked)', alpha=0.7)
        unit_label = canonical_mem_unit if canonical_mem_unit.lower() in ("mib", "mb") else "MB/MiB"
        ax.set_xticks(x); ax.set_xticklabels(profiles)
        ax.set_ylabel(f'Memory ({unit_label})')
        ax.set_title(f'{codec.upper()} - Memory by Profile (CPU vs GPU experiments)\n'
                     f'Rightmost bar = CPU+GPU (stacked, types diversi, solo footprint)')
        ax.grid(axis='y', alpha=0.3); ax.legend(ncol=2)
        plt.tight_layout(); plt.savefig(os.path.join(comp_dir, f'{codec}_memory_comparison.png'), dpi=150); plt.close()

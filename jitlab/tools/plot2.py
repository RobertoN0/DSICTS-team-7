import argparse
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os
import glob

def average_csv_files(file_paths, file_type='CPU', output_path=None):
    """
    Loads multiple CSV files and computes the row-wise average.
    """
    if not file_paths:
        raise ValueError(f"File paths list for {file_type} is empty.")

    print(f"Averaging data from {len(file_paths)} {file_type} files...")
    df_list = [pd.read_csv(f) for f in file_paths]

    num_rows = len(df_list[0])
    if not all(len(df) == num_rows for df in df_list):
        # Provide more detail in the error message
        row_counts = [len(df) for df in df_list]
        raise ValueError(f"All CSV files must have the same number of rows. Found counts: {row_counts}")

    # Create uniform datetime timestamps, 1 second apart
    start_ts = pd.to_datetime(df_list[0]['ts'].iloc[0], unit='s', errors='coerce')
    new_ts = pd.date_range(start=start_ts, periods=num_rows, freq='1S')

    # Average all other data columns
    data_cols = [col for col in df_list[0].columns if col != 'ts']
    data_arrays = [df[data_cols].to_numpy() for df in df_list]
    stacked_data = np.stack(data_arrays, axis=0)
    averaged_data = np.mean(stacked_data, axis=0)
    
    averaged_df = pd.DataFrame(averaged_data, columns=data_cols)
    averaged_df.insert(0, 'ts', new_ts)
    
    # if output_path is None:
    #     output_path = f"averaged_{file_type}.csv"
    
    # averaged_df.to_csv(output_path, index=False, date_format='%Y-%m-%d %H:%M:%S')
    # print(f"Averaged {file_type} data saved to: {os.path.abspath(output_path)}")

    return averaged_df

def merge_dataframes(cpu_df, gpu_df, profile_name):
    """
    Merge averaged CPU and GPU dataframes based on timestamp.
    """
    print("Merging averaged CPU and GPU data...")
    
    # Convert Unix timestamps to datetime for merging
    cpu_df['ts_dt'] = pd.to_datetime(cpu_df['ts'], unit='s')
    gpu_df['ts_dt'] = pd.to_datetime(gpu_df['ts'], unit='s')

    cpu_df = cpu_df.sort_values('ts_dt').reset_index(drop=True)
    gpu_df = gpu_df.sort_values('ts_dt').reset_index(drop=True)

    # Use merge_asof for time-based merge with tolerance
    merged_df = pd.merge_asof(cpu_df, gpu_df, left_on='ts_dt', right_on='ts_dt',
                              direction='nearest', tolerance=pd.Timedelta('1s'),
                              suffixes=('_cpu', '_gpu'))
    
    # Clean up timestamp columns (keep the original float version from CPU)
    merged_df = merged_df.rename(columns={'ts_cpu': 'ts'}).drop(columns=['ts_dt', 'ts_gpu'], errors='ignore')

    # Forward/backward fill to handle any misalignments at the edges
    merged_df = merged_df.ffill().bfill()
    
    # Ensure power columns exist before summing them up
    if 'power_w_cpu' in merged_df.columns and 'power_w_gpu' in merged_df.columns:
        merged_df['total_power_w'] = merged_df['power_w_cpu'] + merged_df['power_w_gpu']
    else:
        print("  Warning: Could not calculate total power, one or more power columns missing.")

    merged_df['profile'] = profile_name
    print(f"  Merged records for '{profile_name}': {len(merged_df)}")
    
    return merged_df

def generate_single_experiment_plots(merged_df, cpu_df, gpu_df, title, output_prefix):
    """Generate plots for a single experiment."""
    
    # Normalize time to start from 0
    merged_df['time_s'] = (merged_df['ts'] - merged_df['ts'].min()).dt.total_seconds()
    gpu_df['time_s'] = (gpu_df['ts'] - gpu_df['ts'].min()).dt.total_seconds()
    
    # === 1. Line Plot: CPU, GPU, and Total Power ===
    plt.figure(figsize=(12, 6))
    plt.plot(merged_df['time_s'], merged_df['power_w_cpu'], label='CPU Power (W)', color="blue")
    plt.plot(merged_df['time_s'], merged_df['power_w_gpu'], label='GPU Power (W)', color="orange")
    plt.plot(merged_df['time_s'], merged_df['total_power_w'], label='Total Power (W)', color='black')

    # Add average lines
    avg_power_cpu = merged_df['power_w_cpu'].mean()
    avg_power_gpu = merged_df['power_w_gpu'].mean()
    avg_power_total = merged_df['total_power_w'].mean()
    plt.axhline(y=avg_power_cpu, linestyle='--', alpha=0.7, color='blue', label=f'Avg CPU: {avg_power_cpu:.1f} W')
    plt.axhline(y=avg_power_gpu, linestyle='--', alpha=0.7, color='orange', label=f'Avg GPU: {avg_power_gpu:.1f} W')
    plt.axhline(y=avg_power_total, linestyle='--', alpha=0.7, color='black', label=f'Avg Total: {avg_power_total:.1f} W')

    plt.title(f'{title} - Power Usage Over Time')
    plt.xlabel('Time (seconds)')
    plt.ylabel('Power (W)')
    plt.xlim(left=0)  # Force x-axis to start at 0
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(f'{output_prefix}_1_power_usage_line.png', dpi=150)
    print(f"✓ Saved: {output_prefix}_1_power_usage_line.png")
    plt.close()
    
    # === 2. Bar Graph: Total Energy Consumption ===
    cpu_total_energy = merged_df['energy_j_total_cpu'].iloc[-1]
    gpu_total_energy = merged_df['energy_j_total_gpu'].iloc[-1]
    total_energy = cpu_total_energy + gpu_total_energy
    
    fig, ax = plt.subplots(figsize=(8, 6))
    categories = ['CPU', 'GPU', 'Total']
    energies = [cpu_total_energy, gpu_total_energy, total_energy]
    colors = ['#3498db', '#2ecc71', '#34495e']
    bars = ax.bar(categories, energies, color=colors, alpha=0.8)
    
    # Add value labels on bars
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.1f} J\n({height/3600:.4f} Wh)',
                ha='center', va='bottom', fontsize=10)
    
    ax.set_ylabel('Total Energy (J)')
    ax.set_title(f'{title} - Total Energy Consumption')
    ax.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig(f'{output_prefix}_2_total_energy_bar.png', dpi=150)
    print(f"✓ Saved: {output_prefix}_2_total_energy_bar.png")
    plt.close()

    # # === 3. GPU Utilization Over Time ===
    # plt.figure(figsize=(12, 6))

    # # Normalize time
    # merged_df['time_s'] = (merged_df['ts'] - merged_df['ts'].min()).dt.total_seconds()

    # plt.plot(merged_df['time_s'], merged_df['gpu_util_percent'], color='#e74c3c', linewidth=2, label='GPU Utilization (%)')
    # plt.fill_between(merged_df['time_s'], merged_df['gpu_util_percent'], alpha=0.3, color='#e74c3c')

    # # Add average line
    # avg_util = merged_df['gpu_util_percent'].mean()
    # plt.axhline(y=avg_util, color='red', linestyle='--', alpha=0.7, label=f'Avg: {avg_util:.1f}%')

    # plt.xlabel('Time (seconds)', fontsize=12)
    # plt.ylabel('GPU Utilization (%)', fontsize=12)
    # plt.title(f'{title} - GPU Utilization Over Time', fontsize=13, fontweight='bold')
    # plt.ylim(0, 100)
    # plt.xlim(left=0)  # Force x-axis to start at 0
    # plt.grid(True, alpha=0.3)
    # plt.legend(loc='upper right')
    # plt.tight_layout()
    # plt.savefig(f'{output_prefix}_3_gpu_utilization.png', dpi=150)
    # print(f"✓ Saved: {output_prefix}_3_gpu_utilization.png")
    # plt.close()
    
    # # === 4. Temperature Over Time ===
    # plt.figure(figsize=(12, 6))
    # plt.plot(gpu_df['time_s'], gpu_df['temp_c'], color='#e74c3c', linewidth=2)
    # plt.fill_between(gpu_df['time_s'], gpu_df['temp_c'], alpha=0.3, color='#e74c3c')
    # plt.xlabel('Time (seconds)', fontsize=12)
    # plt.ylabel('Temperature (°C)', fontsize=12)
    # plt.xlim(left=0)  # Force x-axis to start at 0
    # plt.title(f'{title} - GPU Temperature Over Time')
    # plt.grid(True, alpha=0.3)
    
    # # Add average line
    # avg_temp = gpu_df['temp_c'].mean()
    # plt.axhline(y=avg_temp, color='red', linestyle='--', 
    #             alpha=0.7, label=f'Avg: {avg_temp:.1f}°C')
    # plt.legend(loc='upper right')
    
    # plt.tight_layout()
    # plt.savefig(f'{output_prefix}_4_gpu_temperature.png', dpi=150)
    # print(f"✓ Saved: {output_prefix}_4_gpu_temperature.png")
    # plt.close()
    
    # # === 5. Memory Usage Over Time ===
    # plt.figure(figsize=(12, 6))
    # plt.plot(merged_df['time_s'], merged_df['rss_mb'], label='CPU RSS (MB)', linewidth=2, color='#3498db')
    # plt.plot(merged_df['time_s'], merged_df['mem_used_MiB'], label='GPU Memory (MiB)', linewidth=2, color='#2ecc71')
    # plt.xlabel('Time (seconds)')
    # plt.ylabel('Memory Usage (MB/MiB)')
    # plt.xlim(left=0)  # Force x-axis to start at 0
    # plt.title(f'{title} - Memory Usage Over Time')
    # plt.legend()
    # plt.grid(True, alpha=0.3)
    # plt.tight_layout()
    # plt.savefig(f'{output_prefix}_5_memory_usage.png', dpi=150)
    # print(f"✓ Saved: {output_prefix}_5_memory_usage.png")
    # plt.close()
    
    # === 6. Summary Statistics ===
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.axis('tight')
    ax.axis('off')
    
    stats_data = [
        ['Metric', 'CPU', 'GPU', 'Total'],
        ['Average Power (W)', f"{merged_df['power_w_cpu'].mean():.2f}", 
         f"{merged_df['power_w_gpu'].mean():.2f}", 
         f"{merged_df['total_power_w'].mean():.2f}"],
        ['Peak Power (W)', f"{merged_df['power_w_cpu'].max():.2f}", 
         f"{merged_df['power_w_gpu'].max():.2f}", 
         f"{merged_df['total_power_w'].max():.2f}"],
        ['Total Energy (J)', f"{cpu_total_energy:.2f}", 
         f"{gpu_total_energy:.2f}", 
         f"{total_energy:.2f}"],
        ['Total Energy (Wh)', f"{cpu_total_energy/3600:.4f}", 
         f"{gpu_total_energy/3600:.4f}", 
         f"{total_energy/3600:.4f}"],
        ['Avg Utilization (%)', f"{merged_df['cpu_percent'].mean():.1f}", 
         f"{merged_df['gpu_util_percent'].mean():.1f}", 
         'N/A'],
        ['Peak Utilization (%)', f"{merged_df['cpu_percent'].max():.1f}", 
         f"{merged_df['gpu_util_percent'].max():.1f}", 
         'N/A'],
        ['Avg Memory (MB/MiB)', f"{merged_df['rss_mb'].mean():.1f}", 
         f"{merged_df['mem_used_MiB'].mean():.1f}", 
         'N/A'],
        ['Peak Memory (MB/MiB)', f"{merged_df['rss_mb'].max():.1f}", 
         f"{merged_df['mem_used_MiB'].max():.1f}", 
         'N/A'],
        ['Avg GPU Temp (°C)', 'N/A', 
         f"{gpu_df['temp_c'].mean():.1f}", 
         'N/A'],
        ['Peak GPU Temp (°C)', 'N/A', 
         f"{gpu_df['temp_c'].max():.1f}", 
         'N/A'],
        ['Duration (s)', f"{(merged_df['ts'].max() - merged_df['ts'].min()).total_seconds():.1f}", 
         '', ''],
    ]
    
    table = ax.table(cellText=stats_data, cellLoc='center', loc='center',
                     colWidths=[0.3, 0.2, 0.2, 0.2])
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 2)
    
    # Style header row
    for i in range(4):
        table[(0, i)].set_facecolor('#34495e')
        table[(0, i)].set_text_props(weight='bold', color='white')
    
    # Alternate row colors
    for i in range(1, len(stats_data)):
        for j in range(4):
            if i % 2 == 0:
                table[(i, j)].set_facecolor('#ecf0f1')
    
    plt.title(f'{title} - Summary Statistics', fontsize=14, weight='bold', pad=20)
    plt.tight_layout()
    plt.savefig(f'{output_prefix}_6_summary_statistics.png', dpi=150, bbox_inches='tight')
    print(f"✓ Saved: {output_prefix}_6_summary_statistics.png")
    plt.close()

def generate_comparison_plots(all_experiments):
    """Generate comparison plots across all JIT profiles."""
    
    profile_colors = ['#95a5a6', '#e74c3c', '#3498db', '#f39c12']  # Gray for baseline, colors for others
    
    # Sort to ensure baseline is first
    profiles = sorted(all_experiments.keys(), key=lambda x: (x != 'baseline', x))
    
    # === COMPARISON 1: Total Energy by Profile ===
    fig, ax = plt.subplots(figsize=(12, 7))
    
    cpu_energies = []
    gpu_energies = []
    total_energies = []
    
    for profile_name in profiles:
        merged_df, _, _ = all_experiments[profile_name]
        cpu_e = merged_df['energy_j_total_cpu'].iloc[-1]
        gpu_e = merged_df['energy_j_total_gpu'].iloc[-1]
        cpu_energies.append(cpu_e)
        gpu_energies.append(gpu_e)
        total_energies.append(cpu_e + gpu_e)
    
    x = np.arange(len(profiles))
    width = 0.25
    
    bars1 = ax.bar(x - width, cpu_energies, width, label='CPU', color='#3498db', alpha=0.8)
    bars2 = ax.bar(x, gpu_energies, width, label='GPU', color='#2ecc71', alpha=0.8)
    bars3 = ax.bar(x + width, total_energies, width, label='Total', color='#34495e', alpha=0.8)
    
    # Add value labels
    for bars in [bars1, bars2, bars3]:
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.0f}J',
                    ha='center', va='bottom', fontsize=9)
    
    ax.set_xlabel('JIT Profile')
    ax.set_ylabel('Total Energy (J)')
    ax.set_title('Energy Consumption Comparison: Baseline vs C1-only vs C2-only')
    ax.set_xticks(x)
    ax.set_xticklabels(profiles)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig('comparison_1_total_energy.png', dpi=150)
    print("✓ Saved: comparison_1_total_energy.png")
    plt.close()
    
    # === COMPARISON 2: Average Power by Profile ===
    fig, ax = plt.subplots(figsize=(12, 7))
    
    avg_cpu_power = []
    avg_gpu_power = []
    avg_total_power = []
    
    for profile_name in profiles:
        merged_df, _, _ = all_experiments[profile_name]
        avg_cpu_power.append(merged_df['power_w_cpu'].mean())
        avg_gpu_power.append(merged_df['power_w_gpu'].mean())
        avg_total_power.append(merged_df['total_power_w'].mean())
    
    bars1 = ax.bar(x - width, avg_cpu_power, width, label='CPU', color='#3498db', alpha=0.8)
    bars2 = ax.bar(x, avg_gpu_power, width, label='GPU', color='#2ecc71', alpha=0.8)
    bars3 = ax.bar(x + width, avg_total_power, width, label='Total', color='#34495e', alpha=0.8)
    
    # Add value labels
    for bars in [bars1, bars2, bars3]:
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.1f}W',
                    ha='center', va='bottom', fontsize=9)
    
    ax.set_xlabel('JIT Profile')
    ax.set_ylabel('Average Power (W)')
    ax.set_title('Average Power Consumption: Baseline vs C1-only vs C2-only')
    ax.set_xticks(x)
    ax.set_xticklabels(profiles)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig('comparison_2_avg_power.png', dpi=150)
    print("✓ Saved: comparison_2_avg_power.png")
    plt.close()

    # === COMPARISON 3: Power Over Time (All Profiles) ===
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 12))
    
    for i, profile_name in enumerate(profiles):
        merged_df, _, _ = all_experiments[profile_name]
        color = profile_colors[i % len(profile_colors)]
        
        # Normalize time to start at 0
        merged_df['time_s'] = (merged_df['ts'] - merged_df['ts'].min()).dt.total_seconds()
        
        ax1.plot(merged_df['time_s'], merged_df['power_w_cpu'], 
                label=profile_name, color=color, linewidth=2, alpha=0.8)
        ax2.plot(merged_df['time_s'], merged_df['power_w_gpu'], 
                label=profile_name, color=color, linewidth=2, alpha=0.8)
        ax3.plot(merged_df['time_s'], merged_df['total_power_w'], 
                label=profile_name, color=color, linewidth=2, alpha=0.8)

        # Add average lines
        avg_power_cpu = merged_df['power_w_cpu'].mean()
        avg_power_gpu = merged_df['power_w_gpu'].mean()
        avg_power_total = merged_df['total_power_w'].mean()
        ax1.axhline(y=avg_power_cpu, linestyle='--', alpha=0.7, color=color, label=f'Avg CPU: {avg_power_cpu:.1f} W')
        ax2.axhline(y=avg_power_gpu, linestyle='--', alpha=0.7, color=color, label=f'Avg GPU: {avg_power_gpu:.1f} W')
        ax3.axhline(y=avg_power_total, linestyle='--', alpha=0.7, color=color, label=f'Avg Total: {avg_power_total:.1f} W')
    
    ax1.set_ylabel('CPU Power (W)')
    ax1.set_title('CPU Power Comparison: Baseline vs C1-only vs C2-only')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.set_xlim(left=0)
    
    ax2.set_ylabel('GPU Power (W)')
    ax2.set_title('GPU Power Comparison: Baseline vs C1-only vs C2-only')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    ax2.set_xlim(left=0)
    
    ax3.set_xlabel('Time (seconds)')
    ax3.set_ylabel('Total Power (W)')
    ax3.set_title('Total Power Comparison: Baseline vs C1-only vs C2-only')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    ax3.set_xlim(left=0)
    
    plt.tight_layout()
    plt.savefig('comparison_3_power_over_time.png', dpi=150)
    print("✓ Saved: comparison_3_power_over_time.png")
    plt.close()
    
    
    # === COMPARISON 4: Performance Metrics Summary Table ===
    fig, ax = plt.subplots(figsize=(14, 8))
    ax.axis('tight')
    ax.axis('off')
    
    table_data = [['Metric'] + profiles]
    
    # Total Energy
    table_data.append(['Total Energy (J)'] + [f"{e:.1f}" for e in total_energies])
    table_data.append(['Total Energy (Wh)'] + [f"{e/3600:.4f}" for e in total_energies])
    
    # Average Power
    table_data.append(['Avg Total Power (W)'] + [f"{p:.2f}" for p in avg_total_power])
    table_data.append(['Avg CPU Power (W)'] + [f"{p:.2f}" for p in avg_cpu_power])
    table_data.append(['Avg GPU Power (W)'] + [f"{p:.2f}" for p in avg_gpu_power])
    
    # Utilization
    avg_cpu_util = [all_experiments[p][0]['cpu_percent'].mean() for p in profiles]
    avg_gpu_util = [all_experiments[p][0]['gpu_util_percent'].mean() for p in profiles]
    table_data.append(['Avg CPU Util (%)'] + [f"{u:.1f}" for u in avg_cpu_util])
    table_data.append(['Avg GPU Util (%)'] + [f"{u:.1f}" for u in avg_gpu_util])
    
    # Temperature
    avg_temps = [all_experiments[p][2]['temp_c'].mean() for p in profiles]
    max_temps = [all_experiments[p][2]['temp_c'].max() for p in profiles]
    table_data.append(['Avg GPU Temp (°C)'] + [f"{t:.1f}" for t in avg_temps])
    table_data.append(['Max GPU Temp (°C)'] + [f"{t:.1f}" for t in max_temps])
    
    # Duration
    durations = [(all_experiments[p][0]['ts'].max() - all_experiments[p][0]['ts'].min()).total_seconds() 
                 for p in profiles]
    table_data.append(['Duration (s)'] + [f"{d:.1f}" for d in durations])
    
    # Energy efficiency (J/s)
    efficiency = [total_energies[i] / durations[i] for i in range(len(profiles))]
    table_data.append(['Energy/Time (W)'] + [f"{e:.2f}" for e in efficiency])
    
    table = ax.table(cellText=table_data, cellLoc='center', loc='center',
                     colWidths=[0.25] + [0.75/len(profiles)]*len(profiles))
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 2)
    
    # Style header row
    for i in range(len(profiles) + 1):
        table[(0, i)].set_facecolor('#34495e')
        table[(0, i)].set_text_props(weight='bold', color='white')
    
    # Style metric column
    for i in range(1, len(table_data)):
        table[(i, 0)].set_facecolor('#95a5a6')
        table[(i, 0)].set_text_props(weight='bold')
    
    # Alternate row colors
    for i in range(1, len(table_data)):
        for j in range(1, len(profiles) + 1):
            if i % 2 == 0:
                table[(i, j)].set_facecolor('#ecf0f1')
    
    plt.title('JIT Profile Performance Comparison - Summary Metrics', 
              fontsize=14, weight='bold', pad=20)
    plt.tight_layout()
    plt.savefig('comparison_4_summary_table.png', dpi=150, bbox_inches='tight')
    print("✓ Saved: comparison_4_summary_table.png")
    plt.close()
    
    # === COMPARISON 5: Normalized Energy Comparison (Bar Chart) ===
    fig, ax = plt.subplots(figsize=(12, 8))
    
    # Find baseline energy for normalization
    baseline_idx = profiles.index('baseline')
    baseline_energy = total_energies[baseline_idx]
    
    # Remove baseline from the comparison, only show c1-only and c2-only
    comparison_profiles = [p for p in profiles if p != 'baseline']
    comparison_energies = [total_energies[i] for i, p in enumerate(profiles) if p != 'baseline']
    
    # Calculate percentage difference from baseline
    energy_diff_pct = [((e - baseline_energy) / baseline_energy) * 100 for e in comparison_energies]
    
    # Create positions: baseline in middle, others on sides
    positions = []
    labels = []
    energies_to_plot = []
    colors_for_bars = []
    
    # Determine positioning based on number of comparison profiles
    n_comparisons = len(comparison_profiles)
    if n_comparisons == 2:
        # c1 on left, baseline in middle, c2 on right
        positions = [0, 1.5, 3]
        labels = [comparison_profiles[0], 'baseline', comparison_profiles[1]]
        energies_to_plot = [comparison_energies[0], baseline_energy, comparison_energies[1]]
        
        # Colors: green if better than baseline, red if worse, gray for baseline
        colors_for_bars = []
        for i, label in enumerate(labels):
            if label == 'baseline':
                colors_for_bars.append('#95a5a6')
            elif energies_to_plot[i] < baseline_energy:
                colors_for_bars.append('#2ecc71')  # Green for better
            else:
                colors_for_bars.append('#e74c3c')  # Red for worse
    else:
        # Baseline in middle, others distributed around
        mid = n_comparisons // 2
        positions = list(range(n_comparisons + 1))
        positions.insert(mid, mid + 0.5)
        labels = comparison_profiles[:mid] + ['baseline'] + comparison_profiles[mid:]
        energies_to_plot = comparison_energies[:mid] + [baseline_energy] + comparison_energies[mid:]
        
        colors_for_bars = []
        for i, label in enumerate(labels):
            if label == 'baseline':
                colors_for_bars.append('#95a5a6')
            elif energies_to_plot[i] < baseline_energy:
                colors_for_bars.append('#2ecc71')
            else:
                colors_for_bars.append('#e74c3c')
    
    bars = ax.bar(positions, energies_to_plot, color=colors_for_bars, alpha=0.8, width=0.8)
    
    # Add value labels with percentage difference
    for i, (bar, label) in enumerate(zip(bars, labels)):
        height = bar.get_height()
        if label == 'baseline':
            label_text = f'{height:.0f} J\n(baseline)'
        else:
            pct_diff = ((height - baseline_energy) / baseline_energy) * 100
            label_text = f'{height:.0f} J\n({pct_diff:+.1f}%)'
        
        ax.text(bar.get_x() + bar.get_width()/2., height,
                label_text, ha='center', va='bottom', fontsize=11, fontweight='bold')
    
    # Add a horizontal line at baseline level
    ax.axhline(y=baseline_energy, color='black', linestyle='--', linewidth=2, 
               alpha=0.5, label=f'Baseline Level ({baseline_energy:.0f} J)')
    
    ax.set_ylabel('Total Energy Consumption (J)', fontsize=12)
    ax.set_xlabel('JIT Profile', fontsize=12)
    ax.set_title('Energy Consumption Comparison: Baseline vs C1-only vs C2-only', 
                 fontsize=14, fontweight='bold')
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, fontsize=11)
    ax.legend(fontsize=10)
    ax.grid(axis='y', alpha=0.3)
    
    # Add text box with summary
    best_profile = labels[energies_to_plot.index(min(energies_to_plot))]
    worst_profile = labels[energies_to_plot.index(max(energies_to_plot))]
    best_savings = ((baseline_energy - min(energies_to_plot)) / baseline_energy) * 100
    worst_increase = ((max(energies_to_plot) - baseline_energy) / baseline_energy) * 100
    
    summary_text = f'Best: {best_profile} ({best_savings:.1f}% savings)\n'
    if worst_increase > 0:
        summary_text += f'Worst: {worst_profile} ({worst_increase:.1f}% increase)'
    
    ax.text(0.02, 0.98, summary_text, transform=ax.transAxes,
            fontsize=10, verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    plt.tight_layout()
    plt.savefig('comparison_5_energy_vs_baseline.png', dpi=150)
    print("✓ Saved: comparison_5_energy_vs_baseline.png")
    plt.close()

def main():
    ap = argparse.ArgumentParser(description='Visualize and compare JIT profile experiments')
    ap.add_argument("--runs-dir", default="./runs",
                    help="Directory containing run subdirectories (default: ./runs)")
    ap.add_argument("--output-dir", default="./plots",
                    help="Output directory for plots (default: ./plots)")
    args = ap.parse_args()
    
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)
    
    # Find all top-level experiment directories (e.g., 'runs/baseline_*')
    run_dirs = [d for d in glob.glob(os.path.join(args.runs_dir, '*')) if os.path.isdir(d)]
    
    if not run_dirs:
        print(f"Error: No run directories found in {args.runs_dir}")
        return
    
    print("="*60)
    print("Found run directories:")
    for run_dir in run_dirs:
        print(f"  - {os.path.basename(run_dir)}")
    print("="*60)
    
    all_experiments = {}
    
    # Process each experiment profile
    for run_dir in run_dirs:
        dir_name = os.path.basename(run_dir)
        profile_name = dir_name.split('_')[0]
        
        print(f"\nProcessing Profile: {profile_name.upper()} from {dir_name}...")
        
        try:
            # Step 1: Find all iteration files for this profile using a recursive glob
            cpu_files = glob.glob(os.path.join(run_dir, '**', 'monitor_iter.csv'), recursive=True)
            gpu_files = glob.glob(os.path.join(run_dir, '**', 'gpu_monitor_iter.csv'), recursive=True)

            if not cpu_files or not gpu_files:
                print(f"  --> SKIPPING '{profile_name}': Could not find monitor files.")
                continue

            # Step 2: Average the data from all iterations
            avg_cpu_df = average_csv_files(cpu_files, file_type='CPU')
            avg_gpu_df = average_csv_files(gpu_files, file_type='GPU')

            # Step 3: Merge the two averaged dataframes
            merged_df = merge_dataframes(avg_cpu_df, avg_gpu_df, profile_name)
            
            # Step 4: Store the results for plotting
            # We store the averaged dataframes, which replace the old single-run dataframes
            all_experiments[profile_name] = (merged_df, avg_cpu_df, avg_gpu_df)
            
            # Generate individual plots using the newly averaged & merged data
            print(f"  Generating plots for {profile_name}...")
            output_prefix = os.path.join(args.output_dir, profile_name)
            generate_single_experiment_plots(
                merged_df, avg_cpu_df, avg_gpu_df, 
                profile_name, 
                output_prefix
            )
        except Exception as e:
            print(f"  Error processing {profile_name}: {e}")
            continue
    
    if len(all_experiments) < 2:
        print("\nWarning: Need at least 2 profiles for comparison plots. Processing finished.")
        return
    
    print("\n" + "="*60)
    print("Generating comparison plots...")
    print("="*60)
    
    os.chdir(args.output_dir)
    generate_comparison_plots(all_experiments)
    
    print("\n" + "="*60)
    print(f"All plots generated successfully in {args.output_dir}!")
    print("="*60)

if __name__ == "__main__":
    main()
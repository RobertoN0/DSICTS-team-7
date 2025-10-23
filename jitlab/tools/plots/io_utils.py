import pandas as pd
import numpy as np

# conversione MB <-> MiB
_MB_PER_MIB = 1.048576
def mb_to_mib(x): return x / _MB_PER_MIB
def mib_to_mb(x): return x * _MB_PER_MIB

def to_datetime_series(ts_series):
    """Return a datetime series regardless of the input format."""
    if pd.api.types.is_datetime64_any_dtype(ts_series):
        return ts_series
    try:
        return pd.to_datetime(ts_series, unit='s', errors='coerce')
    except Exception:
        return pd.to_datetime(ts_series, errors='coerce')

def unify_memory_units_cpu(df, canonical_mem_unit):
    """
    Normalize CPU RAM in the DF:
      - if canonical = "MiB" -> create/use 'rss_mib'
      - if canonical = "MB"  -> create/use 'rss_mb'
    """
    df = df.copy()
    u = (canonical_mem_unit or "MiB").lower()
    if u == "mib":
        if 'rss_mib' in df.columns:
            df['rss_mib'] = df['rss_mib'].astype(float)
        elif 'rss_mb' in df.columns:
            df['rss_mib'] = mb_to_mib(df['rss_mb'].astype(float))
    else:
        if 'rss_mb' in df.columns:
            df['rss_mb'] = df['rss_mb'].astype(float)
        elif 'rss_mib' in df.columns:
            df['rss_mb'] = mib_to_mb(df['rss_mib'].astype(float))
    return df

def unify_memory_units_gpu(df, canonical_mem_unit):
    """
    Normalize GPU VRAM in the DF:
      - if canonical = "MiB" -> create/use 'mem_used_mib'
      - if canonical = "MB"  -> create/use 'mem_used_mb'
    """
    df = df.copy()
    u = (canonical_mem_unit or "MiB").lower()
    if u == "mib":
        if 'mem_used_mib' in df.columns:
            df['mem_used_mib'] = df['mem_used_mib'].astype(float)
        elif 'mem_used_MiB' in df.columns:
            df['mem_used_mib'] = df['mem_used_MiB'].astype(float)
        elif 'mem_used_mb' in df.columns:
            df['mem_used_mib'] = mb_to_mib(df['mem_used_mb'].astype(float))
    else:
        if 'mem_used_mb' in df.columns:
            df['mem_used_mb'] = df['mem_used_mb'].astype(float)
        elif 'mem_used_MiB' in df.columns:
            df['mem_used_mb'] = mib_to_mb(df['mem_used_MiB'].astype(float))
        elif 'mem_used_mib' in df.columns:
            df['mem_used_mb'] = mib_to_mb(df['mem_used_mib'].astype(float))
    return df

def get_cpu_mem_col(cpu_df, canonical_mem_unit):
    """Return (column_name, label) for CPU RAM based on the canonical unit."""
    u = (canonical_mem_unit or "MiB").lower()
    if u == "mib":
        if 'rss_mib' in cpu_df.columns:
            return 'rss_mib', 'CPU RAM (MiB)'
    else:
        if 'rss_mb' in cpu_df.columns:
            return 'rss_mb', 'CPU RAM (MB)'
    return None, 'CPU RAM'

def get_gpu_mem_col(gpu_df, canonical_mem_unit):
    """Return (column_name, label) for GPU VRAM based on the canonical unit."""
    u = (canonical_mem_unit or "MiB").lower()
    if u == "mib":
        if 'mem_used_mib' in gpu_df.columns:
            return 'mem_used_mib', 'GPU VRAM (MiB)'
    else:
        if 'mem_used_mb' in gpu_df.columns:
            return 'mem_used_mb', 'GPU VRAM (MB)'
    return None, 'GPU VRAM'

def average_csv_files(file_paths, file_type='CPU'):
    """
    Load multiple CSV files and compute row-wise average.
    Assumes same structure and same number of rows for each file.
    Generates uniform 'ts' at 1s.
    """
    if not file_paths:
        raise ValueError(f"File paths list for {file_type} is empty.")
    df_list = [pd.read_csv(f) for f in file_paths]

    num_rows = len(df_list[0])
    if not all(len(df) == num_rows for df in df_list):
        row_counts = [len(df) for df in df_list]
        raise ValueError(f"All CSV files must have the same number of rows. Found counts: {row_counts}")

    start_ts = to_datetime_series(df_list[0]['ts']).iloc[0]
    new_ts = pd.date_range(start=start_ts, periods=num_rows, freq='1s')

    data_cols = [c for c in df_list[0].columns if c != 'ts']
    data_arrays = [df[data_cols].to_numpy() for df in df_list]
    averaged = np.mean(np.stack(data_arrays, axis=0), axis=0)

    out = pd.DataFrame(averaged, columns=data_cols)
    out.insert(0, 'ts', new_ts)
    return out

def merge_dataframes(cpu_df, gpu_df, profile_name):
    """
    Merge CPU and GPU dataframes on 'ts' using nearest merge within 1s tolerance.
    Adds 'total_power_w' if both power columns are present.
    """
    cpu_df = cpu_df.copy()
    gpu_df = gpu_df.copy()
    cpu_df['ts'] = to_datetime_series(cpu_df['ts'])
    gpu_df['ts'] = to_datetime_series(gpu_df['ts'])
    cpu_df = cpu_df.sort_values('ts').reset_index(drop=True)
    gpu_df = gpu_df.sort_values('ts').reset_index(drop=True)

    merged_df = pd.merge_asof(
        cpu_df, gpu_df, on='ts',
        direction='nearest', tolerance=pd.Timedelta('1s'),
        suffixes=('_cpu', '_gpu')
    ).ffill().bfill()

    if 'power_w_cpu' in merged_df.columns and 'power_w_gpu' in merged_df.columns:
        merged_df['total_power_w'] = merged_df['power_w_cpu'] + merged_df['power_w_gpu']

    merged_df['profile'] = profile_name
    return merged_df

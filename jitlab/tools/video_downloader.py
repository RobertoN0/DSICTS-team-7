#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scarica un video YouTube allA risoluzione specificata in formato MP4 **con audio**.
Strategia:
  1) Preferisce stream MP4 "adaptive" (video-only) alla/e risoluzione/i richiesta/e
     + migliore audio (m4a), poi unisce con ffmpeg in un unico .mp4.
  2) Se non trova MP4 adaptive, usa MP4 "progressive" (audio+video insieme) alla
     migliore risoluzione disponibile ≤ richiesta.
  3) Evita di restituire WebM come file finale (mantiene MP4).
Requisiti: ffmpeg nel PATH, pytubefix installato.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from pytubefix import YouTube


# ----------------------------- Utils ---------------------------------

def sanitize_filename(name: str) -> str:
    # Rimuove caratteri non validi per filesystem
    name = re.sub(r'[\\/*?:"<>|]+', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def res_to_int(res: Optional[str]) -> int:
    # "1080p" -> 1080, "0p"/None -> 0
    if not res or not res.endswith("p"):
        return 0
    try:
        return int(res[:-1])
    except ValueError:
        return 0


def ffmpeg_path() -> str:
    ff = shutil.which("ffmpeg")
    if not ff:
        raise EnvironmentError("ffmpeg non trovato nel PATH")
    return ff


# --------------------------- Listing (debug) ---------------------------

def list_streams(yt: YouTube) -> None:
    print(f"\nAvailable streams for: {yt.title}\n")
    for s in yt.streams.order_by('resolution').desc():
        info = {
            'itag': getattr(s, 'itag', None),
            'type': getattr(s, 'type', None),
            'mime_type': getattr(s, 'mime_type', None),
            'resolution': getattr(s, 'resolution', None),
            'fps': getattr(s, 'fps', None),
            'abr': getattr(s, 'abr', None),
            'is_progressive': getattr(s, 'is_progressive', False),
            'filesize_approx': getattr(s, 'filesize_approx', None)
        }
        print(info)
    print()


# ------------------------ Selezione degli stream ----------------------

def find_best_adaptive_mp4_video(yt: YouTube, desired_resolutions: List[str]):
    """
    Restituisce il miglior stream MP4 adaptive (video-only) alla prima
    risoluzione disponibile nella lista desiderata (in ordine di preferenza).
    Se nessuna corrisponde, restituisce il miglior MP4 adaptive <= max richiesto.
    """
    video_mp4 = [
        s for s in yt.streams.filter(adaptive=True, file_extension='mp4')
        if getattr(s, 'resolution', None)
    ]
    if not video_mp4:
        return None

    # Ordina tutti gli adaptive mp4 per risoluzione crescente
    video_mp4_sorted = sorted(video_mp4, key=lambda s: res_to_int(s.resolution))

    # 1) match esatto in ordine di preferenza (prima voce della lista ha max priorità)
    desired_order = [r if r.endswith("p") else f"{r}p" for r in desired_resolutions]
    for r in desired_order:
        for s in video_mp4_sorted:
            if s.resolution == r:
                return s

    # 2) fallback: migliore <= massima desiderata
    max_target = max((res_to_int(r) for r in desired_order), default=0)
    candidates = [s for s in video_mp4_sorted if res_to_int(s.resolution) <= max_target]
    return candidates[-1] if candidates else None


def find_best_progressive_mp4(yt: YouTube, desired_resolutions: List[str]):
    """
    Progressivo MP4 (audio+video insieme). Usa *solo* come fallback
    se non esistono adaptive mp4: prende il migliore ≤ risoluzione richiesta.
    """
    progs = [
        s for s in yt.streams.filter(progressive=True, file_extension='mp4')
        if getattr(s, 'resolution', None)
    ]
    if not progs:
        return None

    progs_sorted = sorted(progs, key=lambda s: res_to_int(s.resolution))
    desired_order = [r if r.endswith("p") else f"{r}p" for r in desired_resolutions]

    # match esatto
    for r in desired_order:
        for s in progs_sorted:
            if s.resolution == r:
                return s

    # migliore ≤ obiettivo massimo
    max_target = max((res_to_int(r) for r in desired_order), default=0)
    candidates = [s for s in progs_sorted if res_to_int(s.resolution) <= max_target]
    return candidates[-1] if candidates else progs_sorted[-1]


def find_best_audio_m4a(yt: YouTube):
    """Preferisce audio-only in contenitore mp4/m4a (AAC)."""
    audios = [s for s in yt.streams.filter(only_audio=True)]
    if not audios:
        return None
    # prefer audio/mp4 (m4a)
    m4a = [s for s in audios if 'audio/mp4' in (getattr(s, 'mime_type', '') or '').lower()]
    pool = m4a if m4a else audios
    # bitrate più alto
    def abr_kbps(s):
        abr = getattr(s, 'abr', '') or ''
        m = re.search(r'(\d+)\s*kbps', abr)
        return int(m.group(1)) if m else 0
    return sorted(pool, key=abr_kbps)[-1]


# ------------------------------ Merge ---------------------------------

def merge_with_ffmpeg(video_path: Path, audio_path: Path, out_path: Path) -> None:
    """
    Unisce video (mp4 video-only) + audio (m4a) in un unico MP4.
    -c:v copy mantiene il video intatto; l'audio lo riconverte in AAC per compatibilità.
    """
    ff = ffmpeg_path()
    cmd = [
        ff, "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


# ------------------------------ Download ------------------------------

def download(url: str, output_dir: str = "./videos",
             desired_resolutions: Optional[List[str]] = None) -> str:
    """
    Scarica MP4 con audio alla migliore risoluzione disponibile tra quelle desiderate.
    Ritorna il percorso del file MP4 finale.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    desired_resolutions = desired_resolutions or ["1080p", "720p", "480p", "360p"]

    yt = YouTube(url)
    title = sanitize_filename(yt.title)
    print(f"Title: {title}")

    # 1) Preferisci sempre ADAPTIVE MP4 (video-only) + audio → merge in MP4
    v = find_best_adaptive_mp4_video(yt, desired_resolutions)
    if v:
        print(f"Downloading adaptive MP4 video-only: itag={v.itag} res={v.resolution}")
        v_file = Path(v.download(output_path=output_dir))

        a = find_best_audio_m4a(yt)
        if not a:
            raise RuntimeError("Nessun audio-only trovato (m4a/AAC) per il merge.")
        print(f"Downloading audio-only: itag={a.itag} abr={a.abr}")
        a_file = Path(a.download(output_path=output_dir))

        merged = Path(output_dir) / f"{title}_{v.resolution}_merged.mp4"
        try:
            merge_with_ffmpeg(v_file, a_file, merged)
            print(f"Merged to {merged}")
            return str(merged)
        finally:
            # opzionale: lascia i sorgenti oppure pulisci
            pass

    # 2) Fallback: MP4 progressivo (audio+video insieme)
    print("⚠️  Nessun MP4 adaptive idoneo trovato: provo MP4 progressivo…")
    prog = find_best_progressive_mp4(yt, desired_resolutions)
    if prog:
        print(f"Downloading progressive MP4: itag={prog.itag} res={prog.resolution}")
        out_file = Path(prog.download(output_path=output_dir))
        print(f"Downloaded to {out_file}")
        return str(out_file)

    # 3) Nessun MP4 disponibile
    raise RuntimeError("Nessuno stream MP4 adatto trovato (né adaptive, né progressivo).")


# -------------------------------- CLI ---------------------------------

def build_desired_list(res_arg: str) -> List[str]:
    if res_arg.lower() == "highest":
        return ["2160p", "1440p", "1080p", "720p", "480p", "360p", "240p", "144p"]
    parts = [p.strip() for p in res_arg.split(",") if p.strip()]
    out = []
    for p in parts:
        out.append(p if p.endswith("p") else f"{p}p")
    # garantisci ordine dal più desiderato al meno desiderato
    return out


def main():
    ap = argparse.ArgumentParser(description="Scarica MP4 alla risoluzione specificata (con audio).")
    ap.add_argument("url", help="URL YouTube")
    ap.add_argument("--out", "-o", default="./videos", help="Cartella di output (default: ./videos)")
    ap.add_argument("--res", "--resolution", dest="resolution", default="1080p",
                    help="Risoluzione desiderata (es. 1080p) oppure lista separata da virgola (es. '1080p,720p') "
                         "oppure 'highest' per massima disponibile.")
    ap.add_argument("--list", action="store_true", help="Mostra gli stream disponibili e termina (debug).")
    args = ap.parse_args()

    yt = YouTube(args.url)

    if args.list:
        list_streams(yt)
        return

    desired = build_desired_list(args.resolution)
    try:
        final_file = download(args.url, output_dir=args.out, desired_resolutions=desired)
        print("Result file:", final_file)
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

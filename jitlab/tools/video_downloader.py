import argparse
import os
import shutil
import subprocess
import sys
from pytubefix import YouTube


def list_streams(yt):
    print(f"Available streams for: {yt.title}\n")
    for s in yt.streams.order_by('resolution').desc():
        # not all streams have resolution (audio-only)
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


def find_best_progressive_mp4(yt, desired_resolutions):
    # Try progressive MP4 first (contains audio+video)
    candidates = [s for s in yt.streams.filter(progressive=True, file_extension='mp4')]
    # Order by desired resolution
    for r in desired_resolutions[::-1]:
        for s in candidates:
            if getattr(s, 'resolution', None) == r:
                return s
    # fallback to highest resolution progressive mp4
    if candidates:
        return sorted(candidates, key=lambda s: int(getattr(s, 'resolution', '0p')[:-1]) if getattr(s, 'resolution', None) else 0)[-1]
    return None


def find_best_adaptive_mp4(yt, desired_resolutions):
    # video-only mp4 streams
    video_mp4 = [s for s in yt.streams.filter(adaptive=True, file_extension='mp4') if getattr(s, 'resolution', None)]
    for r in desired_resolutions[::-1]:
        for s in video_mp4:
            if getattr(s, 'resolution', None) == r:
                return s
    if video_mp4:
        return sorted(video_mp4, key=lambda s: int(getattr(s, 'resolution', '0p')[:-1]))[-1]
    return None


def find_best_audio(yt):
    # prefer m4a/aac audio, then any audio
    audios = [s for s in yt.streams.filter(only_audio=True)]
    if not audios:
        return None
    # prefer file_extension mp4/m4a
    pref = [s for s in audios if getattr(s, 'abr', None) and getattr(s, 'mime_type', '').lower().find('audio/mp4') != -1]
    if pref:
        return sorted(pref, key=lambda s: int(getattr(s, 'abr', '0').replace('kbps', '').strip() or 0))[-1]
    return sorted(audios, key=lambda s: int(getattr(s, 'abr', '0').replace('kbps', '').strip() or 0))[-1]


def merge_with_ffmpeg(video_path, audio_path, out_path):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise EnvironmentError('ffmpeg not found on PATH')
    cmd = [ffmpeg, '-y', '-i', str(video_path), '-i', str(audio_path), '-c', 'copy', str(out_path)]
    subprocess.run(cmd, check=True)


def download(url, output_path='./videos', merge=False, desired_resolutions=None):
    os.makedirs(output_path, exist_ok=True)
    # desired_resolutions is a list ordered by preference, highest preference first
    desired_resolutions = desired_resolutions or ['2160p', '1440p', '1080p', '720p', '480p', '360p', '240p', '144p']

    yt = YouTube(url)
    print(f"Title: {yt.title}")
    list_streams(yt)

    # 1) try progressive mp4
    prog = find_best_progressive_mp4(yt, desired_resolutions)
    if prog:
        print(f"Downloading progressive MP4: itag={prog.itag} res={prog.resolution}")
        out_file = prog.download(output_path=output_path)
        print('Downloaded to', out_file)
        return out_file

    # 2) try adaptive mp4 (video-only) + audio
    v = find_best_adaptive_mp4(yt, desired_resolutions)
    a = find_best_audio(yt)
    if v and a:
        print(f"Downloading adaptive MP4 video-only: itag={v.itag} res={v.resolution}")
        v_file = v.download(output_path=output_path)
        print(f"Downloading audio-only: itag={a.itag} abr={a.abr}")
        a_file = a.download(output_path=output_path)
        # Derive merged filename
        base = os.path.splitext(os.path.basename(v_file))[0]
        merged = os.path.join(output_path, base + '_merged.mp4')
        if merge:
            try:
                merge_with_ffmpeg(v_file, a_file, merged)
                print('Merged to', merged)
                return merged
            except Exception as e:
                print('Failed to merge automatically:', e)
                print('Files saved as:', v_file, a_file)
                return v_file
        else:
            print('Downloaded video and audio separately; use ffmpeg to merge:')
            print(f"ffmpeg -i '{v_file}' -i '{a_file}' -c copy '{merged}'")
            return v_file

    # 3) fallback: allow webm
    print('No MP4 (progressive or adaptive) available. Falling back to best available stream (may be .webm).')
    all_streams = [s for s in yt.streams.filter(progressive=True)]
    if all_streams:
        best = all_streams[-1]
        out = best.download(output_path=output_path)
        print('Downloaded fallback stream to', out)
        return out

    raise RuntimeError('No downloadable streams found')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('url', nargs='?', default='https://www.youtube.com/watch?v=LXb3EKWsInQ', help='YouTube video URL')
    p.add_argument('--out', '-o', default='./videos', help='Output directory')
    p.add_argument('--merge', action='store_true', help='If adaptive streams are downloaded, attempt to merge with ffmpeg')
    p.add_argument('--list', action='store_true', help='Only list streams and exit')
    p.add_argument('--res', '--resolution', dest='resolution', default='highest',
                   help="Desired resolution: 'highest' (default) or specify like '720p' or '1080p'. You can also pass a comma-separated list e.g. '1080p,720p' to prefer 1080 then 720.")
    args = p.parse_args()

    yt = YouTube(args.url)
    if args.list:
        list_streams(yt)
        return

    # Build desired_resolutions list from CLI option
    if args.resolution.lower() == 'highest':
        desired_res = ['2160p', '1440p', '1080p', '720p', '480p', '360p', '240p', '144p']
    else:
        # allow comma separated list or single resolution
        parts = [p.strip() for p in args.resolution.split(',') if p.strip()]
        # normalize entries to end with 'p' if numeric
        desired_res = []
        for p in parts:
            if p.isdigit():
                desired_res.append(p + 'p')
            else:
                desired_res.append(p)

    try:
        result = download(args.url, output_path=args.out, merge=args.merge, desired_resolutions=desired_res)
        print('Result file:', result)
    except Exception as e:
        print('Error:', e, file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()



#python tools/video_downloader.py 'https://www.youtube.com/watch?v=8dQx3yZRUm4' --out ./videos
#curl -i -F "file=@/videos/MILAN-NAPOLI 2-1 | HIGHLIGHTS | Milan is back on top of the table! | SERIE A 202526.mp4" http://localhost:8080/videos/upload
#!/usr/bin/env python3
"""Assemble the narrated slide preview; refuses to overwrite an existing video."""
import json
from pathlib import Path
import re
import subprocess
import sys
import wave

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "demo"


def wav_seconds(path):
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def srt_timestamp(seconds):
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def caption_chunks(text, limit=24):
    pieces = re.findall(r"[^，。；！？：]+[，。；！？：]?", text)
    chunks = []
    current = ""
    for piece in pieces:
        if current and len(current) + len(piece) > limit:
            chunks.append(current)
            current = ""
        while len(piece) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(piece[:limit])
            piece = piece[limit:]
        current += piece
    if current:
        chunks.append(current)
    return chunks


def write_subtitles(storyboard, path):
    entries = []
    segment_start = 0.0
    number = 1
    for item in storyboard:
        audio = DEMO / "build/narration" / f"{item['id']}.wav"
        audio_duration = wav_seconds(audio)
        chunks = caption_chunks(item["narration"])
        weights = [len(re.sub(r"[\s，。；！？：、,.]", "", chunk)) + 2 for chunk in chunks]
        cursor = segment_start
        for index, (chunk, weight) in enumerate(zip(chunks, weights)):
            if index == len(chunks) - 1:
                end = segment_start + audio_duration
            else:
                end = cursor + audio_duration * weight / sum(weights)
            entries.append(
                f"{number}\n{srt_timestamp(cursor)} --> {srt_timestamp(end)}\n{chunk}\n")
            number += 1
            cursor = end
        segment_start += audio_duration + 0.8
    path.write_text("\n".join(entries), encoding="utf-8-sig")


def probe_seconds(ffprobe, path):
    result = subprocess.run(
        [str(ffprobe), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, text=True, encoding="utf-8", capture_output=True)
    return float(result.stdout.strip())


def build_video_segment(ffmpeg, ffprobe, item, audio, segment, duration):
    source = ROOT / item["video"]
    if not source.is_file():
        raise SystemExit(f"missing footage for {item['id']}: {source}")
    source_duration = probe_seconds(ffprobe, source)
    pad = duration - source_duration
    chain = (
        "fps=30,split=2[bg][fg];"
        "[bg]scale=1920:1080:force_original_aspect_ratio=increase,"
        "crop=1920:1080,boxblur=25:2[bgc];"
        "[fg]scale=1920:1080:force_original_aspect_ratio=decrease[fgc];"
        "[bgc][fgc]overlay=(W-w)/2:(H-h)/2"
    )
    if pad > 0:
        chain += f",tpad=stop_mode=clone:stop_duration={pad + 0.5:.3f}"
    fade_out = max(0.0, duration - 0.3)
    chain += (f",fade=t=in:st=0:d=0.25,fade=t=out:st={fade_out:.3f}:d=0.3,"
              "format=yuv420p")
    subprocess.run([
        str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(source), "-i", str(audio),
        "-t", f"{duration:.3f}",
        "-filter_complex",
        f"[0:v]{chain}[v];[1:a]apad=pad_dur=0.8,aresample=48000[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-threads", "4",
        "-r", "30", "-fps_mode", "cfr", "-video_track_timescale", "90000",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-shortest",
        "-movflags", "+faststart", str(segment),
    ], check=True)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: build_preview.py FFMPEG OUTPUT_MP4")
    ffmpeg = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite {output}")
    storyboard = json.loads((DEMO / "storyboard.json").read_text(encoding="utf-8"))
    segments = DEMO / "build/segments"
    segments.mkdir(parents=True, exist_ok=True)
    concat_lines = []
    total = 0.0
    ffprobe = ffmpeg.with_name("ffprobe.exe")
    for item in storyboard:
        audio = DEMO / "build/narration" / f"{item['id']}.wav"
        if not audio.is_file():
            raise SystemExit(f"missing narration for {item['id']}")
        duration = wav_seconds(audio) + 0.8
        total += duration
        segment = segments / f"{item['id']}.mp4"
        if "video" in item:
            build_video_segment(ffmpeg, ffprobe, item, audio, segment, duration)
        else:
            slide = DEMO / "build/slides" / f"{item['id']}.png"
            if not slide.is_file():
                raise SystemExit(f"missing slide for {item['id']}")
            fade_out = max(0.0, duration - 0.3)
            subprocess.run([
                str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
                "-loop", "1", "-framerate", "30", "-i", str(slide), "-i", str(audio),
                "-t", f"{duration:.3f}",
                "-vf", f"scale=1920:1080,format=yuv420p,fade=t=in:st=0:d=0.25,fade=t=out:st={fade_out:.3f}:d=0.3",
                "-af", "apad=pad_dur=0.8",
                "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-threads", "4",
                "-r", "30", "-fps_mode", "cfr", "-video_track_timescale", "90000",
                "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-shortest",
                "-movflags", "+faststart", str(segment),
            ], check=True)
        concat_lines.append(f"file '{segment.name}'")
        print(f"SEGMENT {item['id']} {duration:.2f}s")
    if total > 590:
        raise SystemExit(f"preview is too long: {total:.1f}s")
    concat = segments / "concat.txt"
    concat.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
    subtitles = DEMO / "build/subtitles.srt"
    write_subtitles(storyboard, subtitles)
    inputs = []
    for item in storyboard:
        inputs += ["-i", str(segments / f"{item['id']}.mp4")]
    subtitle_filter = (
        "fps=30,setpts=PTS-STARTPTS,"
        "subtitles=subtitles.srt:"
        "force_style='FontName=Microsoft YaHei,FontSize=11,"
        "PrimaryColour=&H00FFFFFF,BackColour=&H80000000,"
        "BorderStyle=3,Outline=0.5,Shadow=0,Alignment=2,"
        "MarginL=25,MarginR=25,MarginV=12',format=yuv420p"
    )
    count = len(storyboard)
    subprocess.run([
        str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", *inputs,
        "-filter_complex",
        f"concat=n={count}:v=1:a=1[v0][a0];"
        f"[v0]{subtitle_filter}[v];"
        "[a0]aresample=48000,volume=3dB,asetpts=PTS-STARTPTS[a]",
        "-map", "[v]", "-map", "[a]",
        "-filter_threads", "1",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-threads", "2",
        "-profile:v", "high", "-level:v", "4.1", "-r", "30",
        "-fps_mode", "cfr", "-video_track_timescale", "90000",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", str(output),
    ], cwd=DEMO / "build", check=True)
    size_mb = output.stat().st_size / 1_000_000
    if size_mb >= 100:
        raise SystemExit(f"preview is too large: {size_mb:.1f} MB")
    print(f"PREVIEW_OK duration={total:.1f}s size={size_mb:.1f}MB path={output}")


if __name__ == "__main__":
    main()

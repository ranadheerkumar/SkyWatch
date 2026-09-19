from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Literal

VoiceGender = Literal["male", "female"]

VOICE_HINTS: dict[VoiceGender, re.Pattern[str]] = {
    "male": re.compile(r"\b(male|man|david|mark|george|james|daniel|guy|ryan|alex|fred|tom|lee|matthew|jason|thomas)\b|\+m", re.IGNORECASE),
    "female": re.compile(r"\b(female|woman|zira|hazel|susan|aria|jenny|samantha|victoria|karen|sara|sarah|ava|emma|allison|joanna|linda|kate|moira|fiona|veena|tessa|serena)\b|\+f", re.IGNORECASE),
}


def _safe_narration_text(value: str) -> str:
    safe_value = re.sub(r"https?://\S+", "target URL", value, flags=re.IGNORECASE)
    safe_value = re.sub(r"\[redacted\]", "protected value", safe_value, flags=re.IGNORECASE)
    safe_value = re.sub(r"\b(password|secret|token|api key)\b[^.;,\n]*", "protected credential", safe_value, flags=re.IGNORECASE)
    safe_value = re.sub(r"\b(?:label=|text=)", "", safe_value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", safe_value).strip()[:4_000]


def build_execution_narration(target_url: str, messages: list[str], status: str) -> str:
    step_messages = [
        message.strip()
        for message in messages
        if re.match(r"^Step\s+\d+(?:\s*(?:/|of)\s*\d+)?\s*:", message.strip(), re.IGNORECASE)
    ]
    return _safe_narration_text(" ".join(step_messages))


def _resolve_ffmpeg() -> str | None:
    configured_path = os.getenv("AI_QA_ENGINE_FFMPEG_PATH", "").strip()
    if configured_path and Path(configured_path).is_file():
        return configured_path

    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, OSError, RuntimeError):
        return None


def _select_voice(engine, gender: VoiceGender) -> None:
    voices = engine.getProperty("voices") or []
    matching_voice = next(
        (
            voice
            for voice in voices
            if VOICE_HINTS[gender].search(
                " ".join(
                    str(getattr(voice, attribute, ""))
                    for attribute in ("id", "name", "gender", "languages")
                )
            )
        ),
        None,
    )
    if matching_voice is not None:
        engine.setProperty("voice", matching_voice.id)


def _probe_video_duration(ffmpeg_path: str, video_path: Path) -> float:
    probe = subprocess.run(
        [ffmpeg_path, "-hide_banner", "-i", str(video_path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", probe.stderr or "")
    if not match:
        raise RuntimeError("Unable to determine the recorded video duration")
    hours, minutes, seconds = match.groups()
    return max(0.1, (int(hours) * 3600) + (int(minutes) * 60) + float(seconds))


def create_video_with_audio(
    video_path: Path,
    narration: str,
    voice_gender: VoiceGender,
) -> Path:
    if not video_path.is_file():
        raise FileNotFoundError(f"Recorded video was not found: {video_path.name}")
    if not narration.strip():
        raise ValueError("Execution narration is empty")

    ffmpeg_path = _resolve_ffmpeg()
    if not ffmpeg_path:
        raise RuntimeError("FFmpeg is not installed or AI_QA_ENGINE_FFMPEG_PATH is not configured")

    try:
        import pyttsx3
    except ImportError as error:
        raise RuntimeError("pyttsx3 is not installed") from error

    audio_path = video_path.with_name(f"{video_path.stem}-narration.wav")
    output_path = video_path.with_name(f"{video_path.stem}-audio.webm")
    engine = None
    try:
        engine = pyttsx3.init()
        _select_voice(engine, voice_gender)
        engine.setProperty("rate", 165)
        engine.setProperty("volume", 1.0)
        engine.save_to_file(_safe_narration_text(narration), str(audio_path))
        engine.runAndWait()
        if not audio_path.is_file() or audio_path.stat().st_size == 0:
            raise RuntimeError("Text-to-speech did not produce an audio file")

        video_duration = _probe_video_duration(ffmpeg_path, video_path)
        command = [
            ffmpeg_path,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-filter_complex",
            "[1:a]apad[audio]",
            "-map",
            "0:v:0",
            "-map",
            "[audio]",
            "-c:v",
            "copy",
            "-c:a",
            "libopus",
            "-t",
            f"{video_duration:.3f}",
            "-metadata",
            "comment=AI QA Engine execution narration",
            str(output_path),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
        if completed.returncode != 0 or not output_path.is_file() or output_path.stat().st_size == 0:
            detail = (completed.stderr or "FFmpeg did not produce a narrated video.").strip()[-500:]
            raise RuntimeError(detail)
        return output_path
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    finally:
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                pass
        audio_path.unlink(missing_ok=True)
        if output_path.is_file() and output_path.stat().st_size == 0:
            output_path.unlink(missing_ok=True)

#!/usr/bin/env python3
"""
High-Quality Video Compressor
Uses FFmpeg with optimized settings for quality preservation.
"""

import os
import sys
import json
import subprocess
import argparse
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Literal
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class CompressionProfile:
    """Compression quality profiles"""
    name: str
    crf: int
    preset: str
    codec: str
    audio_bitrate: str
    max_width: Optional[int] = None
    max_height: Optional[int] = None
    fps: Optional[int] = None


PROFILES = {
    "ultra": CompressionProfile(
        name="ultra",
        crf=16,
        preset="veryslow",
        codec="libx264",
        audio_bitrate="320k",
        max_width=None,
        max_height=None
    ),
    "high": CompressionProfile(
        name="high",
        crf=18,
        preset="slow",
        codec="libx264",
        audio_bitrate="256k",
        max_width=None,
        max_height=None
    ),
    "balanced": CompressionProfile(
        name="balanced",
        crf=23,
        preset="medium",
        codec="libx264",
        audio_bitrate="192k",
        max_width=1920,
        max_height=1080
    ),
    "web": CompressionProfile(
        name="web",
        crf=28,
        preset="fast",
        codec="libx264",
        audio_bitrate="128k",
        max_width=1280,
        max_height=720,
        fps=30
    ),
    "h265_ultra": CompressionProfile(
        name="h265_ultra",
        crf=20,
        preset="slow",
        codec="libx265",
        audio_bitrate="256k",
        max_width=None,
        max_height=None
    ),
    "h265_balanced": CompressionProfile(
        name="h265_balanced",
        crf=26,
        preset="medium",
        codec="libx265",
        audio_bitrate="192k",
        max_width=1920,
        max_height=1080
    ),
}


class VideoCompressor:
    """High-quality video compression using FFmpeg"""

    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path
        self._verify_ffmpeg()

    def _verify_ffmpeg(self):
        """Check if FFmpeg is available"""
        try:
            result = subprocess.run(
                [self.ffmpeg_path, "-version"],
                capture_output=True,
                text=True,
                check=True
            )
            version_line = result.stdout.split('\n')[0]
            logger.info(f"FFmpeg detected: {version_line}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError(
                "FFmpeg not found. Install it:\n"
                "  Ubuntu/Debian: sudo apt-get install ffmpeg\n"
                "  macOS: brew install ffmpeg\n"
                "  Windows: choco install ffmpeg"
            )

    def get_video_info(self, input_path: str) -> dict:
        """Get video metadata using ffprobe"""
        ffprobe_cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", input_path
        ]

        result = subprocess.run(ffprobe_cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def compress(
        self,
        input_path: str,
        output_path: str,
        profile: CompressionProfile,
        two_pass: bool = False,
        keep_audio: bool = True,
        hardware_accel: Optional[Literal["nvenc", "vaapi", "videotoolbox"]] = None
    ) -> dict:
        """
        Compress video with specified profile.

        Args:
            input_path: Path to input video
            output_path: Path for compressed output
            profile: Compression profile
            two_pass: Enable two-pass encoding (better quality, slower)
            keep_audio: Preserve original audio if possible
            hardware_accel: Use hardware acceleration (nvenc, vaapi, videotoolbox)
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Build FFmpeg command
        cmd = [self.ffmpeg_path, "-y", "-i", str(input_path)]

        # Video filter chain
        filters = []

        # Scale filter if max dimensions specified
        if profile.max_width or profile.max_height:
            w = profile.max_width or "-1"
            h = profile.max_height or "-1"
            filters.append(f"scale={w}:{h}:force_original_aspect_ratio=decrease")

        # FPS filter
        if profile.fps:
            filters.append(f"fps={profile.fps}")

        # Apply video filters
        if filters:
            cmd.extend(["-vf", ",".join(filters)])

        # Video codec settings
        if hardware_accel == "nvenc" and profile.codec == "libx264":
            cmd.extend(["-c:v", "h264_nvenc", "-preset", "p4", "-cq", str(profile.crf)])
        elif hardware_accel == "nvenc" and profile.codec == "libx265":
            cmd.extend(["-c:v", "hevc_nvenc", "-preset", "p4", "-cq", str(profile.crf)])
        else:
            cmd.extend(["-c:v", profile.codec])

            if profile.codec == "libx265":
                cmd.extend(["-x265-params", f"crf={profile.crf}:preset={profile.preset}"])
                cmd.extend(["-tag:v", "hvc1"])  # Better compatibility
            else:
                cmd.extend(["-crf", str(profile.crf), "-preset", profile.preset])

        # Pixel format for compatibility
        cmd.extend(["-pix_fmt", "yuv420p"])

        # Two-pass encoding
        if two_pass and not hardware_accel:
            pass_log = str(output_path.with_suffix(".pass"))

            # First pass
            pass1_cmd = cmd + [
                "-an", "-f", "null",
                "-pass", "1", "-passlogfile", pass_log,
                os.devnull if os.name != 'nt' else "NUL"
            ]
            logger.info("Running first pass...")
            subprocess.run(pass1_cmd, capture_output=True, check=True)

            # Second pass
            cmd.extend(["-pass", "2", "-passlogfile", pass_log])

        # Audio settings
        if keep_audio:
            cmd.extend(["-c:a", "aac", "-b:a", profile.audio_bitrate])
        else:
            cmd.extend(["-an"])

        # Copy metadata
        cmd.extend(["-movflags", "+faststart"])

        # Output
        cmd.append(str(output_path))

        logger.info(f"Compressing with profile '{profile.name}': {input_path.name}")
        logger.debug(f"Command: {' '.join(cmd)}")

        # Execute
        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )

        if process.returncode != 0:
            logger.error(f"FFmpeg error: {process.stderr}")
            raise RuntimeError(f"Compression failed: {process.stderr}")

        # Cleanup pass log
        if two_pass:
            for f in output_path.parent.glob("*.pass-*"):
                f.unlink()

        # Calculate compression stats
        original_size = input_path.stat().st_size
        compressed_size = output_path.stat().st_size
        reduction = (1 - compressed_size / original_size) * 100

        stats = {
            "input_file": str(input_path),
            "output_file": str(output_path),
            "profile": asdict(profile),
            "original_size_mb": round(original_size / (1024 * 1024), 2),
            "compressed_size_mb": round(compressed_size / (1024 * 1024), 2),
            "reduction_percent": round(reduction, 2),
            "two_pass": two_pass,
            "hardware_accel": hardware_accel
        }

        logger.info(
            f"Complete: {stats['original_size_mb']}MB → "
            f"{stats['compressed_size_mb']}MB "
            f"({stats['reduction_percent']}% reduction)"
        )

        return stats

    def batch_compress(
        self,
        input_dir: str,
        output_dir: str,
        profile_name: str = "high",
        extensions: tuple = (".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm"),
        **kwargs
    ) -> list:
        """Compress all videos in a directory"""
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        profile = PROFILES.get(profile_name, PROFILES["high"])
        results = []

        for video_file in input_dir.iterdir():
            if video_file.suffix.lower() in extensions:
                output_file = output_dir / f"{video_file.stem}_compressed.mp4"
                try:
                    result = self.compress(
                        str(video_file),
                        str(output_file),
                        profile,
                        **kwargs
                    )
                    results.append(result)
                except Exception as e:
                    logger.error(f"Failed to compress {video_file.name}: {e}")
                    results.append({
                        "input_file": str(video_file),
                        "error": str(e)
                    })

        return results


def main():
    parser = argparse.ArgumentParser(
        description="High-Quality Video Compressor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Profiles:
  ultra        - CRF 16, veryslow, max quality (larger files)
  high         - CRF 18, slow, excellent quality (recommended)
  balanced     - CRF 23, medium, 1080p max, good quality/smaller size
  web          - CRF 28, fast, 720p max, optimized for web streaming
  h265_ultra   - HEVC CRF 20, superior compression, slower
  h265_balanced- HEVC CRF 26, great compression, 1080p max

Examples:
  %(prog)s -i video.mov -o compressed.mp4 --profile high
  %(prog)s -i video.mov -o compressed.mp4 --profile high --two-pass
  %(prog)s -i ./videos/ -o ./output/ --profile balanced --batch
        """
    )

    parser.add_argument("-i", "--input", required=True, help="Input file or directory")
    parser.add_argument("-o", "--output", required=True, help="Output file or directory")
    parser.add_argument("--profile", default="high", choices=list(PROFILES.keys()),
                       help="Compression profile (default: high)")
    parser.add_argument("--two-pass", action="store_true", help="Enable two-pass encoding")
    parser.add_argument("--batch", action="store_true", help="Batch process directory")
    parser.add_argument("--hwaccel", choices=["nvenc", "vaapi", "videotoolbox"],
                       help="Hardware acceleration")
    parser.add_argument("--no-audio", action="store_true", help="Remove audio track")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="Path to ffmpeg binary")

    args = parser.parse_args()

    compressor = VideoCompressor(args.ffmpeg)
    profile = PROFILES[args.profile]

    if args.batch:
        results = compressor.batch_compress(
            args.input,
            args.output,
            args.profile,
            two_pass=args.two_pass,
            keep_audio=not args.no_audio,
            hardware_accel=args.hwaccel
        )

        # Print summary
        successful = [r for r in results if "error" not in r]
        failed = [r for r in results if "error" in r]

        print(f"\n{'='*50}")
        print(f"BATCH COMPRESSION SUMMARY")
        print(f"{'='*50}")
        print(f"Total: {len(results)} | Success: {len(successful)} | Failed: {len(failed)}")

        if successful:
            avg_reduction = sum(r["reduction_percent"] for r in successful) / len(successful)
            total_saved = sum(r["original_size_mb"] - r["compressed_size_mb"] for r in successful)
            print(f"Average reduction: {avg_reduction:.1f}%")
            print(f"Total space saved: {total_saved:.1f} MB")

        if failed:
            print(f"\nFailed files:")
            for r in failed:
                print(f"  - {r['input_file']}: {r['error']}")
    else:
        stats = compressor.compress(
            args.input,
            args.output,
            profile,
            two_pass=args.two_pass,
            keep_audio=not args.no_audio,
            hardware_accel=args.hwaccel
        )

        print(f"\n{'='*50}")
        print(f"COMPRESSION RESULTS")
        print(f"{'='*50}")
        for key, value in stats.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()

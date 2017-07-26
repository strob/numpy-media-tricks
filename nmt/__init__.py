from __future__ import absolute_import

import logging

__all__ = (
    'media',
    'mediate',
    'remediate',
    'get_ffmpeg'
)

FFMPEG = 'ffmpeg'               # system FFMpeg
def get_ffmpeg():
    return FFMPEG

from .media import (
    video_info,
    frame_reader,
    video_frames,
    webcam_reader,
    webcam_frames,
    video2np,
    frame_writer,
    frames_to_video,
    np2video,
    image2np,
    np2image,
    sound_chunks,
    sound2np,
    chunk_writer,
    chunks_to_sound,
    np2sound)

try:
    from .mediate import ArrayUI
except ImportError:
    logging.info("livecoding not available")

try:
    from .remediate import run, multi_run, render
except ImportError:
    logging.info("recoding not available")

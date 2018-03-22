from PIL import Image
import numpy as np
import subprocess
import re
import sys

from . import get_ffmpeg# = "ffmpeg"

def image2np(path):
    "Load an image file into an array."

    im = Image.open(path)

    # autorotate image w/exif metadata
    # http://www.lifl.fr/~damien.riquet/auto-rotating-pictures-using-pil.html
    if hasattr(im, "_getexif"):
        exif = im._getexif()
        if exif:
            orientation_key = 274 # cf ExifTags
            if orientation_key in exif:
                orientation = exif[orientation_key]
                rotate_values = {
                    3: 180,
                    6: 270,
                    8: 90
                }
                if orientation in rotate_values:
                    # Rotate and save the picture
                    im = im.rotate(rotate_values[orientation])

    if im.mode == 'RGBA':
        # Fill background with white
        # http://stackoverflow.com/questions/9166400/convert-rgba-png-to-rgb-with-pil
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[3]) # 3 is the alpha channel
        im = bg
    else:
        im = im.convert('RGB')
    arr = np.asarray(im, dtype=np.uint8)
    return arr

def np2image(np, path):
    "Save an image array to a file."
    if len(np.shape) > 2:
        if np.shape[2] == 3:
            mode = 'RGB'
        elif np.shape[2] == 2:
            mode = 'LA'
    else:
        mode = 'L'
    im = Image.frombytes(
        mode, (np.shape[1], np.shape[0]), np.tostring())
    im.save(path)

def _video_info(stderr):
    out = {}

    # eg.:
    # Duration: 01:37:20.86, start: 0.000000, bitrate: 5465 kb/s
    #   Stream #0.0(eng): Video: h264 (Main), yuv420p, 1280x720, 2502 kb/s, 21.60 fps, 25 tbr, 3k tbn, 6k tbc

    dur_match = re.search(r'Duration: (\d\d):(\d\d):(\d\d).(\d\d)', stderr)

    if dur_match:
        h, m, s, ms = [int(x) for x in dur_match.groups()]
        out["duration"] = s + ms/100.0 + 60*(m + 60*h)
    else:
        out["duration"] = None

    start_match = re.search(r", start: (\d+\.\d+),", stderr)
    if start_match:
        out["start"] = float(start_match.groups()[0])

    ar_match = re.search(r'[^\d](\d+) Hz', stderr)
    if ar_match:
        out["audiorate"] = int(ar_match.groups()[0])

    ch_match_1 = re.search(r'[^\d](\d+) channels,', stderr)
    if ch_match_1:
        out["nchannels"] = int(ch_match_1.groups()[0])
    elif 'stereo,' in stderr:
        out["nchannels"] = 2
    elif 'mono,' in stderr:
        out["nchannels"] = 1

    wh_match = re.search(r'Stream .*[^\d](\d\d+)x(\d\d+)[^\d]', stderr)
    if wh_match:
        w,h = [int(x) for x in wh_match.groups()]
        out["width"] = w
        out["height"] = h

    fps_match = re.search(r'Stream .*[^\d\.](\d+)(\.\d+)? fps', stderr)
    if fps_match:
        num,frac = fps_match.groups()
        frac = frac or ""
        out["fps"] = float("%s%s" % (num,frac))

    # Look for rotation
    # displaymatrix: rotation of -90.00 degrees
    rot_match = re.search(r'rotation of ([0-9\.\-]+) degrees', stderr)
    if rot_match:
        out["rotation"] = float(rot_match.groups()[0])

    # ... look for timecode
    # creation_time   : 2018-03-21T13:26:13.000000Z
    ctime_match = re.search(r'creation_time\s+:\s+([\d\-T\:\.]+Z)', stderr)
    if ctime_match:
        out['creation_time'] = ctime_match.groups()[0]    

    return out

def video_info(path, preamble=[]):
    cmd = [get_ffmpeg()] + preamble + ['-i', path]
    p = subprocess.Popen(cmd, stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()

    return _video_info(stderr)

def _infer_size(path, width, height, preamble=[]):
    def div4(i):
        return 4*int(i/4.0)

    if width is None or height is None:
        # compute aspect ratio
        info = video_info(path, preamble=preamble)
        if width is None and height is None:
            width = info["width"]
            height = info["height"]
        elif width is None:
            width = div4(height * (info["width"] / float(info["height"])))
        else:
            height = div4(width * (info["height"] / float(info["width"])))

    return (width, height)

def frame_reader(path, height=None, width=None, start=0, fps=30, duration=None, colororder='rgb', bitrate='24', preamble=[]):
    # low-level ffmpeg wrapper
    width, height = _infer_size(path, width, height, preamble=preamble)

    dur_opts = []
    if duration is not None:
        dur_opts = ['-t', str(duration)]

    cmd = [get_ffmpeg()] + preamble + [
           '-ss', "%f" % (start),
           '-i', path] + dur_opts + [
           '-vf', 'scale=%d:%d'%(width,height),
           '-r', str(fps),
           '-an',
           '-vcodec', 'rawvideo', '-f', 'rawvideo',
           '-pix_fmt', '%s%s' % (colororder, bitrate),
           '-']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=open('/dev/null', 'w'))
    return (width, height, p)

def webcam_reader(name="", preamble=[], **kw):
    # https://trac.ffmpeg.org/wiki/Capture/Webcam
    # osx
    if "darwin" in sys.platform:
        return frame_reader(name, preamble=["-f", "avfoundation"]+preamble, **kw)
    elif "linux" in sys.platform:
        return frame_reader(name, preamble=["-f", "v4l2"]+preamble, **kw)

def video_frames(path, **kw):
    width, height, p = frame_reader(path, **kw)

    while True:
        arr = np.fromstring(p.stdout.read(width*height*3), dtype=np.uint8)
        if len(arr) == 0:
            p.wait()
            return

        yield arr.reshape((height, width, 3))

def webcam_frames(*a, **kw):
    # Returns a never-ending generator of webcam frames
    # XXX: duplicated code with video_frames
    width, height, p = webcam_reader(*a, **kw)

    while True:
        arr = np.fromstring(p.stdout.read(width*height*3), dtype=np.uint8)
        if len(arr) == 0:
            p.wait()
            return

        yield arr.reshape((height, width, 3))

def video2np(path, **kw):
    return np.array([X for X in video_frames(path, **kw)])

def frame_writer(first_frame, path, fps=30, ffopts=[]):
    fr = first_frame
    cmd =[get_ffmpeg(), '-y', '-s', '%dx%d' % (fr.shape[1], fr.shape[0]),
          '-r', str(fps), 
          '-an',
          '-pix_fmt', 'rgb24',
          '-vcodec', 'rawvideo', '-f', 'rawvideo', 
          '-i', '-'] + ffopts + [path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE,stderr=open('/dev/null', 'w'))
    return p

def frames_to_video(generator, *a, **kw):
    p = None 
    for fr in generator:
        if p is None:
            p = frame_writer(fr, *a, **kw)
        p.stdin.write(fr.tostring())
    p.stdin.close()
    print('done generating video')
    p.wait()

def np2video(np, *a, **kw):
    def vgen():
        for fr in np:
            yield fr
    return frames_to_video(vgen(), *a, **kw)

def sound_chunks(path, chunksize=2048, R=44100, nchannels=2, start=0, duration=None, ffopts=[]):
    # XXX: endianness EEK
    # TODO: detect platform endianness & adjust ffmpeg params accordingly

    dur_opts = []
    if duration is not None:
        dur_opts = ['-t', str(duration)]

    cmd = [get_ffmpeg(), 
           '-ss', "%f" % (start), 
           '-i', path] + dur_opts + [
           '-vn',
           '-ar', str(R), 
           '-ac', str(nchannels), 
           '-f', 's16le',
           '-acodec', 'pcm_s16le'] + ffopts + [
           '-']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=open('/dev/null', 'w'))
    frsize = 2*nchannels*chunksize

    while True:
        out = np.fromstring(p.stdout.read(frsize), dtype=np.int16).reshape((-1,nchannels))
        yield out

        if len(out) < chunksize:
            # Make sure the process ends
            p.wait()
            return

def sound2np(path, **kw):
    """
    Load audio data from a file.
    """
    return np.concatenate([x for x in sound_chunks(path, **kw)])

def chunk_writer(first_chunk, path, R=44100, ffopts=[]):
    nchannels = first_chunk.shape[1] if len(first_chunk.shape) > 1 else 1
    cmd =[get_ffmpeg(), '-y',
          '-vn',
          '-ar', str(R),
          '-ac', str(nchannels),
          '-acodec', 'pcm_s16le',
          '-f', 's16le',
          '-i', '-'] + ffopts + [path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=open('/dev/null', 'w'))
    return p

def chunks_to_sound(generator, *a, **kw):
    p = None 
    for ch in generator:
        if p is None:
            p = chunk_writer(ch, *a, **kw)
        p.stdin.write(ch.tostring())
    p.stdin.close()
    print('done generating sound')
    p.wait()

def np2sound(np, *a, **kw):
    def agen():
        rest = np
        while len(rest) > 0:
            yield rest[:2048]
            rest = rest[2048:]
    return chunks_to_sound(agen(), *a, **kw)

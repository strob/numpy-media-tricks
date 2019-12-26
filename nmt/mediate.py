from __future__ import absolute_import

# pysdl2-based numm api

import numpy as np
import sdl2
import sdl2.ext  # Maybe I shouldn't use `ext'?

from . import get_ffmpeg
from .media import _video_info, webcam_reader
import subprocess
import traceback

KEYMAP = dict(
    [(getattr(sdl2, X), X.split("_")[-1]) for X in dir(sdl2) if X.startswith("SDLK_")]
)
KEYMODS = dict(
    [(getattr(sdl2, X), X.split("_")[-1]) for X in dir(sdl2) if X.startswith("KMOD_")]
)


def _get_keymods(mod):
    return dict([(kval, True) for kmod, kval in KEYMODS.items() if mod & kmod])


class ArrayUI:
    def __init__(
        self,
        size=(320, 240),
        in_size=(320, 240),
        name="numpy-media-tricks",
        R=44100,
        nchannels=2,
        chunksize=1024,
        webcam="",
        spoof_webcam=None,
        nowindow=False,
        fullscreen=False,
    ):
        self.size = size
        self.in_size = in_size
        self.chunksize = chunksize
        self.name = name
        self.R = R
        self.nchannels = nchannels
        self.webcam = webcam
        self.spoof_webcam = spoof_webcam
        self.fullscreen = fullscreen

        if not nowindow:
            if hasattr(self, "video_out"):
                self._init_video()
            if hasattr(self, "audio_out"):
                self._init_audio()
            if hasattr(self, "audio_in"):
                self._init_mic()
            if hasattr(self, "video_in"):
                if self.spoof_webcam is not None:
                    self._init_spoof_video_in()
                else:
                    self._init_video_in()

    def _init_video(self):
        sdl2.ext.init()
        self._win = sdl2.ext.Window(
            self.name,
            size=self.size,
            flags=(sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP if self.fullscreen else None),
        )
        self._win.show()
        # TODO: determine (or override?) color-order
        # on linux, this seems to be BGRA, while on mac it's ARGB
        self._v = (
            sdl2.ext.pixels2d(self._win.get_surface())
            .T.view(np.uint8)
            .reshape((self.size[1], self.size[0], 4))
        )

    def go_fullscreen(self):
        sdl2.SDL_SetWindowFullscreen(
            self._win.window, sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP
        )

    def leave_fullscreen(self):
        sdl2.SDL_SetWindowFullscreen(self._win.window, 0)

    def _init_mic(self):
        import pyaudio

        p = pyaudio.PyAudio()
        self._mic = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.R,
            input=True,
            frames_per_buffer=self.chunksize,
        )

    def _init_video_in(self):
        w, h = (None, None)
        if self.in_size is not None:
            w, h = self.in_size
        (w, h, p) = webcam_reader(self.webcam, width=w, height=h)
        self.in_size = (w, h)
        self._v_in = p

    def _init_spoof_video_in(self):
        self._v_in = subprocess.Popen(
            [
                get_ffmpeg(),
                "-i",
                self.spoof_webcam,  # "-r", "60", (XXX: How to deal with speed?)
                "-vf",
                "scale=%d:%d" % (self.in_size[0], self.in_size[1]),
                "-an",
                "-vcodec",
                "rawvideo",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "bgr24",
                "-",
            ],
            stdout=subprocess.PIPE,
        )

    def _next_video_in_fr(self):
        in_fr = np.fromstring(
            self._v_in.stdout.read(self.in_size[0] * self.in_size[1] * 3),
            dtype=np.uint8,
        )
        try:
            in_fr = in_fr.reshape((self.in_size[1], self.in_size[0], 3))
        except ValueError:
            if self.spoof_webcam is not None:
                self._init_spoof_video_in()
                return self._next_video_in_fr()
            else:
                raise
        return in_fr

    def _handle_audio_cb(self, _udata, cbuf, N):
        # Read from mic
        if hasattr(self, "audio_in") and hasattr(self, "_mic"):
            in_buf = np.fromstring(self._mic.read(self.chunksize), dtype=np.int16)
            self.audio_in(in_buf)

        # ...and output
        arr = np.ctypeslib.as_array(cbuf, shape=(N,)).view(np.int16)
        if self.nchannels > 1:
            arr.shape = (-1, self.nchannels)
        self.audio_out(arr)

    def _init_audio(self):
        if sdl2.SDL_InitSubSystem(sdl2.SDL_INIT_AUDIO) != 0:
            raise RuntimeError("Failed to init audio")

        nsamples = self.chunksize * self.nchannels
        # For some reason, on OS X, this is 2x bigger than expected.
        # HACK!
        import sys

        if sys.platform == "darwin":
            nsamples /= 2

        self._audio_spec = sdl2.SDL_AudioSpec(
            self.R,
            # sdl2.AUDIO_S16MSB,
            sdl2.AUDIO_S16LSB,  # endianness eek!
            self.nchannels,
            nsamples,
            sdl2.SDL_AudioCallback(self._handle_audio_cb),
        )

        self._devid = sdl2.SDL_OpenAudioDevice(None, 0, self._audio_spec, None, 0)
        # start playing (well-named function!)
        sdl2.SDL_PauseAudioDevice(self._devid, 0)

    def tick(self):
        if self.handle_events():
            return True  # Quit
        self._update_av()

    def _update_av(self):
        # Update visuals
        if hasattr(self, "video_in"):
            # Read input frame
            in_fr = self._next_video_in_fr()
            self.video_in(in_fr)

        if hasattr(self, "video_out"):
            self.video_out(self._v[:, :, :3])
            self._win.refresh()
        else:
            # If audio only, slow down loop
            import time

            time.sleep(0.1)

    def handle_events(self):
        # Get all events
        for ev in sdl2.ext.get_events():
            self._handle_event(ev)

    def _handle_event(self, ev):
        if hasattr(self, "mouse_in"):
            if ev.type == sdl2.SDL_MOUSEMOTION:
                self.mouse_in("mouse-move", ev.motion.x, ev.motion.y, None)
            elif ev.type == sdl2.SDL_MOUSEBUTTONDOWN:
                self.mouse_in("mouse-button-press", ev.motion.x, ev.motion.y, ev.button)
            elif ev.type == sdl2.SDL_MOUSEBUTTONUP:
                self.mouse_in(
                    "mouse-button-release", ev.motion.x, ev.motion.y, ev.button
                )
            # Add touch events as if they were mouse events (...)
            elif ev.type == sdl2.SDL_FINGERDOWN:
                self.mouse_in(
                    "mouse-button-press",
                    int(self.size[0] * ev.tfinger.x),
                    int(self.size[1] * ev.tfinger.y),
                    ev.tfinger.touchId,
                )
            elif ev.type == sdl2.SDL_FINGERUP:
                self.mouse_in(
                    "mouse-button-release",
                    int(self.size[0] * ev.tfinger.x),
                    int(self.size[1] * ev.tfinger.y),
                    ev.tfinger.touchId,
                )
            elif ev.type == sdl2.SDL_FINGERMOTION:
                self.mouse_in(
                    "mouse-move",
                    int(self.size[0] * ev.tfinger.x),
                    int(self.size[1] * ev.tfinger.y),
                    ev.tfinger.touchId,
                )

        if hasattr(self, "keyboard_in"):
            if ev.type == sdl2.SDL_KEYDOWN:
                # ev.key.keysym.unicode is returning integers like 32640. howto decode?
                # self.keyboard_in("key-press", ev.key.keysym.unicode, ev.key.keysym.mod)
                self.keyboard_in(
                    "key-press",
                    KEYMAP[ev.key.keysym.sym],
                    _get_keymods(ev.key.keysym.mod),
                )
            if ev.type == sdl2.SDL_KEYUP:
                self.keyboard_in(
                    "key-release",
                    KEYMAP[ev.key.keysym.sym],
                    _get_keymods(ev.key.keysym.mod),
                )
        # else:
        #     print "unknown event", ev, ev.type

    def run_forever(self):
        if hasattr(self, "init"):
            self.init()
        while True:
            self.tick()


def multi_run(ns):
    windows_by_id = {}  # winid -> Numm
    for n in ns:
        if hasattr(n, "_win"):
            # print n, 'window-id', sdl2.SDL_GetWindowID(n._win.window)
            windows_by_id[sdl2.SDL_GetWindowID(n._win.window)] = n
        if hasattr(n, "init"):
            n.init()

    while True:
        for ev in sdl2.ext.get_events():
            if hasattr(ev, "window") and ev.window.windowID in windows_by_id:
                windows_by_id[ev.window.windowID]._handle_event(ev)
            else:
                # print "ev not handled by either window", ev, dir(ev)
                pass
        for n in ns:
            n._update_av()


class HotPluggableUI(ArrayUI):
    def __init__(self, *a, **kw):
        self.cbs = {}
        ArrayUI.__init__(self, *a, **kw)

    def _do_thing(self, name, *a):
        if name in self.cbs:
            try:
                self.cbs[name](*a)
                return True
            except:
                del self.cbs[name]
                traceback.print_exc()
        return False

    def video_out(self, *a):
        self._do_thing("video_out", *a)

    def audio_out(self, a):
        if not self._do_thing("audio_out", a):
            a[:] = 0

    def audio_in(self, a):
        self._do_thing("audio_in", a)

    def mouse_in(self, *a):
        self._do_thing("mouse_in", *a)

    def keyboard_in(self, *a):
        self._do_thing("keyboard_in", *a)


class TestUI(ArrayUI):
    def init(self):
        self.x = 0
        self.y = 0

    def audio_out(self, a):
        a[:, 0] = 2 ** 12 * np.sin(
            np.linspace(0, np.pi * 2 * 15, num=len(a), endpoint=False)
        )
        a[:, 1] = 2 ** 12 * np.sin(
            np.linspace(0, np.pi * 2 * 14, num=len(a), endpoint=False)
        )

    def video_out(self, a):
        a[:] = 0
        a[self.y : self.y + 50, self.x : self.x + 80] = (255, 0, 0)

    def mouse_in(self, type, px, py, buttons):
        self.x = px
        self.y = py


if __name__ == "__main__":
    n = TestUI()
    n.run_forever()

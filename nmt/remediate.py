from __future__ import print_function
from __future__ import absolute_import
# If run from a file, watch it (the file) for changes

from . import media
from . import mediate
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import numpy as np
import os
import subprocess
import sys
import tempfile
import traceback

def _load_module(path, g={}):
    source = open(path).read()
    code = compile(source, path, 'exec')
    exec(code, g)
    return g

class Ev2CB(FileSystemEventHandler):
    def __init__(self, pathmap):
        self.pathmap = pathmap  # {path: cb}
        FileSystemEventHandler.__init__(self)

    def get_cb(self, ev):
        print('get_cb', ev.src_path, ev)
        for path in self.pathmap.keys():
            if os.path.abspath(ev.src_path) == os.path.abspath(path):
                return self.pathmap[path]
        return None

    def on_created(self, ev):
        cb = self.get_cb(ev)
        if cb:
            cb()
    def on_deleted(self, ev):
        pass
    def on_modified(self, ev):
        cb = self.get_cb(ev)
        if cb:
            cb()

def print_errors(f):
    def g(*a, **kw):
        try:
            f(*a, **kw)
        except Exception:
            traceback.print_exc()

    return g

class HotPluggableUI(mediate.ArrayUI):
    def __init__(self, *a, **kw):
        self.cbs = {}
        mediate.ArrayUI.__init__(self, *a, **kw)

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

    def mouse_in(self, *a):
        self._do_thing("mouse_in", *a)
    def keyboard_in(self, *a):
        self._do_thing("keyboard_in", *a)

# TODO: Fix single-window version

def _monitor_changes(path, cb):
    obs = Observer()
    e2cb = Ev2CB({path: cb})
    obs.schedule(e2cb, os.path.dirname(os.path.abspath(path)))
    obs.start()
    return obs

def run(path, g={}, **kw):
    run = HotPluggableUI(**kw)

    def load():
        print('load!')
        g['self'] = run
        try:
            module = _load_module(path, g=g)
        except Exception:
            traceback.print_exc()
            return

        for k,v in module.items():
            run.cbs[k] = print_errors(v)

    load()
    obs = _monitor_changes(path, load)
    try:
        run.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        obs.stop()
    obs.join()

def onload(run, path, g):
    def load():
        print('load!', path)
        g['self'] = run
        module = _load_module(path, g=g)
        for k,v in module.items():
            run.cbs[k] = print_errors(v)
    return load

def multi_run(ns):
    "ns is a sequence of (path, g, kw) tuples"

    cbs = {}                    # path -> cb
    uis = []

    for (path, g, kwarg) in ns:

        run = HotPluggableUI(**kwarg)
        uis.append(run)

        cbs[path] = onload(run, path, g)
        cbs[path]()

    obs = Observer()
    e2cb = Ev2CB(cbs)
    dirpath = os.path.dirname(os.path.abspath(list(cbs.keys())[0]))
    print('dirpath', dirpath)
    obs.schedule(e2cb, dirpath)
    obs.start()

    try:
        mediate.multi_run(uis)
    except KeyboardInterrupt:
        print('interrupt...')
    finally:
        obs.stop()
    obs.join()

def multi_run_static(ns):
    # don't track, but use same semantics
    uis = []
    for (path, g, kwarg) in ns:
        run = HotPluggableUI(**kwarg)
        uis.append(run)
        onload(run, path, g)()
    mediate.multi_run(uis)

def render(path, out_path, duration, g={}, **kw):
    kw['nowindow']= True
    
    run = HotPluggableUI(**kw)
    def load():
        g['self'] = run
        try:
            module = _load_module(path, g=g)
        except Exception:
            traceback.print_exc()
            return

        for k,v in module.items():
            run.cbs[k] = print_errors(v)

    load()

    # TODO: expose
    FPS = 30
    R = 44100
    CHUNK_LEN = R / FPS         # XXX: integer assert?
    audio_chunks = []
    nframes = int(duration * FPS)

    v_frame_writer = None
    a_frame_writer = None

    with tempfile.NamedTemporaryFile(suffix='.%s' % (out_path.split('.')[-1])) as v_fh:
        with tempfile.NamedTemporaryFile(suffix='.wav') as a_fh:

            for idx in range(nframes):
                v_fr = np.zeros((run.size[1], run.size[0], 3), dtype=np.uint8)
                a_fr = np.zeros((CHUNK_LEN, 2), dtype=np.int16)
                
                if v_frame_writer is None:
                    v_frame_writer = media.frame_writer(v_fr, v_fh.name, fps=FPS)
                if a_frame_writer is None:
                    a_frame_writer = media.chunk_writer(a_fr, a_fh.name, R=R)

                run.video_out(v_fr)
                run.audio_out(a_fr)

                v_frame_writer.stdin.write(v_fr[:,:,(2,1,0)].tostring())
                a_frame_writer.stdin.write(a_fr.tostring())

            v_frame_writer.stdin.close()
            a_frame_writer.stdin.close()
                
            v_frame_writer.wait()
            a_frame_writer.wait()

            # Merge files
            # TODO: expose in media.py
            subprocess.call([media.FFMPEG,
                             '-y',
                             '-i', v_fh.name,
                             '-i', a_fh.name,
                             '-map', '0:v', '-map', '1:a',
                             '-c:v', 'copy',
                             '-strict', '-2',
                             '-b:a', '192k',
                             '-movflags', 'faststart', # XXX: will this break on non-mp4's?
                             out_path])

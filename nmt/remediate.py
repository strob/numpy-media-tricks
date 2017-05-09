from __future__ import print_function
from __future__ import absolute_import
# If run from a file, watch it (the file) for changes

from . import mediate
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import os
import sys
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

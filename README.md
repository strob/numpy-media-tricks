# numpy-media-tricks

- flip audio and video in and out of **numpy** arrays
- livecode treating the screen and speakers as **numpy** arrays

## Installation

You need SDL and FFmpeg installed, system-wide

```sh
(apt-get|brew) install sdl2 ffmpeg portaudio
pip install -r requirements.txt
sudo python setup.py install
```

## History

**numpy-media-tricks** was originally developed as **numm** in
2011 in collaboration with [Dafydd Harries](http://rhydd.org).
It was re-written (generally for the worse) over the years by
[Robert M Ochshorn](http://rmozone.com), who is to blame for
all current deficiencies.

## Licence

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or (at
your option) any later version.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.

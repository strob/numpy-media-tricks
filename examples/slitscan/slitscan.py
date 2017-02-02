import sys
import numpy as np

import nmt

# On different systems, colororder may be rgb.
arr = nmt.video2np(sys.argv[1], width=320, height=240, colororder='bgr')

nmt.run('slitscan.nmt.py', globals(), size=(320,240), name='slitscan')

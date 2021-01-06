#windowUtils.py
#A part of NonVisual Desktop Access (NVDA)
#Copyright (C) 2013 NV Access Limited
#This file is covered by the GNU General Public License.
#See the file COPYING for more details.

"""
Back-ported from NVDA 2018.2 windowUtils:
 - DEFAULT_DPI_LEVEL
 - LOGPIXELSX
 - getWindowScalingFactor

Utilities for working with windows (HWNDs).
"""

import ctypes
from logHandler import log


DEFAULT_DPI_LEVEL = 96.0

# The constant (defined in winGdi.h) to get the number of logical pixels per inch on the x axis
# via the GetDeviceCaps function.
LOGPIXELSX = 88


def getWindowScalingFactor(window):
	"""Gets the logical scaling factor used for the given window handle. This is based off the Dpi reported by windows
	for the given window handle / divided by the "base" DPI level of 96. Typically this is a result of using the scaling
	percentage in the windows display settings. 100% is typically 96 DPI, 150% is typically 144 DPI.
	@param window: a native Windows window handle (hWnd)
	@returns the logical scaling factor. EG. 1.0 if the window DPI level is 96, 1.5 if the window DPI level is 144"""
	user32 = ctypes.windll.user32
	try:
		winDpi = user32.GetDpiForWindow(window)
	except:
		log.debug("GetDpiForWindow failed, using GetDeviceCaps instead")
		dc = user32.GetDC(window)
		winDpi = ctypes.windll.gdi32.GetDeviceCaps(dc, LOGPIXELSX)
		ret = user32.ReleaseDC(window, dc)
		if ret != 1:
			log.error("Unable to release the device context.")

	# For GetDpiForWindow: an invalid hwnd value will result in a return value of 0.
	# There is little information about what GetDeviceCaps does in the case of a failure for LOGPIXELSX, however,
	# a value of zero is certainly an error.
	if winDpi <= 0:
		log.debugWarning("Failed to get the DPI for the window, assuming a "
		                 "DPI of {} and using a scaling of 1.0. The hWnd value "
		                 "used was: {}".format(DEFAULT_DPI_LEVEL, window))
		return 1.0

	return winDpi / DEFAULT_DPI_LEVEL

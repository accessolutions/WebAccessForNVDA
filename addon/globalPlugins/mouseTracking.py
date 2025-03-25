"""MouseTracking GlobalPlugin for NVDA >= 2024.1

Improvements to the tracking of the mouse cursor by NVDA.
Still way not perfect.
"""

__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"
__licence__ = "GPL"


from NVDAObjects import NVDAObject, NVDAObjectTextInfo
import api
from buildVersion import version_detailed as NVDA_VERSION
import config
import controlTypes
import globalPluginHandler
import locationHelper
from logHandler import log
import mouseHandler
import speech
import textInfos
import textUtils
import vision


# Applications names for which MouseTrackingNVDAObject.objectFromPointRedirect
# will attempt to introspect its children for a finer match based on their location.
OBJECT_FROM_POINT_REDIRECT_INTROSPECT_APP_NAMES = (
	"chrome",
	"firefox",
	"ms-teams",
	"msedge",
	"windowsterminal",
)


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	
	def __init__(self):
		if NVDA_VERSION < "2024.1":
			raise Exception("This GlobalPlugin targets NVDA >= 2024.1")
		super().__init__()
	
	def chooseNVDAObjectOverlayClasses(self, obj, clsList):
		clsList.append(MouseTrackingNVDAObject)


class MouseTrackingNVDAObject(NVDAObject):

	def event_mouseMove(self, x: int, y: int) -> None:
		if NVDA_VERSION < "2024.1":
			super().event_mouseMove(x, y)
			return
		# Changed from NVDA 2024.1 implementation:
		#  - Treat NotImplementedError and LookupError the same when retrieving TextInfo.
		#    NVDAObject.makeTextInfo has been seen to sometimes raise a LookupError when passed
		#    coordinates while still succeeding when passed textInfos.POSITION_FIRST.
		#    Eg. some controls on web pages.
		from utils.security import objectBelowLockScreenAndWindowsIsLocked

		if not self._mouseEntered and config.conf["mouse"]["reportObjectRoleOnMouseEnter"]:
			speech.cancelSpeech()
			speech.speakObject(self, reason=controlTypes.OutputReason.MOUSE)
			speechWasCanceled = True
		else:
			speechWasCanceled = False
		self._mouseEntered = True
		vision.handler.handleMouseMove(self, x, y)
		try:
			info = self.makeTextInfo(locationHelper.Point(x, y))
		except (LookupError, NotImplementedError):
			info = NVDAObjectTextInfo(self, textInfos.POSITION_FIRST)

		# This event may fire on the lock screen, as such
		# ensure the target TextInfo does not contain secure information.
		if objectBelowLockScreenAndWindowsIsLocked(info.obj):
			return

		if config.conf["reviewCursor"]["followMouse"]:
			api.setReviewPosition(info, isCaret=True)
		info.expand(info.unit_mouseChunk)
		oldInfo = getattr(self, "_lastMouseTextInfoObject", None)
		self._lastMouseTextInfoObject = info
		if (
			not oldInfo
			or info.__class__ != oldInfo.__class__
			or info.compareEndPoints(oldInfo, "startToStart") != 0
			or info.compareEndPoints(oldInfo, "endToEnd") != 0
		):
			text = info.text
			notBlank = False
			if text:
				for ch in text:
					if not ch.isspace() and ch != textUtils.OBJ_REPLACEMENT_CHAR:
						notBlank = True
			if notBlank:
				if not speechWasCanceled:
					speech.cancelSpeech()
				speech.speakText(text)

	def objectFromPointRedirect(self, x: int, y: int) -> "NVDAObject | None":
		# Method added in NVDA 2024.4 (issue #16788 / PR #16807 / commit 9b63cd50fe)
		if NVDA_VERSION >= "2024.4":
			obj = super().objectFromPointRedirect(x, y)
			if obj is not None:
				return obj
		# Introspecting children might be unsafe in some cases.
		# Thus, limit to applications where it is both necessary and has been successfully tested.
		try:
			if self.appModule.appName in OBJECT_FROM_POINT_REDIRECT_INTROSPECT_APP_NAMES:
				obj = self.firstChild
				while obj is not None:
					loc = obj.location
					if loc is None:
						return None
					if loc.left <= x <= loc.left + loc.width and loc.top <= y <= loc.top + loc.height:
						redirect = obj.objectFromPointRedirect(x, y)
						if redirect is not None:
							return redirect
						return obj
					obj = obj.next
				return None
		except Exception:
			log.exception()
		return None

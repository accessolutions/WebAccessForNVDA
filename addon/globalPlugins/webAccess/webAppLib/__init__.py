# globalPlugins/webAccess/webAppLib/__init__.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2024 Accessolutions (https://accessolutions.fr)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# See the file COPYING.txt at the root of this distribution for more details.

# Get ready for Python 3


__version__ = "2019.07.17"
__author__ = "Frédéric Brugnot <f.brugnot@accessolutions.fr>"


import os

import api
import braille
import config
import controlTypes
import inputCore
from keyboardHandler import KeyboardInputGesture, currentModifiers
from logHandler import log
import mouseHandler
import nvwave
import scriptHandler
import speech
import textInfos
import time
import tones
import virtualBuffers
import winUser

from . import html


try:
	from six import string_types
except ImportError:
	# NVDA version < 2018.3
	string_types = str


def speechOff():
	speech.setSpeechMode(speech.SpeechMode.off)
	
def speechOn(delay=0):
	time.sleep(delay)
	api.processPendingEvents ()
	speech.setSpeechMode(speech.SpeechMode.talk)

def playWebAppSound (name):
	from ... import webAccess
	try:
		playSound(os.path.join(webAccess.SOUND_DIRECTORY, "%s.wav" % name))
	except:
		pass

def playSound(sound):
	sound = os.path.abspath(os.path.join(os.path.dirname(__file__), sound))
	nvwave.playWaveFile(sound)

def getParentByRole (obj, role, func=None, max=30):
	if func is None:
		func = lambda x: True
	while obj is not None and not (obj.role == role and  func (obj)) and max > 0:
		obj = obj.parent
		max -= 1
	if max <= 0:
		return None
	return obj

def trace (msg="trace"):
	speech.speakMessage (msg)

def beep (freq=1000, dur=50):
	import tones
	tones.beep (freq, dur)
	
def reportFocus (obj):
	obj.reportFocus ()
	braille.handler.handleGainFocus (obj)

_startTime = 0

def logTimeStart ():
	global _startTime
	_startTime = time.time()
	return _startTime
	
def logTime (msg, startTime=None):
	global _startTime
	if not startTime:
		startTime = _startTime
	t = time.time()
	log.info("time %s = %d ms" %(msg, (t - startTime) * 1000))
	_startTime = t
	
def focusVirtualBuffer (obj=None):
	# place le focus NVDA sur le premier objet qui a un attribut treeInterceptor afin d'accÃ©der au curseur virtuel
	if obj is None:
		obj = api.getFocusObject()
		if obj.role == controlTypes.ROLE_UNKNOWN:
			obj = obj.parent
	if hasattr (obj, "treeInterceptor") and obj.treeInterceptor is not None:
		api.setFocusObject(obj)
		return True
	for child in obj.children:
		if focusVirtualBuffer (child):
			return True
	return False

def leftClick (x, y):
	winUser.setCursorPos(x, y)
	winUser.mouse_event(winUser.MOUSEEVENTF_LEFTDOWN,0,0,None,None)
	winUser.mouse_event(winUser.MOUSEEVENTF_LEFTUP,0,0,None,None)
def routeReviewToFocus ():
	obj=api.getFocusObject()
	try:
		pos=obj.makeTextInfo(textInfos.POSITION_CARET)
	except (NotImplementedError,RuntimeError):
		pos=obj.makeTextInfo(textInfos.POSITION_FIRST)
	api.setReviewPosition(pos)


def handleGesture (gesture):
	focus = api.getFocusObject()
	if not focus:
		return
	# to avoid infinite recursive call
	saveAppModule = focus.appModule
	focus.appModule = None
	gesture.script = scriptHandler.findScript(gesture)
	# process the gesture
	if gesture.script:
		gesture.speechEffectWhenExecuted = None # to suppress speech cancelation
		inputCore.manager.executeGesture(gesture)
	else:
		gesture.send()
	focus.appModule = saveAppModule

def waitKeyUp ():
	while len(currentModifiers) >  0:
		time.sleep(0.1)

def sendGestures(gestureList):
	waitKeyUp ()
	for gesture in gestureList:
		KeyboardInputGesture.fromName(gesture).send()
		time.sleep(0.1)

def sendGesture(gesture):
	sendGestures([gesture])

def mouseMove (x, y, relative=False):
	if relative:
		obj=api.getForegroundObject()
		left, top, width, height = obj.location
		x += left
		y += top
	winUser.setCursorPos(x, y)
	mouseHandler.executeMouseMoveEvent(x, y)

def leftMouseClick (x=None, y=None, relative=False):
	if x is not None:
		mouseMove(x, y, relative=relative)
	winUser.mouse_event(winUser.MOUSEEVENTF_LEFTDOWN,0,0,None,None)
	winUser.mouse_event(winUser.MOUSEEVENTF_LEFTUP,0,0,None,None)

def focusOnPosition(x, y, relative=False):
	mouseMove(x, y, relative=relative)
	winUser.mouse_event(winUser.MOUSEEVENTF_LEFTDOWN,0,0,None,None)
	mouseMove(x, y+30, relative=relative)
	time.sleep(0.3)
	winUser.mouse_event(winUser.MOUSEEVENTF_LEFTUP,0,0,None,None)

def sleep (seconds):
	time.sleep(seconds)
	
def getColorBackground (obj):
	if obj is None:
		return None
	formatConfig={
		"detectFormatAfterCursor":False,
		"reportFontName":True,"reportFontSize":True,"reportFontAttributes":True,"reportColor":True,"reportRevisions":False,
		"reportStyle":True,"reportAlignment":True,"reportSpellingErrors":True,
		"reportPage":False,"reportLineNumber":False,"reportTables":False,
		"reportLinks":True,"reportHeadings":False,"reportLists":False,
		"reportBlockQuotes":False,"reportComments":False,
	}
	info = obj.makeTextInfo (textInfos.POSITION_ALL)
	if info is None:
		return None
	for field in info.getTextWithFields(formatConfig):
		if isinstance(field,textInfos.FieldCommand):
			f = field.field
			if isinstance (f, textInfos.FormatField):
				try:
					return f["background-color"]
				except:
					pass
	# end of loop
	return None

def searchNameByColor (obj, background):
	formatConfig={
		"detectFormatAfterCursor":False,
		"reportFontName":True,"reportFontSize":True,"reportFontAttributes":True,"reportColor":True,"reportRevisions":False,
		"reportStyle":True,"reportAlignment":True,"reportSpellingErrors":True,
		"reportPage":False,"reportLineNumber":False,"reportTables":False,
		"reportLinks":True,"reportHeadings":False,"reportLists":False,
		"reportBlockQuotes":False,"reportComments":False,
	}
	info = obj.makeTextInfo (textInfos.POSITION_ALL)
	for field in info.getTextWithFields(formatConfig):
		if isinstance(field,textInfos.FieldCommand):
			f = field.field
			if isinstance (f, textInfos.FormatField):
				#log.info ("trace : %s" % repr(f))
				try:
					red = f["background-color"][0]
					trace (repr(f["background-color"]))
				except:
					red = -1
		elif isinstance (field, string_types):
			if red == background and len(field) > 3:
				return str (field)
	# end of loop
	return ""

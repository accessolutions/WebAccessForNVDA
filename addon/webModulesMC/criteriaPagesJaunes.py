from __future__ import absolute_import, division, print_function

from NVDAObjects.IAccessible import IAccessible
import queueHandler
import api
import browseMode
import ui
import controlTypes
from globalCommands import commands
from logHandler import log
import mouseHandler
import speech
import winUser
import review
import braille
import brailleInput
import time
import core
import scriptHandler
from scriptHandler import script
from globalPlugins.webAccess import webModuleHandler
from globalPlugins.webAccess.webAppLib import *
from globalPlugins.webAccess.ruleHandler import Zone
import re
from NVDAObjects.IAccessible.ia2Web import Ia2Web
from keyboardHandler import KeyboardInputGesture, currentModifiers
import globalPlugins.webAccess.webAppLib as lib

API_VERSION = "0.4"

class WebModule(webModuleHandler.WebModule):

	def action_testActionCritere(self, result, gesture):
		log.info("=================================================== TEST ACTION CRITERIA CALLED USING action_func FROM pageJaunes.py ==============================")
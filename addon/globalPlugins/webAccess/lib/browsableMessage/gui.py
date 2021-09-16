# -*- coding: utf-8 -*-
# globalPlugins/browsableMessage/gui.py

# This file is part of browsableMessage-nvda.
# Copyright (C) 2020-2021 Accessolutions (http://accessolutions.fr)
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

"""
Browsable Message GUI. 
"""

from __future__ import absolute_import, division, print_function

__version__ = "2021.09.16"
__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"
__license__ = "GPL"


import ctypes
from io import BytesIO
import os.path
from six import string_types
import six
import sys
import wx

import addonHandler
from logHandler import log
import winUser


addonHandler.initTranslation()


# As it comes with compiled .pyd files, the version of wx.html2 to import here
# must match the versions of Python and wxPython shipped with NVDA.
if sys.version_info[:3] == (2, 7, 16) and wx.__version__ == "4.0.3":
	# NVDA 2019.2.x
	import os.path
	import sys
	sys.modules["wx"].__path__.append(
		os.path.join(
			os.path.dirname(os.path.abspath(__file__)),
			r"lib\python-2.7.16\wx"
		),
	)
elif sys.version_info[:2] == (3, 7) and wx.__version__ == "4.0.3":
	# NVDA 2019.3.x / Python 3.7.5
	# NVDA 2020.1 / Python 3.7.7
	# NVDA 2020.2 / Python 3.7.8
	# NVDA 2020.3 / Python 3.7.9
	# NVDA 2020.4 / Python 3.7.9
	import os.path
	import sys
	sys.modules["wx"].__path__.append(
		os.path.join(
			os.path.dirname(os.path.abspath(__file__)),
			r"lib\python-3.7.5\wx"
		),
	)
elif sys.version_info[:3] == (3, 7, 9) and wx.__version__ == "4.1.1":
	# NVDA 2021.1, 2021.2
	import os.path
	import sys
	sys.modules["wx"].__path__.append(
		os.path.join(
			os.path.dirname(os.path.abspath(__file__)),
			r"lib\python-3.7.9\wx"
		),
	)
else:
	raise ValueError("Unsupported Python ({}) and wxPython ({}) combination".format(
		".".join((str(part) for part in sys.version_info[:3])),
		wx.__version__
	))


import wx.html2


class WebViewHandler(wx.html2.WebViewHandler):

	def __init__(self, parent, callback, rootDirs, scheme="memory"):
		super(WebViewHandler, self).__init__(scheme)
		self.parent = parent
		self.callback = callback
		self.rootDirs = rootDirs
	
	def GetFile(self, uri):
		if not uri or not uri.startswith("{}:".format(self.Name)):
			raise ValueError("uri: {!r}".format(uri))
		scheme, id = uri.split(":", 1)
		if id.startswith("/"):
			location = id.split("/")[-1]
			relpath = id[1:]
			for candidate in self.rootDirs:
				abspath = os.path.join(candidate, relpath)
				if os.path.isfile(abspath):
					break
			else:
				raise FileNotFoundError(
					"Could not find {!r} in {!r}".format(relpath, self.rootDirs)
				)
			with open(abspath, "rb") as f:
				data = f.read()
			if id.endswith(".md"):
				from . import transforms
				data = transforms.getHtmlDocFromMarkdown(data.decode("utf8")).encode("utf8")
				mimeType = "text/html"
			else:
				mimeType = ""
			stream = BytesIO(data)
		else:
			location = ""
			res = self.callback(id)
			if not res:
				self.parent.Parent.shouldClose = True
				#self.parent.Parent.Show(False)
				return wx.FSFile(BytesIO(b"<html/>"), id, "text/plain", "", wx.DateTime.Now())
			mimeType = res.get("mimeType")
			stream = res.get("stream")
			if not stream:
				data = res["data"]
				if (mimeType or "").startswith("text") or isinstance(data, string_types):
					data = data.encode("utf8")
				stream = BytesIO(data)
		return wx.FSFile(stream, id, mimeType, location, wx.DateTime.Now())


class WebViewDialog(wx.Dialog):
	
	def __init__(self, parent, title, callback, rootDirs):
		super(wx.Dialog, self).__init__(
			parent,
			title=title,
			style=wx.DEFAULT_DIALOG_STYLE | wx.MAXIMIZE_BOX,
			size=(620, 460),
		)
		self.callback = callback
		self.rootDirs = rootDirs
		self.shouldClose = False
		sizer = wx.BoxSizer(wx.VERTICAL)
		item = self.webView = wx.html2.WebView.New(self)
		item.Bind(wx.EVT_CHILD_FOCUS, self.onWebViewChildFocus)
		item.Bind(wx.EVT_SET_FOCUS, self.onWebViewSetFocus)
		item.Bind(wx.html2.EVT_WEBVIEW_LOADED, self.onWebViewLoaded)
		item.RegisterHandler(WebViewHandler(item, callback, rootDirs))
		item.LoadURL("memory:index")
		sizer.Add(item, proportion=1, flag=wx.EXPAND)
		sizer.Add(
			self.CreateSeparatedButtonSizer(wx.CLOSE),
			flag=wx.EXPAND | wx.BOTTOM,
			border=8
		)
		self.Bind(wx.EVT_BUTTON, self.onClose, id=wx.ID_CLOSE)
		self.SetSizer(sizer)
		self.Layout()

	def onClose(self, evt):
		self.Show(False)
	
	def onWebViewChildFocus(self, evt):
		evt.Skip(False)
		evt.StopPropagation()
		self.focusWebViewDocument()
	
	def onWebViewLoaded(self, evt):
		if self.shouldClose:
			evt.Skip()
			self.Show(False)
	
	def onWebViewSetFocus(self, evt):
		evt.Skip(False)
		evt.StopPropagation()
		self.focusWebViewDocument()
	
	def focusWebViewDocument(self, retry=5):
		user32 = ctypes.windll.user32
		GW_CHILD = 5
		hwnd = self.webView.Handle
		try:
			while True:
				hwnd = user32.GetWindow(hwnd, GW_CHILD)
				if not hwnd:
					if retry >= 0:
						wx.CallLater(1, self.focusWebViewDocument, retry - 1)
					return
				className = winUser.getClassName(hwnd)
				if className == u"Internet Explorer_Server":
					winUser.setFocus(hwnd)
					return
		except Exception:
			log.exception()

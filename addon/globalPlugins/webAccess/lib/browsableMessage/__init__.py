# -*- coding: utf-8 -*-
# globalPlugins/browsableMessage/__init__.py

# This file is part of browsableMessage-nvda.
# Copyright (C) 2020 Accessolutions (http://accessolutions.fr)
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
Browsable Message. 
"""

from __future__ import absolute_import, division, print_function

__version__ = "2020.10.11"
__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"
__license__ = "GPL"


from six import string_types
import weakref

import addonHandler
import globalPluginHandler
import globalVars
import languageHandler
from logHandler import log

from . import transforms


addonHandler.initTranslation()


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	pass


BROWSABLE_MESSAGE_TRANSFORMS = {
	"body": lambda data: data and {
		"data": transforms.getHtmlDocFromBody(data),
		"mimeType": "text/html"
	},
	"html": lambda data: data and {
		"data": data,
		"mimeType": "text/html"
	},
	"markdown": lambda data: data and {
		"data": transforms.getHtmlDocFromMarkdown(data),
		"mimeType": "text/html"
	},
	# Plain text seems not supported by this mode of Internet Explorer.
	"plain": lambda data: data and {
		"data": transforms.getHtmlDocFromPlainText(data, pre=True),
		"mimeType": "text/html"
	},
	"text": lambda data: data and {
		"data": transforms.getHtmlDocFromPlainText(data),
		"mimeType": "text/html"
	},
}

lastBrowsableMessageDialog = None


def browsableMessage(source, type=None, title=None, rootDirs=None):
	"""Present the user with a message or an hyperlinked series of messages in a web browser dialog.
	
	A single message can be specified as the value for the `source` argument.
	A series of messages can instead be specified by passing a callback function as `source`.
	The callback function will in turn get called with the URI of the requested message.
	
	The `type` parameter specifies how the returned messages should be converted into HTML documents.
	It accepts the following values:
	 * "html": No conversion but set MIME type to "text/html".
	 * "body": The message is an HTML snippet that gets wrapped as the content of the `body` element
	   of a basic HTML document template.
	 * "markdown": The message is formatted in markdown and gets converted into HTML.
	 * "text": The message is plain text and gets displayed in the regular paragraph body style. No HTML code is interpreted.
	 * "plain": The message is plain text and gets displayed in a monospace font style. No HTML code is interpreted.
	
	If `source` is a callback function and a `type` is specified, the callback is expected to return
	the content as a string or bytearray.
	If `source` is a callback function and no `type` is specified, the callback is expected to return
	a dictionary with the following items:
	 - "mimeType", mapping to the MIME type of the content
	 - and either "stream", mapping to a file-like object to the content
	 - or "data", mapping to a string or bytearray representation of the content
	
	URLs starting with a leading forward slash ("/") are treated as file URLs.
	`rootDirs` specifies the sequence of directories in which files are looked up.
	If omitted, files are looked up in the user configuration directory.
	"""
	# First close the eventual previous instance.
	global lastBrowsableMessageDialog
	if lastBrowsableMessageDialog:
		dlg = lastBrowsableMessageDialog()
		if dlg:
			try:
				dlg.Show(False)
			except:
				pass
	
	callback = None
	if isinstance(source, string_types):
		callback = lambda id: source if id == "index" else None
		if type is None:
			type = "text"
	elif callable(source):
		callback = source
	else:
		ValueError("Unsupported source type: {}".format(type(source)))
	if type:
		transform = BROWSABLE_MESSAGE_TRANSFORMS[type]
		callback = (lambda a, b: lambda id: b(a(id)))(callback, transform)

	if not title:
		# Translators: The title for the dialog used to present general NVDA messages in browse mode.
		title = _("NVDA Message")	
	
	from gui import mainFrame
	from .gui import WebViewDialog
	if rootDirs is None:
		rootDirs = [globalVars.appArgs.configPath]
	dlg = WebViewDialog(mainFrame, title, callback, rootDirs)
	lastBrowsableMessageDialog = weakref.ref(dlg)
	mainFrame.prePopup()
	dlg.Show()
	mainFrame.postPopup()

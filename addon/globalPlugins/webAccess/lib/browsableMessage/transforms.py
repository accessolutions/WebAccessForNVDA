# -*- coding: utf-8 -*-
# globalPlugins/browsableMessage/transforms.py

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
Browsable Message - Common content transformations.
"""

from __future__ import absolute_import, division, print_function

__version__ = "2020.03.03"
__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"
__license__ = "GPL"


import addonHandler
import languageHandler
from logHandler import log


addonHandler.initTranslation()


# Translators: Default HTML document template for browsable messages
DEFAULT_HTML_DOC_TEMPLATE = _("""<html lang="{lang}">
<head>
<meta charset="utf-8"/>
</head>
<body>
{body}
</body>
</html>""")


def getHtmlDocFromBody(body, lang=None):
	if body is None:
		return None
	if not lang:
		lang = languageHandler.getLanguage().split("_")[0]
	return DEFAULT_HTML_DOC_TEMPLATE.format(lang=lang, body=body)


def getHtmlBodyFromMarkdown(source, *args, **kwargs):
	from .lib.markdown2 import markdown
	return markdown(source, *args, **kwargs)


def getHtmlDocFromMarkdown(source):
	return getHtmlDocFromBody(getHtmlBodyFromMarkdown(source))


HTML_ESCAPE_MAP = {
	"&": "&amp;",
	'"': "&quot;",
	"'": "&apos;",
	">": "&gt;",
	"<": "&lt;",
}


def getHtmlEscaped(text):
	return "".join(HTML_ESCAPE_MAP.get(c, c) for c in text)


def getHtmlDocFromPlainText(source, pre=False):
	data = getHtmlEscaped(source)
	if pre:
		data = u"<pre>{}</pre>".format(data)
	return getHtmlDocFromBody(data)

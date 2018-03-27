# -*- coding: UTF-8 -*-

# Build customizations
# Change this file instead of sconstruct or manifest files, whenever possible.

# Full getext (please don't change)
_ = lambda x : x

# Add-on information variables
addon_info = {
	# for previously unpublished addons, please follow the community guidelines at:
	# https://bitbucket.org/nvdaaddonteam/todo/raw/master/guideLines.txt
	# add-on Name, internal for nvda
	"addon_name" : "webAccess",
	# Add-on summary, usually the user visible name of the addon.
	# Translators: Summary for this add-on to be shown on installation and add-on information.
	"addon_summary" : _("Web Access for NVDA"),
	# Add-on description
	# Translators: Long description to be shown for this add-on on add-on information from add-ons manager
	"addon_description" : _("""Web application modules support for modern or complex web sites."""),
	# version
	"addon_version" : "2018.03.27",
	# Author(s)
	"addon_author" : (
		u"Frédéric Brugnot <f.brugnot@accessolutions.fr>, "
		u"Yannick Plassiard <yan@mistigri.org>, "
		u"Julien Cochuyt <j.cochuyt@accessolutions.fr>"
		),
	# URL for the add-on documentation support
	"addon_url" : "http://www.accessolutions.fr",
	# Documentation file name
	"addon_docFileName" : "readme.html",
}


import os.path

# Define the python files that are the sources of your add-on.
# You can use glob expressions here, they will be expanded.
pythonSources = [
	os.path.join(entry[0], filename)
	for entry in os.walk("addon")  # yields a 3-tuple (dirpath, dirnames, filenames)
		for filename in entry[2]
		if os.path.splitext(filename)[1] in (".py")
	]

# Files that contain strings for translation. Usually your python sources
i18nSources = pythonSources + ["buildVars.py"]

# Files that will be ignored when building the nvda-addon file
# Paths are relative to the addon directory, not to the root directory of your addon sources.
excludedFiles = []

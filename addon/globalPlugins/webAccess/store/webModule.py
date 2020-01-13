# globalPlugins/webAccess/store/webModule.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2020 Accessolutions (http://accessolutions.fr)
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

"""Web Module data store."""

# Get ready for Python 3
from __future__ import absolute_import, division, print_function

__version__ = "2020.01.02"
__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"


from collections import OrderedDict
import errno
import imp
import os
import os.path
import re
import sys

import globalVars
from logHandler import log

from ..packaging import version
from ..webModuleHandler import InvalidApiVersion, WebModule, getWebModuleFactory
from . import DispatchStore
from . import DuplicateRefError
from . import MalformedRefError
from . import Store
from .addons import AddonsStore


try:
	import json
except ImportError:
	from .. import json



class Data(dict):
	pass


class WebModuleJsonFileDataStore(Store):
	
	def __init__(self, name, basePath, dirName="webModules"):
		super(WebModuleJsonFileDataStore, self).__init__(name=name)
		self.path = os.path.join(basePath, dirName)
	
	def catalog(self, errors=None):
		if not os.path.isdir(self.path):
			return
		for f in os.listdir(self.path):
			if os.path.isfile(os.path.join(self.path, f)):
				matches = re.match("^(.*)\.json$", f)
				if not matches:
					continue
				ref = matches.group(1)
				try:
					data = self.get(ref)
					meta = {}
					for key in ("windowTitle", "url"):
						value = data.get("WebModule", data.get("WebApp", {})).get(key)
						if value:
							meta[key] = value
				except:
					if errors:
						errors.append((ref, sys.exc_info()))
					else:
						log.exception(
							u"Error while retrieving item: ref={}".format(ref)
						)
					continue
				yield ref, meta

	def create(self, item, force=False):
		ref = self.getNewRef(item)
		path = self.getCheckedPath(ref, new=True, force=force)
		self.write(path, item)
		self.setRef(item, ref)
		return ref
	
	def delete(self, item, ref=None):
		if ref is None:
			ref = self.getRef(item)
		path = self.getCheckedPath(ref)
		return os.remove(path)
	
	def get(self, ref):
		path = self.getCheckedPath(ref)
		item = Data(self.read(path))
		self.setRef(item, ref)
		return item
	
	def getCheckedPath(self, ref, new=False, force=False):
		path = self.getPath(ref)
		if os.path.lexists(path):
			if not os.path.isfile(path):
				raise Exception(
					u"Non-file resource found at path: {path}".format(
						path=path
						)
					)
			elif new and not force:
				raise DuplicateRefError(
					u"File already exists: {path}".format(path=path)
					)
		elif not new:
			raise Exception(u"File not found: {path}".format(path=path))
		else:
			try:
				os.lstat(path)
			except Exception as e:
				# Malformed path
				if e.errno == errno.EINVAL:
					raise MalformedRefError(
						u"Invalid path: {path}".format(path=path)
						)
				# Parent directory not found, will get created on write
				elif e.errno == errno.ESRCH:
					os.mkdir(self.path)
					pass
				# File not found, as expected
				elif e.errno == errno.ENOENT:
					pass
				# Houston?
				else:
					raise
			if not os.path.lexists(self.path):
				os.mkdir(self.path)
		return path			
		
	def getNewRef(self, item):
		return item.name
	
	def getPath(self, ref):
		return os.path.join(self.path, u"{ref}.json".format(ref=ref))
	
	def getRef(self, item):
		ref = item.storeRef
		if isinstance(ref, tuple):
			return ref[-1] 
		return ref
	
	def hasRef(self, item):
		return (
			hasattr(item, "storeRef")
			and item.storeRef
		)
	
	def setRef(self, item, ref):
		if hasattr(item, "storeRef") and isinstance(item.storeRef, tuple):
			ref = item.storeRef[:-1] + (ref,)
		item.storeRef = ref
	
	def supports(self, operation, **kwargs):
		if operation in ["create", "delete", "update"]:
			return True
		return super(WebModuleJsonFileDataStore, self).supports(operation, **kwargs)
	
	def update(self, item, ref=None, force=False):
		if not self.hasRef(item):
			raise ValueError()
		if ref is None:
			ref = self.getRef(item)
		path = self.getCheckedPath(ref)
		newRef = self.getNewRef(item)
		if ref != newRef:
			newPath = self.getCheckedPath(newRef, new=True, force=force)
			os.rename(path, newPath)
			self.setRef(item, newRef)
			path = newPath
		return self.write(path, item)
	
	def read(self, path):
		try:
			with open(path, "r") as f:
				return json.load(f)
		except:
			log.exception(u"Failed reading file: {}".format(path))
			raise
	
	def write(self, path, item):
		data = item.dump()
		try:
			with open(path, "w") as f:
				json.dump(data, f, indent=4)
		except:
			log.exception(
				u"Failed writing file: {path}".format(path=path)
			)
			return False
		return True


class WebModuleStore(DispatchStore):

	def __init__(self, *args, **kwargs):
		kwargs["stores"] = [
			# The order of this list is meaningful. See WebModuleStore.catalog
			WebModuleJsonFileDataStore(name="userConfig", basePath=globalVars.appArgs.configPath),
			AddonsStore(
				addonStoreFactory=lambda addon: WebModuleJsonFileDataStore(
						name=addon.name, basePath=addon.path,
				)
			),
		]
		super(WebModuleStore, self).__init__(*args, **kwargs)
	
	def catalog(self, errors=None):
		# Keep only the first occurence of each ref in stores.
		# Thus, the order of the stores sets precedence.
		keyRefs = set()
		for storeRef, meta in super(WebModuleStore, self).catalog(errors=errors):
			keyRef = self._getKeyRef(storeRef)
			if keyRef not in keyRefs:
				keyRefs.add(keyRef)
				yield storeRef, meta
	
	def get(self, ref):
		data = super(WebModuleStore, self).get(ref)
		ctor = None
		keyRef = self._getKeyRef(ref)
		ctor = getWebModuleFactory(keyRef)
		try:
			item = ctor(data=data)
		except:
			log.exception(u"Failed to load JSON file: {ref}: {ctor}: {data}".format(**locals()))
			raise
		item.storeRef = data.storeRef
		return item
	
	def supports(self, operation, **kwargs):
		if operation == "mask":
			currStore, kwargs = self.route(**kwargs)
			for newStore in self.getSupportingStores("create", **kwargs):
				break
			else:
				return False
			if self.stores.index(newStore) < self.stores.index(currStore):
				return True
		return super(WebModuleStore, self).supports(operation, **kwargs)
	
	def _getKeyRef(self, storeRef):
		# Consider only the tail of DispatcherStore refs
		if isinstance(storeRef, tuple) and (len(storeRef) > 0):
			return storeRef[-1]
		else:
			return storeRef

# globalPlugins/webAccess/store/webModule.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2018 Accessolutions (http://accessolutions.fr)
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

__version__ = "2018.10.10"

__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"


import errno
import imp
import os
import os.path
import re

import globalVars
from logHandler import log

from .. import json
from ..webModuleHandler.webModule import WebModule
from . import DispatchStore
from . import DuplicateRefError
from . import MalformedRefError
from . import Store
from .addons import AddonsStore


class WebModuleJsonFileStore(Store):
	
	def __init__(self, name, path):
		super(WebModuleJsonFileStore, self).__init__(name=name)
		self.path = path
	
	def catalog(self):
		if not os.path.isdir(self.path):
			return
		for f in os.listdir(self.path):
			if os.path.isfile(os.path.join(self.path, f)):
				matches = re.match("^(.*)\.json$", f)
				if matches:
					yield matches.group(1)

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
		data = self.getData(path)
		try:
			item = WebModule(data=data)
		except:
			log.exception(
				u"Failed to load JSON file: {path}".format(path=path)
				)
			return None
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
		
	def getData(self, path):
		try:
			fd = os.open(path, os.O_RDONLY)
		except:
			log.exception(u"Failed to open file: {path}".format(path=path))
			return None
		serialized = ""
		eof = False
		while not eof:
			try:
				s = os.read(fd, 65536)
			except:
				log.exception(
					u"Failed to read from file: {path}".format(path=path)
					)
				os.close(fd)
				return None
			if s is None or s == "":
				eof = True
			else:
				serialized += s
		os.close(fd)
		try:
			return json.loads(serialized)
		except:
			log.exception(
				u"Failed to parse JSON file: {path}".format(path=path)
				)
			return None
	
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
		return super(WebModuleJsonFileStore, self).supports(operation, **kwargs)
	
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
	
	def write(self, path, item):
		data = item.dump()
		serialized = json.dumps(data, indent=4)
		try:
			fd = os.open(path, os.O_WRONLY | os.O_TRUNC | os.O_CREAT)
		except:
			log.exception(
				u"Failed to open file for writing: {path}".format(path=path)
				)
			return False
		bytesWritten = 0
		while bytesWritten < len(serialized):
			bytes = os.write(fd, serialized)
			if bytes == 0:
				log.warning(
					u"Failed writing to file: {path}".format(path=path)
					)
				return False
			serialized = serialized[bytes:]
			bytesWritten += bytes
		os.close(fd)
		return True
	
	
class WebModulePythonFileStore(Store):
	
	def __init__(self, name, path):
		super(WebModulePythonFileStore, self).__init__(name=name)
		self.path = path
		self.defaultDataStore = WebModuleJsonFileStore(
			name=u"{name}/data".format(name=name),
			path=path,
			)
	
	def catalog(self):
		if not os.path.isdir(self.path):
			return
		for f in os.listdir(self.path):
			if os.path.isfile(os.path.join(self.path, f)):
				matches = re.match("^(.*)\.py$", f)
				if matches:
					yield matches.group(1)
	
	def get(self, ref):
		path = self.getPathByRef(ref)
		name = ref
		try:
			mod = imp.load_source(name, path)
		except:
			log.exception(
				u"Failed to compile module: {name}".format(name=name)
				)
			return None
		ctor = getattr(mod, "WebModule", None)
		if ctor is None:
			log.error(
				u"Python module {name} does not provide a 'WebModule' class: "
				u"{path}".format(name=name, path=path)
				)
			return None
		kwargs = {}
		try:
			dataPath = self.defaultDataStore.getCheckedPath(ref)
			data = self.defaultDataStore.getData(dataPath)
			kwargs["data"] = data
		except:
			log.exception(
				u"While loading data for module: {name}".format(name=name)
				)
			pass
		try:
			instance = ctor(**kwargs)
		except:
			log.exception(
				u"Failed to instanciate web module: {name}".format(name=name)
				)
			return None
		if not hasattr(instance, "name"):
			instance.name = name
		if not hasattr(instance, "dataStore"):
			instance.dataStore = self.defaultDataStore
		self.setRef(instance, ref)
		return instance
	
	def getPathByItem(self, item):
		return self.getPathByRef(self.getRef(item))
	
	def getPathByRef(self, ref):
		return os.path.join(self.path, u"{ref}.py".format(ref=ref))
	
	def getRef(self, item):
		return item.name
	
	def setRef(self, item, ref):
		if hasattr(item, "storeRef") and isinstance(item.storeRef, tuple):
			ref = item.storeRef[:-1] + (ref,)
		item.storeRef = ref
	
	def update(self, item, ref=None, force=False):
		return item.dataStore.update(item=item, ref=ref, force=force)
	
	def supports(self, operation, **kwargs):
		if operation == "update":
			item = kwargs.get("item")
			if item is not None:
				return item.dataStore.supports(operation, **kwargs)
			# This might be wrong if the Python WebModule provides a
			# readonly custom data store.
			return self.defaultDataStore.supports(operation, **kwargs)
		return False


class WebModuleFileStore(DispatchStore):
	
	def __init__(self, *args, **kwargs):
		self.basePath = kwargs["basePath"]
		self.dirName = kwargs["dirName"] if "dirName" in kwargs else "webModules"
		dirPath = os.path.join(self.basePath, self.dirName)
		kwargs["stores"] = [
			# The order of this list is meaningful. See WebModuleStore.catalog
			WebModulePythonFileStore(name="code", path=dirPath),
			WebModuleJsonFileStore(name="data", path=dirPath),
			]
		super(WebModuleFileStore, self).__init__(*args, **kwargs)
	
# 	def __getStores(self):
# 		dirPath = os.path.join(self.basePath, self.dirName)
# 		return [
# 			# The order of this list is meaningful. See WebModuleStore.catalog
# 			WebModulePythonFileStore(name="code", path=dirPath),
# 			WebModuleJsonFileStore(name="data", path=dirPath),
# 			]
# 	
# 	stores = property(__getStores)


class WebModuleStore(DispatchStore):

	def __init__(self, *args, **kwargs):
		kwargs["stores"] = [
			# The order of this list is meaningful. See WebModuleStore.catalog
			WebModuleFileStore(
				name="userConfig",
				basePath=globalVars.appArgs.configPath
				),
			AddonsStore(
				addonStoreFactory=lambda(addon): (
					WebModuleFileStore(
						name=addon.name,
						basePath=addon.path,
						)
					)
				)
			]
		super(WebModuleStore, self).__init__(*args, **kwargs)
	
	def catalog(self):
		# Keep only the first occurence of each ref in stores.
		# Thus, the order of the stores sets precedence.
		uniqueRefs = set()
		for storeRef in super(WebModuleStore, self).catalog():
			# Consider only the tail of DispatcherStore refs
			if isinstance(storeRef, tuple) and (len(storeRef) > 0):
				uniqueRef = storeRef[-1]
			else:
				uniqueRef = storeRef
			if uniqueRef not in uniqueRefs:
				uniqueRefs.add(uniqueRef)
				yield storeRef
	
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


_instance = None

def getInstance():
	global _instance
	if _instance is None:
		_instance = WebModuleStore()
	return _instance

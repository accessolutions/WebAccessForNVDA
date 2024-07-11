# globalPlugins/webAccess/store/webModule.py
# -*- coding: utf-8 -*-

# This file is part of Web Access for NVDA.
# Copyright (C) 2015-2021 Accessolutions (http://accessolutions.fr)
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


__version__ = "2021.03.12"
__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"


from collections import OrderedDict
import errno
import imp
import os
import os.path
from pprint import pformat
import re
import sys

import config
import globalVars
from logHandler import log

from ..lib.packaging import version
from ..webModuleHandler import InvalidApiVersion, WebModule, WebModuleDataLayer, getWebModuleFactory
from . import DispatchStore
from . import DuplicateRefError
from . import MalformedRefError
from . import Store
from .addons import AddonsStore


try:
	import json
except ImportError:
	from ..lib import json


class WebModuleJsonFileDataStore(Store):

	def __init__(self, name, basePath, dirName="webModulesMC"):
		super(WebModuleJsonFileDataStore, self).__init__(name=name)
		self.basePath = basePath
		self.path = os.path.join(basePath, dirName)

	def __repr__(self):
		return "<WebModuleJsonFileDataStore (name={!r}, path={!r}".format(self.name, self.path)

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
					data = self.get(ref).data
					meta = {}
					for key in ("windowTitle", "url"):
						value = data.get("WebModule", data.get("WebApp", {})).get(key)
						if value:
							meta[key] = value
				except Exception:
					if errors:
						errors.append((ref, sys.exc_info()))
					else:
						log.exception(
							"Error while retrieving item: ref={}".format(ref)
						)
					continue
				yield ref, meta

	def create(self, item, force=False):
		ref = self.getNewRef(item)
		path = self.getCheckedPath(ref, new=True, force=force)
		self.write(path, item.data)
		self.setRef(item, ref)
		return ref

	def delete(self, item, ref=None):
		if ref is None:
			ref = self.getRef(item)
		path = self.getCheckedPath(ref)
		return os.remove(path)

	def get(self, ref):
		path = self.getCheckedPath(ref)
		data = self.read(path)
		item = WebModuleDataLayer(None, data, ref)
		return item

	def getCheckedPath(self, ref, new=False, force=False):
		path = self.getPath(ref)
		if os.path.lexists(path):
			if not os.path.isfile(path):
				raise Exception(
					"Non-file resource found at path: {path}".format(
						path=path
						)
					)
			elif new and not force:
				raise DuplicateRefError(
					"File already exists: {path}".format(path=path)
				)
		elif not new:
			raise Exception("File not found: {path}".format(path=path))
		else:
			try:
				os.lstat(path)
			except Exception as e:
				# Malformed path
				if e.errno == errno.EINVAL:
					raise MalformedRefError(
						"Invalid path: {path}".format(path=path)
					)
				# File not found, as expected
				elif e.errno == errno.ENOENT:
					pass
				# Houston?
				else:
					raise
		return path

	def getNewRef(self, item):
		return item.data["WebModule"]["name"]

	def getPath(self, ref):
		return os.path.join(self.path, "{ref}.json".format(ref=ref))

	def getRef(self, item):
		ref = item.storeRef
		if isinstance(ref, tuple):
			return ref[-1]
		return ref

	def hasRef(self, layer):
		return (
			hasattr(item, "storeRef")
			and item.storeRef
		)

	def setRef(self, item, ref):
		if hasattr(item, "storeRef") and isinstance(item.storeRef, tuple):
			ref = item.storeRef[:-1] + (ref,)
		item.storeRef = ref

	def supports(self, operation, **kwargs):
		if operation in ["create", "delete", "mask", "update"]:
			if self.basePath == globalVars.appArgs.configPath:
				return not config.conf["webAccess"]["disableUserConfig"]
			return config.conf["webAccess"]["devMode"]
		return super(WebModuleJsonFileDataStore, self).supports(operation, **kwargs)

	def update(self, item, ref=None, force=False):
		if ref is None:
			ref = self.getRef(item)
		path = self.getCheckedPath(ref)
		newRef = self.getNewRef(item)
		if ref != newRef:
			newPath = self.getCheckedPath(newRef, new=True, force=force)
			os.rename(path, newPath)
			self.setRef(item, newRef)
			path = newPath
		self.write(path, item.data)

	def read(self, path):
		try:
			with open(path, "r") as f:
				return json.load(f)
		except Exception:
			log.exception("Failed reading file: {}".format(path))
			raise

	def write(self, path, data):
		try:
			dir = os.path.dirname(path)
			if not os.path.isdir(dir):
				os.makedirs(dir)
			with open(path, "w") as f:
				json.dump(data, f, indent=4)
		except Exception:
			log.exception(
				"Failed writing file: {path}".format(path=path)
			)
			return False
		return True


class WebModuleStore(DispatchStore):

	def __init__(self, *args, **kwargs):
			# The order of this list is meaningful. See `catalog`
		stores = kwargs["stores"] = []
		store = self.userStore = WebModuleJsonFileDataStore(
			name="userConfig", basePath=globalVars.appArgs.configPath
		)
		stores.append(store)
		if config.conf["development"]["enableScratchpadDir"]:
			store = self.scratchpadStore = WebModuleJsonFileDataStore(
				name="scratchpad", basePath=config.getScratchpadDir()
			)
			stores.append(store)
		else:
			self.scratchpadStore = None
		stores.append(AddonsStore(
			addonStoreFactory=lambda addon: WebModuleJsonFileDataStore(
					name=addon.name, basePath=addon.path,
			)
		))
		super(WebModuleStore, self).__init__(*args, **kwargs)

	def alternatives(self, keyRef):
		return (
			storeRef for storeRef, meta in super(WebModuleStore, self).catalog()
			if self._getKeyRef(storeRef) == keyRef
		)

	def catalog(self, errors=None):
		full = OrderedDict()
		for storeRef, meta in super(WebModuleStore, self).catalog(errors=errors):
			full[storeRef] = meta
		uniqueKeyRefs = set()
		consolidated = OrderedDict()
		for storeRef, meta in list(full.items()):
			keyRef = self._getKeyRef(storeRef)
			if keyRef in uniqueKeyRefs:
				continue
			if not self._isUserConfig(storeRef):
				uniqueKeyRefs.add(keyRef)
				consolidated[storeRef] = meta
				continue
			elif config.conf["webAccess"]["disableUserConfig"]:
				continue
			base = None
			for alternative in self.alternatives(keyRef):
				if alternative != storeRef:
					assert not self._isUserConfig(alternative)
					base = full[alternative]
					break
			if base is None:
				uniqueKeyRefs.add(keyRef)
				consolidated[storeRef] = meta
				continue
			for property in ["url", "windowTitle"]:
				if not (
					property in meta.get("overrides", {})
					and meta["overrides"][property] == base.get(property)
				):
					if property in base:
						meta[property] = base[property]
					elif property in meta:
						del meta[property]
			uniqueKeyRefs.add(keyRef)
			consolidated[storeRef] = meta
		return list(consolidated.items())

	def create(self, item, **kwargs):
		layers = [layer for layer in reversed(item.layers) if layer.storeRef is None]
		if len(layers) != 1:
			raise ValueError("Expecting a single new data layer, found {}.".format(len(layers)))
		layer = layers[0]
		layer = item.dump(layer.name)
		layer.storeRef = super(WebModuleStore, self).create(layer, **kwargs)

	def delete(self, item, layerName=None, ref=None, **kwargs):
		if layerName is not None:
			layer = item.getLayers(layerName, raiseIfMissing=True)
		else:
			for layerName in ("user", "scratchpad", "addon"):
				layer = item.getLayer(layerName)
				if layer is not None:
					break
			else:
				raise Exception("No data layer candidate for deletion")
		if ref is not None and layer.storeRef != ref:
			raise ValueError("References mismatch: layer.storeRef={!r} != {ref}")
		ref = layer.storeRef
		if self._isUserConfig(ref):
			if config.conf["webAccess"]["disableUserConfig"]:
				raise Exception("UserConfig is disabled")
		elif not config.conf["webAccess"]["devMode"]:
			raise Exception("This action is allowed only in Developer Mode")
		super(WebModuleStore, self).delete(layer, ref=ref, **kwargs)

	def get(self, ref):
		keyRef = self._getKeyRef(ref)
		alternatives = self.alternatives(keyRef)
		if self._isUserConfig(ref):
			if config.conf["webAccess"]["disableUserConfig"]:
				raise Exception("User Configuration is disabled")
			baseRef = None
			userRef = ref
			for alternative in alternatives:
				if not self._isUserConfig(alternative):
					baseRef = alternative
					break
		else:
			baseRef = ref
			userRef = None
			if not config.conf["webAccess"]["disableUserConfig"]:
				for alternative in alternatives:
					if self._isUserConfig(alternative):
						userRef = alternative
						break
		log.debug(f"ref={ref!r} ({ref}), keyRef={keyRef!r} ({keyRef})")
		ctor = getWebModuleFactory(keyRef)
		item = ctor()
		layers = []
		if baseRef is not None:
			try:
				baseLayerName = "addon" if baseRef[0] == "addons" else baseRef[0]
			except Exception:
				baseLayerName = str(baseRef)
			layers.append((baseLayerName, baseRef))
		if userRef is not None:
			layers.append(("user", userRef))
		for layerName, storeRef in layers:
			item.load(layerName, storeRef=storeRef)
		item.alternatives = self.alternatives(keyRef)
		return item

	def getData(self, ref):
		return super(WebModuleStore, self).get(ref)

	def getSupportingStores(self, operation, **kwargs):
		if operation == "create":
			item = kwargs.get("item")
			if isinstance(item, WebModule):
				if len(item.layers) == 1:
					item = item.layers[0]
				else:
					raise Exception("item={!r}".format(item))
			elif not isinstance(item, WebModuleDataLayer):
				raise TypeError("item={!r}".format(item))
			layerName = item.name
			if layerName == "user":
				if self.userStore.supports(operation):
					return (self.userStore,)
			elif layerName == "scratchpad":
				if self.scratchpadStore and self.scratchpadStore.supports(operation):
					return (self.scratchpadStore,)
			return tuple()
		return super(WebModuleStore, self).getSupportingStores(operation, **kwargs)

	def update(self, item, layerName=None, ref=None, **kwargs):
		if layerName is not None or ref is not None:
			for layer in reversed(item.layers):
				if (
					layer.storeRef
					and (layerName is None or layer.name == layerName)
					and (ref is None or layer.storeRef == ref)
				):
					break
			else:
				raise LookupError("layerName={!r}, ref={!r}".format(layerName, ref))
		else:
			layers = [layer for layer in reversed(item.layers) if layer.storeRef and layer.dirty]
			if len(layers) != 1:
				raise ValueError("Expecting a single dirty data layer, found {}.".format(len(layers)))
			layer = layers[0]
		ref = layer.storeRef
		if self._isUserConfig(ref):
			if config.conf["webAccess"]["disableUserConfig"]:
				raise Exception("UserConfig is disabled")
		elif not config.conf["webAccess"]["devMode"]:
			raise Exception("This action is allowed only in Developer Mode")
		layer = item.dump(layer.name)
		super(WebModuleStore, self).update(layer, ref=ref, **kwargs)

	def _getKeyRef(self, storeRef):
		# Consider only the tail of DispatcherStore refs
		if isinstance(storeRef, tuple) and (len(storeRef) > 0):
			return storeRef[-1]
		else:
			return storeRef

	def _isUserConfig(self, ref):
		try:
			return ref[0] == "userConfig"
		except Exception:
			pass
		return False

# globalPlugins/webAccess/store/__init__.py
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

"""Web Access data store."""


__version__ = "2021.02.04"
__author__ = "Julien Cochuyt <j.cochuyt@accessolutions.fr>"


import sys

from logHandler import log


class Store(object):
	
	def __init__(self, *args, **kwargs):
		if "name" in kwargs:
			self.name = kwargs["name"]

	def __str__(self, *args, **kwargs):
		return self.name if hasattr(self, "name") \
			else super(Store, self).__str__(*args, **kwargs)
	
	def catalog(self, errors=None):
		"""Return, or yield, a sequence of tuples (ref, metaData)
		"""
		raise NotImplementedError()

	def create(self, item, **kwargs):
		raise NotImplementedError()

	def delete(self, item, **kwargs):
		raise NotImplementedError()
			
	def get(self, ref, **kwargs):
		return None
	
	def list(self, errors=None):
		for ref, meta in self.catalog(errors=errors):
			try:
				item = self.get(ref)
			except Exception:
				if errors is not None:
					errors.append((ref, sys.exc_info()))
				else:
					log.exception(
						"Error while retrieving item: ref={ref}".format(
							ref=ref
						)
					)
				continue
			if item is None:
				log.warning(
					"No item retrieved for ref: {ref}".format(ref=ref)
				)
			else:
				yield item
	
	def supports(self, operation, **kwargs):
		return False

	def update(self, item, **kwargs):
		raise NotImplementedError()
	
	
class DispatchStore(Store):
	
	def __init__(self, *args, **kwargs):
		if "stores" in kwargs:
			self.stores = kwargs["stores"]
		elif not hasattr(self, "stores"):
			self.stores = []
		if not hasattr(self, "storeDic"):
			self.storeDic = dict()
		super(DispatchStore, self).__init__(*args, **kwargs)

	def catalog(self, errors=None):
		for store in self.stores:
			for ref, meta in store.catalog(errors=errors):
				yield self.track(store, ref=ref)["ref"], meta
	
	def create(self, item, **kwargs):
		for store in self.getSupportingStores("create", item=item, **kwargs):
			ref = store.create(item, **kwargs)
			return self.track(store, ref=ref)["ref"]
	
	def delete(self, item, ref=None, **kwargs):
		store, kwargs = self.route(ref, item, **kwargs)
		return store.delete(kwargs.pop("item"), **kwargs)

	def get(self, ref, **kwargs):
		store, kwargs = self.route(ref, **kwargs)
		item = store.get(kwargs.pop("ref"), **kwargs)
		if item is None:
			return
		return self.track(store, item=item)["item"]
	
	def getStoreKey(self, store):
		return store.name
	
	def getSupportingStores(self, operation, **kwargs):
		for store in self.stores:
			if store.supports(operation, **kwargs):
				yield store		
	
	def route(self, ref=None, item=None, **kwargs):
		if ref is None and item is None:
			raise Exception("At least one of ref or item should be specified.")
		if ref is None:
			ref = item.storeRef
		hasNestedRef = False
		if isinstance(ref, tuple):
			if len(ref) >= 1:
				storeKey = ref[0]
				ref = ref[1:]
				if len(ref) > 0:
					hasNestedRef = True
					if len(ref) == 1:
						ref = ref[0]
			else:
				ValueError("Unexpected ref format: {ref}".format(ref))
		else:
			storeKey = ref
		store = None
		if storeKey in self.storeDic:
			store = self.storeDic[storeKey]
		else:
			for candidate in self.stores:
				if self.getStoreKey(candidate) == storeKey:
					store = candidate
					break
			if store is None:
				raise Exception(
					"Unknown store: {storeKey}".format(storeKey=storeKey)
				)
			self.storeDic[storeKey] = store
		if hasNestedRef:
			kwargs["ref"] = ref
		if item is not None:
			kwargs["item"] = item
		return store, kwargs

	def supports(self, operation, **kwargs):
		if operation == "create":
			for store in self.getSupportingStores(operation, **kwargs):
				return True
			return False
		if "ref" in kwargs or "item" in kwargs:
			store, kwargs = self.route(**kwargs)
			return store.supports(operation, **kwargs)
		return super(DispatchStore, self).supports(operation, **kwargs)

	def track(self, store, item=None, **kwargs):
		if "ref" not in kwargs and item is None:
			raise Exception("At lease one of ref or item should be specified.")
		storeKey = self.getStoreKey(store)
		self.storeDic[storeKey] = store
		if "ref" in kwargs:
			ref = kwargs["ref"]
		elif hasattr(item, "storeRef"):
			ref = item.storeRef
		else:
			ref = tuple()
		ref = (storeKey,) + (ref if isinstance(ref, tuple) else (ref,))
		if "ref" in kwargs:
			kwargs["ref"] = ref
		if item is not None:
			item.storeRef = ref
			kwargs["item"] = item
		return kwargs

	def update(self, item, ref=None, **kwargs):
		store, kwargs = self.route(ref, item, **kwargs)
		return store.update(kwargs.pop("item"), **kwargs)
	

class DuplicateRefError(Exception):
	
	def __init__(self, *args, **kwargs):
		super(Exception, self).__init__(*args, **kwargs)

		
class MalformedRefError(Exception):
	
	def __init__(self, *args, **kwargs):
		super(Exception, self).__init__(*args, **kwargs)
		

class UnknownRefError(Exception):
	
	def __init__(self, *args, **kwargs):
		super(Exception, self).__init__(*args, **kwargs)
		

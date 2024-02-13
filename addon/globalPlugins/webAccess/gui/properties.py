
__version__ = "2024.02.02"

from abc import ABC, abstractmethod
from enum import Enum
from typing import Tuple, Optional
import wx
import gui
from logHandler import log

def showPropsDialog(context):
	PropsMenu(context).ShowModal()
	return True

class PropsMenu(wx.Menu):

	def __init__(self, context):
		super(PropsMenu, self).__init__()
		self.context = context
		for props in propertiesList:
			if props.get_flag():
				id = self.FindItem(props.get_displayName())
				if id != -1:
					self.Delete(id)
					self.Bind(wx.EVT_MENU, props.updateFlag)
					return
			else:
				itemCheck = self.Append(wx.ID_ANY, props.get_displayName())
				#itemCheck.Check(check=False)
				self.Bind(wx.EVT_MENU, props.updateFlag, itemCheck)

	def ShowModal(self):
		gui.mainFrame.prePopup(contextMenuName="Properties rules")
		gui.mainFrame.PopupMenu(self)
		gui.mainFrame.postPopup()


class PropertyType(Enum):
	TOGGLE = "toggle"  # True / False
	EDITABLE = "editable"
	SINGLE_CHOICE = "singleChoice"
	MULTIPLE_CHOICE = "multipleChoice"

class Property(ABC):
	@abstractmethod
	def __init__(
			self,
			id: str,
			display_name: str,
			type: PropertyType
	):
		self.__id = id
		self.__display_name = display_name
		self.__type = type

	@abstractmethod
	def get_id(self):
		return self.__id

	@abstractmethod
	def get_displayName(self):
		return self.__display_name

class ToggleProperty(Property):
	def __init__(
			self,
			id: str,
			display_name: str,
			value: bool,
			flag: bool
	):
		super(ToggleProperty, self).__init__(id, display_name, PropertyType.TOGGLE)
		self.__flag = flag
		self.__value = value

	def get_id(self):
		return super(ToggleProperty, self).get_id()

	def get_displayName(self):
		return super(ToggleProperty, self).get_displayName()

	def get_value(self):
		return self.__value

	def set_value(self, value):
		self.__value = value

	def get_flag(self):
		return self.__flag

	def set_flag(self, flag):
		self.__flag = flag

	def updateFlag(self, evt):
		self.set_flag(True)

class SingleChoiceProperty(Property):
	def __init__(
			self,
			id: str,
			display_name: str,
			flag: bool,
			options: Tuple[str, ...],
			selected_option: Optional[str] = None
	):
		super(SingleChoiceProperty, self).__init__(id, display_name, PropertyType.SINGLE_CHOICE)
		self.options = options
		self.__flag = flag
		self.__selected_option = selected_option if selected_option in options else options[0]

	def get_id(self):
		return super(SingleChoiceProperty, self).get_id()

	def get_displayName(self):
		return super(SingleChoiceProperty, self).get_displayName()

	def get_flag(self):
		return self.__flag

	def set_flag(self, flag):
		self.__flag = flag

	def get_value(self):
		return self.__selected_option

	def set_value(self, option):
		self.__selected_option = option

	def updateFlag(self, evt):
		self.set_flag(True)

class MultipleChoiceProperty(Property):
	def __init__(
			self,
			id: str,
			display_name: str,
			flag: bool,
			options: Tuple[str, ...],
			selected_options: Optional[Tuple[str, ...]] = (1, 3)
	):
		super(MultipleChoiceProperty, self).__init__(id, display_name, PropertyType.MULTIPLE_CHOICE)
		self.__flag = flag
		self.options = options
		self.__selected_options = selected_options if all(
			option in options for option in selected_options
		) else tuple()


	def get_id(self):
		return super(MultipleChoiceProperty, self).get_id()

	def get_displayName(self):
		return super(MultipleChoiceProperty, self).get_displayName()

	def get_value(self):
		return self.__selected_options


	def set_value(self, options):
		self.__selected_options = options

	def get_flag(self):
		return self.__flag

	def set_flag(self, flag):
		self.__flag = flag

	def updateFlag(self, evt):
		self.set_flag(True)

class EditableProperty(Property):

	def __init__(
			self,
			id: str,
			display_name: str,
			flag: bool,
			value: Optional[str] = None,
	):
		super(EditableProperty, self).__init__(id, display_name, PropertyType.EDITABLE)
		self.__value = value
		self.__flag = flag

	def get_id(self):
		return super(EditableProperty, self).get_id()

	def get_displayName(self):
		return super(EditableProperty, self).get_displayName()

	def get_value(self):
		return self.__value

	def set_value(self, options):
		self.__value = options

	def get_flag(self):
		return self.__flag

	def set_flag(self, flag):
		self.__flag = flag

	def updateFlag(self, evt):
		log.info("========================== Edit text control  ==+> {}  {}".format(self.get_value(), self.get_displayName()))
		self.set_flag(True)


mutation_options = ("","heading.1", "heading.2", "heading.3", "labelled")
formmode_options = ("","Inchangé", "Activé", "Désactivé")
PROPS_LEN = 7
propertiesList = [
	ToggleProperty(
		"sayName",
		"Dire le nom de la règle",
 		False,
		False
	),
	ToggleProperty(
		"skip",
		"Ignorer la page suivante",
		False,
		False
	),
	ToggleProperty(
		"Multiple",
		"Résultats Multiples",
		False,
		False,
	),
	EditableProperty(
		"customName",
		"Nom personnalisé",
		False
	),
	EditableProperty(
		"customValue",
		"Message personnalisé",
		False
	),
	SingleChoiceProperty(
		"formMode",
		"Activer le mode formulaire",
		False,
		formmode_options

	),
	SingleChoiceProperty(
		"mutation",
		"Transformation",
		False,
		mutation_options
	)
]












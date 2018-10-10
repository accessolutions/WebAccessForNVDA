
# Web Access pour NVDA - User Guide

Version 2018.10.10

Copyright (C) 2015-2018 [Accessolutions](http://accessolutions.fr)


## The web modules

The web modules allow, interactively, to create NVDA scripts to ease and customize browsing web sites and business web applications.


### Creating a web module

Set the focus on one of the pages of the web site for which you want to create a module.

Press NVDA+W.  

Select "New web module" in the menu. 

The dialog "New web module" opens.

In the field "Web module name", give a meaningful name thet identifies this web site. (This name must conform to Windows file names syntax)

In the drop-down list "URL", choose the part of the URL which is common to all the pages of the intended site. Press the up and down arrow keys to get the possible subsets of the current URL.
In most cases, you may use the first proposal as it contains only the first part of the URL up to the first slash ("/").

In the drop-down list "Window title", you can enter a part of the title of the browser window. 
Only use this parameter if the match by URL cannot identify the web site. In most cases, you should leave this field empty.

Click the "OK" button to create the module.

A file with a ".json" extension is created in the "webModule" folder in the NVDA user folder. 


### Modifying a web module

Set the focus on one of the pages of the web site for which you want to modify the module.

Press NVDA+W.

Select "Edit the web module" in the menu.

Alternatively, select "Manage web modules" in the menu.

The dialog "Web modules manager" opens.

Select the module you want to modify or delete, and click the "Edit" or "Delete" buttons, respectively. 


## Module rules

A web module is made of a set of rules.
Each rule is used to identify a specific element on a web page and associate it with keyboard shorcuts and actions.


### Creating a rule

To create a rule, first set the browse mode cursor in the web page on the element for which you want to create a rule.

Press NVDA+W.

In the menu, select "New rule".

In the field "Rule name", give a name to this new rule.
This name will be automatically announced when you will later press the keyboard shortcut assigned to this rule.


#### Filtering criteria

The next fields are used to define the criteria identifying the element for which to apply the rule. One or more criterion can be specified.
On each drop-down list, by pressing on the down arrow key, you will get proposals from most to least specific to the current element.
It is usually advisable to choose amongst the first proposals.
Technically, these proposals are the attributes of the HTML ancestors to the current HTML element.  


##### Text

In the "Text" field, enter a string of text to look for.
If the string begins with a left angle bracket ("<"), the search will look at the previous element. This is especially useful to look up an edit field whose label is placed just before it.


##### Role

In the "Role" drop-down list, select one of the roles proposed for this element.


##### Tag

In the "Tag" drop-down list, select the HTML tag used for this element.

It is usually enough to select only either a role or a HTML tag.


##### ID

In the "ID" drop-down list, select one of the strings that identifies the most specifically the element, if any.


##### Classe

In the "class" drop-down list, select one of the strings that identifies the most specifically the element, if any.

As is usual for file names, the strings in "ID" and "Class" fields may contain an asterisk ("*") to allow for matching a substring.


##### SRC

The field "SRC" is useful only for image elements with a source filename or URL. 


##### Context

Select in the drop-down list a rule which is defined as a context rule.
The current rule will then be active only if the context rule is matched.

You can negate this condition by entering an exclamation mark ("!") before the name of the context rule.


##### Index

If several elements match the criteria for the rule, this field sets the index of the element to consider as the intended one.


##### Multiple results available

By default, if several elements on the page meet the criteria for the rule, only the first one will be considered. All the other matches are ignored.

If this box is checked, then all of the matching elements are considered. 
That is, pressing the page up and page down keys will allow to successively go to each of the elements matching the rule.
Nevertheless, this does not change the behavior of the assigned keyboard shorcut, which still applies to the sole first matched element. 
It is advised to check this box for a rule matching search results on a given page, otherwise only the first result would be identified. 


#### Keyboard shortcuts

Click on the "Add a keyboard shortcut" button.

Press the keyboard shorcut you want to assign.

In the opening menu, select the action you want to associate to this keyboard shorcut.


The available actions are:

* "Move to" : Move the browse mode cursor to the element and announce it.
* "Speak" : Announce the text of the element, but do not move the cursor.
* "Say all" : Move the browse mode cursor to the element and start reading aloud all the text from this position.
* "Activate" : Perform a mouse click on the element.
* "Mouse move" : Move the mouse cursor onto this element, but do not click.

Several keyboard shortcuts, with different actions, can be assigned to the same rule.


##### Special handling of the "Speak" action :

When a keyboard shorcut is assigned to the "Speak" action, pressing twice quickly this same shorcut will perform the "Move to" action.

This may be used to define a shorcut to read aloud an error message shown on the web page without moving, while still being able to move
to this message for a more precise reading with braille or speech commands, all while only having one shortcut to remember.


#### Automatic actions

The automatic action is not bound to a keyboard shorcut. It executes automatically when an element matching the rule criteria is found on the page. This can be used to automatically move the cursor at a specific starting position when a page loads. Alternatively, it also allows to automatically read aloud an error message as it appears.

Caution: While very useful, the automatic actions can lead to seemingly unpredictable browsing behavior if not defined carefully.
The "Speak" action is most likely harmless. 
The actions "Move to" and "Say all" can lead to blocking the user.
The "Activate" action should be avoided unless strictly necessary. 


#### Activate form mode

This checkbox specifies if the form mode should be automatically activating upon moving to the element.
By default, it is checked when a rule is created for an edit field.


#### Speak rule name

This checkbox sets whether the name of the rule should be anounced when activated.
It is checked by default and can be unchecked to avoid making a double announce when the rule name and the text of the element are alike.
  

#### Skip with Page Down

This checkbox sets whether the cursor should stop on the element matching this rule when pressing the Page Up and Page Down keys.


#### Page title

This checkbox sets whether this rule is used as page title when pressing NVDA+T.


#### Is a context

This checkbox sets whether this rule is to be used as defining a context for other rules.


## Best practice

In order the end user of a module to easily learn, understand, remember the keyboard shortcuts and the structure of the pages,
it is advised to the module developper to adhere, as much as possible, to a few recommandations.


### Be consistent while choosing keyboard shortcuts

The same shorcut should have the same effect on every page of web site. 
By example, Control+Shift+B should lead to the main button bar, whatever the page.

Any keyboard shorcut can be defined, but we advise on using Control+Shift+Letter to avoid as much as possible conflicting with other existing use.


### Defining the zones that structure a page

Most web sites use a common squeleton for all of their pages.
This layout is made for an immediate visual understanding, but can often be cumbersome to grasp with braille or speech.

Not only do keyboard shortcuts let the user move faster, but they can also allow him/her a better understanding of the page structure.   

Thus, it is advised to always use the same keyboard shorcuts for the main zones that compose a web site.

Example : 

* Control+Shift+L: Move to the beginning of the main content of the page.  
* Control+Shift+E: Move to the first edit field of the main form.
* Control+Shift+H: Move to the main menu (of the web site, not the browser).  
* Control+Shift+O: Move to the tab captions (for page with inner tabs, not the browser tabs).  
* Control+Shift+B: Move to the main button bar (usually at the bottom of the main form).  
* Control+Shift+A: Move to the tree navigation control (often shown on the left side of the page).  
* Control+Shift+F: Move to the main search field, if any, in form mode.  
* Control+Shift+M: Announce an error or informative message.
* Control+Enter: Click on the main form validation button.  

This list is of course neither mandatory nor complete.


### Handling error and informative messages

Error or informative messages are often pretty difficult to detect with a screen reader when not properly advertised in Aria.
Should they be displayed while editing a field or after form validation, an automatic action can typically be used to announce them as soon as they are detected.

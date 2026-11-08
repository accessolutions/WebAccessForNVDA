# Web Access pour NVDA -- Quickstart Guide

Copyright (C) 2015-2024 [Accessolutions](http://accessolutions.fr)


## The web modules

The web modules allow, interactively, to create NVDA scripts to ease and
customize browsing web sites and business web applications.


### Creating a web module

Set the focus on one of the pages of the web site for which you want to create a
module.

Press `NVDA+W`.

Select "New web module" in the menu. 

The dialog "New web module" opens.

In the field "Web module name", give a meaningful name thet identifies this web
site. (This name must conform to Windows file names syntax)

In the drop-down list "URL", choose the part of the URL which is common to all
the pages of the intended site. Press the up and down arrow keys to get the
possible subsets of the current URL.
In most cases, you may use the first proposal as it contains only the first part
of the URL up to the first slash ("/").

In the drop-down list "Window title", you can enter a part of the title of the
browser window. 
Only use this parameter if the match by URL cannot identify the web site. In
most cases, you should leave this field empty.

Click the "OK" button to create the module.

A file with a ".json" extension is created in the "webModule" folder in the NVDA
user folder. 


### Modifying a web module

Set the focus on one of the pages of the web site for which you want to modify
the module.

Press `NVDA+W`.

Select "Edit the web module" in the menu.

Alternatively, select "Manage web modules" in the menu.

The dialog "Web modules manager" opens.

Select the module you want to modify or delete, and click the "Edit" or "Delete"
buttons, respectively.


### Configuration profiles

A web module can activate an NVDA configuration profile while it is active, that
is while the focus is in a page it applies to.
It is deactivated as soon as the focus leaves the page, eg. when moving to the
address bar, to another tab or to another application.

The profile is chosen in the "Configuration profile" field of the web module
editor. It can be either a regular NVDA profile or a profile embedded in the web
module. Embedded profiles are stored in the web module itself, so that they are
distributed along with it.

Embedded profiles are managed in the "Embedded profiles" list of the web module
editor:

 - "New..." creates an empty embedded profile.
 - "Rename..." and "Delete" rename or delete the selected embedded profile.
   This is not possible for profiles inherited from a web module provided by an
   add-on.
 - "Save and edit settings..." saves the web module and opens the NVDA settings
   with the selected embedded profile activated, until they are closed.
   The changes are then saved in the web module.

While an embedded profile is active, the changes made in NVDA settings apply to
it, as for any NVDA profile. They are saved in the web module along with the
NVDA configuration.
For a web module provided by an add-on, only the differences are saved in your
user configuration, so that updates of the add-on still apply.

A profile can also be activated in a given context only, using the
"Configuration profile" property of a rule. See the related section below.

Profiles activated by web modules are stacked above the profile of the
application, ie. the web browser, and below a manually activated profile.
If several apply, the most specific takes precedence: The one of a sub-module
over the one of its parent, the one of a rule over the one of the web module.

Developers of custom web modules can also activate profiles from Python code:

 - Override `getProfiles(context)` to return profile references depending on the
   context: The focused object, the caret position, the matched page types or the
   rules results at the caret.
 - Call `pushProfile(ref)` to activate a profile until the returned handle is
   released. The handle can be used as a context manager:
   `with self.pushProfile("myProfile"): ...`
 - Call `requestProfileUpdate()` when `getProfiles` would return a different
   result.

These features require `API_VERSION = "0.8"`.


## Module rules

A web module is made of a set of rules.
Each rule is used to identify a specific element on a web page and act upon it.

There are a few rule types, allowing to structure navigation through the web
application. We will focus here on the "Marker" rule type, which allows to bind
keyboard gestures and automatic actions.


### Creating a rule

To create a rule, first set the browse mode cursor in the web page on the
element for which you want to create a rule.

Press `NVDA+W`.

In the menu, select "New rule".

A window featuring multiple categories is opened, with the General category highlighted.

In the field "Rule type", select "Marker".

In the field "Rule name", give a name to this new rule.
This name will be automatically announced when you will later press the keyboard
shortcut assigned to this rule.


#### Filtering criteria

Switch to the "Criteria" category.

Click on "New..." button (or press ALT+n).

The next fields are used to define the criteria identifying the element for
which to apply the rule. One or more criterion can be specified.
On each drop-down list, by pressing on the down arrow key, you will get
proposals from most to least specific to the current element.
It is usually advisable to choose amongst the first proposals.
Technically, these proposals are the attributes of the HTML ancestors to the
current HTML element.  


##### Search mode

In the full mode of the criteria set editor (`F12`), the "Search mode" field
sets how the criteria are matched:

 - "Simple" (default): Each criterion can apply to the element or to one of its
   parents. For example, "Tag: li" and "Class: toto" also find a `li` element
   within a `div` element having the class "toto". This is the easiest mode,
   suitable for most rules.
 - "Same element": All the criteria apply to the found element itself. For
   example, "Tag: li" and "Class: toto" only find `li` elements having the class
   "toto". The "Text" criterion then means "whose content contains this text".
 - "CSS selector": The structure of the document is described by a CSS
   selector, which replaces the "Tag", "ID", "Class" and "Image source" fields.
   The other fields still apply, to the found element itself.

The supported CSS selectors are:

 - Selector lists: `h2, h3`
 - Combinators: descendant (`nav a`), child (`ul > li`), next sibling
   (`h2 + p`) and subsequent siblings (`h2 ~ p`)
 - Type (`li`), universal (`*`), ID (`#main`) and class (`.item`) selectors
 - Attribute selectors: `[href]`, `[href="/home"]`, `[class~=item]`,
   `[lang|=en]`, `[href^="https"]`, `[src$=".png"]`, `[href*=login]`, with an
   optional `i` flag for a case-insensitive comparison (`[type=submit i]`)
 - Structural pseudo-classes: `:root`, `:empty`, `:first-child`,
   `:last-child`, `:only-child`, `:first-of-type`, `:last-of-type`,
   `:only-of-type`, `:nth-child()`, `:nth-last-child()`, `:nth-of-type()` and
   `:nth-last-of-type()`, accepting `odd`, `even` or `An+B` (eg. `2n+1`)
 - Logical pseudo-classes: `:not()`, `:is()`, `:where()` and `:has()`, eg.
   `li:has(> a.active)`

For example: `ul#menu > li.toto`, `table.results tr:nth-child(odd)`,
`nav li:not(.disabled) > a[href]`.

Like the other fields, the "CSS selector" field suggests values computed from
the element at the cursor: a selector designating this very element, one
designating similar elements (eg. all the items of the same list), then
selectors designating its closest ancestors.

In the inspector (`F8` from the rule or criteria set editors), `F11` copies to
the clipboard a CSS selector designating the inspected element, and `Shift+F11`
a selector relative to the node marked with `F9` (one of its ancestors).

Pseudo-elements and the pseudo-classes depending on the state of the element
(`:hover`, `:checked`…) are not supported: Use the "States" field instead.
Only the elements exposed by the browser to the screen reader are considered,
which can occasionally differ from the source code of the page (eg. for some
layout containers), affecting `>`, `+` and the structural pseudo-classes.

This field is not shown in the simple mode of the editors, nor in the wizard,
unless the criteria already use another mode.


##### Text

In the "Text" field, enter a string of text to look for.
If the string begins with a left angle bracket ("<"), the search will look at
the previous element. This is especially useful to look up an edit field whose
label is placed just before it.


##### Role

In the "Role" drop-down list, select one of the roles proposed for this element.


##### Tag

In the "Tag" drop-down list, select the HTML tag used for this element.

As the concepts of roles and tags mostly overlap, one might want to set either
one or the other, but rarely both.


##### ID

In the "ID" drop-down list, select one of the strings that identifies the most
specifically the element, if any.


##### Class

In the "class" drop-down list, select one of the strings that identifies the
most specifically the element, if any.

As is usual for file names, the strings in "ID" and "Class" fields may contain
an asterisk ("*") to allow for matching a substring.


##### SRC

The field "SRC" is useful only for image elements with a source filename or URL. 


##### Index

If several elements match the criteria for the rule, this field sets the index
of the element to consider as the intended one.


Once the criteria are set, hit `enter` or tab to the "OK" button to close the
dialog.


#### Alternatives

A rule can have several alternative sets of criteria, for example when the same
element is coded differently from one page to another.
Each alternative can override the properties and keyboard shortcuts of the
rule.

The "When several alternatives match" field, in the "Criteria" category of the
rule editor, sets how the alternatives combine:

 - "Use only the first matching alternative" (default): The alternatives are
   evaluated in order, and the first one finding at least one element is the
   only one considered.
 - "Use all matching alternatives": The elements found by all the alternatives
   are considered, in their order of appearance on the page. An element found
   by several alternatives is considered only once, with the properties and
   keyboard shortcuts of the first of them.


#### Keyboard shortcuts

1. Switch to the "Input Gestures" category.
2. Choose "New..." button (or `ALT+N`).
3. Press the keyboard shorcut you want to assign.
4. Pair an action. The available actions are:

	* "Move to" : Move the browse mode cursor to the element and announce it.
	* "Speak" : Announce the text of the element, but do not move the cursor.
	* "Say all" : Move the browse mode cursor to the element and start reading aloud all the text from this position.
	* "Activate" : Perform a mouse click on the element.
	* "Mouse move" : Move the mouse cursor onto this element, but do not click.

Several keyboard shortcuts, with different actions, can be assigned to the same
rule.


##### Special handling of the "Speak" action :

When a keyboard shorcut is assigned to the "Speak" action, pressing twice
quickly this same shorcut will perform the "Move to" action.

This may be used to define a shorcut to read aloud an error message shown on the
web page without moving, while still being able to move
to this message for a more precise reading with braille or speech commands, all
while only having one shortcut to remember.


#### Automatic actions

The automatic action is not bound to a keyboard shorcut. It executes
automatically when an element matching the rule criteria is found on the page.
This can be used to automatically move the cursor at a specific starting
position when a page loads. Alternatively, it also allows to automatically read
aloud an error message as it appears.

Caution: While very useful, the automatic actions can lead to seemingly
unpredictable browsing behavior if not defined carefully.
The "Speak" action is most likely harmless. 
The actions "Move to" and "Say all" can lead to blocking the user.
The "Activate" action should be avoided unless strictly necessary. 


#### Properties

##### Multiple results available

By default, if several elements on the page meet the criteria for the rule, only
the first one will be considered. All the other matches are ignored.

If this box is checked, then all of the matching elements are considered. 
That is, pressing the page up and page down keys will allow to successively go
to each of the elements matching the rule.
Nevertheless, this does not change the behavior of the assigned keyboard
shorcut, which still applies to the sole first matched element. 
It is advised to check this box for a rule matching search results on a given
page, otherwise only the first result would be identified. 


#### Activate form mode

This checkbox specifies if the form mode should be automatically activating upon
moving to the element.
By default, it is checked when a rule is created for an edit field.


#### Speak rule name

This checkbox sets whether the name of the rule should be anounced when
activated.
It is unchecked by default, which avoids making a double announce when the rule
name and the text of the element are alike.
  

#### Skip with Page Down

This checkbox sets whether the cursor should stop on the element matching this
rule when pressing the Page Up and Page Down keys.


#### Configuration profile

This property activates an NVDA configuration profile, either an NVDA profile or
a profile embedded in the web module:

 - For a "Page type" rule, on the whole page while this page type is matched.
 - For a "Zone", "Marker" or "Parent element" rule, while the caret is within
   the matched element.

As other properties, it can be set for a given alternative only, which allows
to activate a profile depending on the context page type, title or parent
element of this alternative.


#### Overriding properties and shortcuts for an alternative

When a rule has several alternative sets of criteria, each alternative can
define its own properties and keyboard shortcuts, overriding those of the rule
for the elements it matches.

In the criteria set editor, switch to the full mode (`F12`, or the "Properties
and shortcuts specific to this criteria set" button) to reach the "Input
Gestures" and "Properties" categories.

Properties:

 - Only the properties listed in the "Properties" category are overridden,
   the other ones are inherited from the rule.
 - Choose "New" (`ALT+N`) to override a property. Its initial value differs from
   the value of the rule: The opposite for a checkbox, "No action" or "None" if
   the rule defines an automatic action or a transform, an empty text if the
   rule defines a custom name or message.
   Hence, an alternative can cancel an automatic action defined on the rule.
 - An override keeps applying even if its value equals that of the rule, so
   that it is not affected by later changes on the rule.
 - Choose "Delete" (or press `DELETE` on the list) to inherit again the value
   of the rule.

Keyboard shortcuts:

 - The shortcuts of the rule are listed as "inherited from the rule".
 - A shortcut defined on the alternative adds to those of the rule, or replaces
   the one of the rule for the same key combination.
 - "Disable" disables a shortcut of the rule for this alternative, choosing
   either to let the key combination reach the web page as if it was not
   assigned, or to announce that the shortcut is not available here.
   "Restore" enables it again.




## Best practice

In order the end user of a module to easily learn, understand, remember the
keyboard shortcuts and the structure of the pages,
it is advised to the module developper to adhere, as much as possible, to a few
recommandations.


### Be consistent while choosing keyboard shortcuts

The same shorcut should have the same effect on every page of web site. 
By example, Control+Shift+B should lead to the main button bar, whatever the
page.

Any keyboard shorcut can be defined, but we advise on using Control+Shift+Letter
to avoid as much as possible conflicting with other existing use.


### Defining the zones that structure a page

Most web sites use a common squeleton for all of their pages.
This layout is made for an immediate visual understanding, but can often be
cumbersome to grasp with braille or speech.

Not only do keyboard shortcuts let the user move faster, but they can also allow
him/her a better understanding of the page structure.   

Thus, it is advised to always use the same keyboard shorcuts for the main zones
that compose a web site.

Example : 

* Control+Shift+L: Move to the beginning of the main content of the page.  
* Control+Shift+E: Move to the first edit field of the main form.
* Control+Shift+H: Move to the main menu (of the web site, not the browser).  
* Control+Shift+O: Move to the tab captions (for page with inner tabs, not the
browser tabs).  
* Control+Shift+B: Move to the main button bar (usually at the bottom of the
main form).  
* Control+Shift+A: Move to the tree navigation control (often shown on the left
side of the page).  
* Control+Shift+F: Move to the main search field, if any, in form mode.  
* Control+Shift+M: Announce an error or informative message.
* Control+Enter: Click on the main form validation button.  

This list is of course neither mandatory nor complete.


### Handling error and informative messages

Error or informative messages are often pretty difficult to detect with a screen
reader when not properly advertised in Aria.
Should they be displayed while editing a field or after form validation, an
automatic action can typically be used to announce them as soon as they are
detected.

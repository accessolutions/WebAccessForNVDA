# Web Access for NVDA

[Web application modules](http://webmodules.org/) support for modern or complex web sites.

Copyright (C) 2015-2018 Accessolutions (http://accessolutions.fr)

## License

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

See the file COPYING.txt at the root of this distribution for more details.


## Requirements

This is an add-on targeting the NVDA screen reader version 2016.2 or greater. 

Additionally, the following software is required in order to build this add-on:

- a Python distribution (2.7 or greater 32 bits is recommended). Check the [Python Website](http://www.python.org) for Windows Installers.
- SCons - [Website](http://www.scons.org/) - version 2.1.0 or greater. Install it using **pip** or grab an windows installer from the website.
- GNU Gettext tools. You can find windows builds [here](http://gnuwin32.sourceforge.net/downlinks/gettext.php).
- Markdown-2.0.1 or greater, to convert documentation files to HTML documents. You can [Download Markdown-2.0.1 installer for Windows](https://pypi.python.org/pypi/Markdown/2.0.1) or get it using `pip install markdown`.


## Virtual environment

The recommended way to setup a Python build environment is to use `virtualenv`.

It is especially true when using different versions and flavours of the Python
interpreter or working on projects that might have conflicting dependencies. 

In this section, we will assume your Python 2.7 32 bits interpreter is *not*
in the `PATH` environment variable. In later sections, we will assume it
either is or you activated (as we recommend) the dedicated virtual environment.

The following commands use our dev team installation paths, amend according to
your needs.

 - First, install `virtualenv`:
 	
	```
	D:\dev\Python27-32\Scripts\pip install virtualenv
	```

 - Then, create a home folder for your virtual environments:
 	
	```
	md D:\dev\venv
	```

 - Create a new virtual environment:
 	
	```
	D:\dev\Python27-32\Scripts\virtualenv.exe D:\dev\venv\nvda-addon
	```
	
	We will then need to inject in this virtual environment the Python dependencies
	for the targeted release of NVDA.

 - Download the NVDA misc deps package:
[Link for release 2017.4](https://github.com/nvaccess/nvda-misc-deps/archive/3707b8e4052670c454343e32d8de3f0b8beab642.zip)
	
	And uncompress it in a directory of your choice.
	
	You might of course as well clone the NVDA git repo (with submodules) to obtain these.

 - Then, create a `.pth` file in the `site-packages` of your virtual environment with
a single line containing the path to the `python` directory contained in NVDA misc deps.
	
	From the `python` directory of the uncompressed NVDA misc deps archive, run:
	
	```
	cd > D:\dev\venv\nvda-addon\Lib\site-packages\nvda-misc-deps.pth
	```
	
	Note that, even if you invoke a Windows Python from Git Bash (as we do), this path
	*must* be in Windows format. That is, from the same `python` directory:
	
	```
	cygpath -w $(pwd) > /d/dev/venv/nvda-addon/Lib/site-packages/nvda-misc-deps.pth
	```

 - Copy the file `scons.py` from the root of this project to the `Scripts`
 directory of the virtual environment:
 	
 	This is only a convenience script allowing easier invocation of the SCons found
 	in NVDA misc deps. 

 - Then, activate the virtual environment.
 	
	```
	D:\dev\venv\nvda-addon\Script\activate.bat
	```
	
	or from Git Bash:
	
	```
	. /d/dev/venv/nvda-addon/Scripts/activate
	```
	
	Note the leading period, meaning the script is sourced, not run.
	
	Your command prompt should now be prefixed with the name of the virtual
	environment in parenthesis.
	
	Any subsequent command will be run in the context of this virtual
	environment.
	The corresponding `python.exe` is now the first in your `PATH` environment
	variable, whether another one was already present or not.
	Furthermore, packages installed via `pip` will land in this virtual
	environment instead of the base Python installation.
	
	You can later run `deactivate` to leave this virtual environment, but let's
	first finish to set it up.

 - Install the remaining build dependencies:
 	
	```
	pip install Markdown>=2.0.1
	```
	
The new `nvda-addon` virtual environment is now ready to build our addon.

Note that it can also be used by many IDEs, such as PyDev for Eclipse, as
the interpreter for the project. 


## Build

This add-on is based upon the
[addonTemplate](https://bitbucket.org/nvdaaddonteam/addontemplate)
from the NVDA Add-ons Team and, as such, is built using SCons.


Depending on your environment, your SCons command might be either `scons.py`
or `scons.bat`. As a convention, `scons` will be used within this document.


The following commands are to be run from the project root folder. 


### Generate Gettext POT translation file

```
scons pot
```


The resulting `WebAccess.pot` file will be created (or updated) in the project
root folder.


### Build the installation package

```
scons
```


The resulting `WebAccess-<version>.nvda-addon` file will be created (or
updated) in the project root folder.


### Cleaning

In order to ease in place execution during development, the manifest
and documentation files generated by the build process are stored within the
source tree, instead of a separate `build` folder.

To get rid of them:

```
scons -c
```



To also get rid of the generated Gettext POT translation file:

```
scons -c pot
```


## Install

This project follows NVDA standards regarding installation of `.nvda-addon`
files.


However, one might want to use a development version executed directly from
the source tree.

A possible solution is to use file-system junction. Run the following command
from the current user config `addons` directory:

```
mklink /J WebAccess <path to the addon folder in the source tree>
```

Note: Local administrator privileges are required.


In this configuration, run the following command from the same
directory to remove the junction, uninstalling the development version:

```
rd WebAccess
```

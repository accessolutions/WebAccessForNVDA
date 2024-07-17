# Web Access for NVDA - Contributing

[Web application modules](http://webmodules.org/) support for modern or complex web sites.

This is an add-on targeting the NVDA screen reader version 2021.1 or greater. 


Copyright (C) 2015-2024 Accessolutions (http://accessolutions.fr)

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


## Setting-up the build environment

All commands in this section must be run from the root folder of this project.


### Requirements

The following software is required in order to build this add-on:


#### Python

NVDA currently uses Python 3.11 32 bits. However, NVDA 2021.1 used Python 3.7 32 bits.
This add-on does not include binary files, hence any version greater or equal to 3.7 can be used.  
Check the [Python website](http://www.python.org) for Windows Installers.

This guide assumes you installed the Python Launcher alongside your distribution of Python as this is
a default option with modern Windows distributions.
If not, amend accordingly.


#### GNU Gettext tools

You can either use the version bundled with the NVDA source code (detailed later on) or download it from
[here](https://mlocati.github.io/articles/gettext-iconv-windows.html) and ensure the `bin` folder is in your
`PATH` environment variable.


### Virtual environment

The recommended way to setup a Python build environment is to use a virtual environment.

It is especially true when using different versions and flavours of the Python
interpreter or working on projects that might have conflicting dependencies. 

If you plan on contributing to several add-ons for NVDA, we advise you create a unique virtual
environment in a separate folder. For simplicity, this guide assume the virtual environment
is created in the root folder of this project.


#### Creation

```sh
py -3.11-32 -m venv .venv
```

	
#### (Optional) Inject references

We will inject in the new virtual environment references to the targetted
NVDA source code and its Python dependencies.

This step is not strictly necessary, but it eases IDE integration and the
use of code linters / style checkers.


Create a text file named eg. `nvda.pth` in the folder `.venv\Lib\site-packages` with
the following content, amending according to the actual location on your system:

```
D:\dev\src\nvda\source
D:\dev\src\nvda\miscDeps\python
```


#### (Optional) Use GNU Gettext bundled with the NVDA source code

The source of NVDA comes with the necessary binaries from GNU Gettext.

If you did not download GNU Gettext and set its `bin` folder in your `PATH` environment variable,
you can modify the activation script of the virtual environment to use the version bundled
with the NVDA source code.

##### If using the Windows Command Prompt

Edit the file `.venv\Scripts\activate.bat` with a text editor and locate the line

```
set PATH=%VIRTUAL_ENV%\Scripts;%PATH%
```

Replace it with (amend according to the actual path on your system):

```
set PATH=%VIRTUAL_ENV%\Scripts;D:\dev\src\nvda\miscDeps\tools;%PATH%
```


##### If using Git Bash

Edit the file `.venv\Scripts\activate` with a text editor and locate the line:

```
PATH="$VIRTUAL_ENV/Scripts:$PATH"
```

Replace it with (amend according to the actual path on your system):

```
PATH="$VIRTUAL_ENV/Scripts:/d/dev/src/nvda/miscDeps/tools:$PATH"
```


#### Activate the virtual environment

If using the Windows Command Prompt:

```sh
.venv\Scripts\activate.bat
```

If using Git Bash:
```sh
. .venv/Scripts/activate
```

Note the leading period, meaning the script is sourced, not run.


In both cases, your command prompt should now be prefixed with the name of the virtual
environment in parenthesis, eg. `(.venv)`.


Any subsequent command will be run in the context of this virtual
environment.

The corresponding `python.exe` is now the first in your `PATH` environment
variable, whether another one was already present or not.

Invocation using the Python Launcher (`py.exe`) also uses this very interpreter.

Furthermore, packages installed via `pip` will land in this virtual
environment instead of the base Python installation.


To leave this virtual environment, you can later run `deactivate` or simply
close the console window, but let's first finish to set it up.


#### Install dependancies

```sh
pip install -r requirements.txt
```


The virtual environment is now ready to build our addon.


Note that it can also be used by many IDEs, such as PyDev for Eclipse, as
the interpreter for the project. 


## Building

All commands in this section must be run from the base directory of the source code for this project
after first activating the virtual environment.


This add-on is based upon the
[addonTemplate](https://bitbucket.org/nvdaaddonteam/addontemplate)
from the NVDA Add-ons Team and, as such, is built using SCons.


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

In order to ease in-place execution during development, the manifest
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

This project follows NVDA standards regarding installation of `.nvda-addon` files.


However, one might want to use a development version executed directly from
the source tree.

A possible solution, using the Windows Command Prompt, is to use file-system
junction. Run the following command from NVDA's current user config `addons` folder:

```
mklink /J WebAccess-dev <path to the addon folder in the source tree>
```

Note: Local administrator privileges are required.


In this configuration, run the following command from the same
directory to remove the junction, uninstalling the development version:

```
rd WebAccess-dev
```

Note: Do not attempt a recursive deletion, or the target source tree will be
deleted too.


Alternatively, using Git Bash:

```
ln -s WebAccess-dev <path to the addon folder in the source tree>
```

and

```
rm WebAccess-dev
```

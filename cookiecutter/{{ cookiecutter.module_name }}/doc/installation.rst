Installation
============

Prerequisites
-------------

* Python 3.5 or later (http://www.python.org/)
* See the ``setup.py`` file for python package dependencies.
* See the ``tryton.cfg`` file for tryton module dependencies.


Using pip
---------

The easiest way to install this module and it's dependencies is directly from
the Python Package Index:

.. code-block:: bash

    pip3 install {{ cookiecutter.package_name }}


Using Sources
-------------

Alternatively, you can clone the *{{ cookiecutter.tryton_modules_repository_name }}* repository, and install the
module from there:

.. code-block:: bash

    hg clone {{ cookiecutter.tryton_modules_repository_url }}
    cd {{ cookiecutter.tryton_modules_repository_name }}/{{ cookiecutter.module_name }}
    python3 setup.py install


Other Information
-----------------

You may need administrator/root privileges to perform the installation, as the
install commands will by default attempt to install the module to the system
wide Python site-packages directory on your system.

For advanced options, please refer to the easy_install and/or the distutils
documentation:

* https://docs.python.org/3/installing/index.html
* http://peak.telecommunity.com/DevCenter/EasyInstall

To use without installation, extract the archive into ``trytond/modules`` with
the directory name ``{{ cookiecutter.module_name }}``.

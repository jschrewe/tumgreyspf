#!/usr/bin/python

from distutils.core import setup

import tumgreyspfsupp

setup(
    name = 'tumgreyspf',
    maintainer = 'Jan Schrewe',
    maintainer_email = 'jan@schafproductions.com',
    version = tumgreyspfsupp.__version__,
    license = 'GPL v2',
    py_modules = ['tumgreyspfsupp'],
    scripts = [
        'tumgreyspf',
        'tumgreyspf-clean',
        'tumgreyspf-stat',
        'tumgreyspf-configtest',
    ],
    data_files = [
        ('/etc/tumgreyspf/', ['tumgreyspf.conf', ]),
    ],
)

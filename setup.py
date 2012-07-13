#!/usr/bin/python

from distutils2.core import setup

setup(
    name = 'tumgreyspf',
    maintainer = 'Jan Schrewe',
    maintainer_email = 'jan@schafproductions.com',
    version = 'mongo-0.1',
    license = 'GPL v2',
    include_package_data=True,
    requires=['ipaddr', 'pymongo',],
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

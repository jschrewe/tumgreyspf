#!/usr/bin/python

from setuptools import setup

setup(
    name = 'tumgreyspf',
    maintainer = 'Jan Schrewe',
    maintainer_email = 'jan@schafproductions.com',
    version = 'mongo-0.1',
    license = 'GPL v2',
    include_package_data=True,
    install_requires=['ipaddr', 'pymongo',],
    py_modules = ['tumgreyspfsupp'],
    scripts = [
        'tumgreyspf',
        'tumgreyspf-clean',
        'tumgreyspf-stat',
        'tumgreyspf-configtest',
        'tumgreyspf-whitelist',
    ],
    data_files = [
        ('/etc/tumgreyspf/', ['tumgreyspf.conf', ]),
    ],
)

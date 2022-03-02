#!/usr/bin/env python

from distutils.core import setup

setup(name='lbrc_selenium',
    version='1.0',
    description='NIHR Leicester BRC Selenium Helper',
    author='Richard Bramley',
    author_email='rabramley@gmail.com',
    url='https://github.com/LCBRU/lbrc_selenium/',
    packages=['lbrc_selenium'],
    install_requires=[
        'selenium',
    ],
)
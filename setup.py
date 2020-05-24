#!/usr/bin/env python
"""
Simple interface to CCS trending database designed to be used from Jupyter
"""
from setuptools import setup

setup(
    name='ccs_tools',
    version='1.0.13',
    description='Simple interface to CCS trending database',
    url='https://github.com/tony-johnson/ccs_tools',
    maintainer='Tony Johnson',
    maintainer_email="tonyj@stanford.edu",
    classifiers=[
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'Programming Language :: Python :: 3.6',
    ],
    packages=['ccs_tools'],
    install_requires=[]
)

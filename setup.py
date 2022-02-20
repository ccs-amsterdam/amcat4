#!/usr/bin/env python

from distutils.core import setup

setup(
    name="amcat4",
    version="0.07c",
    description="API for AmCAT4 Text Analysis",
    author="Wouter van Atteveldt",
    author_email="wouter@vanatteveldt.com",
    packages=["amcat4"],
    include_package_data=True,
    zip_safe=False,
    keywords=["API", "text"],
    classifiers=[
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Topic :: Text Processing",
    ],
    install_requires=[
        "Flask~=2.0.3",
        "Flask-HTTPAuth",
        "flask-cors",
        "flask-selfdoc",
        "elasticsearch~=7.16",
        "bcrypt",
        "peewee",
        "authlib",
        "amcat4annotator>=0.14"
    ],
    extras_require={
        'dev': [
            'pytest',
            'pytest-flask',
            'mypy',
            'types-Flask',
            'flake8'
        ]
    },
)

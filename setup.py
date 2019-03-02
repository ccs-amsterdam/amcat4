#!/usr/bin/env python

from distutils.core import setup

setup(
    name="amcat4",
    version="0.04",
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
        "Flask",
        "Flask-HTTPAuth",
        "flask-cors",
        "elasticsearch",
        "bcrypt",
        "peewee",
        "itsdangerous",
    ],
    extras_require={
        'dev': [
            'nose',
            'codecov',
        ]
    },
)

#!/usr/bin/env python

from distutils.core import setup

setup(
    name="AmCAT4API",
    version="0.01",
    description="API for AmCAT4 Text Analysis",
    author="Wouter van Atteveldt",
    author_email="wouter@vanatteveldt.com",
    packages=["amcat4api"],
    include_package_data=True,
    zip_safe=False,
    keywords = ["API", "text"],
    classifiers=[
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Topic :: Text Processing",
    ],
    install_requires=[
        "Flask",
        "Flask-HTTPAuth",
        "elasticsearch",
        "bcrypt",
    ]
)
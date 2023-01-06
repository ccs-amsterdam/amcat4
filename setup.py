#!/usr/bin/env python

from distutils.core import setup

setup(
    name="amcat4",
    version="0.10",
    description="API for AmCAT4 Text Analysis",
    author="Wouter van Atteveldt",
    author_email="wouter@vanatteveldt.com",
    packages=["amcat4", "amcat4.api"],
    include_package_data=True,
    zip_safe=False,
    keywords=["API", "text"],
    classifiers=[
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Topic :: Text Processing",
    ],
    install_requires=[
        "fastapi[all]",
        "elasticsearch~=7.16",
        "python-multipart",
        "python-dotenv",
        "requests",
        "authlib",
        "pydantic[email]",
        'uvicorn',
        'requests'
    ],
    extras_require={
        'dev': [
            'pytest',
            'mypy',
            'flake8',
            'responses',
        ]
    },
)

#!/usr/bin/env python

from distutils.core import setup

setup(
    name="amcat4",
    version="4.0.15",
    description="API for AmCAT4 Text Analysis",
    author="Wouter van Atteveldt",
    author_email="wouter@vanatteveldt.com",
    packages=["amcat4", "amcat4.api", "amcat4.preprocessing"],
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
        "elasticsearch~=8.6",
        "python-multipart",
        "python-dotenv",
        "requests",
        "authlib",
        "pydantic[email]",
        "pydantic-settings",
        "typing_extensions",
        "uvicorn",
        "requests",
        "class_doc",
        "mypy",
        "minio",
        "jsonpath_ng",
    ],
    extras_require={
        "dev": [
            "pytest",
            "pytest-httpx",
            "mypy",
            "flake8",
            "responses",
            "pre-commit",
            "types-requests",
            "pytest-asyncio",
            "pytest-minio-mock @ git+ssh://git@github.com/vanatteveldt/pytest-minio-mock.git",
        ]
    },
    entry_points={"console_scripts": ["amcat4 = amcat4.__main__:main"]},
)

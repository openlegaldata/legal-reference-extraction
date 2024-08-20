#!/usr/bin/env python

from __future__ import print_function

import codecs
import os
import re

from setuptools import setup, find_packages


def read(*parts):
    filename = os.path.join(os.path.dirname(__file__), *parts)
    with codecs.open(filename, encoding='utf-8') as fp:
        return fp.read()


def find_version(*file_paths):
    version_file = read(*file_paths)
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]",
                              version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


setup(
    name="legal-reference-extraction",
    version=find_version("refex", "__init__.py"),
    url='https://github.com/openlegaldata/legal-reference-extraction',
    license='MIT',
    description="Extract references from legal documents",
    long_description=read('README.md'),
    author='Malte Schwarzer',
    author_email='hello@openlegaldata.io',
    packages=find_packages(),
    install_requires=[
        'nltk==3.9',
        # 'Markdown==2.6.11',
        # 'lxml==3.7.3',
        # 'beautifulsoup4==4.6.0',
    ],
    include_package_data=True,
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.5',
        'Topic :: Utilities',
    ],
    zip_safe=False,
)


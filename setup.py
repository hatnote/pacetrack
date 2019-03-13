
import os
import imp
from setuptools import setup, find_packages

__author__ = "Stephen LaPorte and Mahmoud Hashemi"
__contact__ = "mahmoud@hatnote.com"
__license__ = 'GPLv3'
__url__ = 'https://github.com/hatnote/pacetrack'

CUR_PATH = os.path.abspath(os.path.dirname(__file__))
_version_mod_path = os.path.join(CUR_PATH, 'pacetrack', '_version.py')
_version_mod = imp.load_source('_version', _version_mod_path)
__version__ = _version_mod.__version__

setup(
    name="pacetrack",
    description="Track and coordinate WikiProject improvement campaign progress.",
    author=__author__,
    author_email=__contact__,
    url=__url__,
    license=__license__,
    platforms='any',
    version=__version__,
    long_description=__doc__,
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    entry_points={'console_scripts': ['pt = pacetrack.__main__:main',
                                      'ptrack = pacetrack.__main__:main',
                                      'pacetrack = pacetrack.__main__:main']},
    install_requires=['ashes',
                      'attrs',
                      'boltons',
                      'face',
                      'gevent==1.2.2',
                      'hyperlink',
                      'lithoxyl',
                      'PyNaCl',
                      'ruamel.yaml',
                      'schema',
                      'tqdm']
)

"""
Release process:

* tox  # TODO
* git commit (if applicable)
* Remove dev suffix from pacetrack/_version.py version
* git commit -a -m "bump version for vX.Y.Z release"
* python setup.py sdist bdist_wheel upload
* git tag -a vX.Y.Z -m "brief summary"
* write CHANGELOG
* git commit
* bump pacetrack/_version.py version onto n+1 dev
* git commit
* git push

Versions are of the format YY.MINOR.MICRO, see calver.org for more details.
"""

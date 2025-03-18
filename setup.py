from setuptools import find_packages
from setuptools import setup
import os


def read_file(name):
    with open(os.path.join(os.path.dirname(__file__), name)) as f:
        return f.read()


version = '0.9.dev0'
shortdesc = 'SQLAlchemy integration for cone.app'
longdesc = '\n\n'.join([read_file(name) for name in [
    'README.rst',
    'CHANGES.rst',
    'LICENSE.rst'
]])


setup(
    name='cone.sql',
    version=version,
    description=shortdesc,
    long_description=longdesc,
    classifiers=[
        'Environment :: Web Environment',
        'Programming Language :: Python',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
    keywords='node pyramid cone web',
    author='Cone Contributors',
    author_email='dev@conestack.org',
    url='http://github.com/conestack/cone.sql',
    license='Simplified BSD',
    packages=find_packages('src'),
    package_dir={'': 'src'},
    namespace_packages=['cone'],
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        'cone.app>=1.0.3',
        'node.ext.ugm>=0.9.13',
        'pyramid_retry',
        'pyramid_tm',
        'setuptools',
        'zope.sqlalchemy'
    ],
    extras_require=dict(
        ugm=[
            'cone.ugm'
        ],
        test=[
            'pytest',
            'zope.pytestlayer',
            'cone.ugm'
        ]
    ),
    entry_points="""\
    [paste.filter_app_factory]
    session = cone.sql:make_app
    """
)

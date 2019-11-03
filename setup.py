from setuptools import setup, find_packages

with open('README.md') as f:
    readme = f.read()

with open('LICENSE') as f:
    license = f.read()

setup(
    name='htmlbuilder',
    version='0.1.0',
    description='htmlbuilder module',
    long_description=readme,
    author='Paul Webb',
    author_email='p@technobok.org',
    url='https://dev.technobok.org/technobok/htmlbuilder',
    license=license,
    packages=find_packages(exclude=('tests', 'docs'))
)


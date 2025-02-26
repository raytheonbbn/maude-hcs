from setuptools import setup, find_packages

setup(
    name='maude_hcs',
    version='0.0.1',
    packages=find_packages(),
    install_requires=[
        'argparse',
        'argcomplete',
        'maude==1.2.2',
        'z3-solver==4.8.12',
        'pyyaml',
        'dns'
    ],
    python_requires='>=3.9',
    entry_points={
        'console_scripts': [
            'maude-hcs = maude_hcs.main:main',
        ],
    },
)

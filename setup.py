from setuptools import setup, find_packages

with open('README.md', 'r') as fh:
    description = fh.read()

setup(
    name='EstimPy',
    version='0.1',
    author='Psynapse',
    author_email='psykinkster@gmail.com',
    packages=find_packages(),
    description='A package for Estim playback and visualization',
    long_description=description,
    long_description_content_type='text/markdown',
    url='https://github.com/PsyApps/EstimPy',
    license='MIT',
    python_requires='>=3.11,<3.13',
    install_requires=[
        'flatdict',
        'matplotlib>=3.7.2',
        'mutagen',
        'numpy',
        'pydub',
        'pygame',
        'pyyaml',
        'scipy'
    ],
    entry_points={
        'console_scripts': [
            'estimpy-visualizer=visualizer:main',  # Optional: If you want visualizer.py to be a CLI command
            'estimpy-player=player:main',          # Optional: If you want player.py to be a CLI command
        ],
    }
)
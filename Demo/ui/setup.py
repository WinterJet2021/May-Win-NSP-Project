# Demo/ui/setup.py

from setuptools import setup, find_packages

setup(
    name="nurse_scheduler",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "gurobipy",
        "flask",
    ],
    author="Chirayu SUkhum",
    author_email="csukhum@cmkl.ac.th",
    description="A nurse scheduling optimization system using Gurobi",
    keywords="nurse, scheduling, optimization, gurobi",
    url="https://github.com/WinterJet2021/May-Win-NSP-Project.git",
)
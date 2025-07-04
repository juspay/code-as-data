from setuptools import setup, find_packages

setup(
    name="code_as_data",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "sqlalchemy",
        "python-dotenv",
        "alembic",
        "annotated-types",
        "contourpy",
        "cycler",
        "fonttools",
        "iniconfig",
        "kiwisolver",
        "Mako",
        "MarkupSafe",
        "matplotlib",
        "networkx",
        "numpy",
        "packaging",
        "pillow",
        "pluggy",
        "psutil",
        "psycopg2-binary",
        "pydantic",
        "pydantic_core",
        "pyparsing",
        "pytest",
        "python-dateutil",
        "python-dotenv",
        "setuptools",
        "six",
        "SQLAlchemy",
        "tqdm",
        "typing_extensions",
        "neo4j",
    ],
    python_requires=">=3.6",
)

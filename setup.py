from setuptools import setup, find_packages

setup(
    name="code_analysis",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "sqlalchemy",
        "python-dotenv",
    ],
    python_requires=">=3.6",
)

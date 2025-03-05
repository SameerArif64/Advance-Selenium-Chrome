from setuptools import setup, find_packages

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="advancechromedriver",
    version="0.1.0",
    packages=find_packages(),
    install_requires=requirements,
    author="Sameer Arif",
    author_email="supersameer64@gmail.com",
    description="Enhanced Selenium Chrome WebDriver with remote debugging and tab recovery.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/SameerArif64/advance-selenium-chrome",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
    license="MIT",
)

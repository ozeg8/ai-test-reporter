from setuptools import setup, find_packages

setup(
    name="ai-test-reporter",
    version="1.0.0",
    description="Automated website testing tool powered by Claude Code",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "playwright>=1.40.0",
        "pytest>=7.4.0",
        "pytest-asyncio>=0.23.0",
        "jinja2>=3.1.0",
        "aiohttp>=3.9.0",
        "beautifulsoup4>=4.12.0",
        "Pillow>=10.0.0",
        "httpx>=0.25.0",
    ],
    entry_points={
        "console_scripts": [
            "ai-test-reporter=src.test_runner:main",
        ],
    },
)

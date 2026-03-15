from setuptools import find_packages, setup

setup(
    name="youtube-cash-cow",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "anthropic>=0.40.0",
        "google-api-python-client>=2.100.0",
        "google-auth-oauthlib>=1.0.0",
        "gTTS>=2.4.0",
        "moviepy>=1.0.3",
        "Pillow>=10.0.0",
        "requests>=2.31.0",
        "python-dotenv>=1.0.0",
        "schedule>=1.2.0",
        "pydub>=0.25.1",
        "numpy>=1.24.0",
    ],
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "yt-cashcow=youtube_cash_cow.main:main",
        ],
    },
)

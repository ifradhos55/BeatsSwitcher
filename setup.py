from setuptools import setup

APP = ['beats_switcher.py']
DATA_FILES = ['menubar_iconTemplate.png', 'config.json']
OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'app_icon.icns',
    'plist': {
        'LSUIElement': True,
        'CFBundleName': 'BeatsSwitcher',
        'CFBundleDisplayName': 'BeatsSwitcher',
        'CFBundleIdentifier': 'com.mastereggway.beatsswitcher',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1',
        'LSMinimumSystemVersion': '10.15',
        'NSHumanReadableCopyright': '© 2026 mastereggway. All rights reserved.',
    },
    'packages': ['rumps', 'objc', 'Foundation'],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)

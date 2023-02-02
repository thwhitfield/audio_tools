import setuptools

setuptools.setup(
    name='audio_tools',
    version = '0.0.1',
    author = 'Travis Whitfield',
    description = "Tools to process audio data to make it easier to listen to on shokz openswim mp3 players.",
    packages = setuptools.find_packages(),
    classifiers = [
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent"
    ],
    python_requires = '>=3.7',
    install_requires = [
        'pydub',
        'gTTS'
    ],
    entry_points = '''
    [console_scripts]
    process_podcast_folder=audio_tools:process_podcast_folder
    '''
)
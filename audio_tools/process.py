
import os
from gtts import gTTS
from io import BytesIO
from pydub import AudioSegment
from pathlib import Path
import click

def process_pod(filepath, db_change = None):
    """Process podcast file to add audio saying the name of the file to the beginning of the
    audio file, and to change the overall sound level if necessary.
    
    Args:
        filepath (str, path): filepath of the podcast audio mp3 to be processed
        db_change (int, default: None): number of decibels to change the audio (positive values increase the 
            sound level)

    Returns:
        pod2 (AudioSegment): processed audio object        
    """

    filepath = Path(filepath)
    filename = filepath.name
    
    pod = AudioSegment.from_mp3(filepath)

    if db_change:
        pod = pod + db_change

    # Replace underscores with spaces so that the audio pronounces individual words
    filename_text = filename.replace('_',' ').replace('.mp3','')
    filename_audio = gTTS(text=filename_text)
    
    # Create temporary fake-file to 'save' the audio to and then add it to the podcast
    filename_audio_file = BytesIO()
    filename_audio.write_to_fp(filename_audio_file)
    
    # This line seems necessary in order to use the just created fake-file
    filename_audio_file.seek(0)

    # Convert the gTTS audio segment to the pdub.AudioSegment object
    filename_audio2 = AudioSegment.from_mp3(filename_audio_file)

    # Concatenate the two audio files together
    pod2 = filename_audio2 + pod

    return pod2

@click.command()
@click.option('--folder_path', default = '.', help='Folder path containing mp3s to modify')
@click.option('--output_folder_path', required=False)
@click.option('--db_change', required=False)
@click.option('--prefix', required=False)
@click.option('--suffix', required=False)
def process_podcast_folder(folder_path, output_folder_path = None, db_change = 0, prefix = None, suffix = None):
    """Process each of the files in a folder.
    
    Args:
        folder_path (str, path): path to the folder containing mp3s to process (note, all mp3s in
            folder will be processed)
        output_folder_path (str, path, default: None): path to the output folder where processed
            files should be saved
        db_change (int, default: None): number of decibels to change the audio (positive values increase the 
            sound level)
        prefix (str, default: None): prefix to add to the output filenames
        suffix (str, default: None): suffix to add to the output filenames

    Returns:
        None
    """
    
    print('did the function even run?')

    # Set defaults for arguments if they're None
    if not output_folder_path:
        output_folder_path = folder_path
    if not prefix:
        prefix = ''
    if not suffix:
        suffix = ''

    folder_path = Path(folder_path)
    output_folder_path = Path(output_folder_path)

    for filename in os.listdir(folder_path):
        if not filename.endswith('mp3'):
            continue

        # Process individual podcast file
        pod = process_pod(filepath = Path(folder_path) / filename, db_change = db_change)

        # Save processed pod file to output path
        output_filepath = (output_folder_path / 
                           Path(prefix + Path(filename).stem + suffix + Path(filename).suffix))  
        pod.export(output_filepath)  

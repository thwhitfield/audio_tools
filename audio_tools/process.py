import os
from io import BytesIO
from pathlib import Path

from gtts import gTTS
from pydub import AudioSegment

# import click


def process_pod(filepath, db_change=None, start_audio_text=None):
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
    if start_audio_text is None:
        filename_text = filename.replace("_", " ").replace(".mp3", "")
        filename_audio = gTTS(text=filename_text)
    else:
        filename_audio = gTTS(text=start_audio_text)

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


# @click.command()
# @click.option('--folder_path', default = '.', help='Folder path containing mp3s to modify')
# @click.option('--output_folder_path', required=False)
# @click.option('--db_change', required=False)
# @click.option('--prefix', required=False)
# @click.option('--suffix', required=False)
def process_podcast_folder(
    folder_path,
    output_folder_path=None,
    db_change=0,
    prefix="louder_",
    suffix=None,
    start_audio_text_map=None,
):
    """Process each of the files in a folder.

    Args:
        folder_path (str, path): path to the folder containing mp3s to process (note, all mp3s in
            folder will be processed)
        output_folder_path (str, path, default: None): path to the output folder where processed
            files should be saved
        db_change (int, default: None): number of decibels to change the audio (positive values increase the
            sound level)
        prefix (str, default: 'louder_'): prefix to add to the output filenames
        suffix (str, default: None): suffix to add to the output filenames
        start_audio_text_map (dict, default: None): dictionary mapping filenames to custom start audio text

    Returns:
        None
    """

    # Set defaults for arguments if they're None
    if not output_folder_path:
        output_folder_path = folder_path
    if not suffix:
        suffix = ""

    folder_path = Path(folder_path)
    output_folder_path = Path(output_folder_path)

    for filename in os.listdir(folder_path):
        if not filename.endswith("mp3"):
            continue

        try:
            # Determine start audio text for this file
            start_audio_text = None
            if start_audio_text_map and filename in start_audio_text_map:
                start_audio_text = start_audio_text_map[filename]

            # Process individual podcast file
            pod = process_pod(
                filepath=Path(folder_path) / filename,
                db_change=db_change,
                start_audio_text=start_audio_text,
            )

            # Save processed pod file to output path
            output_filepath = output_folder_path / Path(
                prefix + Path(filename).stem + suffix + Path(filename).suffix
            )
            pod.export(output_filepath)
        except:
            print(f"Failed to process: {filename}")


def split_podcast(filepaths, output_folder_path, split_length=20):
    """Split podcast files into smaller chunks of specified length.

    Args:
        filepaths (list of str, paths): list of filepaths to the podcast audio mp3s to be split
        split_length (int, default: 20): length in minutes of each split chunk

    Returns:
        chunk_filenames (list): list of generated chunk filenames
    """

    if not Path(output_folder_path).exists():
        Path(output_folder_path).mkdir(parents=True, exist_ok=True)

    chunk_filenames = []

    for filepath in filepaths:
        filepath = Path(filepath)

        pod = AudioSegment.from_mp3(filepath)

        pod_length_min = len(pod) / 60000  # Length of podcast in minutes
        num_splits = int(pod_length_min / split_length) + 1

        for i in range(num_splits):
            start_time = i * split_length * 60000  # Start time in milliseconds
            end_time = min(
                (i + 1) * split_length * 60000, len(pod)
            )  # End time in milliseconds

            pod_chunk = pod[start_time:end_time]

            chunk_filename = f"{filepath.stem}_part{i+1:02d}{filepath.suffix}"
            chunk_filepath = output_folder_path / chunk_filename

            pod_chunk.export(chunk_filepath)
            chunk_filenames.append(chunk_filename)

    return chunk_filenames


def _generate_intro_audio(text):
    """Generate a spoken intro audio segment from text.

    Args:
        text (str): text to convert to speech

    Returns:
        AudioSegment: audio segment of the spoken text
    """
    audio = gTTS(text=text)
    audio_file = BytesIO()
    audio.write_to_fp(audio_file)
    audio_file.seek(0)
    return AudioSegment.from_mp3(audio_file)


def full_process_podcast_episode(
    filepath,
    db_change=10,
    split_length=10,
    use_part_numbers_only=True,
    progress_callback=None,
):
    """Fully process a podcast episode by adjusting sound level and adding filename audio.

    This optimized version loads the file once, applies volume adjustment, then splits
    and adds intros in a single pass - avoiding intermediate disk writes.

    Args:
        filepath (str, path): filepath of the podcast audio mp3 to be processed
        db_change (int, default: 10): number of decibels to change the audio (positive values increase the
            sound level)
        use_part_numbers_only (bool, default: True): if True, use only "part 1", "part 2", etc. as the
            start audio text instead of the full filename
        progress_callback (callable, default: None): optional callback function that receives
            (current_chunk, total_chunks, status_message) to report progress
    Returns:
        output_path (Path): path to the processed podcast episode
    """
    filepath = Path(filepath)
    stem = filepath.stem
    output_folder = filepath.parent / stem

    if not output_folder.exists():
        output_folder.mkdir(parents=True, exist_ok=True)

    # Report loading status
    if progress_callback:
        progress_callback(0, 1, "Loading audio file...")

    # Load the full podcast once
    pod = AudioSegment.from_mp3(filepath)

    # Apply volume adjustment to the entire file (more efficient than per-chunk)
    if db_change:
        if progress_callback:
            progress_callback(0, 1, "Adjusting volume...")
        pod = pod + db_change

    # Calculate split parameters
    split_ms = split_length * 60000  # Convert minutes to milliseconds
    total_length = len(pod)
    num_chunks = (total_length // split_ms) + (1 if total_length % split_ms else 0)

    # Process each chunk in memory and export directly
    for i in range(num_chunks):
        if progress_callback:
            progress_callback(i, num_chunks, f"Processing chunk {i + 1} of {num_chunks}...")

        start_time = i * split_ms
        end_time = min((i + 1) * split_ms, total_length)

        # Extract chunk (already has volume adjusted)
        chunk = pod[start_time:end_time]

        # Generate intro audio
        if use_part_numbers_only:
            intro_text = f"part {i + 1}"
        else:
            intro_text = stem.replace("_", " ")

        intro = _generate_intro_audio(intro_text)

        # Combine intro + chunk
        final_chunk = intro + chunk

        # Export directly (single disk write per chunk)
        output_filename = f"louder_{stem}_part{i + 1:02d}.mp3"
        final_chunk.export(output_folder / output_filename)

    if progress_callback:
        progress_callback(num_chunks, num_chunks, "Complete!")

    return output_folder

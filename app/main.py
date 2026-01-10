"""
Audio Tools - Streamlit App

A simple GUI for processing podcast MP3 files:
- Add spoken intro (filename or custom text)
- Adjust volume
- Split long podcasts into chunks
"""

import sys
import tempfile
import time
import zipfile
from io import BytesIO
from pathlib import Path


def setup_environment():
    """Setup paths and ffmpeg for both development and bundled modes."""
    # Determine if we're running as a bundled app
    if getattr(sys, "frozen", False):
        # Running as bundled executable
        bundle_dir = Path(sys._MEIPASS)
        # Add the bundled audio_tools to path
        sys.path.insert(0, str(bundle_dir))
    else:
        # Running in normal Python environment
        sys.path.insert(0, str(Path(__file__).parent.parent))

    # Setup ffmpeg using static-ffmpeg if available
    try:
        import static_ffmpeg

        static_ffmpeg.add_paths()
    except ImportError:
        pass  # Assume ffmpeg is in PATH


setup_environment()

import streamlit as st

from audio_tools.process import (
    full_process_podcast_episode,
    process_pod,
    process_podcast_folder,
    split_podcast,
)

st.set_page_config(
    page_title="Audio Tools",
    page_icon="🎧",
    layout="centered",
)

st.title("Audio Tools")
st.markdown("Process podcast MP3 files for your Shokz OpenSwim player")

# Sidebar for mode selection
mode = st.sidebar.radio(
    "Processing Mode",
    ["Single File", "Full Process (Split + Process)", "Batch Process Folder"],
    help="Choose how you want to process your audio files",
)

st.sidebar.markdown("---")
st.sidebar.markdown("### About")
st.sidebar.markdown(
    """
This tool helps you:
- Add spoken intros to audio files
- Boost volume for better playback
- Split long podcasts into chunks
"""
)


def export_audio_to_bytes(audio_segment) -> bytes:
    """Export an AudioSegment to bytes for download."""
    buffer = BytesIO()
    audio_segment.export(buffer, format="mp3")
    buffer.seek(0)
    return buffer.getvalue()


# =============================================================================
# Single File Processing
# =============================================================================
if mode == "Single File":
    st.header("Process Single File")
    st.markdown("Upload an MP3 file to add a spoken intro and adjust volume.")

    uploaded_file = st.file_uploader("Upload MP3 file", type=["mp3"])

    col1, col2 = st.columns(2)

    with col1:
        db_change = st.slider(
            "Volume Adjustment (dB)",
            min_value=-20,
            max_value=30,
            value=10,
            help="Positive values increase volume, negative decrease",
        )

    with col2:
        use_custom_intro = st.checkbox("Use custom intro text")
        if use_custom_intro:
            custom_intro = st.text_input(
                "Custom intro text",
                placeholder="e.g., 'Episode 1 - Introduction'",
            )
        else:
            custom_intro = None

    if uploaded_file is not None:
        st.audio(uploaded_file, format="audio/mp3")

        if st.button("Process File", type="primary"):
            with st.spinner("Processing audio..."):
                start_time = time.time()

                # Save uploaded file to temp location
                with tempfile.NamedTemporaryFile(
                    suffix=".mp3", delete=False
                ) as tmp_file:
                    tmp_file.write(uploaded_file.getvalue())
                    tmp_path = tmp_file.name

                try:
                    # Process the file
                    processed_audio = process_pod(
                        filepath=tmp_path,
                        db_change=db_change if db_change != 0 else None,
                        start_audio_text=custom_intro if use_custom_intro else None,
                    )

                    # Convert to bytes for download
                    audio_bytes = export_audio_to_bytes(processed_audio)

                    elapsed_time = time.time() - start_time
                    st.success(f"Processing complete! Took {elapsed_time:.1f} seconds.")

                    # Create download button
                    output_filename = f"processed_{uploaded_file.name}"
                    st.download_button(
                        label="Download Processed File",
                        data=audio_bytes,
                        file_name=output_filename,
                        mime="audio/mpeg",
                    )

                except Exception as e:
                    st.error(f"Error processing file: {e}")

                finally:
                    # Clean up temp file
                    Path(tmp_path).unlink(missing_ok=True)


# =============================================================================
# Full Process (Split + Process)
# =============================================================================
elif mode == "Full Process (Split + Process)":
    st.header("Full Process")
    st.markdown(
        """
    Upload a long podcast to:
    1. Split it into smaller chunks
    2. Add spoken part numbers ("Part 1", "Part 2", etc.)
    3. Boost volume

    Perfect for long podcasts you want to listen to in segments.
    """
    )

    uploaded_file = st.file_uploader("Upload MP3 file", type=["mp3"])

    col1, col2, col3 = st.columns(3)

    with col1:
        split_length = st.slider(
            "Chunk Length (minutes)",
            min_value=5,
            max_value=60,
            value=10,
            help="How long each split chunk should be",
        )

    with col2:
        db_change = st.slider(
            "Volume Adjustment (dB)",
            min_value=-20,
            max_value=30,
            value=10,
            key="full_process_db",
            help="Positive values increase volume",
        )

    with col3:
        speed = st.slider(
            "Playback Speed",
            min_value=0.5,
            max_value=2.0,
            value=1.0,
            step=0.1,
            key="full_process_speed",
            help="1.0 = normal, 1.5 = 50% faster, 0.75 = 25% slower",
        )

    use_part_numbers = st.checkbox(
        "Use simple part numbers",
        value=True,
        help="If checked, intro will be 'Part 1', 'Part 2', etc. Otherwise uses full filename.",
    )

    if uploaded_file is not None:
        st.audio(uploaded_file, format="audio/mp3")

        if st.button("Process File", type="primary", key="full_process_btn"):
            start_time = time.time()
            chunk_times = []  # Track time per chunk for estimation

            # Create progress bar and status text
            progress_bar = st.progress(0)
            status_text = st.empty()

            # Create temp directory for processing
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_dir = Path(tmp_dir)

                # Save uploaded file
                input_path = tmp_dir / uploaded_file.name
                input_path.write_bytes(uploaded_file.getvalue())

                last_chunk_time = [start_time]  # Use list to allow mutation in nested function

                def update_progress(current, total, message):
                    now = time.time()
                    elapsed = now - start_time

                    # Track chunk processing times
                    if current > 0 and total > 1:
                        chunk_time = now - last_chunk_time[0]
                        chunk_times.append(chunk_time)
                        last_chunk_time[0] = now

                    # Calculate ETA
                    if current > 0 and total > 0 and chunk_times:
                        avg_chunk_time = sum(chunk_times) / len(chunk_times)
                        remaining_chunks = total - current
                        eta_seconds = remaining_chunks * avg_chunk_time
                        eta_str = f" | ETA: {eta_seconds:.0f}s"
                    else:
                        eta_str = ""

                    # Format elapsed time
                    elapsed_str = f"Elapsed: {elapsed:.0f}s"

                    if total > 0:
                        progress_bar.progress(current / total)
                    status_text.text(f"{message} | {elapsed_str}{eta_str}")

                try:
                    # Run full processing with progress callback
                    output_folder = full_process_podcast_episode(
                        filepath=input_path,
                        db_change=db_change,
                        split_length=split_length,
                        use_part_numbers_only=use_part_numbers,
                        progress_callback=update_progress,
                        speed=speed,
                    )

                    # Update progress for zip creation
                    elapsed = time.time() - start_time
                    status_text.text(f"Creating ZIP file... | Elapsed: {elapsed:.0f}s")

                    # Create zip file of all processed chunks
                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(
                        zip_buffer, "w", zipfile.ZIP_DEFLATED
                    ) as zip_file:
                        for mp3_file in output_folder.glob("louder_*.mp3"):
                            zip_file.write(mp3_file, mp3_file.name)

                    zip_buffer.seek(0)

                    # Clear progress indicators
                    progress_bar.empty()
                    status_text.empty()

                    # Count files
                    num_files = len(list(output_folder.glob("louder_*.mp3")))
                    elapsed_time = time.time() - start_time
                    st.success(f"Processing complete! Created {num_files} chunks in {elapsed_time:.1f} seconds.")

                    # Download button for zip
                    zip_filename = f"{Path(uploaded_file.name).stem}_processed.zip"
                    st.download_button(
                        label="Download All Processed Files (ZIP)",
                        data=zip_buffer.getvalue(),
                        file_name=zip_filename,
                        mime="application/zip",
                    )

                except Exception as e:
                    progress_bar.empty()
                    status_text.empty()
                    st.error(f"Error processing file: {e}")


# =============================================================================
# Batch Process Folder
# =============================================================================
elif mode == "Batch Process Folder":
    st.header("Batch Process Multiple Files")
    st.markdown(
        """
    Upload multiple MP3 files to process them all at once.
    Each file will get a spoken intro (the filename) and volume adjustment.
    """
    )

    uploaded_files = st.file_uploader(
        "Upload MP3 files", type=["mp3"], accept_multiple_files=True
    )

    col1, col2 = st.columns(2)

    with col1:
        db_change = st.slider(
            "Volume Adjustment (dB)",
            min_value=-20,
            max_value=30,
            value=10,
            key="batch_db",
            help="Positive values increase volume",
        )

    with col2:
        prefix = st.text_input(
            "Output filename prefix",
            value="louder_",
            help="Text to add before each filename",
        )

    if uploaded_files:
        st.markdown(f"**{len(uploaded_files)} files selected:**")
        for f in uploaded_files:
            st.markdown(f"- {f.name}")

        if st.button("Process All Files", type="primary", key="batch_btn"):
            with st.spinner(f"Processing {len(uploaded_files)} files..."):
                start_time = time.time()

                # Create temp directory for processing
                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp_dir = Path(tmp_dir)
                    output_dir = tmp_dir / "output"
                    output_dir.mkdir()

                    # Save all uploaded files
                    for uploaded_file in uploaded_files:
                        input_path = tmp_dir / uploaded_file.name
                        input_path.write_bytes(uploaded_file.getvalue())

                    try:
                        # Process the folder
                        process_podcast_folder(
                            folder_path=tmp_dir,
                            output_folder_path=output_dir,
                            db_change=db_change,
                            prefix=prefix,
                        )

                        # Create zip of all processed files
                        zip_buffer = BytesIO()
                        with zipfile.ZipFile(
                            zip_buffer, "w", zipfile.ZIP_DEFLATED
                        ) as zip_file:
                            for mp3_file in output_dir.glob("*.mp3"):
                                zip_file.write(mp3_file, mp3_file.name)

                        zip_buffer.seek(0)

                        num_processed = len(list(output_dir.glob("*.mp3")))
                        elapsed_time = time.time() - start_time
                        st.success(f"Processing complete! Processed {num_processed} files in {elapsed_time:.1f} seconds.")

                        st.download_button(
                            label="Download All Processed Files (ZIP)",
                            data=zip_buffer.getvalue(),
                            file_name="processed_podcasts.zip",
                            mime="application/zip",
                        )

                    except Exception as e:
                        st.error(f"Error processing files: {e}")

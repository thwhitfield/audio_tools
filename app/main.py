"""
Audio Tools - Streamlit App

A simple GUI for processing podcast MP3 files:
- Add spoken intro (filename or custom text)
- Adjust volume
- Split long podcasts into chunks
"""

import sys
import tempfile
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

                    st.success("Processing complete!")

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

    col1, col2 = st.columns(2)

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

    use_part_numbers = st.checkbox(
        "Use simple part numbers",
        value=True,
        help="If checked, intro will be 'Part 1', 'Part 2', etc. Otherwise uses full filename.",
    )

    if uploaded_file is not None:
        st.audio(uploaded_file, format="audio/mp3")

        if st.button("Process File", type="primary", key="full_process_btn"):
            with st.spinner("Processing audio (this may take a while for long files)..."):
                # Create temp directory for processing
                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp_dir = Path(tmp_dir)

                    # Save uploaded file
                    input_path = tmp_dir / uploaded_file.name
                    input_path.write_bytes(uploaded_file.getvalue())

                    try:
                        # Run full processing
                        output_folder = full_process_podcast_episode(
                            filepath=input_path,
                            db_change=db_change,
                            split_length=split_length,
                            use_part_numbers_only=use_part_numbers,
                        )

                        # Create zip file of all processed chunks
                        zip_buffer = BytesIO()
                        with zipfile.ZipFile(
                            zip_buffer, "w", zipfile.ZIP_DEFLATED
                        ) as zip_file:
                            for mp3_file in output_folder.glob("louder_*.mp3"):
                                zip_file.write(mp3_file, mp3_file.name)

                        zip_buffer.seek(0)

                        # Count files
                        num_files = len(list(output_folder.glob("louder_*.mp3")))
                        st.success(f"Processing complete! Created {num_files} chunks.")

                        # Download button for zip
                        zip_filename = f"{Path(uploaded_file.name).stem}_processed.zip"
                        st.download_button(
                            label="Download All Processed Files (ZIP)",
                            data=zip_buffer.getvalue(),
                            file_name=zip_filename,
                            mime="application/zip",
                        )

                    except Exception as e:
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
                        st.success(f"Processing complete! Processed {num_processed} files.")

                        st.download_button(
                            label="Download All Processed Files (ZIP)",
                            data=zip_buffer.getvalue(),
                            file_name="processed_podcasts.zip",
                            mime="application/zip",
                        )

                    except Exception as e:
                        st.error(f"Error processing files: {e}")

import subprocess
import os
import sys
import json

def get_video_dimensions(input_file):
    """Returns (width, height) of the video using ffprobe."""
    command = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json",
        input_file
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        width = data['streams'][0]['width']
        height = data['streams'][0]['height']
        return width, height
    except Exception as e:
        print(f"Warning: Could not detect video dimensions: {e}")
        return None, None

def split_video(input_file, format_for_reels=False):
    # Output directory
    output_dir = "raw footages"
    
    # Create the directory if it doesn't exist
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")

    # Check if input file exists
    if not os.path.exists(input_file):
        print(f"Error: File '{input_file}' not found.")
        return

    # Extract filename without extension
    filename = os.path.splitext(os.path.basename(input_file))[0]
    extension = os.path.splitext(input_file)[1]
    
    # ffmpeg command configuration
    output_pattern = os.path.join(output_dir, f"{filename}_part%03d{extension}")
    
    if format_for_reels:
        print("Formatting for Reels (9:16)... This will involve re-encoding and may take some time.")
        # Crop to 9:16 and scale to 1080x1920
        # Filter: crop=ih*9/16:ih (for landscape)
        # We also scale it to a standard Reels resolution 
        video_filters = "crop=ih*9/16:ih,scale=1080:1920"
        
        command = [
            "ffmpeg",
            "-i", input_file,
            "-vf", video_filters,
            "-f", "segment",
            "-segment_time", "60",
            "-reset_timestamps", "1",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            output_pattern
        ]
    else:
        # ffmpeg command to split video into 1-minute segments without re-encoding
        command = [
            "ffmpeg",
            "-i", input_file,
            "-f", "segment",
            "-segment_time", "60",
            "-c", "copy",
            "-reset_timestamps", "1",
            output_pattern
        ]

    print(f"Splitting '{input_file}'...")
    try:
        subprocess.run(command, check=True)
        print(f"\nSuccess! Segments saved in '{output_dir}'.")
    except subprocess.CalledProcessError as e:
        print(f"Error occurred during splitting: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        video_path = sys.argv[1]
    else:
        video_path = input("Enter the path to the video file: ").strip('"')
    
    choice = input("Do you want to format the video for Insta Reels (9:16 crop)? (y/n): ").lower().strip()
    for_reels = choice == 'y'
    
    split_video(video_path, format_for_reels=for_reels)

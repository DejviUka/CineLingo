import os
import subprocess
import whisper
from googletrans import Translator, LANGUAGES
import re
from tqdm import tqdm

# Global verbosity flag
VERBOSE = True

def log(message):
    if VERBOSE:
        print(message)

def list_languages():
    """
    Lists available languages from googletrans.
    Returns a sorted list of tuples: (code, language_name)
    """
    languages_list = sorted(LANGUAGES.items(), key=lambda x: x[1])
    log("\nAvailable languages:")
    for idx, (code, lang_name) in enumerate(languages_list, 1):
        print(f"{idx}. {lang_name.title()} ({code})")
    return languages_list

def get_language_choice():
    """
    Prompts user to choose a language from the list.
    Returns the selected language code.
    """
    languages_list = list_languages()
    while True:
        try:
            choice = int(input("\nEnter the number for the language to translate to: "))
            if 1 <= choice <= len(languages_list):
                lang_code, lang_name = languages_list[choice - 1]
                log(f"✔️  You selected: {lang_name.title()} ({lang_code})")
                return lang_code, lang_name.title()
            else:
                log("⚠️  Number out of range. Please try again.")
        except ValueError:
            log("⚠️  Please enter a valid number.")

def read_profanity_map(lang_code, filepath_template="profanity_map_{}.txt"):
    """
    Reads profanity mappings from a file that is named based on the target language.
    If the file is not found, warns the user and returns an empty dictionary.
    Each line of the file should be in the format:
         english_profanity:translated_text
    """
    filepath = filepath_template.format(lang_code)
    profanity_dict = {}
    if os.path.exists(filepath):
        log(f"📖 Reading profanity mapping from '{filepath}'...")
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    english, translation = line.split(":", 1)
                    profanity_dict[english.strip()] = translation.strip()
                else:
                    log(f"⚠️  Skipping invalid line in profanity file: {line}")
    else:
        log(f"⚠️  No profanity file '{filepath}' found for the selected language.")
        log(f"    If you want to enable profanity filtering, please add a file named '{filepath}' in the script directory.")
    return profanity_dict

def extract_audio(video_path, audio_path):
    log("🎧 Extracting audio from video...")
    # Using pcm_s16le for wav file with a sample rate of 16000 Hz and mono audio.
    cmd = f'ffmpeg -i "{video_path}" -vn -acodec pcm_s16le -ar 16000 -ac 1 "{audio_path}" -y'
    subprocess.run(cmd, shell=True, check=True)
    log("✅ Audio extraction completed.")

def transcribe_audio(audio_path):
    log("📝 Loading Whisper model for transcription...")
    model = whisper.load_model("base")
    log("🎙️  Transcribing audio using Whisper...")
    result = model.transcribe(audio_path, task="transcribe")
    log("✅ Transcription completed.")
    return result["segments"]

def format_timestamp(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def write_srt(segments, output_path):
    log(f"✍️  Writing subtitles to {output_path} ...")
    with open(output_path, "w", encoding="utf-8") as f:
        for i, segment in enumerate(segments, 1):
            start = format_timestamp(segment["start"])
            end = format_timestamp(segment["end"])
            text = segment["text"].strip()
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")
    log("✅ SRT file written.")

def translate_srt(segments, src_lang="en", dest_lang="sq"):
    log("🌐 Translating subtitles...")
    translator = Translator()
    for segment in tqdm(segments, desc="Translating", unit="segment"):
        translated = translator.translate(segment["text"], src=src_lang, dest=dest_lang)
        segment["text"] = translated.text
    log("✅ Translation completed.")
    return segments

def clean_profanities(text, profanity_dict):
    for bad, good in profanity_dict.items():
        pattern = re.compile(rf'\b{re.escape(bad)}\b', flags=re.IGNORECASE)
        text = pattern.sub(good, text)
    return text

def sanitize_segments(segments, profanity_dict):
    if profanity_dict:
        log("🚫 Censoring profanities...")
        for seg in segments:
            seg["text"] = clean_profanities(seg["text"], profanity_dict)
        log("✅ Profanity filtering completed.")
    else:
        log("ℹ️  No profanity mapping provided; skipping profanity filtering.")
    return segments

def main(video_path, dest_lang, dest_lang_name):
    base = os.path.splitext(video_path)[0]
    audio_path = f"{base}_audio.wav"
    srt_path = f"{base}_translated_clean.srt"

    # Read profanity mapping from file for the selected language.
    profanity_dict = read_profanity_map(dest_lang)

    # Step 1: Extract audio from the video.
    extract_audio(video_path, audio_path)

    # Step 2: Transcribe the audio to get English subtitles.
    segments = transcribe_audio(audio_path)

    # Step 3: Translate the subtitles into the target language.
    translated_segments = translate_srt(segments, src_lang="en", dest_lang=dest_lang)

    # Step 4: Apply profanity filtering using the loaded mapping.
    clean_segments = sanitize_segments(translated_segments, profanity_dict)

    # Step 5: Write the final SRT file.
    write_srt(clean_segments, srt_path)

    log(f"\n🎉 Process completed! Final subtitle file: {srt_path}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python script.py path_to_video")
        exit(1)
    video_path = sys.argv[1]
    # Prompt for language choice.
    dest_lang, dest_lang_name = get_language_choice()
    main(video_path, dest_lang, dest_lang_name)

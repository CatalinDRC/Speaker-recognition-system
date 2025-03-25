import customtkinter as ctk
from tkinter import messagebox, scrolledtext
from threading import Thread
import pveagle
from pvrecorder import PvRecorder
import sqlite3
from datetime import datetime
import os


# Initialize the database and constants
DB_NAME = "speakers.db"
DEFAULT_DEVICE_INDEX = -1
ACCESS_KEY = "e1gHmgYM4OeuBfsAPEe1h5O/R0EY1zvMeq3vq6kh7nAAlrJo3VQc2Q=="  # Replace with your actual access key


# Global variables for recorders
enroll_recorder = None
recognizer_recorder = None

# Function to initialize the database
def init_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Ensure table exists, but don't delete any existing records
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS speakers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            profile_data BLOB NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# Function to save the speaker to the database
def save_speaker_to_db(name, profile):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    profile_data = profile.to_bytes()  # Serialize profile to bytes
    cursor.execute("""
        INSERT INTO speakers (name, profile_data, created_at)
        VALUES (?, ?, ?)
    """, (name, profile_data, datetime.now().isoformat()))
    conn.commit()
    conn.close()

# Function to load speakers from the database
def load_speakers_from_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name, profile_data FROM speakers")
    speakers_data = cursor.fetchall()
    conn.close()
    return speakers_data

# Function to enroll a speaker (called in the background thread)
def enroll_speaker_gui(speaker_name, log_text_widget):
    try:
        eagle_profiler = pveagle.create_profiler(access_key=ACCESS_KEY)
    except pveagle.EagleError as e:
        log_text_widget.insert(ctk.END, f"Error: {str(e)}\n")
        return

    enroll_recorder = PvRecorder(
        device_index=DEFAULT_DEVICE_INDEX,
        frame_length=eagle_profiler.min_enroll_samples
    )

    enroll_recorder.start()
    enroll_percentage = 0.0

    try:
        while enroll_percentage < 100.0:
            audio_frame = enroll_recorder.read()
            enroll_percentage, feedback = eagle_profiler.enroll(audio_frame)
            log_text_widget.insert(ctk.END, f"Enrollment Progress: {enroll_percentage:.2f}% - {feedback}\n")
            log_text_widget.yview(ctk.END)
    except Exception as e:
        log_text_widget.insert(ctk.END, f"Error: {str(e)}\n")
        return
    finally:
        enroll_recorder.stop()

    try:
        speaker_profile = eagle_profiler.export()
        save_speaker_to_db(speaker_name, speaker_profile)
        log_text_widget.insert(ctk.END, f"Speaker '{speaker_name}' enrolled successfully.\n")
    except pveagle.EagleError as e:
        log_text_widget.insert(ctk.END, f"Failed to export speaker profile: {str(e)}\n")

# Function to recognize speakers (called in the background thread)
def recognize_speakers_gui(log_text_widget):
    try:
        speakers_data = load_speakers_from_db()
        if not speakers_data:
            log_text_widget.insert(ctk.END, "No speakers found in the database.\n")
            return

        profiles = []
        speaker_names = []
        for name, profile_data in speakers_data:
            profile = pveagle.EagleProfile.from_bytes(profile_data)
            profiles.append(profile)
            speaker_names.append(name)

        eagle = pveagle.create_recognizer(
            access_key=ACCESS_KEY,
            speaker_profiles=profiles
        )
    except pveagle.EagleError as e:
        log_text_widget.insert(ctk.END, f"Error: {str(e)}\n")
        return
    except Exception as e:
        log_text_widget.insert(ctk.END, f"Unexpected error: {str(e)}\n")
        return

    recognizer_recorder = PvRecorder(
        device_index=DEFAULT_DEVICE_INDEX,
        frame_length=eagle.frame_length
    )
    recognizer_recorder.start()
    log_text_widget.insert(ctk.END, "Recognition started...\n")

    try:
        recognized_speaker = None
        while True:
            audio_frame = recognizer_recorder.read()
            scores = eagle.process(audio_frame)
            threshold = 0.8
            results = {name: f"{score:.2f}%" for name, score in zip(speaker_names, scores) if score >= threshold}

            if results:
                recognized_speaker = max(results, key=lambda x: float(results[x][:-1]))
                log_text_widget.insert(ctk.END, f"Recognized Speaker: {recognized_speaker} with {results[recognized_speaker]}\n")
            else:
                log_text_widget.insert(ctk.END, "No matches above threshold.\n")
            log_text_widget.yview(ctk.END)

            if recognized_speaker:
                break
    except Exception as e:
        log_text_widget.insert(ctk.END, f"Error: {str(e)}\n")
    finally:
        recognizer_recorder.stop()

# Function to view the enrolled speakers
def view_speakers_gui(log_text_widget):
    speakers = load_speakers_from_db()
    if not speakers:
        log_text_widget.insert(ctk.END, "No speakers found in the database.\n")
    else:
        log_text_widget.insert(ctk.END, "List of Enrolled Speakers:\n")
        for i, (name, _) in enumerate(speakers, 1):
            log_text_widget.insert(ctk.END, f"{i}. {name}\n")
    log_text_widget.yview(ctk.END)

# Function to delete a speaker from the database
def delete_speaker_from_db(speaker_name, log_text_widget):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM speakers WHERE name=?", (speaker_name,))
    conn.commit()
    conn.close()
    log_text_widget.insert(ctk.END, f"Speaker '{speaker_name}' deleted successfully.\n")

# Function to add a speaker to the database
def add_speaker_gui(speaker_name, log_text_widget):
    if not speaker_name:
        messagebox.showerror("Error", "Please enter a speaker name.")
        return
    log_text_widget.insert(ctk.END, f"Adding speaker: {speaker_name}\n")
    log_text_widget.yview(ctk.END)
    Thread(target=enroll_speaker_gui, args=(speaker_name, log_text_widget)).start()

# Function to run the GUI
def run_gui():
    # Initialize the main window
    ctk.set_appearance_mode("System")  # Dark or Light theme
    ctk.set_default_color_theme("blue")  # You can choose a different color theme
    root = ctk.CTk()
    root.title("Speaker Enrollment & Recognition")
    root.geometry("600x500")

    # Log text box
    log_text_widget = scrolledtext.ScrolledText(root, width=60, height=15)
    log_text_widget.grid(row=0, column=0, padx=10, pady=10)

    # Entry for speaker name
    speaker_name_entry = ctk.CTkEntry(root, width=200)
    speaker_name_entry.grid(row=1, column=0, padx=10, pady=10)

    # Function to handle enrolling a speaker when button is clicked
    def on_enroll_button_click():
        speaker_name = speaker_name_entry.get()
        if not speaker_name:
            messagebox.showerror("Error", "Please enter a speaker name.")
            return
        log_text_widget.insert(ctk.END, f"Enrolling speaker: {speaker_name}\n")
        log_text_widget.yview(ctk.END)
        Thread(target=enroll_speaker_gui, args=(speaker_name, log_text_widget)).start()

    # Function to handle recognizing speakers when button is clicked
    def on_recognize_button_click():
        log_text_widget.insert(ctk.END, "Recognition in progress...\n")
        log_text_widget.yview(ctk.END)
        Thread(target=recognize_speakers_gui, args=(log_text_widget,)).start()

    # Function to handle viewing enrolled speakers
    def on_view_button_click():
        log_text_widget.insert(ctk.END, "Viewing enrolled speakers...\n")
        log_text_widget.yview(ctk.END)
        Thread(target=view_speakers_gui, args=(log_text_widget,)).start()

    # Function to handle deleting a speaker
    def on_delete_button_click():
        speaker_name = speaker_name_entry.get()
        if not speaker_name:
            messagebox.showerror("Error", "Please enter a speaker name to delete.")
            return
        delete_speaker_from_db(speaker_name, log_text_widget)

    # Buttons
    enroll_button = ctk.CTkButton(root, text="Enroll Speaker", command=on_enroll_button_click)
    enroll_button.grid(row=2, column=0, padx=10, pady=10)

    recognize_button = ctk.CTkButton(root, text="Recognize Speakers", command=on_recognize_button_click)
    recognize_button.grid(row=3, column=0, padx=10, pady=10)

    view_button = ctk.CTkButton(root, text="View Enrolled Speakers", command=on_view_button_click)
    view_button.grid(row=4, column=0, padx=10, pady=10)

    delete_button = ctk.CTkButton(root, text="Delete Speaker", command=on_delete_button_click)
    delete_button.grid(row=5, column=0, padx=10, pady=10)

    # Start the main event loop
    init_database()
    root.mainloop()

# Run the GUI application
if __name__ == "__main__":
    run_gui()

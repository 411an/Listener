from __future__ import annotations

import importlib.util
import fnmatch
import json
import queue
import subprocess
import threading
import time
import wave
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import filedialog, messagebox, ttk


APP_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = APP_DIR / "settings.json"
LOCALES_DIR = APP_DIR / "locales"
RECORDINGS_DIR = APP_DIR / "recordings"
DEFAULT_MODELS_DIR = APP_DIR / "models"

SAMPLE_RATE = 16_000
CHANNELS = 1

MODEL_CHOICES = ("base", "small", "medium", "large-v3")
MODEL_REPO_IDS = {
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
}
MODEL_PARAMETER_COUNTS = {
    "base": "74M",
    "small": "244M",
    "medium": "769M",
    "large-v3": "1550M",
}
MODEL_ALLOW_PATTERNS = (
    "config.json",
    "preprocessor_config.json",
    "model.bin",
    "tokenizer.json",
    "vocabulary.*",
)
UI_LANGUAGE_CHOICES = ("ru", "en")
LANGUAGE_CHOICES = (
    "auto",
    "ru",
    "en",
    "de",
    "fr",
    "es",
    "it",
    "uk",
    "pl",
    "tr",
    "zh",
    "ja",
    "ko",
)


DEFAULT_SETTINGS: dict[str, Any] = {
    "model_size": "base",
    "models_dir": str(DEFAULT_MODELS_DIR),
    "language": "ru",
    "ui_language": "ru",
    "use_gpu": True,
    "delete_recordings_after_transcribe": True,
    "vad_filter": True,
    "min_silence_duration_ms": 700,
    "beam_size": 1,
    "condition_on_previous_text": True,
    "word_timestamps": False,
    "device": "cpu",
    "compute_type": "int8",
}


BUILTIN_TRANSLATIONS: dict[str, str] = {
    "app_title": "Listener - faster-whisper",
    "section_recording": "Recording",
    "section_options": "Options",
    "section_model": "Model",
    "section_transcript": "Transcript",
    "label_model": "Model",
    "label_language": "Language",
    "label_interface": "Interface",
    "label_min_silence": "Silence, ms",
    "label_beam_size": "Beam size",
    "label_models_dir": "Models folder",
    "option_use_gpu": "Use GPU (CUDA)",
    "option_delete_recordings": "Delete recordings after transcription",
    "gpu_available": "CUDA GPU: {count}",
    "gpu_unavailable": "CUDA GPU: unavailable",
    "gpu_nvidia_without_cuda": "NVIDIA GPU found, CUDA runtime unavailable",
    "dialog_cuda_setup_title": "CUDA setup required",
    "dialog_cuda_setup_prompt": (
        "CUDA is still unavailable to CTranslate2. Show setup instructions and close "
        "the app? Choose No to keep using CPU."
    ),
    "dialog_cuda_setup_body": (
        "Install the NVIDIA CUDA/cuBLAS/cuDNN runtime required by faster-whisper, "
        "make sure the DLLs are available on PATH, then start the app again. "
        "Until then, the app will run on CPU."
    ),
    "button_start_recording": "Start recording",
    "button_stop_recording": "Stop and transcribe",
    "button_save_options": "Save options",
    "button_choose_models_dir": "Set model location",
    "button_check_model": "Check model",
    "button_download_model": "Download model",
    "button_copy": "Copy",
    "button_cut": "Cut",
    "button_clear": "Clear",
    "status_ready": "Ready",
    "status_options_saved": "Options saved: {file}",
    "status_model_required": "Download or connect a model first.",
    "status_recording": "Recording",
    "status_empty_recording": "Recording is empty",
    "status_wav_saved": "Recording saved: {file}",
    "status_downloading_model": "Downloading model {model_size}",
    "status_downloading_model_to": "Downloading {model_size} to {path}",
    "status_downloading_model_progress": (
        "Downloading {model_size}: {percent:.0f}% ({downloaded} / {total})"
    ),
    "status_loading_model": "Transcribing...",
    "status_model_downloaded": "Model downloaded",
    "status_model_already_downloaded": "Model {model_size} is already downloaded",
    "status_model_missing": "Model is not found",
    "status_error": "Error",
    "status_recognition_language_probability": (
        "Recognition: language {language}, probability {probability:.2f}"
    ),
    "status_recognition_language": "Recognition: language {language}",
    "model_found": (
        "Model {model_size} is ready.\n"
        "Parameters: about {parameters}. Disk: {size}; "
        "model.bin: {model_bin_size}.\n"
        "Repo: {repo_id}. Runtime: {device}/{compute_type}.\n"
        "Path: {path}"
    ),
    "model_missing": (
        "Model {model_size} is not found. Expected folder: {path}. "
        "Download it or choose a folder with an existing model."
    ),
    "model_invalid_after_download": (
        "After download, the model did not pass validation. Check folder: {path}"
    ),
    "dialog_model_check_title": "Model check",
    "dialog_model_missing_title": "Model is not found",
    "dialog_model_missing_body": (
        "Download a model first or choose a folder where it already exists."
    ),
    "dialog_missing_dependency_title": "Missing dependency",
    "dialog_missing_sounddevice_body": (
        "sounddevice is not installed. Run: pip install -r requirements.txt"
    ),
    "dialog_missing_faster_whisper_body": (
        "faster-whisper is not installed in the current Python environment. "
        "Run install.cmd or run: pip install -r requirements.txt"
    ),
    "dialog_recording_error_title": "Recording error",
    "dialog_wav_error_title": "WAV error",
    "dialog_error_title": "Error",
    "dialog_choose_models_dir_title": "Choose a folder for faster-whisper models",
    "recording_warning": "Recording warning: {status}",
    "download_error": "Could not download model: {error}",
    "transcribe_error": "Recognition error: {error}",
}


@dataclass(frozen=True)
class ModelStatus:
    exists: bool
    path: Path
    message: str
    total_bytes: int = 0
    already_downloaded: bool = False


@dataclass(frozen=True)
class GpuStatus:
    nvidia_present: bool
    cuda_device_count: int
    names: tuple[str, ...] = ()
    cuda_error: str = ""


def normalize_ui_language(language: str) -> str:
    language = language.strip().lower()
    if language == "eng":
        language = "en"
    if language not in UI_LANGUAGE_CHOICES:
        return "ru"
    return language


def load_settings() -> dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    if SETTINGS_PATH.exists():
        try:
            loaded = json.loads(SETTINGS_PATH.read_text(encoding="utf-8-sig"))
            if isinstance(loaded, dict):
                settings.update(loaded)
        except (OSError, json.JSONDecodeError):
            pass
    settings["ui_language"] = normalize_ui_language(str(settings.get("ui_language", "ru")))
    return settings


def save_settings(settings: dict[str, Any]) -> None:
    SETTINGS_PATH.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_locale(language: str) -> dict[str, str]:
    path = LOCALES_DIR / f"{normalize_ui_language(language)}.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {str(key): str(value) for key, value in loaded.items()}


def load_translations(language: str) -> dict[str, str]:
    translations = dict(BUILTIN_TRANSLATIONS)
    translations.update(read_locale(language))
    return translations


def directory_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return total
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def format_size(total_bytes: int) -> str:
    value = float(total_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def is_faster_whisper_model(path: Path) -> bool:
    if not path.is_dir():
        return False
    required = ("config.json", "model.bin", "tokenizer.json")
    return all((path / name).is_file() for name in required)


def is_model_repo_file(filename: str) -> bool:
    return any(fnmatch.fnmatch(filename, pattern) for pattern in MODEL_ALLOW_PATTERNS)


def repo_sibling_size(sibling: Any) -> int:
    size = getattr(sibling, "size", None)
    if isinstance(size, int):
        return size

    lfs = getattr(sibling, "lfs", None)
    if isinstance(lfs, dict):
        size = lfs.get("size")
    else:
        size = getattr(lfs, "size", None)
    return int(size) if isinstance(size, int) else 0


def has_module(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def run_probe_command(args: list[str], timeout: float = 3.0) -> str:
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
    }
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        completed = subprocess.run(args, **kwargs)
    except (OSError, subprocess.SubprocessError):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def detect_nvidia_gpu_names() -> tuple[str, ...]:
    nvidia_smi = run_probe_command(
        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
        timeout=3.0,
    )
    names = tuple(line.strip() for line in nvidia_smi.splitlines() if line.strip())
    if names:
        return names

    powershell = run_probe_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_VideoController | "
            "Select-Object -ExpandProperty Name",
        ],
        timeout=5.0,
    )
    return tuple(
        line.strip()
        for line in powershell.splitlines()
        if "nvidia" in line.lower()
    )


def detect_cuda_device_count() -> int:
    try:
        import ctranslate2

        return max(0, int(ctranslate2.get_cuda_device_count()))
    except Exception:
        return 0


def detect_gpu_status() -> GpuStatus:
    names = detect_nvidia_gpu_names()
    cuda_error = ""
    try:
        import ctranslate2

        cuda_count = max(0, int(ctranslate2.get_cuda_device_count()))
    except Exception as exc:
        cuda_count = 0
        cuda_error = str(exc)
    return GpuStatus(
        nvidia_present=bool(names) or cuda_count > 0,
        cuda_device_count=cuda_count,
        names=names,
        cuda_error=cuda_error,
    )


class ListenerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.settings = load_settings()
        self.translations = load_translations(str(self.settings["ui_language"]))
        self.localized_widgets: list[tuple[tk.Misc, str]] = []
        self.gpu_status = detect_gpu_status()
        self.cuda_device_count = self.gpu_status.cuda_device_count

        self.title(self.t("app_title"))
        self.geometry("940x680")
        self.minsize(800, 560)

        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.recording_frames: list[bytes] = []
        self.recording_stream: Any | None = None
        self.recording_started_at: float | None = None
        self.recording_job: str | None = None
        self.audio_levels: list[float] = [0.0] * 56
        self.last_audio_level_sent = 0.0
        self.transcript_append_started = False
        self.transcript_append_needs_separator = False
        self.is_busy = False
        self.model_available = False
        self.loaded_model: Any | None = None
        self.loaded_model_key: tuple[str, str, str] | None = None

        self.model_var = tk.StringVar(value=str(self.settings["model_size"]))
        self.models_dir_var = tk.StringVar(value=str(self.settings["models_dir"]))
        self.language_var = tk.StringVar(value=str(self.settings["language"]))
        self.ui_language_var = tk.StringVar(value=str(self.settings["ui_language"]))
        self.use_gpu_var = tk.BooleanVar(
            value=bool(self.settings.get("use_gpu", True)) and self.cuda_device_count > 0
        )
        self.delete_recordings_var = tk.BooleanVar(
            value=bool(self.settings["delete_recordings_after_transcribe"])
        )
        self.vad_var = tk.BooleanVar(value=bool(self.settings["vad_filter"]))
        self.min_silence_var = tk.IntVar(
            value=int(self.settings["min_silence_duration_ms"])
        )
        try:
            beam_size_value = int(self.settings.get("beam_size", 1))
        except (TypeError, ValueError):
            beam_size_value = 1
        self.beam_size_var = tk.IntVar(value=max(1, min(10, beam_size_value)))
        self.status_var = tk.StringVar(value=self.t("status_ready"))
        self.model_status_var = tk.StringVar(value="")
        self.gpu_status_var = tk.StringVar(value=self.gpu_status_text())
        self.timer_var = tk.StringVar(value="00:00")
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_text_var = tk.StringVar(value="")

        self._build_ui()
        self._install_text_shortcuts()
        self._write_initial_settings_if_missing()
        self.check_model_status(show_message=False)
        self.after(80, self._process_events)

    def t(self, key: str, **kwargs: Any) -> str:
        template = self.translations.get(key, BUILTIN_TRANSLATIONS.get(key, key))
        if not kwargs:
            return template
        try:
            return template.format(**kwargs)
        except (KeyError, ValueError):
            return template

    def _localize(self, widget: tk.Misc, key: str) -> tk.Misc:
        self.localized_widgets.append((widget, key))
        widget.configure(text=self.t(key))
        return widget

    def _label(self, parent: tk.Misc, key: str, **kwargs: Any) -> ttk.Label:
        label = ttk.Label(parent, **kwargs)
        self._localize(label, key)
        return label

    def _button(
        self,
        parent: tk.Misc,
        key: str,
        command: Any,
        **kwargs: Any,
    ) -> ttk.Button:
        button = ttk.Button(parent, command=command, **kwargs)
        self._localize(button, key)
        return button

    def _labelframe(self, parent: tk.Misc, key: str, **kwargs: Any) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, **kwargs)
        self._localize(frame, key)
        return frame

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        top = ttk.Frame(self, padding=12)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        recording_frame = self._labelframe(top, "section_recording")
        recording_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        recording_frame.columnconfigure(0, weight=1)

        self.record_button = ttk.Button(
            recording_frame,
            command=self.toggle_recording,
            width=28,
        )
        self.record_button.grid(row=0, column=0, padx=10, pady=(10, 6), sticky="ew")

        ttk.Label(recording_frame, textvariable=self.timer_var, anchor="center").grid(
            row=1, column=0, padx=10, pady=(0, 10), sticky="ew"
        )

        self.audio_meter = tk.Canvas(
            recording_frame,
            height=72,
            bg="#101418",
            highlightthickness=1,
            highlightbackground="#3a424a",
        )
        self.audio_meter.grid(row=2, column=0, padx=10, pady=(0, 8), sticky="ew")
        self.audio_meter.bind("<Configure>", lambda _event: self._draw_audio_meter())

        self.delete_recordings_check = ttk.Checkbutton(
            recording_frame,
            variable=self.delete_recordings_var,
            command=self._on_option_changed,
        )
        self._localize(self.delete_recordings_check, "option_delete_recordings")
        self.delete_recordings_check.grid(
            row=3, column=0, padx=10, pady=(0, 10), sticky="w"
        )

        options_frame = self._labelframe(top, "section_options")
        options_frame.grid(row=0, column=1, sticky="nsew")
        options_frame.columnconfigure(1, weight=1)
        options_frame.columnconfigure(3, weight=1)

        self._label(options_frame, "label_model").grid(
            row=0, column=0, padx=(10, 6), pady=(10, 6), sticky="w"
        )
        self.model_combo = ttk.Combobox(
            options_frame,
            textvariable=self.model_var,
            values=MODEL_CHOICES,
            state="readonly",
            width=12,
        )
        self.model_combo.grid(row=0, column=1, padx=(0, 10), pady=(10, 6), sticky="ew")
        self.model_combo.bind("<<ComboboxSelected>>", self._on_option_changed)

        self._label(options_frame, "label_language").grid(
            row=0, column=2, padx=(10, 6), pady=(10, 6), sticky="w"
        )
        self.language_combo = ttk.Combobox(
            options_frame,
            textvariable=self.language_var,
            values=LANGUAGE_CHOICES,
            width=12,
        )
        self.language_combo.grid(
            row=0, column=3, padx=(0, 10), pady=(10, 6), sticky="ew"
        )
        self.language_combo.bind("<<ComboboxSelected>>", self._on_option_changed)
        self.language_combo.bind("<FocusOut>", self._on_option_changed)

        self.vad_check = ttk.Checkbutton(
            options_frame,
            text="VAD",
            variable=self.vad_var,
            command=self._on_option_changed,
        )
        self.vad_check.grid(row=1, column=0, padx=(10, 6), pady=6, sticky="w")

        self._label(options_frame, "label_min_silence").grid(
            row=1, column=1, padx=(0, 6), pady=6, sticky="e"
        )
        self.min_silence_spin = ttk.Spinbox(
            options_frame,
            from_=100,
            to=3000,
            increment=50,
            textvariable=self.min_silence_var,
            width=8,
            command=self._on_option_changed,
        )
        self.min_silence_spin.grid(
            row=1, column=2, padx=(0, 10), pady=6, sticky="w"
        )
        self.min_silence_spin.bind("<FocusOut>", self._on_option_changed)

        self._label(options_frame, "label_interface").grid(
            row=2, column=0, padx=(10, 6), pady=(6, 10), sticky="w"
        )
        self.ui_language_combo = ttk.Combobox(
            options_frame,
            textvariable=self.ui_language_var,
            values=UI_LANGUAGE_CHOICES,
            state="readonly",
            width=12,
        )
        self.ui_language_combo.grid(
            row=2, column=1, padx=(0, 10), pady=(6, 10), sticky="ew"
        )
        self.ui_language_combo.bind("<<ComboboxSelected>>", self._on_ui_language_changed)

        self._label(options_frame, "label_beam_size").grid(
            row=3, column=0, padx=(10, 6), pady=(0, 6), sticky="w"
        )
        self.beam_size_spin = ttk.Spinbox(
            options_frame,
            from_=1,
            to=10,
            increment=1,
            textvariable=self.beam_size_var,
            width=8,
            command=self._on_option_changed,
        )
        self.beam_size_spin.grid(
            row=3, column=1, padx=(0, 10), pady=(0, 6), sticky="w"
        )
        self.beam_size_spin.bind("<FocusOut>", self._on_option_changed)

        self.use_gpu_check = ttk.Checkbutton(
            options_frame,
            variable=self.use_gpu_var,
            command=self._on_use_gpu_changed,
        )
        self._localize(self.use_gpu_check, "option_use_gpu")
        self.use_gpu_check.grid(
            row=4, column=0, columnspan=4, padx=10, pady=(8, 2), sticky="w"
        )

        ttk.Label(options_frame, textvariable=self.gpu_status_var, anchor="w").grid(
            row=5, column=0, columnspan=4, padx=10, pady=(0, 10), sticky="ew"
        )

        self.save_options_button = self._button(
            options_frame,
            "button_save_options",
            self.save_current_options,
        )
        self.save_options_button.grid(
            row=1, column=3, padx=(0, 10), pady=6, sticky="ew"
        )

        model_frame = self._labelframe(self, "section_model")
        model_frame.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="ew")
        model_frame.columnconfigure(1, weight=1)

        self._label(model_frame, "label_models_dir").grid(
            row=0, column=0, padx=(10, 6), pady=(10, 6), sticky="w"
        )
        self.models_dir_entry = ttk.Entry(
            model_frame,
            textvariable=self.models_dir_var,
        )
        self.models_dir_entry.grid(
            row=0, column=1, padx=(0, 8), pady=(10, 6), sticky="ew"
        )
        self.models_dir_entry.bind("<FocusOut>", self._on_option_changed)

        self.choose_models_button = self._button(
            model_frame,
            "button_choose_models_dir",
            self.choose_models_dir,
        )
        self.choose_models_button.grid(
            row=0, column=2, padx=(0, 8), pady=(10, 6), sticky="ew"
        )

        self.check_model_button = self._button(
            model_frame,
            "button_check_model",
            lambda: self.check_model_status(show_message=True),
        )
        self.check_model_button.grid(
            row=0, column=3, padx=(0, 8), pady=(10, 6), sticky="ew"
        )

        self.download_button = self._button(
            model_frame,
            "button_download_model",
            self.download_selected_model,
        )
        self.download_button.grid(row=0, column=4, padx=(0, 10), pady=(10, 6))

        ttk.Label(
            model_frame,
            textvariable=self.model_status_var,
            anchor="w",
            wraplength=900,
        ).grid(row=1, column=0, columnspan=5, padx=10, pady=(0, 10), sticky="ew")

        text_frame = self._labelframe(self, "section_transcript")
        text_frame.grid(row=2, column=0, padx=12, pady=(0, 10), sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.text = tk.Text(
            text_frame,
            wrap="word",
            undo=True,
            font=("Segoe UI", 11),
            padx=8,
            pady=8,
        )
        self.text.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)

        text_buttons = ttk.Frame(text_frame)
        text_buttons.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 8))
        text_buttons.columnconfigure(3, weight=1)

        self._button(text_buttons, "button_copy", self.copy_text).grid(
            row=0, column=0, padx=(0, 6)
        )
        self._button(text_buttons, "button_cut", self.cut_text).grid(
            row=0, column=1, padx=(0, 6)
        )
        self._button(text_buttons, "button_clear", self.clear_text).grid(
            row=0, column=2, padx=(0, 6)
        )

        bottom = ttk.Frame(self, padding=(12, 0, 12, 12))
        bottom.grid(row=3, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)

        self.progress = ttk.Progressbar(
            bottom,
            mode="determinate",
            maximum=100,
            variable=self.progress_var,
        )
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        ttk.Label(bottom, textvariable=self.progress_text_var, width=6, anchor="e").grid(
            row=0, column=1, sticky="ew", padx=(0, 10)
        )

        ttk.Label(bottom, textvariable=self.status_var, width=40, anchor="w").grid(
            row=0, column=2, sticky="ew"
        )

        self._apply_dynamic_texts()
        self._refresh_action_states()

    def gpu_status_text(self) -> str:
        if self.cuda_device_count > 0:
            return self.t("gpu_available", count=self.cuda_device_count)
        if self.gpu_status.nvidia_present:
            return self.t("gpu_nvidia_without_cuda")
        return self.t("gpu_unavailable")

    def refresh_gpu_status(self) -> None:
        self.gpu_status = detect_gpu_status()
        self.cuda_device_count = self.gpu_status.cuda_device_count
        self.gpu_status_var.set(self.gpu_status_text())

    def selected_runtime(self) -> tuple[str, str]:
        if self.use_gpu_var.get() and self.cuda_device_count > 0:
            return "cuda", "float16"
        return "cpu", "int8"

    def _prompt_cuda_setup_from_user_action(self) -> None:
        if not self.gpu_status.nvidia_present or self.cuda_device_count > 0:
            return
        open_setup = messagebox.askyesno(
            self.t("dialog_cuda_setup_title"),
            self.t("dialog_cuda_setup_prompt"),
            parent=self,
        )
        if open_setup:
            messagebox.showinfo(
                self.t("dialog_cuda_setup_title"),
                self.t("dialog_cuda_setup_body"),
                parent=self,
            )
            self.destroy()

    def _install_text_shortcuts(self) -> None:
        self.text.bind("<KeyPress>", self._on_text_keypress)

    def _write_initial_settings_if_missing(self) -> None:
        if not SETTINGS_PATH.exists():
            self.save_current_options()

    def _on_ui_language_changed(self, _event: object | None = None) -> None:
        self.settings["ui_language"] = normalize_ui_language(self.ui_language_var.get())
        self.ui_language_var.set(str(self.settings["ui_language"]))
        self.translations = load_translations(str(self.settings["ui_language"]))
        self.save_current_options()
        self._refresh_texts()
        self.check_model_status(show_message=False)

    def _on_option_changed(self, _event: object | None = None) -> None:
        self.save_current_options()
        self.check_model_status(show_message=False)

    def _on_use_gpu_changed(self) -> None:
        if self.use_gpu_var.get():
            self.refresh_gpu_status()
            if self.cuda_device_count <= 0:
                self.use_gpu_var.set(False)
                self._refresh_action_states()
                if self.gpu_status.nvidia_present:
                    self._prompt_cuda_setup_from_user_action()
                self.settings["use_gpu"] = False
                self.save_current_options()
                self.check_model_status(show_message=False)
                return
        self.save_current_options()
        self.check_model_status(show_message=False)

    def _refresh_texts(self) -> None:
        self.title(self.t("app_title"))
        for widget, key in self.localized_widgets:
            widget.configure(text=self.t(key))
        self.gpu_status_var.set(self.gpu_status_text())
        self._apply_dynamic_texts()

    def _apply_dynamic_texts(self) -> None:
        if self.recording_stream is None:
            self.record_button.configure(text=self.t("button_start_recording"))
        else:
            self.record_button.configure(text=self.t("button_stop_recording"))

    def save_current_options(self) -> None:
        device, compute_type = self.selected_runtime()
        self.settings.pop("suppress_cuda_setup_prompt", None)
        self.settings.update(
            {
                "model_size": self.model_var.get().strip() or "base",
                "models_dir": self.models_dir_var.get().strip()
                or str(DEFAULT_MODELS_DIR),
                "language": self.language_var.get().strip() or "ru",
                "ui_language": normalize_ui_language(self.ui_language_var.get()),
                "use_gpu": bool(self.use_gpu_var.get())
                and self.cuda_device_count > 0,
                "delete_recordings_after_transcribe": bool(
                    self.delete_recordings_var.get()
                ),
                "vad_filter": bool(self.vad_var.get()),
                "min_silence_duration_ms": self._safe_min_silence(),
                "beam_size": self._safe_beam_size(),
                "device": device,
                "compute_type": compute_type,
            }
        )
        save_settings(self.settings)
        self.status_var.set(self.t("status_options_saved", file=SETTINGS_PATH.name))

    def _safe_min_silence(self) -> int:
        try:
            value = int(self.min_silence_var.get())
        except (tk.TclError, ValueError):
            value = 700
        return max(100, min(3000, value))

    def _safe_beam_size(self) -> int:
        try:
            value = int(self.beam_size_var.get())
        except (tk.TclError, ValueError):
            value = 1
        return max(1, min(10, value))

    def selected_model_path(self) -> Path:
        models_dir = Path(self.models_dir_var.get().strip() or DEFAULT_MODELS_DIR)
        if not models_dir.is_absolute():
            models_dir = APP_DIR / models_dir
        model_size = self.model_var.get().strip() or "base"
        return models_dir / model_size

    def is_recording_path(self, path: Path) -> bool:
        try:
            return path.resolve().is_relative_to(RECORDINGS_DIR.resolve())
        except (OSError, ValueError):
            return False

    def _build_model_status(self, path: Path, model_size: str) -> ModelStatus:
        exists = is_faster_whisper_model(path)
        total = directory_size(path) if exists else 0
        device, compute_type = self.selected_runtime()
        if exists:
            message = self.t(
                "model_found",
                model_size=model_size,
                parameters=MODEL_PARAMETER_COUNTS.get(model_size, "unknown"),
                path=path,
                repo_id=MODEL_REPO_IDS.get(
                    model_size,
                    f"Systran/faster-whisper-{model_size}",
                ),
                size=format_size(total),
                model_bin_size=format_size(file_size(path / "model.bin")),
                device=device,
                compute_type=compute_type,
            )
        else:
            message = self.t("model_missing", model_size=model_size, path=path)
        return ModelStatus(exists=exists, path=path, message=message, total_bytes=total)

    def check_model_status(self, show_message: bool) -> ModelStatus:
        status = self._build_model_status(
            self.selected_model_path(),
            self.model_var.get().strip() or "base",
        )
        self.model_status_var.set(status.message)
        self._set_model_available(status.exists)
        if status.exists:
            self.status_var.set(self.t("status_ready"))
        else:
            self.status_var.set(self.t("status_model_required"))
        if show_message:
            title = self.t("dialog_model_check_title")
            if status.exists:
                messagebox.showinfo(title, status.message)
            else:
                messagebox.showwarning(title, status.message)
        return status

    def _set_model_available(self, available: bool) -> None:
        self.model_available = available
        self._refresh_action_states()

    def _refresh_action_states(self) -> None:
        if not hasattr(self, "record_button"):
            return

        busy = self.is_busy
        recording = self.recording_stream is not None
        can_transcribe = self.model_available and not busy

        self.record_button.configure(
            state="normal" if recording or can_transcribe else "disabled"
        )
        self.download_button.configure(state="disabled" if busy else "normal")
        self.save_options_button.configure(state="disabled" if busy else "normal")
        self.choose_models_button.configure(state="disabled" if busy else "normal")
        self.check_model_button.configure(state="disabled" if busy else "normal")
        self.models_dir_entry.configure(state="disabled" if busy else "normal")
        self.model_combo.configure(state="disabled" if busy else "readonly")
        self.language_combo.configure(state="disabled" if busy else "normal")
        self.ui_language_combo.configure(state="readonly")
        self.use_gpu_check.configure(
            state="normal"
            if not busy and (self.cuda_device_count > 0 or self.gpu_status.nvidia_present)
            else "disabled"
        )
        self.vad_check.configure(state="disabled" if busy else "normal")
        self.min_silence_spin.configure(state="disabled" if busy else "normal")
        self.beam_size_spin.configure(state="disabled" if busy else "normal")
        self.delete_recordings_check.configure(state="disabled" if busy else "normal")
        self._apply_dynamic_texts()

    def choose_models_dir(self) -> None:
        initial = self.models_dir_var.get().strip() or str(DEFAULT_MODELS_DIR)
        initial_path = Path(initial)
        if not initial_path.is_absolute():
            initial_path = APP_DIR / initial_path
        selected = filedialog.askdirectory(
            title=self.t("dialog_choose_models_dir_title"),
            initialdir=str(initial_path if initial_path.exists() else APP_DIR),
        )
        if not selected:
            return
        self.models_dir_var.set(selected)
        self.save_current_options()
        self.check_model_status(show_message=True)

    def set_busy(self, busy: bool) -> None:
        self.is_busy = busy
        self._refresh_action_states()

    def clear_progress_status(self) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress_var.set(0)
        self.progress_text_var.set("")
        self.status_var.set("")

    def _reset_audio_meter(self) -> None:
        self.audio_levels = [0.0] * 56
        self._draw_audio_meter()

    def _append_audio_level(self, level: float) -> None:
        level = max(0.0, min(1.0, level))
        self.audio_levels.append(level)
        self.audio_levels = self.audio_levels[-56:]
        self._draw_audio_meter()

    def _draw_audio_meter(self) -> None:
        if not hasattr(self, "audio_meter"):
            return
        width = max(1, self.audio_meter.winfo_width())
        height = max(1, self.audio_meter.winfo_height())
        self.audio_meter.delete("all")
        self.audio_meter.create_rectangle(0, 0, width, height, fill="#101418", outline="")

        baseline = height - 8
        self.audio_meter.create_line(
            0,
            baseline,
            width,
            baseline,
            fill="#2d3740",
            width=1,
        )
        if not self.audio_levels:
            return

        gap = 2
        bar_count = len(self.audio_levels)
        bar_width = max(2, int((width - gap * (bar_count + 1)) / bar_count))
        usable_height = max(4, height - 16)
        x = gap
        for level in self.audio_levels[-bar_count:]:
            amplified = min(1.0, level * 3.0)
            bar_height = max(2, int(amplified * usable_height))
            y1 = baseline - bar_height
            color = "#34c759" if amplified < 0.7 else "#ffcc00"
            if amplified > 0.9:
                color = "#ff453a"
            self.audio_meter.create_rectangle(
                x,
                y1,
                x + bar_width,
                baseline,
                fill=color,
                outline="",
            )
            x += bar_width + gap

    def show_model_required_warning(self) -> None:
        self.status_var.set(self.t("status_model_required"))
        messagebox.showwarning(
            self.t("dialog_model_missing_title"),
            self.t("dialog_model_missing_body"),
        )

    def show_faster_whisper_required_error(self) -> None:
        self.status_var.set(self.t("status_error"))
        messagebox.showerror(
            self.t("dialog_missing_dependency_title"),
            self.t("dialog_missing_faster_whisper_body"),
        )

    def toggle_recording(self) -> None:
        if self.recording_stream is None:
            if not self.model_available:
                self.show_model_required_warning()
                return
            self.start_recording()
        else:
            self.stop_recording_and_transcribe()

    def start_recording(self) -> None:
        if self.is_busy:
            return
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError:
            messagebox.showerror(
                self.t("dialog_missing_dependency_title"),
                self.t("dialog_missing_sounddevice_body"),
            )
            return

        self.recording_frames.clear()
        self.last_audio_level_sent = 0.0
        self._reset_audio_meter()

        def callback(indata: Any, frames: int, time_info: Any, status: Any) -> None:
            if status:
                self.events.put(
                    ("status", self.t("recording_warning", status=status))
                )
            self.recording_frames.append(bytes(indata))
            now = time.monotonic()
            if now - self.last_audio_level_sent >= 0.04:
                self.last_audio_level_sent = now
                try:
                    peak = float(np.max(np.abs(indata.astype("int32")))) / 32768.0
                except Exception:
                    peak = 0.0
                self.events.put(("audio_level", peak))

        try:
            self.recording_stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                callback=callback,
            )
            self.recording_stream.start()
        except Exception as exc:
            self.recording_stream = None
            messagebox.showerror(self.t("dialog_recording_error_title"), str(exc))
            return

        self.set_busy(True)
        self.recording_started_at = time.monotonic()
        self.status_var.set(self.t("status_recording"))
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress_var.set(0)
        self.progress_text_var.set("")
        self._update_recording_timer()

    def _update_recording_timer(self) -> None:
        if self.recording_stream is None or self.recording_started_at is None:
            return
        elapsed = int(time.monotonic() - self.recording_started_at)
        minutes, seconds = divmod(elapsed, 60)
        self.timer_var.set(f"{minutes:02d}:{seconds:02d}")
        self.recording_job = self.after(250, self._update_recording_timer)

    def stop_recording_and_transcribe(self) -> None:
        if self.recording_stream is None:
            return
        try:
            self.recording_stream.stop()
            self.recording_stream.close()
        finally:
            self.recording_stream = None

        if self.recording_job is not None:
            self.after_cancel(self.recording_job)
            self.recording_job = None

        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress_var.set(0)
        self.progress_text_var.set("0%")
        self._reset_audio_meter()
        self._apply_dynamic_texts()

        if not self.recording_frames:
            self.set_busy(False)
            self.status_var.set(self.t("status_empty_recording"))
            return

        RECORDINGS_DIR.mkdir(exist_ok=True)
        wav_path = RECORDINGS_DIR / f"recording_{datetime.now():%Y%m%d_%H%M%S}.wav"
        try:
            with wave.open(str(wav_path), "wb") as wav_file:
                wav_file.setnchannels(CHANNELS)
                wav_file.setsampwidth(2)
                wav_file.setframerate(SAMPLE_RATE)
                wav_file.writeframes(b"".join(self.recording_frames))
        except OSError as exc:
            self.set_busy(False)
            messagebox.showerror(self.t("dialog_wav_error_title"), str(exc))
            return

        self.status_var.set(self.t("status_wav_saved", file=wav_path.name))
        self.transcribe_audio(wav_path)

    def download_selected_model(self) -> None:
        if self.is_busy:
            return
        if not has_module("faster_whisper"):
            self.show_faster_whisper_required_error()
            return
        self.save_current_options()
        model_size = self.model_var.get().strip() or "base"
        target = self.selected_model_path()
        self.set_busy(True)
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress_var.set(0)
        self.progress_text_var.set("0%")
        self.status_var.set(
            self.t("status_downloading_model_to", model_size=model_size, path=target)
        )
        device, compute_type = self.selected_runtime()

        thread = threading.Thread(
            target=self._download_worker,
            args=(model_size, target, dict(self.translations), device, compute_type),
            daemon=True,
        )
        thread.start()

    def _format_with(
        self,
        translations: dict[str, str],
        key: str,
        **kwargs: Any,
    ) -> str:
        template = translations.get(key, BUILTIN_TRANSLATIONS.get(key, key))
        try:
            return template.format(**kwargs)
        except (KeyError, ValueError):
            return template

    def _download_worker(
        self,
        model_size: str,
        target: Path,
        translations: dict[str, str],
        device: str,
        compute_type: str,
    ) -> None:
        try:
            import httpx
            from huggingface_hub import HfApi, hf_hub_url

            target.mkdir(parents=True, exist_ok=True)
            repo_id = MODEL_REPO_IDS.get(
                model_size,
                f"Systran/faster-whisper-{model_size}",
            )
            api = HfApi()
            info = api.model_info(repo_id, files_metadata=True)
            files: list[tuple[str, int]] = []
            for sibling in getattr(info, "siblings", []) or []:
                filename = str(getattr(sibling, "rfilename", "") or "")
                if filename and is_model_repo_file(filename):
                    files.append((filename, repo_sibling_size(sibling)))

            if not files:
                raise RuntimeError(f"No model files found in {repo_id}")

            total_bytes = sum(size for _, size in files)
            completed_bytes = 0
            completed_files = 0
            downloaded_any = False

            def emit_progress(current_file_bytes: int = 0) -> None:
                if total_bytes > 0:
                    done = min(total_bytes, completed_bytes + current_file_bytes)
                    percent = done / total_bytes * 100.0
                    status = self._format_with(
                        translations,
                        "status_downloading_model_progress",
                        model_size=model_size,
                        percent=percent,
                        downloaded=format_size(done),
                        total=format_size(total_bytes),
                    )
                else:
                    percent = completed_files / max(len(files), 1) * 100.0
                    status = self._format_with(
                        translations,
                        "status_downloading_model_progress",
                        model_size=model_size,
                        percent=percent,
                        downloaded=f"{completed_files}",
                        total=f"{len(files)} files",
                    )
                self.events.put(("progress", percent))
                self.events.put(("status", status))

            emit_progress(0)
            for filename, expected_size in files:
                destination = target / filename
                part_path = destination.with_name(f"{destination.name}.part")
                destination.parent.mkdir(parents=True, exist_ok=True)

                if expected_size and destination.exists():
                    existing_size = destination.stat().st_size
                    if existing_size == expected_size:
                        completed_files += 1
                        completed_bytes += expected_size
                        emit_progress(0)
                        continue
                    destination.replace(part_path)

                resume_from = part_path.stat().st_size if part_path.exists() else 0
                if expected_size and resume_from > expected_size:
                    part_path.unlink()
                    resume_from = 0

                seen = resume_from
                emit_progress(seen)

                url = hf_hub_url(repo_id=repo_id, filename=filename)
                headers = {"Accept-Encoding": "identity"}
                mode = "ab" if resume_from else "wb"
                if resume_from:
                    headers["Range"] = f"bytes={resume_from}-"

                with httpx.stream(
                    "GET",
                    url,
                    follow_redirects=True,
                    headers=headers,
                    timeout=None,
                ) as response:
                    if resume_from and response.status_code != 206:
                        response.close()
                        part_path.unlink(missing_ok=True)
                        resume_from = 0
                        seen = 0
                        mode = "wb"
                        headers.pop("Range", None)
                        with httpx.stream(
                            "GET",
                            url,
                            follow_redirects=True,
                            headers=headers,
                            timeout=None,
                        ) as restart_response:
                            restart_response.raise_for_status()
                            with part_path.open(mode) as output:
                                for chunk in restart_response.iter_bytes(
                                    chunk_size=1024 * 1024
                                ):
                                    if not chunk:
                                        continue
                                    downloaded_any = True
                                    output.write(chunk)
                                    seen += len(chunk)
                                    emit_progress(seen)
                    else:
                        response.raise_for_status()
                        with part_path.open(mode) as output:
                            for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                                if not chunk:
                                    continue
                                downloaded_any = True
                                output.write(chunk)
                                seen += len(chunk)
                                emit_progress(seen)

                if expected_size and part_path.stat().st_size != expected_size:
                    raise RuntimeError(
                        f"Downloaded {filename} has unexpected size: "
                        f"{part_path.stat().st_size} != {expected_size}"
                    )
                part_path.replace(destination)
                completed_files += 1
                completed_bytes += expected_size if expected_size else seen
                emit_progress(0)

            exists = is_faster_whisper_model(target)
            total = directory_size(target) if exists else 0
            if exists:
                message = self._format_with(
                    translations,
                    "model_found",
                    model_size=model_size,
                    parameters=MODEL_PARAMETER_COUNTS.get(model_size, "unknown"),
                    path=target,
                    repo_id=repo_id,
                    size=format_size(total),
                    model_bin_size=format_size(file_size(target / "model.bin")),
                    device=device,
                    compute_type=compute_type,
                )
            else:
                message = self._format_with(
                    translations,
                    "model_invalid_after_download",
                    path=target,
                )
            self.events.put(
                (
                    "download_done",
                    ModelStatus(
                        exists,
                        target,
                        message,
                        total,
                        already_downloaded=exists and not downloaded_any,
                    ),
                )
            )
        except ImportError:
            self.events.put(
                (
                    "error",
                    self._format_with(translations, "dialog_missing_faster_whisper_body"),
                )
            )
        except Exception as exc:
            self.events.put(
                (
                    "error",
                    self._format_with(translations, "download_error", error=exc),
                )
            )

    def transcribe_audio(self, audio_path: Path) -> None:
        if not has_module("faster_whisper"):
            self.show_faster_whisper_required_error()
            return
        status = self.check_model_status(show_message=False)
        if not status.exists:
            self.show_model_required_warning()
            return

        self.save_current_options()
        existing_text = self.text.get("1.0", "end-1c").strip()
        self.transcript_append_started = False
        self.transcript_append_needs_separator = bool(existing_text)
        self.set_busy(True)
        self.progress_var.set(0)
        self.progress_text_var.set("")
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.status_var.set(self.t("status_loading_model"))
        device, compute_type = self.selected_runtime()

        options = {
            "model_path": str(status.path),
            "audio_path": str(audio_path),
            "language": self._language_for_transcribe(),
            "vad_filter": bool(self.vad_var.get()),
            "min_silence_duration_ms": self._safe_min_silence(),
            "beam_size": int(self.settings.get("beam_size", 1)),
            "condition_on_previous_text": bool(
                self.settings.get("condition_on_previous_text", True)
            ),
            "word_timestamps": bool(self.settings.get("word_timestamps", False)),
            "device": device,
            "compute_type": compute_type,
            "translations": dict(self.translations),
            "delete_after_transcribe": bool(self.delete_recordings_var.get())
            and self.is_recording_path(audio_path),
        }

        thread = threading.Thread(
            target=self._transcribe_worker,
            args=(options,),
            daemon=True,
        )
        thread.start()

    def _language_for_transcribe(self) -> str | None:
        language = self.language_var.get().strip().lower()
        if not language or language == "auto":
            return None
        return language

    def _transcribe_worker(self, options: dict[str, Any]) -> None:
        translations = options["translations"]
        try:
            from faster_whisper import WhisperModel

            model_key = (
                options["model_path"],
                options["device"],
                options["compute_type"],
            )
            if self.loaded_model is None or self.loaded_model_key != model_key:
                self.loaded_model = WhisperModel(
                    options["model_path"],
                    device=options["device"],
                    compute_type=options["compute_type"],
                    local_files_only=True,
                )
                self.loaded_model_key = model_key

            kwargs: dict[str, Any] = {
                "language": options["language"],
                "beam_size": options["beam_size"],
                "vad_filter": options["vad_filter"],
                "condition_on_previous_text": options[
                    "condition_on_previous_text"
                ],
                "word_timestamps": options["word_timestamps"],
            }
            if options["vad_filter"]:
                kwargs["vad_parameters"] = {
                    "min_silence_duration_ms": options["min_silence_duration_ms"],
                }

            segments, info = self.loaded_model.transcribe(
                options["audio_path"],
                **kwargs,
            )
            language = getattr(info, "language", None) or "unknown"
            probability = getattr(info, "language_probability", None)
            if probability is not None:
                self.events.put(
                    (
                        "status",
                        self._format_with(
                            translations,
                            "status_recognition_language_probability",
                            language=language,
                            probability=probability,
                        ),
                    )
                )
            else:
                self.events.put(
                    (
                        "status",
                        self._format_with(
                            translations,
                            "status_recognition_language",
                            language=language,
                        ),
                    )
                )
            for segment in segments:
                text = segment.text.strip()
                if text:
                    self.events.put(("append_text", text))

            if options.get("delete_after_transcribe"):
                try:
                    Path(options["audio_path"]).unlink(missing_ok=True)
                except OSError:
                    pass
            self.events.put(("transcribe_done", None))
        except ImportError:
            self.events.put(
                (
                    "error",
                    self._format_with(translations, "dialog_missing_faster_whisper_body"),
                )
            )
        except Exception as exc:
            self.events.put(
                (
                    "error",
                    self._format_with(translations, "transcribe_error", error=exc),
                )
            )

    def _process_events(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if kind == "status":
                self.status_var.set(str(payload))
            elif kind == "progress":
                value = max(0.0, min(100.0, float(payload)))
                self.progress_var.set(value)
                self.progress_text_var.set(f"{value:.0f}%")
            elif kind == "audio_level":
                if self.recording_stream is not None:
                    self._append_audio_level(float(payload))
            elif kind == "append_text":
                self._append_transcript_segment(str(payload))
            elif kind == "download_done":
                self.model_status_var.set(payload.message)
                self._set_model_available(payload.exists)
                if payload.exists:
                    self.clear_progress_status()
                    if payload.already_downloaded:
                        self.status_var.set(
                            self.t(
                                "status_model_already_downloaded",
                                model_size=payload.path.name,
                            )
                        )
                else:
                    self.progress.stop()
                    self.progress.configure(mode="determinate")
                    self.progress_var.set(0)
                    self.progress_text_var.set("0%")
                    self.status_var.set(self.t("status_model_missing"))
                self.set_busy(False)
            elif kind == "transcribe_done":
                self.progress.stop()
                self.progress.configure(mode="determinate")
                self.progress_var.set(0)
                self.progress_text_var.set("")
                self.status_var.set(self.t("status_ready"))
                self.set_busy(False)
            elif kind == "error":
                self.progress.stop()
                self.progress.configure(mode="determinate")
                self.progress_var.set(0)
                self.progress_text_var.set("0%")
                self.status_var.set(self.t("status_error"))
                self.set_busy(False)
                self.check_model_status(show_message=False)
                messagebox.showerror(self.t("dialog_error_title"), str(payload))

        self.after(80, self._process_events)

    def _append_transcript_segment(self, value: str) -> None:
        value = value.strip()
        if not value:
            return

        existing = self.text.get("1.0", "end-1c")
        if self.transcript_append_needs_separator and existing:
            if not existing.endswith("\n\n"):
                self.text.insert("end", "\n\n" if not existing.endswith("\n") else "\n")
            self.transcript_append_needs_separator = False
        elif self.transcript_append_started:
            self.text.insert("end", " ")
        elif existing and not existing.endswith(("\n", " ")):
            self.text.insert("end", "\n\n")

        self.text.insert("end", value)
        self.text.see("end")
        self.transcript_append_started = True

    def _selected_text_range(self) -> tuple[str, str] | None:
        try:
            return self.text.index("sel.first"), self.text.index("sel.last")
        except tk.TclError:
            return None

    def copy_text(self) -> None:
        selected = self._selected_text_range()
        if selected is None:
            value = self.text.get("1.0", "end-1c")
        else:
            value = self.text.get(selected[0], selected[1])
        self.clipboard_clear()
        self.clipboard_append(value)

    def cut_text(self) -> None:
        selected = self._selected_text_range()
        if selected is None:
            self.copy_text()
            self.clear_text()
            return
        value = self.text.get(selected[0], selected[1])
        self.clipboard_clear()
        self.clipboard_append(value)
        self.text.delete(selected[0], selected[1])

    def paste_text(self) -> None:
        try:
            value = self.clipboard_get()
        except tk.TclError:
            return
        selected = self._selected_text_range()
        if selected is not None:
            self.text.delete(selected[0], selected[1])
        self.text.insert("insert", value)

    def clear_text(self) -> None:
        self.text.delete("1.0", "end")

    def select_all_text(self) -> None:
        self.text.tag_add("sel", "1.0", "end-1c")
        self.text.mark_set("insert", "1.0")
        self.text.see("insert")

    def _on_text_keypress(self, event: tk.Event) -> str | None:
        ctrl = bool(event.state & 0x0004)
        shift = bool(event.state & 0x0001)
        keycode = int(getattr(event, "keycode", 0) or 0)

        if ctrl and keycode == 67:
            self.copy_text()
            return "break"
        if ctrl and keycode == 88:
            self.cut_text()
            return "break"
        if ctrl and keycode == 86:
            self.paste_text()
            return "break"
        if ctrl and keycode == 65:
            self.select_all_text()
            return "break"
        if shift and event.keysym == "Delete":
            self.cut_text()
            return "break"
        if ctrl and event.keysym == "Insert":
            self.copy_text()
            return "break"
        if shift and event.keysym == "Insert":
            self.paste_text()
            return "break"
        return None


def main() -> None:
    app = ListenerApp()
    app.mainloop()


if __name__ == "__main__":
    main()

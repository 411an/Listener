# Listener faster-whisper GUI

A small Windows desktop wrapper for recording microphone audio and transcribing it with [`SYSTRAN/faster-whisper`](https://github.com/SYSTRAN/faster-whisper).

The app is intentionally plain: choose a model, record audio, stop recording, and copy the transcript from a text box.

## Features

- Tkinter GUI, no web server.
- Microphone recording with a live level meter.
- Transcription with `base`, `small`, `medium`, or `large-v3`.
- Russian, English, or automatic transcription language detection.
- Optional VAD, enabled by default with `min_silence_duration_ms=700`.
- Configurable `beam_size` for quality/speed experiments.
- Transcript text is appended instead of replacing previous text.
- No fake transcription progress bar: text appears when `faster-whisper` returns completed segments.
- Transcription timer and final part count, including chunked long recordings.
- Model folder selection, model check, and model download from Hugging Face.
- Download progress with percent, target path, `.part` files, resume, and skip for already complete files.
- Model details: approximate parameters, disk size, `model.bin` size, repo, runtime, and local path.
- Optional deletion of recorded WAV files after successful transcription.
- English/Russian UI files in `locales/`.
- Text shortcuts work with non-English keyboard layouts: `Ctrl+C`, `Ctrl+X`, `Ctrl+V`, `Ctrl+A`, `Shift+Delete`, `Ctrl+Insert`, `Shift+Insert`.

## Installation

For a GitHub checkout, `run.cmd` does not install anything silently. If `.venv` is missing, it explains that it will create a local virtual environment and install packages from `requirements.txt`, then asks for confirmation.

```bat
run.cmd
```

Manual installation:

```powershell
py -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python faster_whisper_gui.py
```

`install.cmd`/`run.cmd` install Python packages only. Speech recognition models are downloaded later from the app when the user clicks `Download model`.

## Usage

1. Select a model: `base`, `small`, `medium`, or `large-v3`.
2. Choose a models folder with `Set model location`.
3. Click `Check model`.
4. If the selected model is missing, click `Download model`.
5. Click `Start recording`, then `Stop and transcribe`.

Until the selected model is available, recording is disabled and the status line asks the user to download or connect a model.

Models are stored under the configured `models_dir`, one folder per model:

```text
<models_dir>/
  base/
  small/
  medium/
  large-v3/
```

These are separate model downloads, not modes of one model. The large option in this app is `large-v3`; it is stored in a `large-v3` folder.

## Models

| App option | Hugging Face repo | Approx. parameters |
| --- | --- | --- |
| `base` | `Systran/faster-whisper-base` | 74M |
| `small` | `Systran/faster-whisper-small` | 244M |
| `medium` | `Systran/faster-whisper-medium` | 769M |
| `large-v3` | `Systran/faster-whisper-large-v3` | 1550M |

These public repos normally do not require authentication. A token is only needed for private or gated models.

## Downloads

The app queries Hugging Face file metadata before downloading. It downloads only known model files (`config.json`, `preprocessor_config.json`, `model.bin`, `tokenizer.json`, and vocabulary files) into:

```text
<models_dir>/<model_size>/
```

The status line shows the full destination path before downloading. Partial downloads use `.part` files. If the user clicks `Download model` again, complete files are skipped and incomplete `.part` files are resumed when possible.

After a successful download, the progress bar is cleared and the model block shows the downloaded model details. If the model was already complete, the app reports that it is already downloaded instead of silently doing nothing.

## Settings And UI Language

Settings are saved in `settings.json`; defaults are documented in `settings.example.json`. Local settings, downloaded models, and recordings are ignored by git.

The app reads `settings.json` and `locales/*.json` as UTF-8 with optional UTF-8 BOM, and saves `settings.json` as UTF-8 without BOM.

UI strings are stored in:

```text
locales/en.json
locales/ru.json
```

The interface language is selected in the options block and saved as `ui_language`.

## GPU

On startup, the app only detects hardware/runtime state. It checks for an NVIDIA GPU and then calls `ctranslate2.get_cuda_device_count()`. It does not prompt to install CUDA during startup.

- No NVIDIA GPU: the `Use GPU (CUDA)` checkbox is disabled and transcription uses `device="cpu"` / `compute_type="int8"`.
- NVIDIA GPU with usable CUDA: the checkbox is enabled and selected by default, unless the user previously chose CPU. GPU mode uses `device="cuda"` / `compute_type="float16"`.
- NVIDIA GPU without usable CUDA for CTranslate2: the checkbox is enabled but unchecked. When the user tries to enable it, the app shows setup instructions. Choosing Yes shows the instructions and closes the app so CUDA/cuDNN can be installed; choosing No keeps CPU mode.

The installer does not silently install CUDA/cuDNN. On Windows, faster-whisper expects the required NVIDIA CUDA/cuBLAS/cuDNN runtime DLLs to be available on `PATH`; follow the upstream faster-whisper GPU installation notes.

## Transcription Options

Default VAD settings:

```python
vad_filter=True
vad_parameters={"min_silence_duration_ms": 700}
```

VAD can be disabled in the app. The transcription language can be selected from the list or typed manually; `auto` enables language detection.

`beam_size` is configurable in the options block. The default is `1` for speed; higher values can improve some difficult recordings but are slower, especially on CPU.

Recordings longer than 25 seconds are transcribed in 25-second chunks. This avoids cases where the model/runtime effectively stops at the first 30-second Whisper window.

During transcription, the status line shows elapsed time. At the end, it reports how many parts were recognized and the total elapsed time.

`faster-whisper` returns completed segments, not live partial tokens or a GUI progress callback. The app appends those completed segments to the transcript box.

---

# Listener faster-whisper GUI на русском

Небольшая Windows-оболочка для записи с микрофона и распознавания речи через [`SYSTRAN/faster-whisper`](https://github.com/SYSTRAN/faster-whisper).

Приложение намеренно простое: выбрать модель, записать звук, остановить запись и скопировать расшифровку из текстового окна.

## Возможности

- GUI на Tkinter, без веб-сервера.
- Запись микрофона с живым индикатором уровня.
- Распознавание через `base`, `small`, `medium` или `large-v3`.
- Русский, английский или автоматическое определение языка распознавания.
- Опциональный VAD, по умолчанию включен с `min_silence_duration_ms=700`.
- Настраиваемый `beam_size` для проб качества/скорости.
- Расшифровка дописывается в текстовое окно, а не заменяет предыдущий текст.
- Без фальшивого прогрессбара расшифровки: текст появляется, когда `faster-whisper` возвращает готовые сегменты.
- Таймер расшифровки и итоговое число частей, включая длинные записи, разбитые на фрагменты.
- Выбор папки моделей, проверка модели и скачивание модели с Hugging Face.
- Прогресс скачивания с процентом, путем назначения, `.part` файлами, докачкой и пропуском уже полных файлов.
- Информация о модели: примерное число параметров, размер на диске, размер `model.bin`, repo, runtime и локальный путь.
- Опциональное удаление записанных WAV-файлов после успешной расшифровки.
- Английские и русские файлы интерфейса в `locales/`.
- Горячие клавиши текста работают при неанглийской раскладке: `Ctrl+C`, `Ctrl+X`, `Ctrl+V`, `Ctrl+A`, `Shift+Delete`, `Ctrl+Insert`, `Shift+Insert`.

## Установка

Для копии, скачанной с GitHub, `run.cmd` ничего не устанавливает молча. Если `.venv` отсутствует, скрипт объясняет, что создаст локальное виртуальное окружение и установит пакеты из `requirements.txt`, затем спрашивает подтверждение.

```bat
run.cmd
```

Ручная установка:

```powershell
py -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python faster_whisper_gui.py
```

`install.cmd`/`run.cmd` устанавливают только Python-пакеты. Модели распознавания скачиваются позже из приложения по кнопке `Скачать модель`.

## Как пользоваться

1. Выберите модель: `base`, `small`, `medium` или `large-v3`.
2. Выберите папку моделей через `Задать расположение модели`.
3. Нажмите `Проверить наличие модели`.
4. Если выбранной модели нет, нажмите `Скачать модель`.
5. Нажмите `Начать запись`, затем `Остановить и расшифровать`.

Пока выбранная модель недоступна, запись заблокирована, а строка состояния просит скачать модель или выбрать папку с уже существующей моделью.

Модели хранятся в настроенной папке `models_dir`, по одной папке на модель:

```text
<models_dir>/
  base/
  small/
  medium/
  large-v3/
```

Это отдельные скачиваемые модели, а не режимы одной модели. Большой вариант в приложении называется `large-v3`; он хранится в папке `large-v3`.

## Модели

| Опция в приложении | Репозиторий Hugging Face | Примерно параметров |
| --- | --- | --- |
| `base` | `Systran/faster-whisper-base` | 74M |
| `small` | `Systran/faster-whisper-small` | 244M |
| `medium` | `Systran/faster-whisper-medium` | 769M |
| `large-v3` | `Systran/faster-whisper-large-v3` | 1550M |

Эти публичные репозитории обычно не требуют авторизации. Токен нужен только для приватных или gated-моделей.

## Скачивание

Перед скачиванием приложение запрашивает метаданные файлов Hugging Face. Оно скачивает только известные файлы модели (`config.json`, `preprocessor_config.json`, `model.bin`, `tokenizer.json` и файлы словаря) в:

```text
<models_dir>/<model_size>/
```

Перед скачиванием строка состояния показывает полный путь назначения. Частичные скачивания используют `.part` файлы. Если снова нажать `Скачать модель`, полные файлы пропускаются, а неполные `.part` файлы по возможности докачиваются.

После успешного скачивания прогрессбар очищается, а блок модели показывает детали скачанной модели. Если модель уже была полной, приложение сообщает, что она уже скачана, вместо тихого бездействия.

## Настройки И Язык Интерфейса

Настройки сохраняются в `settings.json`; значения по умолчанию описаны в `settings.example.json`. Локальные настройки, скачанные модели и записи игнорируются git.

Приложение читает `settings.json` и `locales/*.json` как UTF-8 с допустимым UTF-8 BOM, а `settings.json` сохраняет как UTF-8 без BOM.

Строки интерфейса лежат в:

```text
locales/en.json
locales/ru.json
```

Язык интерфейса выбирается в блоке опций и сохраняется как `ui_language`.

## GPU

При запуске приложение только определяет состояние железа/runtime. Оно проверяет наличие NVIDIA GPU, затем вызывает `ctranslate2.get_cuda_device_count()`. Диалог установки CUDA на старте не показывается.

- NVIDIA GPU не найдена: галочка `Использовать GPU (CUDA)` заблокирована, распознавание идет с `device="cpu"` / `compute_type="int8"`.
- NVIDIA GPU найдена и CUDA доступна: галочка активна и включена по умолчанию, если пользователь раньше не выбрал CPU. GPU-режим использует `device="cuda"` / `compute_type="float16"`.
- NVIDIA GPU найдена, но CUDA недоступна для CTranslate2: галочка активна, но снята. При попытке включить ее приложение показывает инструкцию. Если выбрать Да, приложение покажет инструкцию и закроется, чтобы можно было установить CUDA/cuDNN; если выбрать Нет, останется CPU-режим.

Установщик не ставит CUDA/cuDNN молча. На Windows faster-whisper ожидает, что нужные NVIDIA CUDA/cuBLAS/cuDNN runtime DLL доступны в `PATH`; следуйте upstream-инструкции faster-whisper для GPU.

## Опции Расшифровки

Настройки VAD по умолчанию:

```python
vad_filter=True
vad_parameters={"min_silence_duration_ms": 700}
```

VAD можно выключить в приложении. Язык распознавания можно выбрать из списка или вписать вручную; `auto` включает автоопределение.

`beam_size` настраивается в блоке опций. По умолчанию стоит `1` для скорости; большие значения могут улучшить часть сложных записей, но работают медленнее, особенно на CPU.

Записи длиннее 25 секунд расшифровываются кусками по 25 секунд. Это обход для случаев, когда модель/runtime фактически останавливается на первом 30-секундном окне Whisper.

Во время расшифровки строка состояния показывает прошедшее время. В конце она сообщает, сколько частей было распознано и за сколько времени.

`faster-whisper` возвращает готовые сегменты, а не живые частичные токены или GUI-callback прогресса. Приложение дописывает эти готовые сегменты в текстовое окно.

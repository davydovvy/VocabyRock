# Kokoro pack audio generation

In the parent admin page, open **Word Packs** and select **Audio JSON** on a pack.
Copy the downloaded JSON to the GPU computer. `kokoro_words.py` generates three
24 kHz WAV takes per pronunciation using `af_heart`. When the saved IPA marks a
sound as optional, it generates both pronunciations. Each filename starts with
the word's existing GUID, followed by the word, pronunciation, and take number.
Kokoro receives phonemes derived from the saved IPA field.

After listening, keep the preferred WAV for each word and delete the others.
On the same pack in the admin page, select **Upload audio** and choose the WAVs.
If you select multiple takes for one GUID, the first selected file is used and
the rest are skipped. Uploading a new take replaces that word's prior audio.

## Docker on the GPU computer

Docker supplies Python 3.12, so the host's Python version does not matter.
These commands use Bash on Linux or WSL2. From the repository root, build the
image and make folders for the downloaded JSON, WAV files, and model cache:

```bash
docker build -f scripts/Dockerfile.kokoro -t kokoro-words ./scripts
mkdir -p input output/kokoro-audio output/kokoro-cache
# Copy the exported pack JSON into input/pack-audio.json.
docker run --rm --gpus all --user "$(id -u):$(id -g)" \
  -v "$PWD/input/pack-audio.json:/input/pack-audio.json:ro" \
  -v "$PWD/scripts/kokoro_overrides.example.json:/input/overrides.json:ro" \
  -v "$PWD/output/kokoro-audio:/output" \
  -v "$PWD/output/kokoro-cache:/cache" \
  kokoro-words --input /input/pack-audio.json --overrides /input/overrides.json
```

This default image uses the CUDA 12.8 PyTorch wheel. On an NVIDIA host, Docker
must have GPU access through the NVIDIA Container Toolkit; verify it with
`docker run --rm --gpus all ubuntu nvidia-smi`. If your driver needs CUDA 12.6,
build with `--build-arg TORCH_BACKEND=cu126` instead. The installed PyTorch
must report a GPU, or the generator will stop without falling back to CPU.

For a supported AMD ROCm GPU on Linux, build with
`--build-arg TORCH_BACKEND=rocm6.3` and replace `--gpus all` in the run command
with `--device /dev/kfd --device /dev/dri --security-opt seccomp=unconfined`.
ROCm compatibility depends on the specific GPU and host driver.

Each word gets three takes in the same `af_heart` voice, at speeds 1.0,
1.05, and 1.10 by default, for each pronunciation choice. Kokoro inference is
deterministic at a fixed speed, so a different random seed would not produce a
different take.
Use `--dry-run` to preview filenames, `--limit 3` for a short trial, `--words
sure bridge` to select words, or `--takes 1` to generate one take. For a
vocabulary ZIP, add a read-only file mount and the input arguments:

```bash
docker run --rm --gpus all --user "$(id -u):$(id -g)" \
  -v "$PWD/output/kokoro-audio:/output" \
  -v "$PWD/output/kokoro-cache:/cache" \
  -v "$PWD/vacabyrock-vocabulary.zip:/input/vocabulary.zip:ro" \
  kokoro-words --input /input/vocabulary.zip --pack "Lesson 2" --limit 8
```

The image includes spaCy's English data. The first synthesis downloads the
Kokoro model and voices from Hugging Face. The cache mount keeps them for later
runs. The `--user` option makes output files owned by your account; the mounted
output and cache folders must be writable by that UID. Existing takes and the
manifest are protected; use `--overwrite` or mount a new output folder to run
again without replacing files you like.

## Native Python alternative

Use Python 3.11–3.13 in a fresh virtual environment. Install a GPU-enabled
PyTorch build using the command for your OS and CUDA or ROCm version from the
[official PyTorch selector](https://pytorch.org/get-started/locally/). Then run:

```bash
python -m pip install kokoro==0.9.4 soundfile
python -c "import torch; print(torch.cuda.is_available())"
```

The last command must print `True`. PyTorch exposes ROCm GPUs through the same
`torch.cuda` interface. The first synthesis downloads the Kokoro-82M model and
voice from Hugging Face, so an internet connection is needed for that run.
On Windows, use `py -3.12` in place of `python` if needed.

Copy `kokoro_words.py`, `kokoro_lesson2.json`, and
`kokoro_overrides.example.json` to the GPU computer, keeping them in the same
folder. From that folder:

```bash
python kokoro_words.py --dry-run
python kokoro_words.py --output kokoro-output
```

The output folder will contain three WAV files per pronunciation choice, plus a
`manifest.json` recording each word GUID, source IPA, explicit phoneme choices,
voice, take, and filename.
By default the script requires a GPU; `--device cpu` is available for a CPU
trial. Use `--voice` to override the exported voice, `--takes` to override the
take count, `--words sure bridge` to select words, or `--limit 3` for a shorter run.
Existing output files are protected unless `--overwrite` is passed.

To use the pack JSON exported from VacabyRock:

```bash
python kokoro_words.py --input pack-audio.json \
  --overrides kokoro_overrides.example.json --output kokoro-output
```

The bundled `kokoro_lesson2.json` is only a demo with placeholder GUIDs. Use
the JSON exported from your actual pack for uploadable filenames.

The converter uses the first broad `/IPA/` transcription when Wiki also gives
narrow `[IPA]` notes. It expands parentheses into explicit forms; for example,
`sentence` with optional `(t)` produces a form with and without `t`. It maps
rhotic vowels, vowel length, syllabic consonants, diphthongs, and affricates to
Kokoro's American English phoneme set. It checks that set before loading the
model and reports all words needing review instead of silently dropping sounds.
It also maps the American flap `ɾ` in dictionary IPA to Kokoro's `T` token.

Some IPA symbols have no unambiguous American English mapping. In the current
library, `cross` (`ɒ`), `morning` (`o`), and `order` (`o`) need a decision. The
included [override example](kokoro_overrides.example.json) gives explicit
Kokoro phonemes for them; review or edit those choices before generating.
You can pass your own JSON file with `--overrides path/to/overrides.json`, keyed
by English word. A value may be one phoneme string or a list of alternatives.
Overrides are recorded in `manifest.json`. The generator never falls back to
spelling when an IPA conversion is uncertain.

The conversion follows Kokoro's English symbol set, but Wiki transcriptions
can represent different accents or contain mistakes. For example, a bare `e`
is mapped to Kokoro's `ɛ` as a practical English approximation. Listen before
uploading, and use an override whenever the saved transcription or automatic
mapping produces the wrong sound.

For the full Lesson 2 pack, the converter prepares 34 words and 36 pronunciation
choices with the example overrides. Review the resulting `manifest.json` and
listen to the samples: a valid IPA transcription still does not guarantee that
Kokoro will produce the desired accent or pronunciation.

### Why a short clip can sound like an extra word

The `value` source transcription is `/ˈvæl.ju/`; the script does not add an
article. It now converts this to Kokoro's `vˈælju`, moving the stress mark to
the vowel. It also maps IPA diphthongs such as `eɪ` and `aɪ` to Kokoro's
[English phoneme symbols](https://github.com/hexgrad/misaki/blob/main/EN_PHONES.md).
The earlier conversion left stress before the initial consonant and split
diphthongs into separate tokens, which could hurt pronunciation.

Even with correct phonemes, the model's
[voice notes](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)
warn that very short utterances can be weak. A reported
[boundary-token issue](https://github.com/hexgrad/kokoro/issues/344) also finds
that speeds below `1.0` can produce a phantom opening vowel. The default speed
is `1.0`; compare the three takes and keep the cleanest one.

For words that sound wrong when spoken alone, try the included
[`kokoro_phrase_contexts.example.json`](kokoro_phrase_contexts.example.json).
It gives `key` and `affirmative` two sentence contexts each. Kokoro transcribes
the surrounding sentence, then the generator replaces the target word with its
IPA-derived phonemes. It saves only the target word, cutting near the surrounding
word boundary and pause. Each context is marked `context01`, `context02`, etc.
in the filename and manifest. Keep this trial in a new output folder:

```bash
python kokoro_words.py --input pack-audio.json --words key affirmative \
  --phrase-contexts kokoro_phrase_contexts.example.json \
  --output kokoro-phrase-trial
```

To run this in Docker, mount that JSON file at `/input/contexts.json` alongside
the pack export, then add `--phrase-contexts /input/contexts.json --words key
affirmative` to the command. You can edit the sentences or add words with one
`{word}` placeholder each. A word without an entry still uses direct synthesis.
The target must appear between other words; a following comma often gives
Kokoro room to finish it before the cut.

The word boundaries are estimated from Kokoro's predicted token durations,
so listen for clipped or extra sounds before uploading. The `key` phonemes
`kˈi` already match Kokoro's own English conversion, yet isolated and repeated
takes may still sound like a different word. The `affirmative` IPA
`/əˈfɝməɾɪv/` becomes `əfˈɜɹməTɪv`, matching Kokoro's flap token, but that
mapping alone may not remove an unwanted sound at the end.

`--context-repeats 5` remains available as another experiment: it generates
five repetitions and saves the middle one. Use it without `--phrase-contexts`.

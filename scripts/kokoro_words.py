"""Generate uploadable Kokoro-82M WAV takes from a VacabyRock pack export."""

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any
from uuid import UUID

SAMPLE_INPUT = Path(__file__).with_name("kokoro_lesson2.json")
DEFAULT_OUTPUT = Path("output/kokoro-audio")
MODEL_ID = "hexgrad/Kokoro-82M"
DEFAULT_VOICE = "af_heart"
DEFAULT_TAKES = 3
VOWELS = "AIOWYaeiouɑɐɒæɔəɛɜɨɪɯøœʊʌɤ"


def load_words(path: Path, pack_name: str | None) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".zip":
        if not pack_name:
            raise ValueError("--pack is required for a vocabulary ZIP")
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != "vacabyrock-vocabulary":
            raise ValueError("Expected a VacabyRock vocabulary archive")
        pack = next((p for p in manifest["packs"] if p["name"] == pack_name), None)
        if pack is None:
            raise ValueError(f"Pack {pack_name!r} is missing from {path}")
        by_guid = {word["guid"]: word for word in manifest["words"]}
        return [by_guid[guid] for guid in pack["word_guids"]]
    data = json.loads(path.read_text(encoding="utf-8"))
    name = data.get("pack")
    if data.get("format") == "vacabyrock-audio-generation" and data.get("version") == 1:
        name = name.get("name") if isinstance(name, dict) else None
    elif not isinstance(name, str):
        raise ValueError("Expected a VacabyRock audio generation JSON")
    if pack_name and name != pack_name:
        raise ValueError(f"Expected pack {pack_name!r} in {path}")
    return data["words"]


def normalize_ipa(ipa: str) -> str:
    """Convert dictionary IPA to Kokoro's American English phoneme alphabet."""
    ipa = ipa.strip()
    if len(ipa) >= 2 and (ipa[0], ipa[-1]) in {("/", "/"), ("[", "]")}:
        ipa = ipa[1:-1]
    ipa = ipa.translate(str.maketrans("", "", ".̯̩"))
    for source, target in (
        ("d͡ʒ", "ʤ"),
        ("t͡ʃ", "ʧ"),
        ("t͡s", "ʦ"),
        ("eɪ", "A"),
        ("aɪ", "I"),
        ("oʊ", "O"),
        ("aʊ", "W"),
        ("ɔɪ", "Y"),
        ("ɚ", "əɹ"),
    ):
        ipa = ipa.replace(source, target)
    # Dictionary IPA puts stress at syllable onset; Misaki puts it before the vowel.
    ipa = re.sub(
        rf"([ˈˌ])([^{VOWELS}ˈˌ]*)([{VOWELS}])",
        lambda match: match[2] + match[1] + match[3],
        ipa,
    )
    if "ˈ" not in ipa and "ˌ" not in ipa:
        nuclei = list(re.finditer(rf"[{VOWELS}]+", ipa))
        if len(nuclei) == 1:
            index = nuclei[0].start()
            ipa = ipa[:index] + "ˈ" + ipa[index:]
    return ipa


def filename(guid: str, word: str, voice: str, take: int) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", word.lower()).strip("-")
    if not stem:
        raise ValueError(f"Cannot make a filename for {word!r}")
    return f"{guid}--{stem}--{voice.replace(',', '-')}--take{take:02d}.wav"


def take_speed(base_speed: float, take: int) -> float:
    return base_speed * (1 + 0.05 * (take - 1))


def prepare(
    words: list[dict[str, Any]], selected: list[str], limit: int | None
) -> list[dict[str, Any]]:
    wanted = {word.casefold() for word in selected}
    if wanted:
        found = {word["english"].casefold() for word in words}
        missing = wanted - found
        if missing:
            raise ValueError(f"Words not found: {', '.join(sorted(missing))}")
        words = [word for word in words if word["english"].casefold() in wanted]
    if limit is not None:
        words = words[:limit]
    prepared = []
    for index, word in enumerate(words, 1):
        try:
            guid = str(UUID(word["guid"]))
        except (KeyError, ValueError) as exc:
            raise ValueError(f"{word['english']!r} has no valid word GUID") from exc
        ipa = (word.get("ipa") or "").strip()
        if not ipa:
            raise ValueError(f"{word['english']!r} has no IPA transcription")
        if "(" in ipa or ")" in ipa:
            raise ValueError(
                f"{word['english']!r} has optional IPA sounds; choose one transcription"
            )
        phonemes = normalize_ipa(ipa)
        if not phonemes:
            raise ValueError(f"{word['english']!r} has an empty IPA transcription")
        prepared.append(
            {
                "guid": guid,
                "english": word["english"],
                "ipa": ipa,
                "phonemes": phonemes,
                "index": index,
            }
        )
    if not prepared:
        raise ValueError("No words selected")
    return prepared


def generate(
    prepared: list[dict[str, Any]],
    output: Path,
    voice: str,
    takes: int,
    speed: float,
    device: str,
    overwrite: bool,
) -> None:
    try:
        import soundfile as sf
        import torch
        from kokoro import KPipeline
    except ImportError as exc:
        raise RuntimeError("Install Kokoro, soundfile, and GPU-enabled PyTorch first") from exc

    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError(
            "GPU is unavailable to PyTorch; install a CUDA/ROCm build or use --device cpu"
        )

    # KModel silently drops characters absent from its vocabulary, so reject them.
    pipeline = KPipeline(lang_code="a", repo_id=MODEL_ID, device=device)
    vocabulary = pipeline.model.vocab
    for item in prepared:
        unsupported = sorted(set(item["phonemes"]) - vocabulary.keys())
        if unsupported:
            raise ValueError(
                f"{item['english']!r}: IPA {item['ipa']!r} contains Kokoro-unsupported "
                f"symbols {unsupported!r} after conversion to {item['phonemes']!r}"
            )

    paths = [
        output / filename(item["guid"], item["english"], voice, take)
        for item in prepared
        for take in range(1, takes + 1)
    ]
    paths.append(output / "manifest.json")
    if not overwrite and any(path.exists() for path in paths):
        raise FileExistsError(f"Output already exists in {output}; use --overwrite")
    output.mkdir(parents=True, exist_ok=True)

    for item in prepared:
        item["takes"] = []
        for take in range(1, takes + 1):
            # Kokoro inference is deterministic; vary speed to make distinct takes.
            current_speed = take_speed(speed, take)
            result = next(
                pipeline.generate_from_tokens(item["phonemes"], voice=voice, speed=current_speed),
                None,
            )
            if result is None or result.audio is None or result.audio.numel() == 0:
                raise RuntimeError(f"Kokoro produced no audio for {item['english']!r}")
            name = filename(item["guid"], item["english"], voice, take)
            sf.write(output / name, result.audio.cpu().numpy(), 24000, subtype="PCM_16")
            item["takes"].append(
                {"voice": voice, "take": take, "speed": current_speed, "file": name}
            )
            print(f"{item['english']:<16} {voice} take {take} -> {output / name}")

    manifest = {
        "model": MODEL_ID,
        "voice": voice,
        "takes_per_word": takes,
        "speed": speed,
        "device": device,
        "sample_rate": 24000,
        "words": prepared,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=SAMPLE_INPUT,
        help="Lesson JSON or VacabyRock vocabulary ZIP",
    )
    parser.add_argument("--pack", help="Pack name in input (required for ZIP)")
    parser.add_argument("--words", nargs="*", default=[], help="English words to generate")
    parser.add_argument("--limit", type=int, help="Generate only the first N selected words")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--voice", help="American English voice (default: exported setting)")
    parser.add_argument("--takes", type=int, help="Takes per word (default: exported setting)")
    parser.add_argument("--speed", type=float, help="Speech speed (default: exported setting)")
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show phonemes without loading Kokoro"
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        if args.limit is not None and args.limit < 1:
            raise ValueError("--limit must be positive")
        settings = (
            json.loads(args.input.read_text(encoding="utf-8"))
            if args.input.suffix.lower() == ".json"
            else {}
        )
        voice = args.voice or settings.get("voice", DEFAULT_VOICE)
        takes = (
            args.takes if args.takes is not None else settings.get("takes_per_word", DEFAULT_TAKES)
        )
        speed = args.speed if args.speed is not None else settings.get("speed", 1.0)
        if not isinstance(takes, int) or not 1 <= takes <= 10:
            raise ValueError("--takes must be between 1 and 10")
        if not isinstance(speed, (int, float)) or speed <= 0:
            raise ValueError("--speed must be positive")
        if not isinstance(voice, str) or not re.fullmatch(r"a[fm]_[a-z0-9]+", voice):
            raise ValueError(f"Invalid American English voice: {voice!r}")
        prepared = prepare(load_words(args.input, args.pack), args.words, args.limit)
        if args.dry_run:
            for item in prepared:
                print(f"{item['english']:<16} {item['ipa']:<22} -> {item['phonemes']}")
                for take in range(1, takes + 1):
                    print(f"  {filename(item['guid'], item['english'], voice, take)}")
        else:
            generate(prepared, args.output, voice, takes, speed, args.device, args.overwrite)
    except (OSError, KeyError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

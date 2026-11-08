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
# Misaki's American English inventory, which is narrower than the model's
# multilingual vocabulary. An encodable model token is not necessarily an
# English phoneme the voice learned to pronounce.
ENGLISH_PHONES = frozenset("AIOTWYbdfhijklmnpstuvwzðŋɑɔəɛɜɡɪɹʃʊʌʒʤʧˈˌθᵊæᵻ")
MAX_PRONUNCIATIONS = 8


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
    ipa = re.sub(r"([lmnɹ])̩", r"ᵊ\1", ipa)
    ipa = ipa.translate(str.maketrans("", "", ".̯̥ʰː"))
    for source, target in (
        ("d͡ʒ", "ʤ"),
        ("t͡ʃ", "ʧ"),
        ("t͡s", "ts"),
        ("eɪ", "A"),
        ("aɪ", "I"),
        ("oʊ", "O"),
        ("aʊ", "W"),
        ("ɔɪ", "Y"),
        ("ɝ", "ɜɹ"),
        ("ɚ", "əɹ"),
        ("ɫ", "l"),
        ("ɾ", "T"),
        ("ɐ", "ə"),
        ("r", "ɹ"),
        ("g", "ɡ"),
        ("e", "ɛ"),
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


def expand_optionals(ipa: str) -> list[str]:
    """Produce both pronunciations of each parenthesized IPA sound."""
    match = re.search(r"\(([^()]*)\)", ipa)
    if match is None:
        if "(" in ipa or ")" in ipa:
            raise ValueError(f"Malformed optional IPA sounds: {ipa!r}")
        return [ipa]
    before, optional, after = ipa[: match.start()], match[1], ipa[match.end() :]
    if not optional:
        raise ValueError(f"Empty optional IPA sounds: {ipa!r}")
    omitted = expand_optionals(before + after)
    included = expand_optionals(before + optional + after)
    variants = list(dict.fromkeys(omitted + included))
    if len(variants) > MAX_PRONUNCIATIONS:
        raise ValueError(f"Too many optional pronunciations in {ipa!r}")
    return variants


def ipa_pronunciations(ipa: str) -> list[dict[str, str]]:
    """Prefer broad /IPA/ when Wiki also supplies narrow [IPA] detail."""
    broad = re.search(r"/([^/]+)/", ipa)
    narrow = re.search(r"\[([^]]+)\]", ipa)
    if broad:
        choices = [broad[1]]
    elif narrow:
        choices = [part.strip() for part in narrow[1].split("~")]
    else:
        raise ValueError(f"No /IPA/ or [IPA] transcription in {ipa!r}")
    pronunciations = []
    for choice in choices:
        for expanded in expand_optionals(choice):
            phonemes = normalize_ipa(expanded)
            unsupported = sorted(set(phonemes) - ENGLISH_PHONES)
            if unsupported:
                raise ValueError(
                    f"IPA {ipa!r} has ambiguous or unsupported English sounds "
                    f"{unsupported!r} after conversion to {phonemes!r}; add an override"
                )
            if not phonemes:
                raise ValueError(f"Empty pronunciation in {ipa!r}")
            if all(item["phonemes"] != phonemes for item in pronunciations):
                pronunciations.append({"ipa_variant": expanded, "phonemes": phonemes})
    if len(pronunciations) > MAX_PRONUNCIATIONS:
        raise ValueError(f"Too many pronunciations in {ipa!r}")
    return pronunciations


def filename(
    guid: str,
    word: str,
    voice: str,
    take: int,
    pronunciation: int = 1,
    context: int = 0,
) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", word.lower()).strip("-")
    if not stem:
        raise ValueError(f"Cannot make a filename for {word!r}")
    return (
        f"{guid}--{stem}--pron{pronunciation:02d}"
        f"{'--context' + format(context, '02d') if context else ''}--"
        f"{voice.replace(',', '-')}--take{take:02d}.wav"
    )


def take_speed(base_speed: float, take: int) -> float:
    return base_speed * (1 + 0.05 * (take - 1))


def repeated_phonemes(phonemes: str, repeats: int) -> str:
    return " ".join([phonemes] * repeats)


def crop_word_span(audio: Any, pred_dur: Any, tokens: str, start: int, end: int) -> Any:
    """Cut one word at the preceding space and following separator centers."""
    if len(pred_dur) != len(tokens) + 2:
        raise RuntimeError("Kokoro returned unexpected token durations for the phrase")
    if start < 1 or end >= len(tokens) or tokens[start - 1] != " ":
        raise ValueError("Target word must be surrounded by context")
    if tokens[end] not in " ,;:.!?":
        raise ValueError("Target word needs a following separator")
    durations = [int(value) for value in pred_dur]
    start_frame = sum(durations[:start]) + durations[start] / 2
    end_frame = sum(durations[: end + 1]) + durations[end + 1] / 2
    samples_per_frame = len(audio) / sum(durations)
    start_sample = round(start_frame * samples_per_frame)
    end_sample = round(end_frame * samples_per_frame)
    if end_sample <= start_sample:
        raise RuntimeError("Kokoro returned an empty target word")
    return audio[start_sample:end_sample]


def crop_middle_repetition(
    audio: Any, pred_dur: Any, phonemes: str, repeats: int
) -> Any:
    """Cut the middle word from a longer utterance."""
    tokens = repeated_phonemes(phonemes, repeats)
    middle = repeats // 2
    start = middle * (len(phonemes) + 1)
    end = start + len(phonemes)
    return crop_word_span(audio, pred_dur, tokens, start, end)


def phrase_phonemes(
    pipeline: Any, word: str, target: str, template: str
) -> tuple[str, int, int]:
    """Use Kokoro G2P for the sentence, but the saved IPA for its target word."""
    if template.count("{word}") != 1:
        raise ValueError(f"Phrase context for {word!r} must contain one {{word}}")
    _, tokens = pipeline.g2p(template.replace("{word}", word))
    matches = [
        index
        for index, token in enumerate(tokens)
        if token.text.casefold() == word.casefold()
    ]
    if len(matches) != 1:
        raise ValueError(f"Phrase context must contain exactly one standalone {word!r}")
    target_index = matches[0]
    parts = []
    for index, token in enumerate(tokens):
        if token.phonemes is None:
            raise ValueError(
                f"Kokoro could not transcribe {token.text!r} in a phrase context"
            )
        parts.append(
            (target if index == target_index else token.phonemes) + token.whitespace
        )
    phonemes = "".join(parts).strip()
    start = len("".join(parts[:target_index]).lstrip())
    end = start + len(target)
    if start < 1 or end >= len(phonemes) or phonemes[start - 1] != " ":
        raise ValueError(f"Place {word!r} between other words in the phrase context")
    return phonemes, start, end


def prepare(
    words: list[dict[str, Any]],
    selected: list[str],
    limit: int | None,
    overrides: dict[str, str | list[str]] | None = None,
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
    errors = []
    for index, word in enumerate(words, 1):
        try:
            guid = str(UUID(word["guid"]))
            ipa = (word.get("ipa") or "").strip()
            if not ipa:
                raise ValueError("has no IPA transcription")
            override = (overrides or {}).get(word["english"].casefold())
            if override is not None:
                if isinstance(override, str):
                    override = [override]
                if (
                    not isinstance(override, list)
                    or not 1 <= len(override) <= MAX_PRONUNCIATIONS
                    or any(
                        not isinstance(choice, str) or not choice for choice in override
                    )
                ):
                    raise ValueError("has an invalid phoneme override")
                pronunciations = []
                for phonemes in override:
                    unsupported = sorted(set(phonemes) - ENGLISH_PHONES)
                    if unsupported:
                        raise ValueError(
                            f"override {phonemes!r} has unsupported sounds {unsupported!r}"
                        )
                    pronunciations.append(
                        {"ipa_variant": "manual override", "phonemes": phonemes}
                    )
            else:
                pronunciations = ipa_pronunciations(ipa)
        except (KeyError, ValueError) as exc:
            errors.append(f"{word.get('english', '?')!r}: {exc}")
            continue
        prepared.append(
            {
                "guid": guid,
                "english": word["english"],
                "ipa": ipa,
                "phonemes": pronunciations[0]["phonemes"],
                "pronunciations": pronunciations,
                "index": index,
            }
        )
    if errors:
        raise ValueError("Review these transcriptions:\n" + "\n".join(errors))
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
    context_repeats: int = 1,
    phrase_contexts: dict[str, list[str]] | None = None,
) -> None:
    try:
        import soundfile as sf
        import torch
        from kokoro import KPipeline
    except ImportError as exc:
        raise RuntimeError(
            "Install Kokoro, soundfile, and GPU-enabled PyTorch first"
        ) from exc

    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError(
            "GPU is unavailable to PyTorch; install a CUDA/ROCm build or use --device cpu"
        )

    # KModel silently drops characters absent from its vocabulary, so reject them.
    pipeline = KPipeline(lang_code="a", repo_id=MODEL_ID, device=device)
    vocabulary = pipeline.model.vocab
    for item in prepared:
        for pronunciation in item["pronunciations"]:
            unsupported = sorted(set(pronunciation["phonemes"]) - vocabulary.keys())
            if unsupported:
                raise ValueError(
                    f"{item['english']!r}: IPA {item['ipa']!r} contains Kokoro-unsupported "
                    f"symbols {unsupported!r} after conversion to {pronunciation['phonemes']!r}"
                )

    phrase_contexts = phrase_contexts or {}
    paths = [
        output
        / filename(item["guid"], item["english"], voice, take, pronunciation, context)
        for item in prepared
        for pronunciation in range(1, len(item["pronunciations"]) + 1)
        for context in (
            range(1, len(phrase_contexts[item["english"].casefold()]) + 1)
            if item["english"].casefold() in phrase_contexts
            else (0,)
        )
        for take in range(1, takes + 1)
    ]
    paths.append(output / "manifest.json")
    if not overwrite and any(path.exists() for path in paths):
        raise FileExistsError(f"Output already exists in {output}; use --overwrite")
    output.mkdir(parents=True, exist_ok=True)

    for item in prepared:
        item["takes"] = []
        for pronunciation_index, pronunciation in enumerate(item["pronunciations"], 1):
            contexts = phrase_contexts.get(item["english"].casefold())
            choices = list(enumerate(contexts, 1)) if contexts else [(0, None)]
            for context_index, template in choices:
                if template:
                    phonemes, start, end = phrase_phonemes(
                        pipeline, item["english"], pronunciation["phonemes"], template
                    )
                else:
                    phonemes = repeated_phonemes(
                        pronunciation["phonemes"], context_repeats
                    )
                unsupported = sorted(set(phonemes) - vocabulary.keys())
                if unsupported:
                    raise ValueError(
                        f"{item['english']!r}: phrase context has Kokoro-unsupported "
                        f"symbols {unsupported!r}"
                    )
                for take in range(1, takes + 1):
                    # Kokoro inference is deterministic; vary speed to make distinct takes.
                    current_speed = take_speed(speed, take)
                    result = next(
                        pipeline.generate_from_tokens(
                            phonemes, voice=voice, speed=current_speed
                        ),
                        None,
                    )
                    if (
                        result is None
                        or result.audio is None
                        or result.audio.numel() == 0
                    ):
                        raise RuntimeError(
                            f"Kokoro produced no audio for {item['english']!r}"
                        )
                    audio = result.audio
                    if template or context_repeats > 1:
                        if result.pred_dur is None:
                            raise RuntimeError(
                                "Kokoro returned no token durations for context cropping"
                            )
                        if template:
                            audio = crop_word_span(
                                audio, result.pred_dur, phonemes, start, end
                            )
                        else:
                            audio = crop_middle_repetition(
                                audio,
                                result.pred_dur,
                                pronunciation["phonemes"],
                                context_repeats,
                            )
                        # The cut can land inside residual speech energy; soften both edges.
                        audio = audio.clone()
                        fade_samples = min(240, len(audio) // 10)
                        if fade_samples:
                            fade = torch.linspace(
                                0, 1, fade_samples, device=audio.device
                            )
                            audio[:fade_samples] *= fade
                            audio[-fade_samples:] *= fade.flip(0)
                    name = filename(
                        item["guid"],
                        item["english"],
                        voice,
                        take,
                        pronunciation_index,
                        context_index,
                    )
                    sf.write(
                        output / name, audio.cpu().numpy(), 24000, subtype="PCM_16"
                    )
                    item["takes"].append(
                        {
                            "voice": voice,
                            "take": take,
                            "speed": current_speed,
                            "pronunciation": pronunciation_index,
                            "file": name,
                            "context_repeats": context_repeats,
                            "phrase_context": template,
                            "synthesis_phonemes": phonemes,
                        }
                    )
                    print(
                        f"{item['english']:<16} {voice} pronunciation {pronunciation_index} "
                        f"context {context_index} take {take} -> {output / name}"
                    )

    manifest = {
        "model": MODEL_ID,
        "voice": voice,
        "takes_per_pronunciation": takes,
        "speed": speed,
        "device": device,
        "sample_rate": 24000,
        "context_repeats": context_repeats,
        "phrase_contexts": phrase_contexts,
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
    parser.add_argument(
        "--words", nargs="*", default=[], help="English words to generate"
    )
    parser.add_argument(
        "--limit", type=int, help="Generate only the first N selected words"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--voice", help="American English voice (default: exported setting)"
    )
    parser.add_argument(
        "--takes", type=int, help="Takes per pronunciation (default: exported setting)"
    )
    parser.add_argument(
        "--speed", type=float, help="Speech speed (default: exported setting)"
    )
    parser.add_argument(
        "--context-repeats",
        type=int,
        default=1,
        help="Generate an odd number of repetitions and save the middle word (try 5 for short words)",
    )
    parser.add_argument(
        "--phrase-contexts",
        type=Path,
        help="JSON mapping words to sentence templates containing {word}",
    )
    parser.add_argument(
        "--overrides",
        type=Path,
        help="JSON mapping English words to Kokoro phoneme strings",
    )
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
            args.takes
            if args.takes is not None
            else settings.get("takes_per_word", DEFAULT_TAKES)
        )
        speed = args.speed if args.speed is not None else settings.get("speed", 1.0)
        if not isinstance(takes, int) or not 1 <= takes <= 10:
            raise ValueError("--takes must be between 1 and 10")
        if not isinstance(speed, (int, float)) or speed <= 0:
            raise ValueError("--speed must be positive")
        if args.context_repeats not in (1, 3, 5, 7):
            raise ValueError("--context-repeats must be 1, 3, 5, or 7")
        if args.phrase_contexts and args.context_repeats != 1:
            raise ValueError("Use either --phrase-contexts or --context-repeats")
        if not isinstance(voice, str) or not re.fullmatch(r"a[fm]_[a-z0-9]+", voice):
            raise ValueError(f"Invalid American English voice: {voice!r}")
        overrides = {}
        if args.overrides:
            raw_overrides = json.loads(args.overrides.read_text(encoding="utf-8"))
            if not isinstance(raw_overrides, dict):
                raise ValueError("--overrides must contain a JSON object")
            for word, choices in raw_overrides.items():
                if not isinstance(word, str):
                    raise ValueError("Override word names must be strings")
                if isinstance(choices, str):
                    choices = [choices]
                if (
                    not isinstance(choices, list)
                    or not 1 <= len(choices) <= MAX_PRONUNCIATIONS
                    or any(
                        not isinstance(choice, str) or not choice for choice in choices
                    )
                ):
                    raise ValueError(f"Invalid override for {word!r}")
                overrides[word.casefold()] = choices
        phrase_contexts = {}
        if args.phrase_contexts:
            raw_contexts = json.loads(args.phrase_contexts.read_text(encoding="utf-8"))
            if not isinstance(raw_contexts, dict):
                raise ValueError("--phrase-contexts must contain a JSON object")
            for word, templates in raw_contexts.items():
                if not isinstance(word, str):
                    raise ValueError("Phrase context word names must be strings")
                if isinstance(templates, str):
                    templates = [templates]
                if (
                    not isinstance(templates, list)
                    or not 1 <= len(templates) <= MAX_PRONUNCIATIONS
                    or any(
                        not isinstance(template, str) or template.count("{word}") != 1
                        for template in templates
                    )
                ):
                    raise ValueError(f"Invalid phrase contexts for {word!r}")
                phrase_contexts[word.casefold()] = templates
        prepared = prepare(
            load_words(args.input, args.pack), args.words, args.limit, overrides
        )
        if args.dry_run:
            for item in prepared:
                print(f"{item['english']:<16} {item['ipa']}")
                for pronunciation_index, pronunciation in enumerate(
                    item["pronunciations"], 1
                ):
                    print(
                        f"  pronunciation {pronunciation_index}: "
                        f"{pronunciation['ipa_variant']} -> {pronunciation['phonemes']}"
                    )
                    contexts = phrase_contexts.get(item["english"].casefold())
                    for context_index, template in (
                        enumerate(contexts, 1) if contexts else [(0, None)]
                    ):
                        if template:
                            print(f"    context {context_index}: {template}")
                        for take in range(1, takes + 1):
                            print(
                                "    "
                                + filename(
                                    item["guid"],
                                    item["english"],
                                    voice,
                                    take,
                                    pronunciation_index,
                                    context_index,
                                )
                            )
        else:
            generate(
                prepared,
                args.output,
                voice,
                takes,
                speed,
                args.device,
                args.overwrite,
                args.context_repeats,
                phrase_contexts,
            )
    except (OSError, KeyError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from kokoro_words import (
    SAMPLE_INPUT,
    crop_middle_repetition,
    filename,
    ipa_pronunciations,
    load_words,
    normalize_ipa,
    phrase_phonemes,
    prepare,
    repeated_phonemes,
    take_speed,
)


class KokoroWordsTests(unittest.TestCase):
    def test_sample_uses_saved_ipa_and_normalizes_for_kokoro(self):
        words = load_words(SAMPLE_INPUT, "Lesson 2")
        prepared = prepare(words, ["bridge", "climb"], None)
        self.assertEqual(
            [(word["english"], word["ipa"], word["phonemes"]) for word in prepared],
            [("climb", "/ˈklaɪ̯m/", "klˈIm"), ("bridge", "/bɹɪd͡ʒ/", "bɹˈɪʤ")],
        )
        self.assertEqual(normalize_ipa("[ˈvæl.ju]"), "vˈælju")
        self.assertEqual(normalize_ipa("/əˈmeɪ.zɪŋ/"), "əmˈAzɪŋ")
        self.assertEqual(normalize_ipa("/ˈtɹaʊzɚz/"), "tɹˈWzəɹz")
        self.assertEqual(
            filename("00000000-0000-4000-8000-000000000002", "value", "af_heart", 2),
            "00000000-0000-4000-8000-000000000002--value--pron01--af_heart--take02.wav",
        )
        self.assertEqual(
            [round(take_speed(1.0, take), 2) for take in (1, 2, 3)], [1.0, 1.05, 1.1]
        )
        self.assertEqual(
            [item["phonemes"] for item in ipa_pronunciations("[ˈsɛn.tn̩(t)s]")],
            ["sˈɛntᵊns", "sˈɛntᵊnts"],
        )
        self.assertEqual(
            ipa_pronunciations("/pleɪ̯/ [pɫ̥eɪ̯ ~ pʰɫeɪ̯]")[0]["phonemes"],
            "plˈA",
        )
        self.assertEqual(normalize_ipa("/ˈskwɝl/"), "skwˈɜɹl")
        self.assertEqual(normalize_ipa("/əˈfɝməɾɪv/"), "əfˈɜɹməTɪv")

    def test_context_crop_uses_middle_word_and_neighboring_spaces(self):
        phonemes = "kˈi"
        self.assertEqual(repeated_phonemes(phonemes, 3), "kˈi kˈi kˈi")
        durations = [1] + [2] * len("kˈi kˈi kˈi") + [1]
        audio = list(range(sum(durations) * 10))
        cropped = crop_middle_repetition(audio, durations, phonemes, 3)
        self.assertEqual(cropped, audio[80:160])

    def test_phrase_context_keeps_saved_ipa_for_target_word(self):
        tokens = [
            SimpleNamespace(text="the", phonemes="ðə", whitespace=" "),
            SimpleNamespace(text="key", phonemes="wrong", whitespace=""),
            SimpleNamespace(text=",", phonemes=",", whitespace=" "),
            SimpleNamespace(text="then", phonemes="ðˈɛn", whitespace=""),
        ]
        pipeline = SimpleNamespace(g2p=lambda text: ("ignored", tokens))
        phonemes, start, end = phrase_phonemes(
            pipeline, "key", "kˈi", "the {word}, then"
        )
        self.assertEqual(phonemes, "ðə kˈi, ðˈɛn")
        self.assertEqual(phonemes[start:end], "kˈi")
        self.assertEqual(
            filename(
                "00000000-0000-4000-8000-000000000002", "key", "af_heart", 1, 1, 2
            ),
            "00000000-0000-4000-8000-000000000002--key--pron01--context02--af_heart--take01.wav",
        )
        with self.assertRaisesRegex(ValueError, "must contain one"):
            phrase_phonemes(pipeline, "key", "kˈi", "the key, then")

    def test_ambiguous_english_sound_requires_explicit_override(self):
        word = {
            "guid": "00000000-0000-4000-8000-000000000002",
            "english": "cross",
            "ipa": "/kɾɒs/",
        }
        with self.assertRaisesRegex(ValueError, "unsupported English sounds.*ɒ"):
            prepare([word], [], None)
        prepared = prepare([word], [], None, {"cross": ["kɹˈɔs", "kɹˈɑs"]})
        self.assertEqual(
            [item["phonemes"] for item in prepared[0]["pronunciations"]],
            ["kɹˈɔs", "kɹˈɑs"],
        )
        single = prepare([word], [], None, {"cross": "kɹˈɔs"})
        self.assertEqual(single[0]["phonemes"], "kɹˈɔs")
        with self.assertRaisesRegex(ValueError, "Malformed optional IPA"):
            ipa_pronunciations("/ˈsɛn(t(s)/")

    def test_archive_preserves_pack_order_and_rejects_missing_ipa(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vocabulary.zip"
            manifest = {
                "format": "vacabyrock-vocabulary",
                "packs": [
                    {
                        "name": "Lesson 2",
                        "word_guids": [
                            "00000000-0000-4000-8000-000000000002",
                            "00000000-0000-4000-8000-000000000001",
                        ],
                    }
                ],
                "words": [
                    {
                        "guid": "00000000-0000-4000-8000-000000000001",
                        "english": "a",
                        "ipa": "/æ/",
                    },
                    {
                        "guid": "00000000-0000-4000-8000-000000000002",
                        "english": "b",
                        "ipa": None,
                    },
                ],
            }
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("manifest.json", json.dumps(manifest))
            words = load_words(path, "Lesson 2")
            self.assertEqual([word["english"] for word in words], ["b", "a"])
            with self.assertRaisesRegex(ValueError, "has no IPA"):
                prepare(words, [], None)

    def test_exported_json_loads_without_pack_argument(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pack-audio.json"
            word = {
                "guid": "00000000-0000-4000-8000-000000000001",
                "english": "sure",
                "ipa": "/ʃʊɹ/",
            }
            path.write_text(
                json.dumps(
                    {
                        "format": "vacabyrock-audio-generation",
                        "version": 1,
                        "pack": {
                            "guid": "00000000-0000-4000-8000-000000000099",
                            "name": "Lesson 2",
                        },
                        "voice": "af_heart",
                        "takes_per_word": 3,
                        "words": [word],
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(load_words(path, None), [word])
            self.assertEqual(
                prepare(load_words(path, None), [], None)[0]["guid"], word["guid"]
            )


if __name__ == "__main__":
    unittest.main()

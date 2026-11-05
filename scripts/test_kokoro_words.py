import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from kokoro_words import (
    SAMPLE_INPUT,
    filename,
    load_words,
    normalize_ipa,
    prepare,
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
            "00000000-0000-4000-8000-000000000002--value--af_heart--take02.wav",
        )
        self.assertEqual([round(take_speed(1.0, take), 2) for take in (1, 2, 3)], [1.0, 1.05, 1.1])
        with self.assertRaisesRegex(ValueError, "optional IPA sounds"):
            prepare(
                [
                    {
                        "guid": words[0]["guid"],
                        "english": "sentence",
                        "ipa": "[ˈsɛn.tn̩(t)s]",
                    }
                ],
                [],
                None,
            )

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
            self.assertEqual(prepare(load_words(path, None), [], None)[0]["guid"], word["guid"])


if __name__ == "__main__":
    unittest.main()

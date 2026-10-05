import unittest

from subsetzer.langs import display_name, is_known_lang, normalise_lang


class LangTests(unittest.TestCase):
    def test_iso_639_1_codes(self):
        self.assertEqual(normalise_lang("en"), "en")
        self.assertEqual(normalise_lang("de"), "de")
        self.assertEqual(normalise_lang("fr"), "fr")
        self.assertEqual(normalise_lang("ja"), "ja")
        self.assertEqual(normalise_lang("ko"), "ko")

    def test_iso_639_2_codes(self):
        self.assertEqual(normalise_lang("eng"), "en")
        self.assertEqual(normalise_lang("deu"), "de")
        self.assertEqual(normalise_lang("fra"), "fr")
        self.assertEqual(normalise_lang("jpn"), "ja")

    def test_english_names(self):
        self.assertEqual(normalise_lang("English"), "en")
        self.assertEqual(normalise_lang("German"), "de")
        self.assertEqual(normalise_lang("French"), "fr")
        self.assertEqual(normalise_lang("Japanese"), "ja")
        self.assertEqual(normalise_lang("Chinese"), "zh-cn")
        self.assertEqual(normalise_lang("Korean"), "ko")
        self.assertEqual(normalise_lang("Spanish"), "es")

    def test_chinese_variants(self):
        self.assertEqual(normalise_lang("zh"), "zh-cn")
        self.assertEqual(normalise_lang("zh-cn"), "zh-cn")
        self.assertEqual(normalise_lang("zh-hans"), "zh-cn")
        self.assertEqual(normalise_lang("zh-tw"), "zh-tw")
        self.assertEqual(normalise_lang("zh-hant"), "zh-tw")
        self.assertEqual(normalise_lang("zho"), "zh-cn")
        self.assertEqual(normalise_lang("chi"), "zh-cn")

    def test_auto_preserved(self):
        self.assertEqual(normalise_lang("auto"), "auto")
        self.assertEqual(normalise_lang("Auto"), "auto")
        self.assertEqual(normalise_lang("AUTO"), "auto")

    def test_unknown_passthrough(self):
        self.assertEqual(normalise_lang("xyz-unknown"), "xyz-unknown")

    def test_case_insensitive(self):
        self.assertEqual(normalise_lang("GERMAN"), "de")
        self.assertEqual(normalise_lang("FrEnCh"), "fr")

    def test_is_known_lang_iso_codes(self):
        self.assertTrue(is_known_lang("en"))
        self.assertTrue(is_known_lang("de"))
        self.assertTrue(is_known_lang("ja"))
        self.assertTrue(is_known_lang("zh-cn"))
        self.assertTrue(is_known_lang("zh-tw"))
        self.assertTrue(is_known_lang("pt-br"))

    def test_is_known_lang_iso_639_2(self):
        self.assertTrue(is_known_lang("eng"))
        self.assertTrue(is_known_lang("deu"))
        self.assertTrue(is_known_lang("jpn"))

    def test_is_known_lang_english_names(self):
        self.assertTrue(is_known_lang("English"))
        self.assertTrue(is_known_lang("German"))
        self.assertTrue(is_known_lang("Chinese"))

    def test_is_known_lang_unknown(self):
        self.assertFalse(is_known_lang("xyz"))
        self.assertFalse(is_known_lang("xyz-unknown"))
        self.assertFalse(is_known_lang("not-a-language"))

    def test_is_known_lang_empty_and_auto(self):
        self.assertFalse(is_known_lang(""))
        self.assertFalse(is_known_lang("auto"))
        self.assertFalse(is_known_lang("Auto"))

    def test_is_known_lang_case_insensitive(self):
        self.assertTrue(is_known_lang("GERMAN"))
        self.assertTrue(is_known_lang("EnGlIsH"))


class DisplayNameTests(unittest.TestCase):
    def test_codes_to_names(self):
        self.assertEqual(display_name("de"), "German")
        self.assertEqual(display_name("English"), "English")
        self.assertEqual(display_name("zh-cn"), "Chinese")
        self.assertEqual(display_name("zh-hant"), "Zh-Hant")

    def test_auto_and_unknown(self):
        self.assertEqual(display_name("auto"), "auto")
        self.assertEqual(display_name(""), "auto")
        self.assertEqual(display_name("serbian"), "Serbian")

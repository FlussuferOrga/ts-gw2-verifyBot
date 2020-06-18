from unittest import TestCase

from StringShortener import StringShortener


class TestStringShortener(TestCase):
    def test_remove_tags(self):
        self.assertEqual(StringShortener.remove_tags("[RoE] Len", None), "Len")
        self.assertEqual(StringShortener.remove_tags("Len", None), "Len")
        self.assertEqual(StringShortener.remove_tags("[RoE][Side]Len", None), "Len")
        self.assertEqual(StringShortener.remove_tags("[RoE] [Side]Len", None), "Len")

    def test_only_some_words(self):
        self.assertEqual(StringShortener.only_some_words("Len Grey the First", 10), "Len Grey")
        self.assertEqual(StringShortener.only_some_words("Len Grey the First", 5), "Len")
        self.assertEqual(StringShortener.only_some_words("Len Grey the First", 50), "Len Grey the First")
        self.assertEqual(StringShortener.only_some_words("Leeeeeeeeeeeeeeeeeeen", 5), "Leeeeeeeeeeeeeeeeeeen")

    def test_only_first_word(self):
        self.assertEqual(StringShortener.only_first_word("Len Grey", None), "Len")
        self.assertEqual(StringShortener.only_first_word("Len", None), "Len")

    def test_ellipsis(self):
        self.assertEqual(StringShortener.ellipsis("Len Grey", 10), "Len Grey")
        self.assertEqual(StringShortener.ellipsis("Len Grey", 6), "Len...")

    def test_force(self):
        self.assertEqual(StringShortener.force("Len Grey", 10), "Len Grey")
        self.assertEqual(StringShortener.force("Len Grey", 3), "Len")

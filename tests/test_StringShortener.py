from unittest import TestCase

from bot.util.StringShortener import StringShortener


class StringShortenerTest(TestCase):
    def test_remove_tags(self):
        self.assertEqual("Len", StringShortener.remove_tags("[RoE] Len", None))
        self.assertEqual("Len", StringShortener.remove_tags("Len", None))
        self.assertEqual("Len", StringShortener.remove_tags("[RoE][Side]Len", None))
        self.assertEqual("Len", StringShortener.remove_tags("[RoE] [Side]Len", None))

    def test_only_some_words(self):
        self.assertEqual("Len Grey", StringShortener.only_some_words("Len Grey the First", 10))
        self.assertEqual("Len", StringShortener.only_some_words("Len Grey the First", 5))
        self.assertEqual("Len Grey the First", StringShortener.only_some_words("Len Grey the First", 50))
        self.assertEqual("Leeeeeeeeeeeeeeeeeeen", StringShortener.only_some_words("Leeeeeeeeeeeeeeeeeeen", 5))

    def test_only_first_word(self):
        self.assertEqual("Len", StringShortener.only_first_word("Len Grey", None))
        self.assertEqual("Len", StringShortener.only_first_word("Len", None))

    def test_ellipsis(self):
        self.assertEqual("Len Grey", StringShortener.ellipsis("Len Grey", 10))
        self.assertEqual("Len...", StringShortener.ellipsis("Len Grey", 6))

    def test_force(self):
        self.assertEqual("Len Grey", StringShortener.force("Len Grey", 10))
        self.assertEqual("Len", StringShortener.force("Len Grey", 3))

    def test_shortener(self):
        max_size = 30
        spacer = ", "

        shortened_strings = StringShortener(max_size).shorten(["[RoE][Side]Len der Zerstörer", "[RoE][Side]Len der Entwickler", "[RoE][Side]Len der Kommander"], spacer)
        self.assertLessEqual(len(spacer.join(shortened_strings)), max_size)
        self.assertEqual(['Len der', 'Len der', 'Len der'], shortened_strings)

    def test_shortener_2(self):
        max_size = 30
        spacer = ", "

        shortened_strings = StringShortener(max_size).shorten(["[RoE][Side]Len der Zerstörer"], spacer)
        self.assertLessEqual(len(spacer.join(shortened_strings)), max_size)
        self.assertEqual(["[RoE][Side]Len der Zerstörer"], shortened_strings)

    def test_shortener_3(self):
        max_size = 30
        spacer = ", "

        shortened_strings = StringShortener(max_size).shorten(["[RoE][Side]Len der Zerstörer", "Der Andere"], spacer)
        self.assertLessEqual(len(spacer.join(shortened_strings)), max_size)
        self.assertEqual(['Len der', 'Der Andere'], shortened_strings)

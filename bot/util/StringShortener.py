import math
import re
from functools import cmp_to_key
from typing import List


class StringShortener:
    @staticmethod
    def remove_tags(string, length):
        """
        Removes all guild tags, that is all groups of letters in brackets
        at the start of the string. "[x][y] [z] Name" -> "Name"
        """
        return re.search(r"^(?:\[.*\])*(.*)$", string).group(1).strip()

    @staticmethod
    def only_some_words(string, length):
        """
        Splits the string at whitespaces and removes as little
        tokens from the end as needed to match the required string length.
        """
        ts = string.split()
        i = 0
        res = ""
        while i < len(ts) and len(res + ts[i]) + i <= length:
            res = "%s %s" % (res, ts[i])
            i += 1
        res = res.strip()
        return res if len(res) > 0 else string

    @staticmethod
    def only_first_word(string, length):
        """
        Only uses the substring up to the first whitespace.
        """
        res = re.search(r"^(\S+)", string)
        return res.group(1).strip() if res is not None else string

    @staticmethod
    def ellipsis(string, length):
        """
        Cuts off the string (even in the middle of a word)
        and puts in an ellipsis at the end.
        """
        assert length > 3
        dots = "..."
        return "%s%s" % (string[:(length - len(dots))], dots) if len(string) > length else string

    @staticmethod
    def force(string, length):
        """
        Hard cutoff to a substring of a given length. Ultima ratio.
        """
        return string[:length] if len(string) > length else string

    @staticmethod
    def _shorten(strings, functions, length, spacer=", "):
        """
        Shortens a list of strings in various, increasingly intrusive ways.
        Tries to only modify the strings as much as needed and as little as possible.

        strings: the strings to shorten.
        fs: the functions to apply. They should be ordered in increasingly intrusice order.
        length: the maximum length the list should have when concatenated.
        spacer: the glue with which the list will be concatenated later on.
        returns: the input list where each string is shortened so the concatenated list fits the character limit.
        """
        if len(strings) == 0:
            return ""  # early bail
        desired_len_each = math.floor((length - (len(strings) - 1) * len(spacer)) / len(strings))  # devide length evenly, substract some space for the glue-string
        zipped_strings = sorted(zip(strings, range(0, len(strings))),  # zip strings with their original position in the input [(x_1, 0), (x_2, 1), ... (x_n, n-1)]
                                key=cmp_to_key(lambda x, y: len(x[0]) - len(y[0])))  # order ascending by string length

        # l = desired_len_each
        for i in range(len(zipped_strings)):
            next_function_i = 0
            string, position = zipped_strings[i]
            while len(string) > desired_len_each:
                string = functions[next_function_i](string, desired_len_each)
                zipped_strings[i] = (string, position)
                next_function_i += 1  # next_function_i is not checked to be within bounds.
                # This means the last function MUST succeed in shortening the string sufficiently!

            # l = desired_len_each + desired_len_each - len(string)  # list is ordered by string length,
            # so the earlier names could already be below the limit. In that case, they can "pass on" they characters they did not need.

        res = [s for s, p in sorted(zipped_strings, key=cmp_to_key(lambda x, y: x[1] - y[1]))]
        assert len(spacer.join(res)) <= length
        return res

    def shorten(self, ss: List[str], spacer=", "):
        return StringShortener._shorten(ss,
                                        [StringShortener.remove_tags,
                                         StringShortener.only_some_words,
                                         StringShortener.only_first_word,
                                         StringShortener.ellipsis,
                                         StringShortener.force],
                                        self.length, spacer)

    def __init__(self, length):
        self.length = length

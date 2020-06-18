import math
import re
from functools import cmp_to_key


class StringShortener(object):
    @staticmethod
    def remove_tags(s, length):
        """
        Removes all guild tags, that is all groups of letters in brackets
        at the start of the string. "[x][y] [z] Name" -> "Name"
        """
        return re.search(r"^(?:\[.*\])*(.*)$", s).group(1).strip()

    @staticmethod
    def only_some_words(s, length):
        """
        Splits the string at whitespaces and removes as little
        tokens from the end as needed to match the required string length.
        """
        ts = s.split()
        i = 0
        res = ""
        while i < len(ts) and len(res + ts[i]) + i <= length:
            res = "%s %s" % (res, ts[i])
            i += 1
        res = res.strip()
        return res if len(res) > 0 else s

    @staticmethod
    def only_first_word(s, length):
        """
        Only uses the substring up to the first whitespace.
        """
        res = re.search(r"^(\S+)", s)
        return res.group(1).strip() if res is not None else s

    @staticmethod
    def ellipsis(s, length):
        """
        Cuts off the string (even in the middle of a word)
        and puts in an ellipsis at the end.
        """
        assert length > 3
        dots = "..."
        return "%s%s" % (s[:(length - len(dots))], dots) if len(s) > length else s

    @staticmethod
    def force(s, length):
        """
        Hard cutoff to a substring of a given length. Ultima ratio.
        """
        return s[:length] if len(s) > length else s

    @staticmethod
    def _shorten(strings, fs, length, spacer=", "):
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
        sl = math.floor((length - (len(strings) - 1) * len(spacer)) / len(strings))  # devide length evenly, substract some space for the glue-string
        ss = sorted(zip(strings, range(0, len(strings))),  # zip strings with their original position in the input [(x_1, 0), (x_2, 1), ... (x_n, n-1)]
                    key=cmp_to_key(lambda x, y: len(x[0]) - len(y[0])))  # order ascending by string length

        # l = sl
        for i in range(len(ss)):
            j = 0
            s, p = ss[i]
            while len(s) > sl:
                s = fs[j](s, sl)
                ss[i] = (s, p)
                j += 1  # j is not checked to be within bounds. This means the last function MUST succeed in shortening the string sufficiently!
            # l = sl + sl - len(s)  # list is ordered by string length, so the earlier names could already be below the limit. In that case, they can "pass on" they characters they did not need.

        res = [s for s, p in sorted(ss, key=cmp_to_key(lambda x, y: x[1] - y[1]))]
        assert len(spacer.join(res)) <= length
        return res

    def shorten(self, ss, spacer=", "):
        return StringShortener._shorten(ss, [StringShortener.remove_tags, StringShortener.only_some_words, StringShortener.only_first_word, StringShortener.ellipsis, StringShortener.force],
                                        self.length, spacer)

    def __init__(self, length):
        self.length = length

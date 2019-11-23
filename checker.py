
import re
import os
import sys

import tags as tagger
import common


class CheckerBase:
    """Base class for checkers

    handle displaying errors, mostly.
    """
    def __init__(self):
        self.errors = 0

    colors = {"normal": ""}
    if os.isatty(sys.stdout.fileno()):
        # no termcap ... assume ANSI
        colors = {
            "red": "\033[31m",
            "green": "\033[32m",
            "yellow": "\033[33m",
            # 34 is stark blue
            "purple": "\033[35m",
            # this is actually light blue.
            "blue": "\033[36m",
            "normal": "\033[0m"
        }

    severities_text = {
        "error": "%sError%s" % (colors.get("red", ""), colors["normal"]),
        "warn": "%sWarning%s" % (colors.get("yellow", ""), colors["normal"]),
        "notice": "%sNotice%s" % (colors.get("green", ""), colors["normal"]),
        "note": "%sNote%s" % (colors.get("blue", ""), colors["normal"])
    }

    gamecolor = {
        # it normally depends on the font type... here i do a mix.
        # normal: white,red,green,yellow,grey
        # small: grey,red,green,yellow,orange
        # tiny: grey,red,green,yellow
        "0": "normal", "1": "red", "2": "green",
        # game says it's 'purple'
        "3": "yellow",
        # actually gray
        "4": "purple",
        # actually orange, this time
        "5": "orange",
    }

    @staticmethod
    def wrap_output(text, length, indentchar, indentcharwrap=None):
        to_print = []
        if indentcharwrap is None:
            indentcharwrap = indentchar

        def indentbyindex(i):
            if not to_print:
                return ""
            return indentchar if i else indentcharwrap

        for line in text.split('\n'):
            to_print.extend((indentbyindex(i) + line[i:i+length])
                            for i in range(0, len(line), length))
        return "\n".join(to_print)

    def print_error(self, file_dict_path_str, severity, error, text):
        # sadly, we can't give line numbers...
        print("%s: %s%s" % (self.severities_text.get(severity, severity),
                            error, self.colors['normal']))
        print("at %s" % (self.wrap_output(file_dict_path_str, 80-3, "\t\t")))
        print("   %s%s" % (self.wrap_output(text, 72, '\t', '   '),
                           self.colors["normal"]))
        if severity == "error":
            self.errors += 1

    def create_warn_function(self, file_path, dict_path, default_text):
        def print_please(severity, error, display_text=default_text):
            file_dict_path_str = common.serialize_dict_path(file_path,
                                                            dict_path)
            self.print_error(file_dict_path_str, severity, error, display_text)
        return print_please


def iterate_escapes(string):
    r"""Iterate escapes of the form \X

    yield (index_from, index_of_escape), where index_from is where the search
    started from, and index_of_escape is the next escape.  Thus
    string[index_from:index_of_escape] will not contain escapes.

    if a index is sent to this method, then the next iteration will start
    searching at this position (it will become index_from), instead of
    the last index_of_escape + 2
    """
    last = 0
    index = string.find('\\')
    while 0 <= index < len(string):
        next_index = yield (last, index)
        if next_index is not None:
            index = next_index
            yield None
        else:
            # skip \ and the next char
            index = index + 2
        last = index
        index = string.find('\\', index)
    yield (last, len(string))


class CheckerLexer(CheckerBase):
    """Extends Checker with a lexer/parser and variable substitutes.

    the lexer can report errors."""

    TEXT = "TEXT"
    DELAY = "DELAY"
    ESCAPE = "ESCAPE"
    COLOR = "COLOR"
    SPEED = "SPEED"
    VARREF = "VARREF"
    ICON = "ICON"

    @classmethod
    def lex_that_text(cls, text, warn_func):
        """Lex the text

        yields (token_type, text)
        where token type is one of
        TEXT, DELAY, ESCAPE, COLOR, SPEED, VARREF and ICON
        and text depend on the type:
        for TEXT, text is the actual text.
        for DELAY, text is either '.' or '!' depending on the delay type.
        for ESCAPE, text is always '\\'.
        for COLOR, ICON, SPEED, VARREF, text is the parameter of the command.
        """
        iterator = iterate_escapes(text)
        for last_index, index in iterator:
            part = text[last_index:index]
            if part:
                yield cls.TEXT, part
            char = text[index+1: index+2]

            if char in '.!':
                # delaying commands
                yield cls.DELAY, char
            elif char == '\\':
                yield cls.ESCAPE, char
            elif char in 'csiv':
                if text[index+2:index+3] != '[':
                    warn_func("error", "'\\%s' not followed by '['" % char)
                    continue
                end = text.find(']', index+2)
                if end == -1:
                    warn_func("error", "'\\%s[' not finished" % char)
                    continue
                inner = text[index+3:end]
                type_ = {'c': cls.COLOR, 's': cls.SPEED,
                         'i': cls.ICON, 'v': cls.VARREF}[char]
                yield type_, inner
                iterator.send(end+1)
            else:
                warn_func("warn", "unknown escape '\\%s'" % char)

    @staticmethod
    def check_number(text, warn_func):
        """Check that the given parameter is a number, warn otherwise"""
        if not text.isdigit():
            warn_func("error", "'%s' is not a number" % text)
        return text

    def find_stuff_in_orig(self, text, wanted_type):
        """find token of the given type in the text, without warning

        yield all values of the give token type"""
        for type_, value in self.lex_that_text(text, lambda a, b: None):
            if type_ is wanted_type:
                yield value

    VARIABLES = [
        (["lore", "title", "#1"], ["database.json"], ['lore', "#1", 'title']),
        (["item", 0, "name"], ["item-database.json"], ["items", 0, "name"]),
        (["area", "#1", "name"], ["database.json"], ['areas', '#1', 'name']),
        (["area", "#1", "landmarks", "name", "#2"],
         ["database.json"], ['areas', '#1', 'landmarks', '#2', 'name']),
        (["misc", "localNum", 0], lambda param, warn: param[0], None),
        (["combat", "name", "#*"],
         ["database.json"], ['enemies', '#*', 'name']),
    ]

    @staticmethod
    def match_var_params(template, actual, warn_func):
        """Check if a splitted variable reference matches a template

        a template is a list that can contain strings, references for integers
        or references for arbitrary strings.

        integers references are represented by actual integers, while
        string references are represented by strings beginning with '#'.

        Return None if nothing matches. Else, return a dictionnary of
        parameters.

        >>> warn_func = lambda a,b: None
        >>> match_var_params(["tmp", "#1"], ["map", "thingy"], warn_func):
        None
        >>> match_var_params(["tmp", "#1"], ["tmp", "something"], warn_func):
        {"#1": "something"}
        >>> match_var_params(["tmp", 0], ["tmp", "42"], warn_func):
        {0: "42"}
        """
        split = actual
        if template[-1] == '#*':
            split = actual[:len(template)-1]
            split.append(".".join(actual[len(template)-1:]))
        if len(split) != len(template):
            return None
        params = {}
        for our_part, their_part in zip(split, template):
            if isinstance(their_part, int) or their_part.startswith('#'):
                params[their_part] = our_part
            elif our_part != their_part:
                # does not match template
                return None

        for key, value in params.items():
            if isinstance(key, int) and not value.isdigit():
                warn_func("error", "'%s' is not a number" % value)
                return {}
        return params

    def lookup_var(self, name, warn_func, orig, get_text):
        """Look up the given variable and return a replacement

        the replacement may be bonkers.

        get_text(file_path, dict_path, warn_func) should look up the given
        reference.  It is used to replace variable references to known
        texts.
        """
        normal_split = name.split('.')

        for template, file_path, dict_path_template in self.VARIABLES:
            params = self.match_var_params(template, normal_split, warn_func)
            if params is None:
                continue
            if not params:
                # entry in VARIABLES has an error.
                return None

            if callable(file_path):
                return file_path(params, warn_func)
            if file_path is None:
                return "(something)"

            dict_path = []
            for component in dict_path_template:
                subst = params.get(component)
                if subst:
                    dict_path.append(subst.replace('/', '.'))
                else:
                    dict_path.append(component)

            text = get_text(file_path, dict_path, warn_func)
            if text is None:
                warn_func("error",
                          "invalid variable reference '%s': not found" % name)
                return "(invalid)"

            if not isinstance(text, str):
                warn_func("error",
                          "variable reference '%s' is not text" % name)
                return "(invalid)"
            return text

        for maybevar in self.find_stuff_in_orig(orig, self.VARREF):
            if maybevar == name:
                return "(something)"

        warn_func("warn", "unknown variable %s not in original" % name)
        return "(error)"

    def parse_text(self, text, orig, warn_func, get_text):
        """yield (optional_ansi_prefix, text), caller must iterate"""
        result = ""
        current_color = "0"
        # default speed depends on the context
        current_speed = "-1"

        for type_, value in self.lex_that_text(text, warn_func):
            if type_ is self.TEXT:
                yield ("", value)
            elif type_ is self.DELAY:
                pass
            elif type_ is self.ESCAPE:
                warn_func("notice", "\\ present in text, is this intended ?")
            elif type_ is self.COLOR:
                actual_color = self.gamecolor.get(value)
                if actual_color is None:
                    warn_func("error", r"bad \c[] command")
                    continue
                if value == current_color:
                    warn_func("warn", "same color assigned twice")
                current_color = value
                ansi_color = self.colors.get(actual_color)
                if ansi_color:
                    yield (ansi_color, "")
            elif type_ is self.SPEED:
                if len(value) != 1 or value not in "01234567":
                    warn_func("error", r"bad \s[] command")
                    continue
                if result:
                    warn_func("notice", "speed not at start of text, unusal")
                if current_speed == value:
                    warn_func("warn", "same speed specified twice")
                current_speed = value
            elif type_ is self.ICON:
                if value not in self.find_stuff_in_orig(orig, self.ICON):
                    warn_func("notice", "icon not present in original text")
                yield ('', '@')
            elif type_ is self.VARREF:
                value = self.lookup_var(value, warn_func, orig, get_text)
                yield ('', value)
            else:
                assert False
        if current_color != "0":
            warn_func("notice", "color does not end with 0")


class RenderedText:
    """Class holding both 'rendered' text and plain text

    it may also contain stuff like the next space following the text
    or the size of the text in pseudo-pixels"""
    def __init__(self, plain="", ansi="", size=0, space=None):
        # raw text without any ansi escape or var references.
        self.plain = plain
        # rendered text with ansi escapes
        self.ansi = ansi
        # horizontal size once rendered
        self.size = size
        # the space character that follows this text, or None
        self.space = space

    def add_plain_text(self, text):
        """add plain text, to both ansi and plain"""
        self.plain += text
        self.ansi += text

    def __repr__(self):
        return "RenderedText(%s,%s,%s,%s)" % (repr(self.plain),
                                              repr(self.ansi),
                                              repr(self.size),
                                              repr(self.space))


class Formatter:
    """Format the given text, split it in words, do line wrapping..."""
    @staticmethod
    def get_next_space_index(string):
        """Find the index of the next ' ' or '\n' character."""
        next_space = string.find(' ')
        next_nl = string.find('\n')
        if next_space == -1:
            return next_nl
        if next_nl == -1:
            return next_space
        return min(next_space, next_nl)

    @classmethod
    def collect_words(cls):
        """Collect blurbs of text and return words.

        Send it (ansi_code, text) several time (it will yield None, so ignore
        the result), send None to collect an array of RenderedText, one for
        each word in the text.

        word.space will contain the space that followed the word,
        or None for the last word.
        """
        words = []
        current_word = RenderedText()
        current_word.space = None
        while True:
            something = (yield None)
            if something is None:
                break
            ansi, plaintext = something
            current_word.ansi += ansi

            while plaintext:
                next_space = cls.get_next_space_index(plaintext)

                if next_space == -1:
                    next_space = len(plaintext)
                current_word.add_plain_text(plaintext[:next_space])
                if next_space != len(plaintext):
                    current_word.space = plaintext[next_space]
                    words.append(current_word)
                    current_word = RenderedText()
                    current_word.space = None
                plaintext = plaintext[next_space+1:]
        words.append(current_word)
        yield words

    @classmethod
    def get_words(cls, iterator):
        """Adapt collect_word() to a normal function."""
        word_collector = cls.collect_words()
        # you need to go to the first yield before you send stuff to it.
        next(word_collector)
        for ansi, text in iterator:
            word_collector.send((ansi, text))
        return word_collector.send(None)

    @staticmethod
    def wrap_text(words, width_limit, size_of_space):
        """Given an array of words with sizes, lay them out to form lines.

        words must be an iterable of RenderedText with 'space' and 'size'
        attributes.  If 'space' is '\n', a new line is always inserted.

        width_limit is the maximum size of lines, while size_of_space is the
        pseudopixel size of a ' ' character.

        yield an array of RenderedText, one for each line, each having a 'size'
        attribute calculated from each word's size and size_of_space.
        """
        lines = []
        current_line = RenderedText()

        for word in words:
            has_space = bool(current_line.size)
            newsize = (current_line.size + word.size
                       + (size_of_space if has_space else 0))
            if newsize > width_limit:
                lines.append(current_line)
                current_line = RenderedText()
                newsize = word.size
            elif has_space:
                current_line.add_plain_text(" ")

            current_line.ansi += word.ansi
            current_line.plain += word.plain
            current_line.size = newsize
            if word.space == '\n':
                lines.append(current_line)
                current_line = RenderedText()
        lines.append(current_line)
        return lines


class Checker(CheckerLexer):
    def __init__(self, check_settings):
        super().__init__()
        self.parse_options(check_settings)

    def parse_options(self, settings):
        self.char_metrics = {}
        for fonttype, values in settings.get("metrics", {}).items():
            metrics = {}
            self.char_metrics[fonttype] = metrics
            for i, size in enumerate(values.get("metrics", ())):
                if size > 0:
                    metrics[chr(i+32)] = size

            metrics.update(values.get("extra_metrics", {}))
        self.replacements = []

        def make_repl(regex, repl):
            return lambda s: regex.sub(repl, s)

        for subst_regex in settings.get("replacements", ()):
            if len(subst_regex) < len('s///'):
                raise ValueError(
                    "substution '%s' too short" % repr(subst_regex))
            splitted = subst_regex.split(subst_regex[1])
            if len(splitted) != 4 or splitted[0] != 's' or splitted[3]:
                raise ValueError(
                    "substitution '%s' has invalid syntax" % (subst_regex))
            try:
                replace_func = make_repl(re.compile(splitted[1]), splitted[2])
                replace_func("this is a test of your regex: œ")
            except re.error:
                raise ValueError(
                    "regex substitution '%s' failed" % subst_regex)
            else:
                self.replacements.append(replace_func)

        self.to_flag = []

        def make_matcher(regex):
            return lambda s: regex.search(s) is not None

        for name, to_flag in settings.get("badnesses", {}).items():
            try:
                regex = re.compile(to_flag)
            except re.error:
                raise ValueError("badness regex '%s' failed" % to_flag)
            self.to_flag.append((name, make_matcher(regex)))

    def calc_string_size(self, string, metrics, warn_func):
        ret = 0
        for char in string:
            size = metrics.get(char)
            if size is None:
                warn_func("warn", "Character %s has no metrics" % repr(char))
                size = 1
            ret += size
        return ret

    def wrap_text(self, words, metrics, boxtype):
        spacesize = metrics.get(' ')
        width_limit = 999999 if boxtype[1] == "hbox" else boxtype[2]

        return Formatter.wrap_text(words, width_limit, spacesize)

    def check_boxes(self, lines, boxtype, metrics, warn_func):
        if len(lines) > boxtype[3]:
            warn_func("error", "Overfull %s: too many lines" % boxtype[1],
                      "\n".join(l.ansi for l in lines))

        maxsize = 0
        maxindex = None
        for index, line in enumerate(lines):
            maxsize = max(maxsize, line.size)
            if maxsize == line.size:
                maxindex = index

        if maxsize > boxtype[2]:
            assert boxtype[2]
            # Figure out where the cut is
            bigline = lines[maxindex].plain
            indication = None
            for charsize in range(len(bigline), 1, -1):
                trimedsize = self.calc_string_size(bigline[:charsize], metrics,
                                                   lambda *l: None)

                if trimedsize < boxtype[2]:
                    indication = bigline[:charsize] + '[]' + bigline[charsize:]
                    break

            warn_func("error",
                      "Overfull %s: %dpx too large" % (boxtype[1],
                                                       maxsize - boxtype[2]),
                      indication)

    def do_text_replacements(self, text, warn_func):
        flagged = set()
        for flagname, flagfunc in self.to_flag:
            if flagfunc(text):
                flagged.add(flagname)
                warn_func("warn",
                          "badness '%s' in text before substs" % flagname)

        text = common.trim_annotations(text)
        for repl in self.replacements:
            text = repl(text)

        for flagname, flagfunc in self.to_flag:
            if flagname not in flagged and flagfunc(text):
                warn_func("warn",
                          "badness '%s' in text after substs" % flagname)
        return text

    def check_text(self, file_path, dict_path, text, orig, tags, get_text):

        warn_func = self.create_warn_function(file_path, dict_path, text)
        boxtype = tagger.get_box_by_tags(tags)
        metrics = None
        if boxtype is not None:
            metrics = self.char_metrics.get(boxtype[0])

        text = self.do_text_replacements(text, warn_func)

        generator = self.parse_text(text, orig, warn_func, get_text)
        if metrics is None:
            # consume the generator, consume it so it checks stuff
            list(generator)
            return

        words = Formatter.get_words(generator)
        for word in words:
            word.size = self.calc_string_size(word.plain, metrics, warn_func)
        lines = self.wrap_text(words, metrics, boxtype)
        self.check_boxes(lines, boxtype, metrics, warn_func)

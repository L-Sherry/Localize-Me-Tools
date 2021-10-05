#!/usr/bin/python3

import re
import os
import sys
import common
import itertools

from readliner import Readliner

import tags as tagger
from checker import PackChecker, check_assets

class PackFile(common.PackFile):
    def save(self, filename):
        print("Saving", end="...", flush=True)
        super().save(filename)
        print(" ok.")

    def load(self, filename, on_each_text_load=lambda x: None):
        super().load(filename, on_each_text_load)
        print("loaded", filename)
        print(self.get_stats(config))

    def save_modify_load(self, filename, modify_function):
        self.save(filename)
        while True:
            modify_function(filename)
            try:
                super().load(filename)
                return
            except Exception as exc:
                print(exc)
                line = input("Press enter to reedit, or :q! to quit")
                if line.strip() == ':q!':
                    sys.exit(1)
                continue

class CircularBuffer:
    def __init__(self, size):
        self.array = []
        self.index = 0
        self.size = size
    def append(self, elem):
        if self.index < self.size:
            self.array.append(elem)
        else:
            self.array[self.index % self.size] = elem
        self.index += 1
    def __iter__(self):
        if not self.array:
            return
        start_at = self.index % len(self.array)
        yield from (self.array[index] for index in range(start_at,
                                                         len(self.array)))
        yield from (self.array[index] for index in range(start_at))


class CommandParser:
    qualities_commands = (
        ("/bad", "bad"),
        ("/wro", "wrong"),
        ("/miss", "incomplete"),
        ("/unkn", "unknown"),
        ("/spell", "spell"),
        ("/note", None)
    )
    @classmethod
    def parse_line_input(cls, line):
        ret = {}
        note = None
        quality = None
        for command, quality in cls.qualities_commands:
            index = line.find(command)
            if index == -1:
                continue
            note = line[index + len(command):].strip()
            ret["text"] = line[:index]
            if quality is not None:
                ret["quality"] = quality
            if note:
                ret["note"] = note
            break
        else:
            ret["text"] = line
        # Allow the user to use \n for newlines (some translations require this)
        ret["text"] = ret["text"].replace('\\n', '\n')
        return ret

    @classmethod
    def make_parsed(cls, text, quality=None, note=None, partial=None):
        ret = {}
        for key, value in (('text', text), ('quality', quality),
                           ('note', note), ('partial', partial)):
            if value is None:
                continue
            ret[key] = value
        return ret

    @classmethod
    def make_line_input(cls, trans):
        """The inverse of parse_line_input(trans).

        This round trip is guaranteed: parse_line_input(make_line_input(x))==x
        """

        if "text" not in trans:
            return ""
        quality = trans.get("quality")
        note = trans.get("note")
        # apparently readline handles \n just fine. Yet there is no way to
        # make it insert one... or is it ?
        # text = trans["text"].replace('\n', '\\n')
        if quality is None and note is None:
            return trans["text"]
        for command, maybe_quality in cls.qualities_commands:
            if quality == maybe_quality:
                if note:
                    return "%s%s %s"%(trans["text"], command, note)
                return "%s%s"%(trans["text"], command)
        assert False, "unknown quality"
        return trans["text"]



class Configuration:
    def __init__(self):
        self.reset()
        self.check()

    default_options = {
        "gamedir": ".",
        "string_cache_file": "string_cache.json",
        "from_locale": "en_US",
        "show_locales": [],
        "compose_chars": [],
        "filter_file_path": [],
        "filter_dict_path": [],
        "filter_quality": [],
        "filter_tags": [],
        "filter_orig": [],
        "ignore_known": True,
        "ignore_unknown": False,
        "allow_empty": False,
        "editor": os.getenv("EDITOR") or "",
        "packfile": "translations.pack.json",
        "total_count": 0,
        "unique_count": 0,
        "history_size": 200
    }

    def add_options_to_argparser(self, parser):
        parser.add_argument("--gamedir", dest="gamedir",
                            metavar="<path to assets/>", help="""Path to
                            the game's assets/ directory or one of its
                            subdirectory or its direct parent.  Default is to
                            search around the current directory""")
        parser.add_argument("--from-locale", "-l", dest="from_locale",
                            metavar="<locale>", help="""Locale from which the
                            translation is derived.  Defaults to en_US.""")
        parser.add_argument("--show-locales", nargs="+", dest="show_locales",
                            metavar="<locales>", help="""Locale to show for
                            each translation input.  Defaults to only showing
                            the locale in --from-locale""")
        parser.add_argument("--compose-chars", nargs="+", dest="compose_chars",
                            metavar="<char>=<2 chars>", help="""
                            compose keys to use.  If e.g. œ=oe is specified,
                            then typing either "|oe", "|eo", "$oe", "$eo" and
                            then hitting tab will change the three characters
                            into œ.""")
        parser.add_argument("--string-cache-file", dest="string_cache_file",
                            metavar="<path to cache file>", help="""Location of
                            the optional cache file.  If present, it will be
                            used instead of browsing through gamedir.""")

        split_me_regex = re.compile(r'\s+')
        listoflist = split_me_regex.split

        parser.add_argument("--filter-file-path", nargs="+",
                            dest="filter_file_path", type=listoflist,
                            metavar='<file/dir names>',
                            help="""filter the files or directories to
                            consider when translating. The filter applies to
                            any part of the relative path to the considered
                            file.  e.g.
                            --filter-file-path "data.json allies" "enemy"
                            will allow paths that contains "enemy" or
                            paths that contains "allies" and "data.json".""")
        parser.add_argument("--filter-dict-path", nargs="+",
                            dest="filter_dict_path", type=listoflist,
                            metavar='<json indexes>',
                            help="""filter the translations within files to
                            consider when translating. The filter applies to
                            any part of the json index to the considered file.
                            e.g. given a json file of
                            { "c":{"a":42,"b":"me"}, "d":{"a":[43, 44]} },
                            --filter-dict-path "a c" "d", will allow any index
                            containing both a and c or any index containing "d",
                            so the result here will be ["c", "a"],
                            ["d", "a", "0"] and ["d", "a", "1"].""")
        parser.add_argument("--filter-quality", nargs="+",
                            dest="filter_quality", type=listoflist,
                            metavar="<qualities>",
                            help="""Filter current translations qualities.
                            This only make sense if ignore-known is false.""")
        parser.add_argument("--filter-tags", nargs="+", dest="filter_tags",
                            type=listoflist, metavar="<tag1 tag2...>",
                            help="""filter the translations to display given
                            their tags.  Follows the same convention as
                            --filter-file-path and --filter-dict-path, so that
                            --filter-tags "conv player" "xeno" will match
                            translations having both "conv" and "player" tags or
                            translations having the "xeno" tag""")
        parser.add_argument("--filter-orig", nargs="+", dest="filter_orig",
                            type=listoflist, metavar="<tag1 tag2...>",
                            help="""filter the translations to only display
                            translations whose original text contains the given
                            text.  Follows the same convention as
                            --filter-file-path and --filter-dict-path, so that
                            --filter-orig "Hi" "Lea" will match
                            translations having both "Hi" and "Lea" in the
                            original text.  Only the locale specified by
                            from_locale is searched""")
        parser.add_argument("--no-ignore-known", dest="ignore_known",
                            action="store_false", help="")
        parser.add_argument("--ignore-known", dest="ignore_known",
                            action="store_true", help="""Ignore translations
                            that are already translated and are not stale. This
                            is enabled by default""")
        parser.add_argument("--no-ignore-unknown", dest="ignore_unknown",
                            action="store_false", help="")
        parser.add_argument("--ignore-unknown", dest="ignore_unknown",
                            action="store_true", help="""Ignore untranslated
                            texts. This option is disabled by default.
                            Note that stale translations are always displayed,
                            regardless of the value of this option""")
        parser.add_argument("--no-allow-empty", dest="allow_empty",
                            action="store_false", help="")
        parser.add_argument("--allow-empty", dest="allow_empty",
                            action="store_true", help="""Allow empty
                            translations.  By default, if a translated text
                            is empty, it is not stored.  This option allows
                            to translate something as an empty text.""")
        parser.add_argument("--editor", dest="editor",
                            metavar="<editor program>", help="""Editor to use
                            when using ":e".  If not specified, then the EDITOR
                            environment variable is used if it exist.""")

        parser.add_argument("--pack-file", required=False, dest="packfile",
                            metavar="<pack file>",
                            help="""Pack file to create/edit/update. Required
                            """)
        parser.set_defaults(ignore_unknown=None, ignore_known=None,
                            allow_empty=False, total_count=None,
                            unique_count=None, history_size=None)
    def update_with_argparse_result(self, result):
        for key in self.default_options.keys():
            value = getattr(result, key)
            if value is not None:
                setattr(self, key, value)


    get_default_options = staticmethod(x for x in default_options)

    def reset(self):
        for key, value in self.default_options.items():
            setattr(self, key, value)
        self.locales_to_show = [self.from_locale]

    def check(self):
        if not self.show_locales:
            self.locales_to_show = [self.from_locale]
        else:
            self.locales_to_show = self.show_locales

        qualities = frozenset(self.filter_quality)
        if qualities:
            self.filter_quality_func = lambda quality: quality in qualities
        else:
            self.filter_quality_func = lambda quality: True

    def load_from_file(self, filename, unknown_option=lambda key, val: False):
        json = common.load_json(filename)
        for key, value in json.items():
            if key not in self.default_options:
                if unknown_option(key, value):
                    continue
                raise ValueError("Unknown configuration option: %s"%key)
            value_type = self.default_options[key].__class__
            if value.__class__ is not value_type:
                raise ValueError("Bad value type for option %s,"
                                 "expected %s got %s"%(key, value_type,
                                                       value.__class__))
            setattr(self, key, value)
    def save_to_file(self, filename):
        json = {}
        for key in self.default_options.keys():
            json[key] = getattr(self, key)
        common.save_json(filename, json)

    def iterate_over_all_game(self):
        walker = common.GameWalker(game_dir = self.gamedir)
        return walker.walk(self.from_locale, drain=True)

    def iterate_over_configured_source(self, pack, no_cache = False):
        string_cache = None
        if not no_cache and os.path.exists(self.string_cache_file):
            string_cache = self.load_string_cache()
        walker = common.GameWalker(game_dir = self.gamedir,
                                   loaded_string_cache = string_cache)
        walker.set_file_path_filter(self.filter_file_path)
        walker.set_dict_path_filter(self.filter_dict_path)
        walker.set_tags_filter(self.filter_tags)
        walker.set_orig_filter(self.filter_orig)
        walker.set_custom_filter(self.get_trans_known_filter(pack))
        return walker.walk(self.from_locale, drain=True)

    def load_string_cache(self):
        string_cache = common.string_cache(self.from_locale)
        langs = frozenset(self.locales_to_show + [self.from_locale])
        print("loading string cache %s"%(self.string_cache_file), end="...",
              flush=True)
        string_cache.load_from_file(self.string_cache_file, langs)
        print(" ok")
        return string_cache

    def get_trans_known_filter(self, packfile):
        """A filter suitable for other_filter that yield known translations

        it will also reject unknown/known translation as configured"""
        def other_filter(file_dict_path_str, lang_label):
            """Filter the entry depending on config and on what we know

            Return None if we should not present the entry
            return False if the entry should be presented
            return a trans if the entry should be presented and prefilled
            the trans may not have a 'text', in which case it is like
            unknown, but still return it"""
            known = packfile.get(file_dict_path_str)

            if not known or (known and 'text' not in known):
                if self.ignore_unknown:
                    return None
                if known:
                    return known
                return False
            # so, known is not None and it has a text.

            if known and lang_label[self.from_locale] == known.get('orig'):
                if self.ignore_known:
                    return None
                if self.filter_quality_func([known.get('quality', '')]):
                    return known
                return None

            # if we are here, there is stale stuff.
            return known
        return other_filter

    def get_sparse_reader(self):
        if os.path.exists(self.string_cache_file):
            return self.load_string_cache()
        return common.sparse_dict_path_reader(self.gamedir, self.from_locale)
    def prune_langlabel(self, lang_label):
        """Return a simpler locales_to_show"""
        ret = dict.fromkeys(self.locales_to_show, None)
        ret.update(common.filter_langlabel(lang_label, self.locales_to_show))
        return ret


class Translator:
    def __init__(self, config, pack, readliner):
        self.config = config
        self.pack = pack
        self.readliner = readliner

        self.common_commands = {
            'w': self.command_save,
            'q': self.command_quit,
            'wq': self.command_quit,
            'e': self.command_spawn_editor,
            's': self.command_show_stat,
        }

    def setup_autocomplete(self, strings):
        words = set()
        string_set = set()
        for text in strings:
            if not text:
                # filters None too
                continue
            string_set.add(text)
            for word in text.replace('\n', ' ').split(' '):
                if word:
                    words.add(word)
        self.readliner.set_complete_array(words)

        if len(string_set) == 1:
            entire_completion = string_set.pop()
        else:
            entire_completion = ""
        self.readliner.set_entire_completion_string(entire_completion)

    def setup_prefilled_text(self, real_known, stale, duplicate):
        if real_known and '\n' in real_known.get("note",""):
            real_known =real_known.copy()
            del real_known['note']
        if real_known:
            prefill = CommandParser.make_line_input(real_known)
        elif duplicate:
            prefill = CommandParser.make_line_input(duplicate)
        elif stale and 'text' in stale:
            prefill = CommandParser.make_line_input(stale)
        else:
            return

        self.readliner.prefill_text(prefill)

    @staticmethod
    def worddiff(from_text, to_text, min_context_length = 30, min_suppr = 50):
        # I'm not going to do an alignment algorithm, i'm not a geneticist

        max_index = min(len(from_text), len(to_text))


        common_start = 0
        while common_start < max_index:
            if from_text[common_start] != to_text[common_start]:
                break
            common_start += 1
        common_end = 1
        while common_start + common_end < max_index:
            if from_text[-common_end] != to_text[-common_end]:
                break
            common_end += 1

        if common_start + common_end < min_suppr:
            return None, None
        common_start = max(0, common_start - min_context_length // 2)
        common_end = max(0, common_end - min_context_length // 2)

        fmt = "%s%%s%s" % ("..." if common_start else "",
                           "..." if common_end else "")
        from_text = fmt % from_text[common_start : len(from_text) - common_end]
        to_text = fmt % to_text[common_start : len(to_text) - common_end]
        return from_text, to_text

    @staticmethod
    def format_trans_to_show(filtered_lang_label, tags=None, real_known=None,
                             stale=None, orig=None, file_dict_path_str=None):
        string = ""
        if file_dict_path_str is not None:
            string += '%s\n' % (file_dict_path_str)
        if tags is not None:
            string += "%s\n" % (" ".join(tags))
        if stale is not None:
            string += "stale translation:\n"
            if 'old_orig_diff' in stale:
                string += "diff:%s\n--->:%s\n" % (stale['old_orig_diff'],
                                                  stale['new_orig_diff'])
            else:
                string += "our orig :%s\n" % (stale['orig'])
        for locale, orig in filtered_lang_label.items():
            if orig is None:
                string += 'NO %s\n' % locale
            else:
                string += '%s: %s\n' % (locale[:2], orig)
        if real_known and real_known.get("note"):
            string += real_known['note'].rstrip() + '\n'
        return string

    def prompt_user(self, to_show, prompt, commands):
        prompt = to_show + prompt
        while True:
            line = self.readliner.read_line(prompt)
            stripped = line.strip()
            if not stripped.startswith(':'):
                return line
            splitted = stripped.split(None, 1)
            cmd = commands.get(splitted.pop(0)[1:])
            if cmd is None:
                return line
            ret = cmd(splitted[0] if splitted else None)
            if ret is not None:
                return ret

    def command_spawn_editor(self, ignored):
        editor = self.config.editor
        if not editor:
            print("No editor configured")
            return
        # not touching the history here, this is intentionnal, it gets
        # confusing otherwise.
        self.pack.save_modify_load(self.config.packfile,
                lambda filename : os.system("%s %s" % (editor, filename)))

    def command_save(self, ignored):
        self.pack.save(self.config.packfile)

    def command_show_stat(self, ignored):
        print(self.pack.get_stats(self.config))

    def command_quit(self, ignored):
        raise KeyboardInterrupt()

    # Ok, this deserve an explanation.
    # just \.\s+ will fail on the following:
    # "he sent an S.O.S. to me."
    # "Please see Ms. Elizabeth."
    # hence this hack.
    SENTENCE_SPLITTER = re.compile(r'((?<=[^. ]{3})\.|[?!]+)\s+|\n+')

    @classmethod
    def split_sentences(cls, text):
        """Return text splitted into sentences.

        Return is an odd-sized list of
        [sentence, delimiter, sentence, delimiter, sentence]
        sentence may be empty, especially the first.

        The last is never empty, unless it is also the first.
        """
        last_index = 0
        intervaled = []
        for match in cls.SENTENCE_SPLITTER.finditer(text):
            begin, end = match.span()
            intervaled.append(text[last_index:begin])
            intervaled.append(text[begin:end])
            last_index = end
        intervaled.append(text[last_index:])

        if len(intervaled) > 1 and not intervaled[-1].strip():
            end = intervaled.pop()
            sep = intervaled.pop()
            intervaled[-1] += sep + end

        return intervaled

    @staticmethod
    def score_similarity(merged, template):
        """Return a similarity score between candidate 'merged' and 'template'

        lower is better."""
        assert len(merged) == len(template)

        def divergence(a, b): return abs((a-b)/(0.001+b))

        score = 0
        for i, (proposed, original) in enumerate(zip(merged, template)):
            if i & 1:
                if proposed != original:
                    score += 1
            else:
                score += divergence(len(proposed), len(original))
                if '\n' in proposed and '\n' not in original:
                    score += 1
        return score

    @classmethod
    def find_best_merge_sentence(cls, intervaled, template):
        number_of_possible_merges = len(intervaled)//2
        merge_positions = range(number_of_possible_merges)
        number_of_merges = number_of_possible_merges - len(template)//2

        best_merge = None
        best_score = None

        # This is inefficient, but still more than the brain of the user.
        for combination in itertools.combinations(merge_positions,
                                                  number_of_merges):
            new_intervaled = intervaled[:]
            for merges_done, index_to_merge in enumerate(combination):
                index = (index_to_merge - merges_done)*2
                add = new_intervaled.pop(index+1)
                add += new_intervaled.pop(index+1)
                new_intervaled[index] += add

            score = cls.score_similarity(new_intervaled, template)
            if best_score is None or score < best_score:
                best_merge = new_intervaled
                best_score = score

        if best_merge is not None:
            print("Merge %s -> %s, score: %.2f" % (number_of_possible_merges,
                                                   len(template)//2,
                                                   best_score))
            intervaled.clear()
            intervaled.extend(best_merge)

    @classmethod
    def split_translation(cls, filtered_lang_label):
        """Given a lang label, return an array of langlabels for each sentence

        this method contains heuristics, use with care"""
        splitted = {}
        minsize = 99999999
        minsizelocale = None
        maxsize = 0
        for locale, orig in filtered_lang_label.items():
            if orig is None:
                continue
            orig = common.trim_annotations(orig)
            if not orig:
                continue
            intervaled = cls.split_sentences(orig)
            splits = len(intervaled)
            if splits == 1:
                # this would defeat the purpose.
                continue
            splitted[locale] = intervaled
            if splits < minsize:
                minsize = splits
                minsizelocale = locale
            maxsize = max(maxsize, splits)

        if minsizelocale and minsize != maxsize:
            template = splitted[minsizelocale]
            for locale, split in splitted.items():
                if len(split) != len(template):
                    cls.find_best_merge_sentence(split, template)
        elif minsizelocale is None:
            return [filtered_lang_label]
        # splitted is a langlabel of arrays
        # turn it into an array of langlabels
        ret = [dict() for x in range(minsize)]
        for locale, array_of_part in splitted.items():
            assert len(array_of_part) == minsize
            for i, part in enumerate(array_of_part):
                ret[i][locale] = part

        return ret

    def prompt_splitted_trans(self, lang_label, index, count,
                              partial_known=None):
        if not any(lang_label):
            # don't bother asking.
            return CommandParser.parse_line_input("")
        if partial_known is not None:
            # that or autofilling it, though choice, let's see how it goes.
            self.readliner.prefill_text(partial_known)
        to_show = self.format_trans_to_show(lang_label)
        to_show = "---- Part %s / %s\n%s" % (index, count, to_show)
        res = self.prompt_user(to_show, "%s> " % index, self.common_commands)
        if not res:
            return None
        return res.strip()

    QUALITY_SORT = {
        None: 0,
        'note': 0,
        'spell': 1,
        'unknown': 2,
        'bad': 3,
        'incomplete': 4,
        'wrong': 5
    }

    def command_split_trans(self, file_dict_path_str, filtered_lang_label,
                            orig, known):
        splitted = self.split_translation(filtered_lang_label)
        known_partial = [] if not known else known.get("partial", [])
        partial = []
        results = []
        count = 1 + len(splitted) // 2
        for index in range(count):
            lang_label_part = splitted[index * 2]
            known_part = None
            if index < len(known_partial):
                known_part = known_partial[index]

            res = self.prompt_splitted_trans(lang_label_part, 1 + index, count,
                                             known_part)
            partial.append(res)
            if res is None:
                results.append(None)
            else:
                results.append(CommandParser.parse_line_input(res))

            # add this so that saving works in the middle.
            self.pack.add_incomplete_translation(file_dict_path_str, orig,
                                                 {'partial': partial})

        if None not in results:
            trans = self.merge_splitted_trans(file_dict_path_str, splitted,
                                              results)
            self.readliner.prefill_text(CommandParser.make_line_input(trans))

        return None

    def merge_splitted_trans(self, file_dict_path_str, intervaled, results):
        text = ""
        quality = None
        quality_score = self.QUALITY_SORT[quality]
        notes = []
        for index, result in enumerate(results):
            text += result['text']
            if index * 2 + 1 < len(intervaled):
                text += next(iter(intervaled[index * 2 + 1].values()))
            if 'quality' not in result and 'note' not in result:
                continue

            notes.append("[%s]: %s (%s)" % (result['text'],
                                            result.get('quality', 'note'),
                                            result.get('note', '')))
            if 'quality' in result:
                new_quality_score = self.QUALITY_SORT[result['quality']]
                if new_quality_score > quality_score:
                    quality_score = new_quality_score
                    quality = result['quality']
        if notes:
            notes = ", ".join(notes)
        else:
            notes = None
        return CommandParser.make_parsed(text=text, quality=quality,
                                         note=notes)

    def curry_command_split_trans(self, *args):
        return lambda ignored: self.command_split_trans(*args)

    def ask_for_complete_trans(self, file_dict_path_str,
                               filtered_lang_label, tags, known, duplicate,
                               orig):
        real_known = stale = None
        if known and "text" in known:
            if "orig" in known and orig != known["orig"]:
                stale = known.copy()
                from_diff, to_diff = self.worddiff(known["orig"], orig)
                if from_diff is not None:
                    stale['old_orig_diff'] = from_diff
                    stale['new_orig_diff'] = to_diff
            else:
                real_known = known

        to_show = self.format_trans_to_show(filtered_lang_label, tags,
                                            real_known, stale, orig,
                                            file_dict_path_str)
        self.setup_autocomplete(filtered_lang_label.values())
        self.setup_prefilled_text(real_known, stale, duplicate)

        commands = dict(self.common_commands)
        commands['split'] = self.curry_command_split_trans(file_dict_path_str,
                                                           filtered_lang_label,
                                                           orig, known)

        if known and "text" not in known and "partial" in known:
            self.command_split_trans(file_dict_path_str, filtered_lang_label,
                                     orig, known)

        string = self.prompt_user(to_show, '> ', commands)
        if not string and not self.config.allow_empty:
            return
        trans = CommandParser.parse_line_input(string)
        pack.add_translation(file_dict_path_str, orig, trans)

    def ask_for_multiple_translations(self, iterator):
        for file_dict_path_str, lang_label, tags, known in iterator:
            lang_label_to_show = self.config.prune_langlabel(lang_label)
            orig = lang_label[self.config.from_locale]

            dup = pack.get_by_orig(orig)
            self.ask_for_complete_trans(file_dict_path_str, lang_label_to_show,
                                        tags, known, dup, orig)


def parse_args():
    import argparse
    config = Configuration()
    parser = argparse.ArgumentParser(description="Create and update packs "
                                                 " of translated texts\n")
    parser.add_argument("--config-file", "-c", metavar="<config file>",
                        dest="config_file", default="config.json",
                        help="""Location of the optional configuration file.
                                defaults to 'config.json'. The key of this
                                file use the same name as the options,
                                without the leading '--' and with '-'
                                replaced by '_'.  Options given here
                                override those found in the config file.""")
    config.add_options_to_argparser(parser)

    subparser = parser.add_subparsers(metavar="COMMAND", required=True)
    continue_ = subparser.add_parser('continue', help="continue translating",
                                     description="""Find strings to translate
                                     then, for each of them, ask on the
                                     terminal for a translation.

                                     It is possible to quit in the middle, the
                                     program will save existing translations
                                     and the next run will continue from there.

                                     It is possible to enter the following
                                     commands to tag the translation or perform
                                     other actions:

                                     ':w' will save the transient results to
                                     the pack file.  This is normally done
                                     when exiting, but saving often is always
                                     a good idea.
                                     ':q' will save and quit, while ':e' will
                                     save, open a text editor on the pack
                                     file then reload it.

                                     'omelette du fromage/bad' will be saved
                                     as 'omelette du fromage' while indicating
                                     that the translation is bad.  Similarly,
                                     'orden de ???/miss' will indicate that
                                     'orden de ???' is incomplete and
                                     'traditore/unkn' will indicate that it is
                                     unknown if 'traditore' is the correct
                                     translation, e.g. because the gender it
                                     applies to is currently unknown.
                                     'Novemberfest/wro' will indicate that the
                                     translation is wrong and does not match
                                     the original text.

                                     Adding text after '/miss', '/bad', '/unkn'
                                     or '/note' will add a note to the
                                     translation, maybe explaining why the
                                     mark is set.  e.g.
                                     "bolas/note needs to be gross"

                                     To insert a new line in the translated
                                     text, use \\n. Note that tab completion
                                     is available, and will complete to
                                     words in any of the shown original text
                                     or use compose characters.

                                     When the text to translate is too long,
                                     the ':split' command will attempt to split
                                     it into sentences and only present one
                                     sentence at a time.  Note that if more
                                     than one language is displayed, then
                                     :split will attempt to split sentences in
                                     both texts using a very simplistic
                                     heuristic.
                                     """)

    save_config = subparser.add_parser("saveconfig",
                                       help="""create a config file with
                                       the options on the command line.
                                       The default location is config.json
                                       but may be changed with --config-file""")
    save_config.set_defaults(save_config=True)

    count = subparser.add_parser("count", help="""Count the number of texts
                                 left to translate""",
                                 description="""Counts the number of texts
                                 that matches the configured filters.
                                 This is exactly the number of texts that
                                 the 'continue' command would ask for.
                                 """)
    count.set_defaults(count=True)
    count.add_argument("--debug", action="store_true",
                       help="""Enable various debugging output that may be
                               helpful to debug the lang label finder""")

    check = subparser.add_parser("check", help="""Check the translations for
                                 various errors.

                                 The following checks are implemented:
                                 - detects stale translations where the
                                   original text has changed.
                                 - detects syntax error in \\v \\c and others
                                   commands.  Also detects things like
                                   duplicate colors, which mostly indicate a
                                   mistake.
                                 - detect most invalid variable references
                                   (\\v) by implementing the main ones, and/or
                                   checking if the original text have the same
                                   references.
                                 - Also check if a newly introduced variable
                                   reference references text that is not part
                                   of the original translation
                                 - If character metrics are specified in the
                                   configuration file, then it will also detect
                                   overlong text that would overflow its box.
                                   It reimplements the game rendering algorithm
                                   with accuracy down to the pixel.  Not all
                                   texts have annotated size information,
                                   however.
                                 - Can detect user-defined errors in the
                                   translation using regex defined in the
                                   configuration file.

                                 Having a string_cache is strongly recommended
                                 for best performance.  See save_cache for
                                 details on how to create one.

                                 Many checks requires information from
                                 the config file.  config.json should have
                                 a "check" property with an object with the
                                 following properties (all optionals):

                                 "badnesses": an object with arbitrary keys
                                 whose values are parsed as regex.  If a
                                 translation matches a regex, an error is
                                 loggued.

                                 "replacements": an array of 's/regex/repl/'
                                 expressions, which are applied before most
                                 checks take place.

                                 "metrics": An object that contains font
                                 metrics from the game (and possibly from
                                 user-defined additional characters).
                                 the "metrics" object must contains three
                                 subobjects "normal", "small" and "tiny",
                                 each of them may contain the "metrics" or
                                 "extra_metrics" subsubobject. "metrics"
                                 must be an array that can be extracted from
                                 the game as follow:

                                 sc.fontsystem[<font>].widthMap.map(x => x+1)

                                 where <font> is "font", "smallFont" or
                                 "tinyFont" for "normal", "small" and "tiny"
                                 accordingly.  "extra_metrics" is another way
                                 to define metrics where keys are characters
                                 (or icon names) and values are widths.
                                """)
    check.add_argument("--asset-path", dest="assetpath",
                       metavar="<file or directory>",
                       help="""Instead of checking the file specified by
                       --pack-file, check this directory of assets.  This can
                       be used against the game files or some mods's asset.
                       Not everything can be checked in this mode""")
    check.set_defaults(check=True)

    get = subparser.add_parser("get",
                               help="""Get text given their id
                               The format of the output is exactly the same
                               as the one 'continue' uses.""")
    get.add_argument("file_dict_path",
                     help="A file dict path, e.g. 'hello/test.json/thing/4/t'")

    save_cache = subparser.add_parser("save_cache",
                                      help="""Browse the game file to look for
                                      strings and cache them into the file
                                      specified by --string-cache-file
                                      ("string_cache.json" by default), so that
                                      reading from them is faster later on.
                                      "string_cache.json" always contains every
                                      information present from the game (this
                                      command ignores filtering options).
                                      """)
    save_cache.set_defaults(save_cache=True)


    result = parser.parse_args()
    if "save_config" in result:
        config.update_with_argparse_result(result)
        config.check()
        config.save_to_file(result.config_file)
        sys.exit(0)


    extra = {}
    def put_some_in_extra(key, value):
        if key in ("check",):
            extra[key] = value
            return True
        return False

    if os.path.exists(result.config_file):
        config.load_from_file(result.config_file, put_some_in_extra)
    config.update_with_argparse_result(result)
    config.check()

    extra["do_count"] = "count" in result
    extra["do_get"] = vars(result).get("file_dict_path")
    extra["debug"] = vars(result).get("debug", False)
    extra["do_check"] = "check" in result
    extra["check-asset-path"] = vars(result).get("assetpath")
    extra["do_cache"] = "save_cache" in result
    return config, extra

def count_or_debug(config, extra, pack):
    uniques = {}
    count = 0
    iterator = config.iterate_over_configured_source(pack)
    for file_dict_path_str, lang_label, tags, _ in iterator:
        orig = lang_label.get(config.from_locale)
        if orig is None:
            continue
        uniques[orig] = uniques.get(orig, 0) + 1
        count += 1
        if extra["debug"]:
            print("%s: %s"%(file_dict_path_str, " ".join(tags)))
    print("Total strings:", count)
    print("Unique strings:", len(uniques))
    print("Most duplicated strings:")
    for _, (s, c) in zip(range(10), sorted(uniques.items(), key=lambda x: x[1],
                                           reverse=True)):
        print("%d\t%s"%(c, s))
    sys.exit(0)

def save_into_cache(config, pack):
    if not config.string_cache_file:
        print("no string cache file specified")
        sys.exit(1)
    iterator = config.iterate_over_all_game()

    cache = common.string_cache()
    for file_dict_path_str, lang_label, tags, _ in iterator:
        cache.add(file_dict_path_str, lang_label, {"tags": " ".join(tags)})
    cache.save_into_file(config.string_cache_file)

def print_lang_label(config, file_dict_path_str):
    sparse_reader = config.get_sparse_reader()
    complete = sparse_reader.get_complete_by_str(file_dict_path_str)
    langlabel, (file_path, dict_path), reverse_path = complete
    if not langlabel:
        print("Not found")
        sys.exit(1)
    if isinstance(reverse_path, dict) and "tags" in reverse_path:
        tags = reverse_path["tags"].split(" ")
    else:
        tags = tagger.find_tags(file_path, dict_path, reverse_path)
    langlabel = config.prune_langlabel(langlabel)
    a = Translator.format_trans_to_show(langlabel, tags=tags,
                                        file_dict_path_str=file_dict_path_str)
    print(a)


if __name__ == '__main__':
    config, extra = parse_args()

    if extra["do_get"]:
        print_lang_label(config, extra["do_get"])
        sys.exit(0)

    pack = PackFile()
    readliner = Readliner()
    if os.path.exists(config.packfile) and not extra["check-asset-path"]:
        history = CircularBuffer(config.history_size)
        if readliner.has_history_support():
            add_to_history = history.append
        else:
            add_to_history = lambda x: None

        pack.load(config.packfile, add_to_history)
        for entry in history:
            readliner.add_history(CommandParser.make_line_input(entry))
        del history
    if extra["do_count"]:
        count_or_debug(config, extra, pack)
    if extra["do_check"]:
        check_options = extra.get("check", {})
        if extra["check-asset-path"]:
            checker = check_assets(config.get_sparse_reader(), check_options,
                                   extra["check-asset-path"],
                                   config.from_locale)
        else:
            checker = PackChecker(config.get_sparse_reader(), check_options)
            checker.check_pack(pack)
        sys.exit(1 if checker.errors else 0)
    if extra["do_cache"]:
        save_into_cache(config, pack)
        sys.exit(0)

    readliner.set_compose_map(config.compose_chars)
    translator = Translator(config, pack, readliner)

    import signal
    if hasattr(signal, "SIGINT"):
        def sigint_once(sigint, frame):
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            original_sigint_handler(sigint, frame)
        original_sigint_handler = signal.signal(signal.SIGINT, sigint_once)

    try:
        try:
            iterator = config.iterate_over_configured_source(pack)
            translator.ask_for_multiple_translations(iterator)
        except EOFError:
            pass
        except KeyboardInterrupt:
            pass
    finally:
        pack.save(config.packfile)

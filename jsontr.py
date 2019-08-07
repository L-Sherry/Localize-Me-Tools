#!/usr/bin/python3

import common, re, os, sys, argparse

from readliner import Readliner

def find_tags(file_path, dict_path, previous):
    """Find tags to apply to a string given the context of where it was found

    This is very hacky, but does its job most of the time"""
    tags = []

    first_component = file_path[0]
    if first_component.endswith(".json"):
        first_component = first_component[:-5]

    if first_component == "database":
        tags.append("data-%s"%dict_path[0])
        if dict_path[0] == "lore":
            tags.append("lore-%s" % previous[2]["category"].lower())
            tags.append("lore-%s"%dict_path[-1])
            return tags
        if dict_path[0] == "quests":
            tags.append("quests-%s"%dict_path[-1])
            tags.append("quests-%s"%previous[2].get("area"))
        elif dict_path[0] != "commonEvents":
            tags.append("%s-%s"%(dict_path[0], dict_path[-1]))
            return tags

    elif first_component == "item-database":
        tags.append("item")
        tags.append("item-%s"%dict_path[-1])
    else:
        tags.append("%s-%s"%(first_component, dict_path[-1]))

    if isinstance(previous[-1], dict):
        if previous[-1].get("msgType"):
            type_ = previous[-1].get("msgType").lower()
            tags.append(type_)
            tags.append("%s-%s"%(type_, dict_path[-1]))

        elif previous[-1].get("type"):
            text_type = previous[-1].get("type").lower()
            if text_type.startswith("show_"):
                text_type = text_type[5:]
            if text_type.endswith("_msg"):
                text_type = text_type[:-4]
            if text_type in frozenset(("msg", "side")):
                tags.append("conv")
                who = previous[-1].get("person")
                if who:
                    if who.__class__ == str:
                        tags.append(who)
                    else:
                        tags.append(who["person"])
                        tags.append(who["expression"].lower())
            else:
                tags.append(text_type)

    if not tags:
        tags.append("Unknown")

    return tags

class PackFile:
    def __init__(self):
        self.reset()

    def reset(self):
        # dict from serialized file_dict_path to translation object
        # (e.g. {"orig": orig, "text": new})
        self.translations = {}
        # Index from orig to an object in self.translations
        self.translation_index = {}
        # Statistics about badnesses
        self.quality_stats = {"bad":0, "incomplete":0, "unknown":0, "wrong":0}

    def load(self, filename, on_each_text_load = lambda x: None):
        self.reset()

        self.translations = common.load_json(filename)
        for entry in self.translations.values():
            self.translation_index[entry['orig']] = entry
            self.add_quality_stat(entry)
            on_each_text_load(entry)

    def save(self, filename):
        try:
            os.rename(filename, filename+'~')
        except:
            pass
        common.save_json(filename, self.translations)

    def add_quality_stat(self, entry):
        qual = entry.get("quality")
        if qual is not None:
            self.quality_stats[qual] += 1

    def add_translation(self, dict_path_str, orig, new_entry):
        new_entry["orig"] = orig
        self.translations[dict_path_str] = new_entry
        self.add_quality_stat(new_entry)
        # this may erase duplicates, but may be more fitting to the context
        self.translation_index[orig] = new_entry

    def get_by_orig(self, orig):
        return self.translation_index.get(orig)

    def get(self, file_dict_path_str, orig_text = None):
        ret = self.translations.get(file_dict_path_str)
        if ret is None:
            return None
        if orig_text is not None and ret['orig'] != orig_text:
            return None
        return ret

    get_all = lambda self: self.translations

    def get_stats(self, config):
        strings = len(self.translations)
        uniques = len(self.translation_index)
        def format_stat(count, out_of, label):
            if isinstance(out_of, int) and out_of > 1:
                return "%6i / %6i, %s (%.3f%%)"%(count, out_of, label,
                                                 100. * count / out_of)
            else:
                return "%6i %s"%(count, label)

        ret = format_stat(strings, config.total_count, "translations") + '\n'
        desc = {"unknown": "strings of unchecked quality",
                "bad": "badly formulated/translated strings",
                "incomplete": "strings with translated parts missing",
                "wrong": "translations that changes the meaning significantly"}
        for qual, count in self.quality_stats.items():
            ret += "%6i %s(%s)\n"%(count, desc[qual], qual)
        ret += format_stat(uniques, config.unique_count, "uniques")
        return ret


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
        start_at = self.index % len(self.array)
        for index in range(start_at, len(self.array)):
            yield self.array[index]
        for index in range(start_at):
            yield self.array[index]



class CommandParser:
    qualities_commands = (
            ("/bad", "bad"),
            ("/wro", "wrong"),
            ("/miss", "incomplete"),
            ("/unkn", "unknown"),
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
    def make_line_input(cls, trans):
        """The inverse of parse_line_input(trans).

        This round trip is guaranteed: parse_line_input(make_line_input(x))==x
        """
        quality = trans.get("quality")
        note = trans.get("note")
        text = trans["text"].replace('\n','\\n')
        if quality is None and note is None:
            return trans["text"]
        for command, maybe_quality in cls.qualities_commands:
            if quality == maybe_quality:
                if note:
                    return "%s%s %s"%(trans["text"], command, note)
                return "%s%s"%(trans["text"], command)
        assert False, "unknown quality"
        return trans["text"]


class Checker:
    def __init__(self, gamepath, lang, check_settings):
        gamepath = common.get_assets_path(gamepath)
        self.sparse_reader = common.sparse_dict_path_reader(gamepath, lang)
        self.lang = lang

        database_path = os.path.join(gamepath, "data/database.json")
        self.database = common.load_json(database_path)
        item_database_path = os.path.join(gamepath, "data/item-database.json")
        self.item_database = common.load_json(item_database_path)

        self.check_settings = check_settings
        self.errors = 0

    colors = {"normal":""}
    if os.isatty(sys.stdout.fileno()):
        # no termcap ... assume ANSI
        colors = {
            "red": "\033[31m",
            "green": "\033[32m",
            "yellow": "\033[33m",
            # 34 is stark blue
            "purple": "\033[35m",
            "blue": "\033[36m", # light blue actually.
            "normal": "\033[0m"
        }

    severities_text = {
        "error": "%sError%s"%(colors.get("red",""), colors["normal"]),
        "warn": "%sWarning%s"%(colors.get("yellow",""), colors["normal"]),
        "notice": "%sNotice%s"%(colors.get("green",""), colors["normal"]),
        "note": "%sNote%s"%(colors.get("blue",""), colors["normal"])
    }

    gamecolor = {
        "0": "normal", "1": "red", "2":"green",
        "3": "blue", # actually purple
        "4": "purple", # actually gray
        "5": "yellow", # actually orange
    }

    @staticmethod
    def wrap_text(text, length, indentchar):
        to_print = (text[i:i+length] for i in range(0, len(text), length))
        return ("\n%s"%(indentchar)).join(to_print)

    def print_error(self, file_dict_path_str, severity, error, text):
        # sadly, we can't give line numbers...
        print("%s: %s%s"%(self.severities_text.get(severity, severity),
                         error, self.colors['normal']))
        print("at %s"%(self.wrap_text(file_dict_path_str, 64, "\t\t")))
        print("\t%s%s"%(self.wrap_text(text, 72, '\t'), self.colors["normal"]))
        if severity == "error":
            self.errors += 1

    @staticmethod
    def iterate_escapes(string):
        last = 0
        index = string.find('\\')
        while index >= 0 and index < len(string):
            next_index = yield (last, index)
            if next_index is not None:
                index = next_index
                yield None
            else:
                index = index + 2 # skips the \ and the next char
            last = index
            index = string.find('\\', index)
        yield (last, len(string))

    TEXT="TEXT"
    DELAY="DELAY"
    ESCAPE="ESCAPE"
    COLOR="COLOR"
    SPEED="SPEED"
    VARREF="VARREF"
    ICON="ICON"

    @classmethod
    def lex_that_text(cls, text, warn_func):
        iterator = cls.iterate_escapes(text)
        last = 0
        for last_index, index in iterator:
            part = text[last_index:index]
            if part:
                yield cls.TEXT, part
            char = text[index+1: index+2]

            if char in '.!': # delaying commands
                yield cls.DELAY, char
            elif char == '\\':
                yield cls.ESCAPE, char
            elif char in 'csiv':
                if text[index+2:index+3] != '[':
                    warn_func("error", "'\\%s' not followed by '['"%char)
                    continue
                end = text.find(']', index+2)
                if end == -1:
                    warn_func("error", "'\\%s[' not finished"%char)
                    continue
                inner = text[index+3:end]
                type_ = {'c':cls.COLOR, 's':cls.SPEED,
                         'i': cls.ICON, 'v':cls.VARREF}[char]
                yield type_, inner
                iterator.send(end+1)
            else:
                warn_func("warn", "unknown escape '\\%s'"%char)

    @staticmethod
    def check_number(text, warn_func):
        if not text.isdigit():
            warn_func("error", "'%s' is not a number"%text)
        return text

    variables = [
        ("lore.title.", "", "database", ["lore", "%s", "title"]),
        ("item.", ".name", "item_database", ["items", "%i", "name"]),
        # TODO: check
        ("combat.name.", "", "database", ["enemies", "%s", "name"]),
        ("area.", ".name", "database", ["areas", "%s", "name"]),
        ("misc.localNum.", "", check_number.__func__, [])
    ]

    def find_stuff_in_orig(self, orig, wanted_type):
        """find variable references in the original, without warning"""
        for type_, value in self.lex_that_text(orig, lambda a,b: None):
            if type_ is wanted_type:
                yield value

    def lookup_var(self, name, warn_func, orig):

        for prefix, suffix, file_, dict_path_template in self.variables:
            if not name.startswith(prefix) or not name.endswith(suffix):
                continue
            name = name[len(prefix): len(name)-len(suffix)]

            if callable(file_):
                return file_(name, warn_func)

            dict_path = []
            for component in dict_path_template:
                if component == "%s":
                    dict_path.append(name.replace('/', '.'))
                elif component == "%i":
                    if not name.isdigit() or name[0:1] == '0':
                        warn_func("error", "number '%s' is invalid"%name)
                    dict_path.append(int(name))
                else:
                    dict_path.append(component)

            text = common.get_data_by_dict_path(getattr(self, file_), dict_path)
            if text is None:
                warn_func("error",
                          "variable reference '%s' is invalid: not found"%name)
                return "(invalid)"

            if isinstance(text, dict):
                text = text.get(self.lang)
            if not isinstance(text, str):
                warn_func("error", "variable reference '%s' is not text"%name)
                return "(invalid)"
            return text

        for maybevar in self.find_stuff_in_orig(orig, self.VARREF):
            if maybevar == name:
                return "(something)"

        warn_func("warn", "unknown variable %s not in original"%name)
        return "(error)"

    def try_render_text(self, text, orig, warn_func):
        """returns (final, printable with ansi)"""
        result = ""
        printable_result = ""
        current_color = "0"
        current_speed = "-1" # it depends.

        for type_, value in self.lex_that_text(text, warn_func):
            if type_ is self.TEXT:
                result += value
                printable_result += value
            elif type_ is self.DELAY:
                pass
            elif type_ is self.ESCAPE:
                warn_func("notice", "\\ present in text, is this intended ?")
            elif type_ is self.COLOR:
                actual_color = self.gamecolor.get(value)
                if actual_color is None:
                    warn_func("error", "bad \c[] command")
                    continue
                if value == current_color:
                    warn_func("warn", "same color assigned twice")
                current_color = value
                printable_result += self.colors.get(actual_color, "")
            elif type_ is self.SPEED:
                if len(value) != 1 or value not in "01234567":
                    warn_func("error", "bad \s[] command")
                    continue
                if result:
                    warn_func("notice", "speed not at start of text, unusal")
                if current_speed == value:
                    warn_func("warn", "same speed specified twice")
                current_speed = value
            elif type_ is self.ICON:
                if value not in self.find_stuff_in_orig(orig, self.ICON):
                    warn_func("notice", "icon not present in original text")
                result+='[]'
                printable_result+='←'
            elif type_ is self.VARREF:
                value = self.lookup_var(value, warn_func, orig)
                printable_result += value
                result += value
            else:
                assert False
        if current_color != "0":
            warn_func("notice", "color does not end with 0")
        return (result, printable_result)

    def check_text(self, file_dict_path_str, text, orig):
        # it would be great if we had the tags here.
        def print_please(severity, error):
            self.print_error(file_dict_path_str, severity, error, text)

        # that's the only test we are doing for now
        self.try_render_text(text, orig, print_please)

    def check_pack(self, pack, from_locale):
        for file_dict_path_str, trans in pack.get_all().items():
            true_orig = self.sparse_reader.get_str(file_dict_path_str)
            orig = trans.get("orig")
            if true_orig is None:
                self.print_error(file_dict_path_str, "warn",
                                 "translation is stale: does not exist anymore",
                                 text)
                continue
            elif orig is not None and true_orig != orig:
                self.print_error(file_dict_path_str, "warn",
                                 "translation is stale: original text differs",
                                 text)
            text = trans.get("text")
            if not text:
                if "ciphertext" in trans:
                    self.print_error(file_dict_path_str, "notice",
                                     "encrypted entries not supported", "")
                elif true_orig:
                    self.print_error(file_dict_path_str, "error",
                                     "entry has no translation", "")
                continue

            self.check_text(file_dict_path_str, text, true_orig)

    def check_assets(self, assets_path, from_locale):
        it = common.walk_assets_for_translatables(assets_path, from_locale)
        for langlabel, (file_path, dict_path), _ in it:
            orig = langlabel[from_locale]
            file_dict_path_str = common.serialize_dict_path(file_path,
                                                            dict_path)
            self.check_text(file_dict_path_str, orig, orig)

class Configuration:
    def __init__(self):
        self.reset()
        self.check()

    @staticmethod
    def get_filter_from_components(array):
        if len(array) == 0:
            return lambda x: True
        array_of_ands = []
        for x in array:
            if isinstance(x, str):
                array_of_ands.append((x,))
            elif isinstance(x, list):
                array_of_ands.append(x)
            else:
                raise ValueError("bad value for filter: %s"%repr(x))
        def check_filter(some_path_as_list):
            for candidate in array_of_ands:
                if all(c in some_path_as_list for c in candidate):
                    return True
            return False
        return check_filter

    default_options = {
            "gamedir": ".",
            "from_locale": "en_US",
            "show_locales": [],
            "compose_chars": [],
            "filter_file_path": [],
            "filter_dict_path": [],
            "filter_tags": [],
            "ignore_known": True,
            "ignore_unknown": False,
            "allow_empty": False,
            "editor": os.getenv("EDITOR") or "",
            "packfile": "",
            "total_count": 0,
            "unique_count": 0
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

        split_me_regex = re.compile('\s+')
        listoflist = lambda string: split_me_regex.split(string)

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
        parser.add_argument("--filter-tags", nargs="+", dest="filter_tags",
                            type=listoflist, metavar="<tag1 tag2...>",
                            help="""filter the translations to display given
                            their tags.  Follows the same convention as
                            --filter-file-path and --filter-dict-path, so that
                            --filter-tags "conv player" "xeno" will match
                            translations having both "conv" and "player" tags or
                            translations having the "xeno" tag""")
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
                            allow_empty=False, total_count = None,
                            unique_count = None)
    def update_with_argparse_result(self, result):
        for key in self.default_options.keys():
            value = getattr(result, key)
            if value is not None:
                setattr(self, key, value)


    get_default_options = staticmethod(x for x in default_options)

    def reset(self):
        for key, value in self.default_options.items():
            setattr(self, key, value)

    def check(self):
        # filter_file_path -> filter_file_path_func
        # filter_dict_path -> filter_dict_path_func
        # filter_tags -> filter_tags_func
        for filtertype in ("file_path", "dict_path", "tags"):
            components = getattr(self, "filter_%s"%filtertype)
            filter_ = self.get_filter_from_components(components)
            setattr(self, "filter_%s_func"%filtertype, filter_)
        if not self.show_locales:
            self.show_locales = [self.from_locale]

    def load_from_file(self, filename, unknown_option = lambda k,v: False):
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

    def iterate_over_filtered(self, packfile, assets_path):
        filter_ = self.filter_file_path_func
        dirpath = os.path.join(common.get_assets_path(assets_path), "data")
        iterable = common.walk_assets_for_translatables(dirpath,
                                                        self.from_locale,
                                                        filter_)
        for lang_label, (file_path, dict_path), reverse_path in iterable:
            if not self.filter_dict_path_func(dict_path):
                continue
            path_str = common.serialize_dict_path(file_path, dict_path)
            known = packfile.get(path_str)
            if self.ignore_unknown and not known:
                continue
            orig = lang_label[self.from_locale]
            if self.ignore_known and known and orig == known.get('orig'):
                continue

            tags = find_tags(file_path, dict_path, reverse_path)
            if not self.filter_tags_func(tags):
                continue

            yield path_str, lang_label, known, tags

    def get_trans_to_show(self, file_dict_path_str, lang_label, tags, known):
        """Return a (string, list<string>) containing stuff to translate.

        The first one is what to show to the user, the second one is a list
        of original texts contained in the first one."""

        string = "%s\ntags: %s\n"%(file_dict_path_str, " ".join(tags))
        texts = []
        if known:
            our_orig = known.get('orig')
            if our_orig and our_orig != lang_label[self.from_locale]:
                string += "our:%s\n"%known['orig']

        for locale in self.show_locales:
            text = lang_label.get(locale)
            if text is None:
                string += "no %s\n"%locale
            else:
                texts.append(text)
                string += "%s: %s\n"%(locale[:2], text)
        return string, texts


def spawn_editor(editor, pack, filename):
    if not config.editor:
        print("No editor configured")
        return
    pack.save(config.packfile)
    while True:
        os.system("%s %s"%(config.editor, config.packfile))
        try:
            # not touching the history here, this is intentionnal, it gets
            # confusing otherwise.
            pack.load(config.packfile)
            return
        except Exception as e:
            print(e)
            line = input("Press enter to reedit, or :q! to quit")
            if line.strip() == ':q!':
                sys.exit(1)
            continue


def ask_for_translation(config, pack, to_show):
    prompt = to_show + "> "
    while True:
        line = input(prompt)
        stripped = line.strip()
        if stripped == ":w":
            pack.save(config.packfile)
        elif stripped in (":q", ":wq"):
            raise KeyboardInterrupt()
        elif stripped == ':e':
            spawn_editor(config.editor, pack, config.packfile)
        elif stripped == ':s':
            print(pack.get_stats(config))
        else:
            break
    return CommandParser.parse_line_input(line)


def do_the_translating(config, pack, readliner):
    iterator = config.iterate_over_filtered(pack, config.gamedir)
    for file_dict_path_str, lang_label, known, tags in iterator:
        to_show, origs = config.get_trans_to_show(file_dict_path_str,
                                                  lang_label, tags, known)

        words = set()
        for orig in origs:
            for word in orig.replace('\n', ' ').split(' '):
                words.add(word)
        readliner.set_complete_array(words)

        orig = lang_label[config.from_locale]
        if known:
            readliner.prefill_text(CommandParser.make_line_input(known))
        else:
            dup = pack.get_by_orig(orig)
            if dup:
                readliner.prefill_text(CommandParser.make_line_input(dup))
        result = ask_for_translation(config, pack, to_show)
        if not result["text"] and not config.allow_empty:
            continue
        pack.add_translation(file_dict_path_str, orig, result)



def parse_args():
    import argparse
    config = Configuration()
    parser = argparse.ArgumentParser(description="Create and update packs "
                                                 " of translated texts\n")
    parser.add_argument("--config-file", "-c", metavar="<config file>",
                        dest="config_file", default="config.json",
                        help="""Location of the optional configuration file
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
                                  translation is wrong and does not match the
                                  original text.

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
                                  """)

    save_config = subparser.add_parser("saveconfig",
                                       help="""create a config file with
                                       the options on the command line""")
    save_config.set_defaults(save_config=True)

    count = subparser.add_parser("count", help="""Count the number of texts
                                 left to translate""",
                                 description="""Counts the number of texts
                                 that matches the configured filters.""")
    count.set_defaults(count=True)
    count.add_argument("--debug", action="store_true",
                       help="""Enable various debugging output that may be
                               helpful to debug the lang label finder""")

    check = subparser.add_parser("check", help="""Check the translations for
                                 various errors""")
    check.add_argument("--asset-path", dest="assetpath",
                       metavar="<file or directory>",
                       help="""Instead of checking the file specified by
                       --pack-file, check this directory of assets.  This can
                       be used against the game files or some mods's asset.
                       Not everything can be checked in this mode""")
    check.set_defaults(check=True)


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

    extra["count"] = "count" in result
    extra["debug"] = vars(result).get("debug", False)
    extra["check"] = "check" in result
    extra["check-asset-path"] = vars(result).get("assetpath")
    return config, extra

def count_or_debug(config, extra, pack):
    uniques = {}
    count = 0
    iterator = config.iterate_over_filtered(pack, config.gamedir)
    for file_dict_path_str, lang_label, _, tags in iterator:
        orig = lang_label[config.from_locale]
        uniques[orig] = uniques.get(orig, 0) + 1
        count += 1
        if extra["debug"]:
            print("%s: %s"%(file_dict_path_str, " ".join(tags)))
    print("Total strings:", count)
    print("Unique strings:", len(uniques))
    print("Most duplicated strings:")
    for _,(s,c) in zip(range(10), sorted(uniques.items(), key=lambda x:x[1],
                                         reverse=True)):
        print("%d\t%s"%(c, s))
    sys.exit(0)

if __name__ == '__main__':
    config, extra = parse_args()
    pack = PackFile()
    readliner = Readliner()
    if os.path.exists(config.packfile) and not extra["check-asset-path"]:
        history = CircularBuffer(100)
        if readliner.has_history_support():
            add_to_history = history.append
        else:
            add_to_history = lambda x: None

        pack.load(config.packfile, add_to_history)
        for entry in history:
            readliner.add_history(CommandParser.make_line_input(entry))
        del history
        print("loaded", config.packfile)
        print(pack.get_stats(config))
    if extra["count"]:
        count_or_debug(config, extra, pack)
    if extra["check"]:
        checker = Checker(config.gamedir, config.from_locale, "FIXME")
        if extra["check-asset-path"]:
            checker.check_assets(extra["check-asset-path"], config.from_locale)
        else:
            checker.check_pack(pack, config.from_locale)
        sys.exit(1 if checker.errors else 0)

    readliner.set_compose_map(config.compose_chars)

    try:
        do_the_translating(config, pack, readliner)
    except EOFError:
        pack.save(config.packfile)
    except KeyboardInterrupt:
        pack.save(config.packfile)
    finally:
        pack.save(config.packfile)

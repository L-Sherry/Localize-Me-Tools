#!/usr/bin/python3

import re
import os
import sys
import itertools

# This dependency must be installed
import grammalecte

# Nice work... python.
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

import common
import checker


class SimpleGrammalecteDictionnary:
    """Hack compatible with grammalecte.ibdawg.IBDAWG to check spelling

    grammalecte.ibdawg.IBDAWG reads a dictionnary compressed as a DAGs.

    That's great, but it's completely overkill for a personnal dictionnary
    file, but that's the only option grammalecte supports.
    This class emulates IBDAWG so we don't have to deal with this format.
    """
    def __init__(self):
        self.words = {}
    def add_word(self, word, anno = None):
        self.words.setdefault(word, set()).add(anno)
    def set_word_annos(self, word, annos):
        self.words[word] = set(annos)
    def lookup(self, word):
        # strict lookup
        return word in self.words
    def isValid(self, word):
        # The original checks case-insensively. we... probably don't want that.
        return word in self.words
    def isValidToken(self, compound_word):
        if self.isValid(compound_word):
            return True
        # the original tries to split compound_word with '-'. Don't need ?
        #if '-' in compound_word:
        #    return all(self.isValid(word) for word in word.split('-'))
        return False
    def getMorph(self, word):
        ret = []
        for morph in self.words.get(word, ()):
            # use ? in grammalecte-cli to get them.
            ret.append('>%s/%s/*' % (word, morph))
        return ret
    def suggest(self, word, limit, bSplitTrailingNumbers=False):
        return []

class GrammalecteChecker(checker.PackChecker):
    def __init__(self, sparse_reader, check_options, dont_print = False):
        super().__init__(sparse_reader, check_options)
        self.grammar = grammalecte.GrammarChecker("fr")

        opts = check_options.get("grammalecte", {})

        self.setup_dictionnary(opts.get("dictionary"))
        self.whitelist = frozenset(opts.get("whitelist"))
        spellchecker = self.grammar.getSpellChecker().activateStorage()

        replacements = opts.get("replacements", {})

        before = self.prepare_replacements(replacements.get("before"))
        after = self.prepare_replacements(replacements.get("after"))

        # These allow to suppress known issues, especially with formatting.
        # It seems that there is no API to dynamically add words to a custom
        # dictionnary.  So these replacements will do, as long as we replace
        # unknown words with similar words that exist in the dictionnary.
        self.grammalecte_replacements_before = before
        self.grammalecte_replacements_after = after

        self.dont_print = dont_print
        self.all_the_errors = {}
        self.all_spells = {}
        self.spell_count = 0
        self.grammar_count = 0
    def setup_dictionnary(self, dictionnary):
        if not dictionnary:
            return
        personal_dict = SimpleGrammalecteDictionnary()
        #for word, annos in dictionnary.items():
        #    if isinstance(annos, str):
        #        annos = (annos,)
        #    personal_dict.set_word_annos(word, annos)
        for entry in dictionnary:
            personal_dict.add_word(*entry.split('/'))

        # HACK
        spellchecker = self.grammar.getSpellChecker()
        spellchecker.oPersonalDic = personal_dict
        spellchecker.activatePersonalDictionary()
        assert spellchecker.bPersonalDic

    def print_error(self, file_dict_path_str, severity, error, text):
        a = self.all_the_errors.setdefault(file_dict_path_str, [])
        a.append((severity, error, text))
        if self.dont_print:
            return
        super().print_error(file_dict_path_str, severity, error, text)


    def check_paragraph(self, paragraph, warn_func):
        if paragraph in self.whitelist:
            return

        grammar, spells = self.grammar.getParagraphErrors(paragraph)
        if not grammar and not spells:
            return # ok

        self.spell_count += len(spells)
        self.grammar_count += len(grammar)

        for spell in spells:
            badword = spell['sValue']
            self.all_spells[badword] = 1 + self.all_spells.get(badword, 0)

        res = grammalecte.text.generateParagraph(paragraph,
                                                 grammar, spells, 72)
        warn_func("warn", "grammar error" if grammar else "spelling error",
                  str(res))

    @staticmethod
    def prepare_replacements(repls):

        def make_replacer(litteral_or_regex, repl):
            regex = re.compile(litteral_or_regex)
            return lambda text: regex.sub(repl, text)

        return [make_replacer(replace_this, with_this)
                for replace_this, with_this in repls]

    @staticmethod
    def do_replacements(text, replacements):
        for func in replacements:
            text = func(text)
        return text

    def do_all_replacements(self, text, warn_func):
        text = text.strip()

        text = self.do_replacements(text, self.grammalecte_replacements_before)
        text = self.do_text_replacements(text, warn_func)
        text = self.do_replacements(text, self.grammalecte_replacements_after)

        return text

    def check_text(self, file_path, dict_path, text, orig, tags, get_text):
        if text in self.whitelist:
            return
        warn_func = self.create_warn_function(file_path, dict_path, text)

        plain_text = ""
        for _, text_chunk in self.parse_text(text, orig, warn_func, get_text):
            plain_text += text_chunk

        plain_text = self.do_all_replacements(plain_text, warn_func)

        for paragraph in grammalecte.text.getParagraph(plain_text):
            self.check_paragraph(paragraph, warn_func)


settings = common.load_json("config.json")

sparse_reader = common.string_cache('en_US')
sparse_reader.load_from_file(settings["string_cache_file"])

grammar_checker = GrammalecteChecker(sparse_reader, settings.get('check', {}),
                                     False)

french = common.PackFile()
french.load(settings["packfile"])
grammar_checker.check_pack(french)

print("Translations with errors: ", len(grammar_checker.all_spells))
print("Grammar mistakes: ", grammar_checker.grammar_count)
print("Spelling mistakes: ", grammar_checker.spell_count)
print("Most common bad words:")
iterator = sorted(grammar_checker.all_spells.items(), key=lambda v:v[1],
                  reverse=True)
for badword, count in itertools.islice(iterator, 30):
    print(badword, "(%d)" % count)


# hack: save another pack with errors as note, with quality 'spell'.

patch_me = common.load_json(settings["packfile"])
for file_dict_path_str, errors in grammar_checker.all_the_errors.items():
    grammar_errors = []
    for severity, error, text in errors:
        if error == "grammar error" or error == "spelling error":
            grammar_errors.append(text)

    if not grammar_errors:
        continue

    entry = patch_me[file_dict_path_str]


    end_note = entry.get("note", "")
    if entry.get("quality"):
        end_note = "%s: %s"%(entry["quality"], end_note)

    if end_note:
        grammar_errors.append(end_note)

    entry["quality"] = "spell"
    entry["note"] = "\n".join(grammar_errors)

common.save_json(settings["packfile"]+".spellchecked", patch_me)

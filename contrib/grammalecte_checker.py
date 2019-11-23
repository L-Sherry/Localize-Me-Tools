#!/usr/bin/python3

import re
import os
import sys

# This dependency must be installed
import grammalecte

# Nice work... python.
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

import common
import checker


class GrammalecteChecker(checker.PackChecker):
    def __init__(self, sparse_reader, check_options):
        super().__init__(sparse_reader, check_options)
        self.grammar = grammalecte.GrammarChecker("fr")

        opts = check_options.get("grammalecte", {})
        replacements = opts.get("replacements", {})

        before = self.prepare_replacements(replacements.get("before"))
        after = self.prepare_replacements(replacements.get("after"))

        # These allow to suppress known issues, especially with formatting.
        # It seems that there is no API to dynamically add words to a custom
        # dictionnary.  So these replacements will do, as long as we replace
        # unknown words with similar words that exist in the dictionnary.
        self.grammalecte_replacements_before = before
        self.grammalecte_replacements_after = after

    def check_paragraph(self, paragraph, warn_func):
        res = self.grammar.generateParagraph(paragraph,
                                             bEmptyIfNoErrors=True,
                                             nWidth=72)
        if res:
            warn_func("warn", "grammar error", str(res))

    @staticmethod
    def prepare_replacements(repls):

        def make_replacer(litteral_or_regex, repl):
            if '\\' in repl:
                regex = re.compile(litteral_or_regex)
                return lambda text: regex.sub(repl, text)
            return lambda text: text.replace(litteral_or_regex, repl)

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

grammar_checker = GrammalecteChecker(sparse_reader, settings.get('check', {}))

french = common.PackFile()
french.load(settings["packfile"])
grammar_checker.check_pack(french)

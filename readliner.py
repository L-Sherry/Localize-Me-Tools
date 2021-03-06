import re


class Readliner:
    """Interface to the readline module."""
    # most of the stuff are static because the hook is static ... and there
    # is only one readline module anyway
    def __init__(self):
        Readliner.compose_map = {}
        Readliner.preload = ""
        Readliner.entire_completion_string = None
        Readliner.complete_array = []
        Readliner.history_to_add = []
        Readliner.history_start = 0
        Readliner.keep_history = 100
        try:
            import readline
            Readliner.readline = readline
            readline.read_init_file()
            readline.parse_and_bind("tab: complete")
            readline.set_pre_input_hook(Readliner.pre_input_hook)
            readline.set_completer(Readliner.completer_hook)
            readline.set_completer_delims(" ")

        except:
            Readliner.set_preload = lambda x: None
            Readliner.readline = None
            print("'readline' not found. Some features are thus disabled !")

    @staticmethod
    def pre_input_hook():
        Readliner.readline_active = True
        if Readliner.preload:
            Readliner.readline.insert_text(Readliner.preload)
            Readliner.readline.redisplay()
            Readliner.preload = None

    @staticmethod
    def prefill_text(text):
        Readliner.preload = text

    @staticmethod
    def set_complete_array(arr):
        Readliner.complete_array = arr if arr.__class__ == list else list(arr)

    @staticmethod
    def set_entire_completion_string(string):
        Readliner.entire_completion_string = str(string)

    # TODO: should be able to choose the escapes chars
    compose_re = re.compile('[$|](..)')

    @staticmethod
    def set_compose_map(array_of_equalities):
        result = {}
        for equality in array_of_equalities:
            chars, composed = equality.split('=', 1)
            result["".join(sorted(composed))] = chars
            # TODO: should be more dynamic ...
            assert len(composed) == 2, "sorry, only two chars are supported"

        Readliner.compose_map = result

    @staticmethod
    def expand_compose(string):
        def match_replacement(match):
            key = "".join(sorted(match[1]))
            return Readliner.compose_map.get(key, match[0])

        return Readliner.compose_re.sub(match_replacement, string)

    @staticmethod
    def completer_hook(text, state):
        if (Readliner.entire_completion_string and
                not Readliner.readline.get_line_buffer()):
            return Readliner.entire_completion_string if state == 0 else None

        # TODO: should make this more dynamic, like, it would be great to
        # complete the various text replacements.
        expanded = Readliner.expand_compose(text)
        if expanded != text:
            return expanded if state == 0 else None
        for candidate in Readliner.complete_array:
            if not candidate.startswith(text):
                continue
            if not state:
                return candidate
            state -= 1
        return None

    @staticmethod
    def has_history_support():
        return Readliner.readline is not None

    @staticmethod
    def add_history(text):
        if Readliner.readline is not None:
            Readliner.readline.add_history(text)

    @staticmethod
    def read_line(prompt):
        Readliner.readline_active = False
        line = input(prompt)
        if not Readliner.readline_active:
            if not line and Readliner.preload is not None:
                line = Readliner.preload
            elif line == '\t':
                line = Readliner.entire_completion_string
        return line

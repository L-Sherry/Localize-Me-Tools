So you want to translate this game ?
  
Mind you, it will be painful, and everything you didn't discover will
be spoiled.  Actually, even future content may be spoiled ! This may
impress your friends (or maybe even the developers who forgot what they
left for us to discover), but will ruin many surprises.

But you still want to do it, right ?

We will start with simple things right away.

Installing this
===============

These scripts requires nothing but a python interpreter, version 3.6 or above.
That, and a working terminal intepreter.  Most OS comes with one nowadays.
Because yes, these are terminal applications and i expect you to be confortable
with your OS's terminal.

If you are on Linux, this is probably already installed, or readily
available from your favorite package manager.

If you are on OS X, sorry, but the integrated Python version is something like
2.6 and is too old. You will need to install Python 3 yourself, possibly via
one of the numerous package manager for Mac OS X.

If you are on Windows, things will be a lot more complicated, and since i don't
use this OS, you will be a bit on your own.  Basically, if you just go to
Python.org and download the latest version, then this script will work, but
the integrated 'readline' will not be available, marking things harder for you.
If you want this 'readline' thing, you will probably need one of the many solution
to run Linux-like programs on windows.  Possibly Microsoft's Linux Subsystem for Windows
may work.  That, or switch to Linux.

Let's configure it
==================

We will only use jsontr.py for now.  Put the content of this repository somewhere
and run jsontr.py from the command line.

jsontr.py is basically a tool scans every files in your game directory for stuff
to translate, then will show it to you and ask you to translate it, saving the result.

If you run it without any parameters, it will greet you with its usage string ...

```
usage: jsontr.py [-h] [--config-file <config file>]
                 [--gamedir <path to assets/>] [--from-locale <locale>]
                 [--show-locales <locales> [<locales> ...]]
                 [--compose-chars <char>=<2 chars> [<char>=<2 chars> ...]]
                 [--filter-file-path <file/dir names> [<file/dir names> ...]]
                 [--filter-dict-path <json indexes> [<json indexes> ...]]
                 [--filter-tags <tag1 tag2...> [<tag1 tag2...> ...]]
                 [--no-ignore-known] [--ignore-known] [--no-ignore-unknown]
                 [--ignore-unknown] [--editor <editor program>]
                 [--pack-file <pack file>]
                 COMMAND ...
jsontr.py: error: the following arguments are required: COMMAND
```

Running it with `--help` will display even more options.
There are many options that you will have to set to start:

`--gamedir /path/to/crosscode/game/something/something/assets`

tells jsontr.py where to find the game files. It should point either to the directory
containing the `assets/` directory, or be the `assets/` directory itself.  It may even be
a subdirectory of the `assets/` directory.

`--from-locale en_US`

indicate from which language you will primarily translate the game.
The default is to translate from english (`en_US` in UNIX locale parlance) but you
may translate from any language part of the game, which are as of now
`en_US`, `de_DE`, `zh_CN`, `ja_JP` and `ko_KR`.  There are also some `fr_FR` already
in the game files, but I can guarantee you that they do not contain any french text.

You will need to choose it now, because this will influence the file format that
`jsontr.py`uses (it is easily-editable json under the hood, if you want to know).
So choose wisely.  This language will be used for e.g. detecting when texts have changed
when a new game version is released and some other things.

`--show-locales de_DE ko_KR`

Indicate which translation you want to see when translating a string.  While `--from-locale`
influence the file format, this one doesn't so you may change it anytime.
You may specify one or multiple languages. I recommend that you show every language you
are proficient with.  While the `en_US` and `de_DE` are made by the original game developpers,
the others are already translated.  Still, each language comes with its nuances and may help
understanding what you are translating.  If you do not specify this option, then only the
language selected by `--from-locale` will be used.

`--pack-file my_translation.json`

This is the file that will contain all your translations.
`jsontr.py` will create it on the first run and automatically save it on exit.

The other options are not that important right now. You will discover some of them later.

Now these are quite the options and it would be tedious to repeat them. Fortunately,
`jsontr.py` can save them in a configuration file and read them.  By default, it
loads the options from the file `config.json` in the current directory.

Last but not least, `jsontr.py` uses subcommands, like `git`.  There are only two subcommands that
you need right now : The first, you will use it right away, is called `saveconfig`
and it does what you may have guessed: it will save the options from the command
line in `config.json`.  So let's do it !

```
./jsontr.py --gamedir ~/Kazaa/CrossCode-0.9.10-checked-by-w4rl0rd/game/assets \
            --from-locale de_DE --show-locales de_DE --pack-file jaevla-ja.json \
            saveconfig
```

Now you should have a `config.json` in your current directory.

Let's start !
=============

The second subcommand of `jsontr.py` that you will use a lot is very badly named `continue`.

Let's use it right away !

```
./jsontr.py continue
```

Now, `jsontr.py` will start scanning the game directory, and will have quickly found the
first thing it can that require a translation. It will probably be the most uninteresting thing
to translate in the world, but if you want a 100% translation, you will require it anyway.

Probably, it will have picked the names of the achivements in the game.  It will
present it to you as follow:

```
database.json/achievements/story-01/name
tags: data-achievements achievements-name
de: Kapitel 1 vollständig
> 
```

The first line indicate where it found the string. Right now, it's in the file
under `assets/data/database.json`, which, if you load it as JSON into the `x` variable,
is found in `x["achievements"]["story-01"]["name"]`

The second line tells you how `jsontr.py` categorised the text to translate. These
are wonky heuristics that you can use for filtering. You can already guess that
`achievements-name` should match all the name of achievements in the game.

The third line (and possibly following lines) indicate what the string is in
the original game, for each `--show-locales` language that you gave to `jsontr.py`

The fourth line expect your input, so let's input something !

```
> Kapittel 1 ble ferdigstilt
```

And `jsontr.py` will give you the next string, which is ... the description of
the achievements.  Let's translate it for now.

```
database.json/achievements/story-01/description
tags: data-achievements achievements-description
de: Kapitel 1 abgeschlossen.
> Ferdig kjedelig kapittel 1
database.json/achievements/story-02/name
tags: data-achievements achievements-name
de: Kapitel 2 vollständig
>
```

Now, i said that `jsontr.py` uses a readline interface, right ? If you don't know
what a `readline` interface is, it is the one used by `bash` and many other programs.

This means, that instead of repeating `Ferdig kjedelig kapittel 1`, you can 
use the previous translation, simply by pressing the UP key twice
then editing the line with left and right to change the `1` into a `2`.

You can continue for a while, and when you get bored, you can exit
this program in multiple ways :

- Press Ctrl+C
- or Ctrl+D (on Unix-like systems at least)
- or type ':q' as a translation.

Note that `jsontr.py` always save when you exit it normally.

And there, your file is saved. And you can continue doing something else.

Filtering what to translate
===========================

TODO explain `--filter-tags --filter-dict-path --filter-file-path`

Creating a mod with your translations
=====================================

TODO create a mod with a big packfile only, like (untested)

```
(() => {
        var packfile = document.currentScript.src.slice(0, -"mod.js".length);
        packfile += 'jaevla-ja.json';
        window.localizeMe.add_locale("no_NO", {
                from_locale:"de_DE",
                map_file: () => () => packfile,
                language: {
                        en_US: "Norvegian",
                        nl_NL: "Norsk",
                },
        });
})();
```

```
{
        "name":"Norvegian",
        "description": "something something",
        "postload": "mod.js",
        "version": "0.1.0",
        "dependencies": {
                "Localize Me": ">=0.3 <1"
        }
}
```

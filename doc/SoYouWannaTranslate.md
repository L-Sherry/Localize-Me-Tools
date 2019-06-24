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
That, and a working terminal interpreter.  Most OS comes with one nowadays.
Because yes, these are terminal applications and i expect you to be comfortable
with your OS's terminal.

If you are on Linux, this is probably already installed, or readily
available from your favorite package manager.

If you are on OS X, sorry, but the integrated Python version is something like
2.6 and is too old. You will need to install Python 3 yourself, possibly via
one of the numerous package manager for Mac OS X.

If you are on Windows, things will be a lot more complicated, and since i don't
use this OS, you will be a bit on your own.
Basically, if you just go to Python.org and download the latest version, then
this script will work, but the integrated 'readline' will not be available,
marking things harder for you.
If you want this 'readline' thing, you will probably need one of the many
solution to run Linux-like programs on windows.  Possibly Microsoft's Linux
Subsystem for Windows may work.
That, or switch to Linux.  That should work too.

Let's configure it
==================

We will only use jsontr.py for now.  Put the content of this repository
somewhere and run jsontr.py from the command line.

jsontr.py is basically a tool scans every files in your game directory for
stuff to translate, then will show it to you and ask you to translate it,
saving the result.

If you run it without any parameters, it will greet you with its usage
string ...

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

Running it with `--help` will display even more help text.
There are many options that you will have to set to start:

`--gamedir /path/to/crosscode/game/something/something/assets`

tells jsontr.py where to find the game files. It should point either to the
directory containing the `assets/` directory, or be the `assets/` directory
itself.  It may even be a subdirectory of the `assets/` directory.

`--from-locale en_US`

indicates from which language you will primarily translate the game.
The default is to translate from english (`en_US` in UNIX locale parlance) but
you may translate from any language part of the game, which are as of now
`en_US`, `de_DE`, `zh_CN`, `ja_JP` and `ko_KR`.  There are also some `fr_FR`
already in the game files, but I can guarantee you that they contain barely
any french text[1].

You will need to choose it now, because this will influence the file format
that `jsontr.py` uses (it is easily-editable json under the hood, if you want
to know).
So choose wisely.  This language will be used for e.g. detecting when texts
have changed when a new game version is released and some other things.

`--show-locales de_DE ko_KR`

Indicate which translation you want to see when translating a string.  While
`--from-locale` influence the file format, this one doesn't so you may change
it anytime.
You may specify one or multiple languages. I recommend that you show every language you are proficient with.
While the `en_US` and `de_DE` are made by the original game developers,
the others are already translated.
Still, each language comes with its nuances and may help understanding what you
are translating.
If you do not specify this option, then only the language selected by
`--from-locale` will be used.

`--pack-file my_translation.json`

This is the file that will contain all your translations.
`jsontr.py` will create it on the first run and automatically save it on exit.

The other options are not that important right now.
You will discover some of them later.

Now these are quite the options and it would be tedious to repeat them.
Fortunately, `jsontr.py` can save them in a configuration file and read them.
By default, it loads the options from the file `config.json` in the current
directory.

Last but not least, `jsontr.py` uses subcommands, like `git`.
There are only two subcommands that you need right now :
The first, you will use it right away, is called `saveconfig` and it does what
you may have guessed: it will save the options from the command line in
`config.json`.
So let's do it !

```
./jsontr.py --gamedir ~/Kazaa/CrossCode-0.9.10-checked-by-w4rl0rd/game/assets \
            --from-locale de_DE --show-locales de_DE \
	    --pack-file jaevla-ja.json saveconfig
```

Now you should have a `config.json` in your current directory.

Let's start !
=============

The second subcommand of `jsontr.py` that you will use a lot is very badly
named `continue`.

Let's use it right away !

```
./jsontr.py continue
```

Now, `jsontr.py` will start scanning the game directory, and will have quickly
found the first thing it could that requires a translation. It will probably be
the most uninteresting thing to translate in the world, but if you want a 100%
translation, you will require it anyway.

Probably, it will have picked the names of the achievements in the game.
It will present it to you as follow:

```
database.json/achievements/story-01/name
tags: data-achievements achievements-name
de: Kapitel 1 vollständig
> 
```

The first line indicate where it found the string. Right now, it's in the file
under `assets/data/database.json`, which, if you load it as JSON into the `x`
variable, is found in `x["achievements"]["story-01"]["name"]` (using the syntax
of most programming languages anyway)

The second line tells you how `jsontr.py` categorised the text to translate.
These are wonky heuristics that you can use for filtering. You can already
guess that `achievements-name` should match all the name of achievements in the
game.

The third line (and possibly more) indicate what the string is in the original
game, for each `--show-locales` language that you gave to `jsontr.py`.

The last line expect your input, so let's input something !

```
> Kapittel 1 ble ferdigstilt
```

And `jsontr.py` will give you the next string, which is ... the description of
said achievement.  Let's translate it for now.

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

Now, i said that `jsontr.py` uses a readline interface, right ? If you don't
know what a `readline` interface is, it is the one used by `bash` and many
other programs.
OK, if you don't know what bash it, i cannot explain it to you.

This means, that instead of repeating `Kapittel 2 ble ferdigstilt`, you can 
use the previous translation, simply by pressing the UP key twice
then editing the line with left and right to change the `1` into a `2`.

The `readline` interface offers much more, but you will probably discover it
soon enough.

You can continue translating achievements for a while, and when you get bored,
you can exit this program in multiple ways :

- Press Ctrl+C
- or Ctrl+D (on Unix-like systems at least)
- or type ':q' as a translation.

Note that `jsontr.py` always save when you exit it normally. That does not
mean it isn't a good idea to save often anyway. You can do it by typing `:w`
instead of a translation.

And there, you made your first translations. Now on something else.

Let's continue !
================

So maybe the idea of translating boring achievements didn't really appeal to
you ? Or maybe you're stuck because you need to translate enemies names
already ?

Thankfully, `jsontr.py` comes with some filtering options that can help you
select what to translate. You can either put them in the command line or in
the configuration file.

You should note that these filtering options filter directly what jsontr.py
is browsing from the game files. It won't be affected by what you have
already translated, and will not remove things from your translations.

Filtering by tags
-----------------

The first thing that you can filter are tags.  As said earlier, these are
quite hackingly implemented (see the source code for yourself, you'll
understand), but they work reasonably well most of the time.

Many of these tags are dirtily calculated, in a way that make them predictable
given how the game is organized, but still hacky nonetheless. Given how bad
this system work, it will probably be improved over time.

These is at least a tag that should work reasonably well, the 'conv' tag
for stuff that are said in conversations.

So, let's translate conversations !

```
./jsontr.py --filter-tags=conv continue
loaded jaevla-ja.json
     4 translations
     0 badly formulated/translated strings(bad)
     0 strings with translated parts missing(incomplete)
     0 strings of unchecked quality(unknown)
     4 uniques
database.json/commonEvents/quest-sergey-npc_comment/event/1/message
tags: data-commonEvents conv main.sergey worried
de: Scheint so, als hätten diese einfachen Quest-NPCs immer noch keine
ausgefeilteren Antworttexte bekommen.
>
```

Now you may have noticed that conversations have some more tags. Some of them
are pretty decorative, while others are more useful to know more that they are
to filter. You probably guessed that this `main.sergey` (whoever that is) said
that line with a `worried` face.

Oh and we still haven't left the `database.json` file.
Turns out this file is pretty big and contains many completely unrelated things.
What `jsontr.py` have stumbled upon are the "common events" of the game.
These are events that can appear in any or at least more that one area.
These includes things like the D-Link that you can trigged in the social menu,
your party members complaining that you're killing too much too fast, and even
some science facts.

THAT should be more fun than boring achievement names, right ?

Some readline features
----------------------

Now if you translated some more conversations in common events, you probably
noticed that there is this one character that probably love to always says the
same things all over again.

So you boldly translate it once, and the next time it appears ... you notice
that `jsontr.py` will have already pre-filled the input with your last
translation ! And that the only thing left for you to do is to press Return.

It turns out that `jsontr.py` saves every `(original text, your translation)`
(where original text is the value of `--from-locale`) in your pack file and
search it to know if you already translated something.

Now, `jsontr.py` only prefills the text, because in some languages, the same
original text must be translated differently depending on the context, the
gender/plural/opinion or many other contextual things that makes a language
both complicated to learn and beautiful at the same time.

Now if you translate things a little more, you will probably find some places
and game commands that are tedious to type, e.g.:

```
de: Bonjour! Ich bin gerade in \c[3]\v[area.autumn-area.name]\c[0] und genieße
die Landschaft.
```

If you are wondering what this `\c[3]\v[area.autumn-area.name]\c[0]`, then
sorry, this documentation is supposed to describe what `jsontr.py` does, not
how the game works.
For everything else related to the game, you can consult the comprehensive
documentation in the game's `assets/js` directory.
Let's just say for now that \c[x] changes the color of the game, and that
\v[area.autumn-area.name] actually tells the game to insert another string
here.  You will see later how you can translate this string more specifically.

For now, you just have to repeat it verbatim, and that would be a waste of your
precious fast typing skills to just repeat it.

Now, you may be wondering if your `bash` instincts of hitting the Tab key all
the time works here.
Turn out it does: Just typing `\` and hitting tab will complete with the rest
of what `jsontr.py` considers a word, so you will end up with the entire
`\c[3]\v[area.autumn-area.name]\c[0]` all at once !

`jsontr.py` will complete every words in the original text for the current
translation.  And since it's actually `readline` that handles it, hitting
tab more than once will gives you the multiple possibilities for completions,
just like `bash`.

filtering by file or dict path
------------------------------

Now what did I say about `\v[area.autumn-area.name]` ? That the game will
insert another string here ?

Actually, in `jsontr.py` parlance, this will be the string at
`database.json/areas/autumn-area/name`. `jsontr.py` currently call them
'file_dict_path' because they contain both the file path and the path of
the string under the JSON.

Now `jsontr.py` knows that there is two parts in there.
The first is `database.json` and the other is `areas/autumn-area/name`.
`jsontr.py` calls the first one the 'file_path' and the second one the
'dict_path'.
Note that if the file in question is under a directory, then 'file_path'
would be e.g. `maps/henne9001.json` of course.

Now, `jsontr.py` possess two other filtering options: `--filter-dict-path` and
`--filter-file-path` Now you may have already guessed whay they could do.

Yes, they filter strings to translate depending on which file they came from
or what dict_path under the file they have.  except they work by searching
in every component, so e.g. `--file-path database.json` will match any file
whose name is `database.json` or under a directory named `database.json`.

If you give them a space separated string of words, like
`--dict-path "areas name"`, then `jsontr.py` will propose you strings whose
dict_path have a component named `areas` and another named `name`, in any
order.

Creating a mod with your translations
=====================================

This file is supposed to describe `jsontr.py`, but seems like you want to
see your changes, and it's a good idea anyway, because while some lines may
look beautiful in your green-over-black hackerman terminal, they may look
terrible in the game and you already have an idea of what to change instead.

So while the real documentation about how to create a mod using Localize-Me
should not be here, let this serve as a quick example: Create your
mod directory under `assets/mods` and write down a `mod.js` file by looking
at this example for a `no_NO` translation (norvegian as spoken in Norway,
for those not versed in Unix locales):

```
(() => {
        var packfile = document.currentScript.src.slice(0, -"mod.js".length);
        packfile += 'jaevla-ja.json';
        window.localizeMe.add_locale("no_NO", {
                from_locale:"de_DE",
                map_file: () => () => packfile,
                language: {
                        en_US: "Norvegian",
                        no_NO: "Norsk",
                },
        });
})();
```

Now this is an example, probably the name of your pack file with your
translation is not `jaevla-ja.json`, and the `--from-locale` you picked may
not be `de_DE`.  The `language` field indicate what name will be displayed in
the language option in the settings menu.

You may not have noticed, but the various languages name are translated in
every other languages, so that if you run the game in english, the language
options will read `English`, `German` ...
while if you run it in german, it will read `Englisch`, `Deutsch` ... instead.

This is a very small thing from the developpers of the game, but it's a thing
nonetheless.
This mean that you can translate the name of your language in every language
supported by the game, or even in languages supported by other translations
mods.
However, you do not have to fill them all. By default, the string matching
the locale you are adding will be used, so here `Norsk` will be displayed
if you are running the game in japanese.

Now write this in a `package.json` to make the various mod loader happy:

```
{
        "name":"Norsk",
        "description": "CrossCode pa norks",
        "postload": "mod.js",
        "version": "0.1.0",
        "dependencies": {
                "Localize Me": ">=0.3 <1"
        }
}
```

Now this merely tells whatever mod loader you use that this mod is named
`Norsk`, that its description is `CrossCode pa norks` and that it depends on
some version of `Localize Me` and expect its `mod.js` to be loaded after the
game. There seems to be a specification in the CCDirectLink/CLS repository[2]
on what to put where.


Now you should be able to run the game, see that there is this `Norsk` entry
in the language choice without a flag (who likes flags anyway ?) select it,
restart the game and see that almost every text now begins with `--`.  These
are the texts that you didn't translate.

Now go see what you translated, and with a bit of luck, yes, they are here !

But maybe I should have told you to back up your saves first ? Oh ... Oops.

And with this this introduction ends. I'm outta here !


[1] You can check it for yourself using the `count` subcommand.  It simply
count the amount of strings that `jsontr.py` would have asked you to translate.
I leave the command to use as an exercise for the reader.

[2] Currently located at https://github.com/CCDirectLink/CLS/blob/master/proposals/1/standardized-mod-format.md

"""Chapter 17: Renaming and Keeping Your Files Safe."""


def build(s, R):
    s.chapter("17", "Renaming and Keeping Your Files Safe",
              "Renaming a character everywhere, undoing it, and what "
              "Chisel does so that it never damages a file it does not "
              "fully understand.")
    s.p("Your book is a folder of plain files (Chapter 1). That makes it "
        "easy to carry and easy to edit with other programs, and it "
        "means that Chisel has to be careful with files that something "
        "else wrote or touched. This chapter describes the one big "
        "editing tool that changes many files at once, //Rename "
        "everywhere//, and then the rules Chisel follows when a file has "
        "unfamiliar content.",
        idx=["safety", "files|safety"])

    # ------------------------------------------------------------------
    s.h2("Rename Everywhere", idx=["rename everywhere", "renaming a character",
                                   "character|rename"])
    s.p("Sometimes a character needs a new name: the editor suggested one "
        "that is less like another character's, or you changed your mind "
        "in chapter thirty. Changing it by hand means finding every "
        "scene, note and link that uses it. //Rename everywhere// does "
        "that for you, and it does it without any AI. It shows you "
        "every change before it makes one, and it can be undone.")
    s.proc("To rename a character in the desktop application:", [
        "Open the character's note. In the **Notes** tab of the "
        "assistant panel, click **Rename everywhere…**.",
        "Type the **New name**. Leave **Keep “old name” as an alias** "
        "ticked if your old name should still be recognized (it is "
        "ticked by default). If the note has aliases, each is shown in "
        "its own box; change a spelling there to rename that alias too. "
        "An alias you leave as it is stays as it is, so it keeps "
        "linking.",
        "Under **Look in**, choose where to search. **Scenes** is always "
        "on; **Other notes** is on; **Notebook notes** and **Comments** "
        "are off until you tick them.",
        "Press **Preview changes**. Nothing has been written yet.",
        "Read the preview. It is grouped by file; each occurrence shows "
        "the line number and the words around it, with the old text "
        "struck through and the new text beside it. Untick any that "
        "should stay as they are. Press **Apply** (it says how many "
        "changes in how many files).",
        "The last page says how many changes were made and how many "
        "scenes were rewritten. Press **Undo** on that page if you "
        "change your mind, or **Close**.",
    ])
    s.p("In the terminal application, open the note (or put the cursor on "
        "the name in a scene), press `ctrl+p` and choose **Entity · "
        "Rename everywhere…**. The form and the preview have the same "
        "choices. **Entity · Undo last rename** puts it back.")
    s.h3("What it changes", idx=["rename everywhere|what changes"])
    s.bullets([
        "**Mentions in prose**, as whole words, in the capitalization "
        "they were written in (a name at the start of a sentence keeps "
        "its capital). Possessives follow: //Elara's// becomes "
        "//Ela's//.",
        "**Explicit links**, `[[Elara]]`. The target is renamed, and so "
        "is the displayed text when it was the old name; other display "
        "text is kept.",
        "**POV and place** in scene details, when they name the "
        "character.",
        "**The note itself**: its name, its aliases and its file name, "
        "which is made from the new name.",
        "**Pictures** pinned to the note keep following it (Chapter 13), "
        "and comments stay attached to the same passages.",
    ])
    s.p("A longer name that contains the old one is left alone: "
        "renaming //Elara// does not touch //Elara Vance// when that is "
        "another note. A name that is also an ordinary word, such as "
        "//Will//, is the reason the preview exists: untick the ones that "
        "are not the character. Text inside a pending AI draft is "
        "listed but unticked, and the draft markers and saved originals "
        "are never touched.")
    s.h3("How it protects you", idx=["rename everywhere|safety", "before-rename"])
    s.bullets([
        "**Preview first.** Nothing is written until you press Apply.",
        "**It refuses if something changed.** If a file was edited after "
        "you made the preview, Apply stops before writing anything, and "
        "you make the preview again.",
        "**Snapshots.** Before any scene is rewritten, a snapshot named "
        "//before-rename// is taken (Chapter 8).",
        "**It is all or nothing.** If anything fails halfway, every file "
        "already written is put back.",
        "**Undo.** Scenes come back from their snapshots; the other "
        "files and the note come back from a small record kept in the "
        "project's hidden `.chisel` folder, which survives a restart. "
        "A file you edited after the rename is left alone and listed, so "
        "your newer work is never overwritten.",
    ])
    s.p("Rename everywhere is for characters, places, objects and "
        "factions alike; it works on any note under `entities/`.")

    # ------------------------------------------------------------------
    s.h2("Frontmatter That Chisel Does Not Know", idx=["frontmatter|extra keys",
                                                       "tags (Obsidian)"])
    s.p("Notes often carry more in their header than Chisel uses. If you "
        "also open your project in Obsidian, a note may have a `tags:` "
        "or `cssclass:` line. Chisel keeps every key it does not use "
        "exactly as you wrote it, whenever it saves a note. It reads and "
        "writes only `name`, `type`, `aliases`, and the optional `born` "
        "(Chapter 16). The same is true of scenes, whose details are "
        "described in Chapter 5.")
    s.code("""\
---
name: Dace Kuroda
type: character
aliases: [Kuroda]
tags: [police, night-shift]
cssclass: noir
---""")
    s.p("Here, `tags` and `cssclass` survive every save, every rename "
        "and every story-bible update.")

    # ------------------------------------------------------------------
    s.h2("Files That Are Not UTF-8", idx=["UTF-8", "encoding", "Latin-1",
                                          "Windows-1252"])
    s.p("Chisel reads and writes text as //UTF-8//, the encoding almost "
        "every modern program uses. A file written by an older program, "
        "or saved from Windows Notepad with an old setting, may use a "
        "different encoding (usually Windows-1252 or Latin-1). Such a "
        "file looks fine in the program that wrote it but contains bytes "
        "that are not valid UTF-8.")
    s.p("Chisel will //open// such a file, so that you can read it. It "
        "will //not save over it//: writing it back would silently "
        "change every accented letter and curly quote in it, and there "
        "would be no way to get the originals back. Instead, saving is "
        "refused and the program shows a message like this one:")
    s.code("""\
dace-kuroda.md is not valid UTF-8 (probably saved as Latin-1/Windows-1252);
convert it to UTF-8 before editing in the app""")
    s.attention("When you see this message, the file on disk has not "
                "been changed. Do not paste your edits elsewhere and "
                "hope: convert the file first, then make the edits.")
    s.proc("To convert a file to UTF-8:", [
        "Open the named file in an editor that lets you choose the "
        "encoding. In Windows Notepad, choose **File › Save As** and set "
        "**Encoding** to **UTF-8**. In Visual Studio Code, use "
        "**Reopen with Encoding** to pick the old encoding so the "
        "text looks right, then **Save with Encoding** and choose "
        "**UTF-8**.",
        "Check that the accented letters look right, and save.",
        "Open the file in Chisel again. It will now save normally.",
    ])
    s.p("On a command line, `iconv -f WINDOWS-1252 -t UTF-8 old.md > "
        "new.md` does the same.")
    s.p("This rule covers every file Chisel writes: scenes, notes, the "
        "project file and the dictionaries.")

    # ------------------------------------------------------------------
    s.h2("Other Protections", idx=["hardening", "safety|writes"])
    s.bullets([
        "**Titles with special characters.** A scene or part title with "
        "quotes, a colon or other characters that have a meaning in "
        "`project.toml` is written safely and does not break the "
        "project file.",
        "**Interrupted renames.** Renumbering scenes moves several "
        "files. If that is interrupted (a crash, a power cut), the "
        "change is rolled back, and any leftover temporary files with "
        "names starting `.mv` are tidied away when the project is next "
        "opened.",
        "**Names with accents and other alphabets.** A character named "
        "//Zoë// or //Ørjan// or in a non-Latin script gets a proper "
        "file name and is recognized in your prose, including with "
        "curly apostrophes.",
        "**Aliases cannot be stolen.** Adding an alias that already "
        "belongs to another note is refused, so one character cannot "
        "take over another's name.",
        "**Very long names** of titles, characters and notes are "
        "shortened for the file name instead of producing a file the "
        "system cannot open.",
    ])
    s.p("None of these ask anything of you; they are listed so that you "
        "know what to expect.")


GLOSSARY = [
    ("Rename everywhere", "The tool that renames a character, place or "
     "other note across scenes, links and other notes, with a preview, a "
     "snapshot of each scene and an undo."),
    ("UTF-8", "The text encoding Chisel reads and writes. A file in "
     "another encoding opens but is never overwritten."),
    ("frontmatter", "The block of settings between two lines of three "
     "hyphens at the top of a scene or note. Keys Chisel does not know "
     "are kept as written."),
]

MSG_TUI = {
    "info": [],
    "warn": [],
    "err": [
        ["//file// is not valid UTF-8 (probably saved as "
         "Latin-1/Windows-1252); convert it to UTF-8 before editing in "
         "the app",
         "A save was refused so that the file's bytes are not "
         "destroyed. Convert the file to UTF-8 (Chapter 17)."],
    ],
}

MSG_GUI = [
    ["//file// is not valid UTF-8 (probably saved as "
     "Latin-1/Windows-1252); convert it to UTF-8 before editing in the "
     "app",
     "The file opens for reading but will not be saved over."],
    ["Nothing in the text uses this name. Only the note itself will be "
     "renamed.",
     "The Rename everywhere preview found no occurrences."],
    ["Renamed to “//name//”: //n// changes, //m// scenes rewritten.",
     "Rename everywhere finished; Undo is on the same page."],
    ["Undone: the scenes and the note are back as they were.",
     "Undo worked. Files that changed since are listed as left alone."],
]

PROBLEMS = [
    ["Saving a scene or note says the file is not valid UTF-8.",
     "It was saved in another encoding. Convert it to UTF-8 in a text "
     "editor, then reopen it (Chapter 17)."],
    ["Rename everywhere will not apply.",
     "A file changed after the preview. Preview again."],
    ["Rename everywhere changed a word that is not my character.",
     "Press **Undo** on the last page, then preview again and untick "
     "the occurrences that should stay."],
]

PALETTE = []

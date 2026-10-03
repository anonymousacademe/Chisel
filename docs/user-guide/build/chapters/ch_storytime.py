"""Chapter 16: Story Time (optional dates for scenes, birth years for characters)."""


def build(s, R):
    s.chapter("16", "Story Time",
              "An optional way to say when a scene happens and when a "
              "character was born, so that Chisel can tell you how old "
              "someone is.")
    s.p("Most novels are told in the order they happen, and for those "
        "this chapter can be skipped. But some are not: a scene from "
        "twenty years ago, a chapter that jumps forward, a story told "
        "out of order. For these, Chisel lets you attach a //story time// "
        "to a scene and a //birth// to a character. It then works out "
        "ages for you.",
        idx=["story time", "timeline", "dates"])
    s.p("Story time is entirely optional and entirely yours.")
    s.bullets([
        "**Nothing is required.** If you set none, every feature uses the "
        "//reading order// of the book, and says so.",
        "**Nothing is guessed.** Chisel never works out a date from your "
        "prose.",
        "**The book is never reordered.** Story time does not change the "
        "order in which your scenes are read, exported or numbered.",
    ])

    # ------------------------------------------------------------------
    s.h2("Writing a Story Time", idx=["story time|format", "when (scene detail)"])
    s.p("A story time is a year, optionally followed by a month and a day, "
        "separated by hyphens.")
    s.table("t_when", "Story times", ["You write", "It means"], [
        ["2187", "The year 2187."],
        ["2187-03", "March of 2187."],
        ["2187-03-14", "The 14th of March, 2187."],
        ["-40", "A negative year. Negative years, zero and years past "
         "9999 are all fine."],
    ], [0.30, 0.70], mono_cols=(0,))
    s.p("The year is a plain number; Chisel does not need it to be a "
        "real calendar. Months run from 1 to 12 and days from 1 to 31 and "
        "nothing stricter, so an invented calendar works as long as you "
        "stay inside those limits. A story time with no month sorts before "
        "one with a month in the same year. If you give an era label "
        "(below), it is shown after the year, as in //2187 AE//.")
    s.p("A value that is not a story time, such as //spring//, is not "
        "thrown away: it stays in the file as you wrote it, and the "
        "desktop application flags it as //not a story time//.")

    # ------------------------------------------------------------------
    s.h2("Setting a Scene's Time", idx=["when|scene", "scene details|story time"])
    s.p("A scene's story time is one of its //details// (Chapter 5). In "
        "the desktop application, open the scene's details and fill in "
        "**Story time**, next to the POV, place and word target. A faint "
        "hint shows the value the scene inherits when the field is empty "
        "(//inherits 2187//), and a line under the form says which mode "
        "the book is in. In the terminal application, the details form has "
        "a **Story time** field with the formats listed.")
    s.p("In the file, it is a `when:` line in the scene's frontmatter "
        "(Appendix A):")
    s.code("""\
---
pov: Rook Tanaka
when: 2187-03-14
---
# Capsule 7-19""")
    s.p("Like the other details, `when` is not prose: it is not counted as "
        "words, not spell-checked, not a mention, and it is not part of "
        "the scene details line the AI is shown.")
    s.h3("A scene with no time inherits one", idx=["inheritance|story time"])
    s.p("You do not have to date every scene. A scene without a story "
        "time takes the story time of the nearest earlier scene in "
        "reading order that has one. Scenes before the first dated scene "
        "have none. A `when:` that is not a valid story time is flagged "
        "and does not start inheriting. Parked scenes (Chapter 5) have no "
        "story time and are never part of any of this.")

    # ------------------------------------------------------------------
    s.h2("Setting a Character's Birth", idx=["born (character)", "age"])
    s.p("A character note can have a `born:` line in its header, written "
        "in the same way as a story time.")
    s.code("""\
---
name: Rook Tanaka
type: character
born: 2161-06
---""")
    s.p("In the desktop application, open the character, go to the "
        "**Notes** tab of the assistant panel and fill in **Born** (the "
        "field shows //2187 or 2187-03-14// as a guide). When the open "
        "scene has a story time, the tab also shows a line such as "
        "//age 26 at 2187 (this scene)//.")
    s.p("An age is the number of whole years between the two dates. The "
        "month and day count only when both dates have them. Before the "
        "birth there is no age; Chisel says so rather than showing a "
        "negative number.")

    # ------------------------------------------------------------------
    s.h2("Reading Order or Story Time", idx=["reading order|story time",
                                            "mode (story time)"])
    s.p("Chisel decides, for the whole book, which of two modes it is in.")
    s.table("t_whenmodes", "The two modes",
            ["Mode", "When", "What the app says"], [
        ["Story time", "At least one scene of the book has a valid "
         "`when:`.", "//Using story time from N scenes.//"],
        ["Reading order", "No scene has one.",
         "//No story times set; using reading order.//"],
    ], [0.22, 0.40, 0.38])
    s.p("The sentence appears in the scene details. A feature that needs "
        "to ask what happened //before// a scene uses the mode: in story "
        "time mode it means scenes with an earlier story time (scenes with "
        "the same time count up to the scene itself, in reading order); in "
        "reading order mode it means the scenes before it in the book.")
    s.note("In this version, story time shows you ages and keeps your "
           "dates with your work. The AI features do not use it yet, and "
           "there is no timeline view; both are planned (Appendix D).")

    # ------------------------------------------------------------------
    s.h2("The Timeline Setting", idx=["timeline setting", "era", "project.toml|timeline"])
    s.p("A project may add an optional `[timeline]` section to "
        "`project.toml` (Appendix A):")
    s.code("""\
[timeline]
era = "AE"
unit = "year"
""")
    s.p("//era// is a label shown after years. //unit// is for later; "
        "year is the only unit for now. If you write something else by "
        "hand, Chisel reads it as the default, and the section can be "
        "left out entirely.")


GLOSSARY = [
    ("story time", "An optional year (with optional month and day) that you "
     "give a scene in its details. Never guessed, and never reorders the "
     "book."),
    ("reading order", "The order in which the book's scenes are read. "
     "Chisel falls back to it whenever no story times are set."),
    ("born", "The optional birth year (and month, day) in a character "
     "note's header, from which Chisel works out ages."),
]

MSG_TUI = {"info": [], "warn": [], "err": []}

MSG_GUI = [
    ["Using story time from //N// scenes.",
     "The scene details, when at least one scene has a story time."],
    ["No story times set; using reading order.",
     "The scene details, when no scene has one."],
    ["not a story time",
     "A `when:` or `born:` value is not a year, year-month or full date."],
]

PROBLEMS = [
    ["The age line does not appear.",
     "The character needs a `born:` and the open scene needs a story "
     "time, its own or an inherited one. Before the birth there is no "
     "age."],
    ["My `when:` is flagged.",
     "It must be a year, a year and month, or a full date, such as "
     "2187, 2187-03 or 2187-03-14. Anything else is kept but not used."],
]

PALETTE = []

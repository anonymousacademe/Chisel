"""Chapter 15: What the AI Sees (the About chip, What was sent, the context budget)."""


def build(s, R):
    s.chapter("15", "What the AI Sees",
              "Which parts of your project go to an AI service with each "
              "request, how you can tell, and what Chisel does when a "
              "request is too big.")
    s.p("Chapters 10 and 11 describe what the AI features do. This chapter "
        "is about the other half of the story: what each request //carries//. "
        "Every AI feature sends some of your words to the service you chose "
        "(OpenRouter) so that the model has something to work from. Chisel "
        "keeps three promises about that, and this chapter explains how you "
        "can check them.",
        idx=["AI|what is sent", "privacy|AI requests", "context"])
    s.bullets([
        "**You can see what was sent.** Every AI answer can show a //What "
        "was sent// report, listing each part of the request.",
        "**Nothing is cut silently.** If a note was left out, or "
        "shortened, to make a request fit, the report names it.",
        "**You choose the subject.** In the desktop application, the "
        "assistant is told about the item you have open, and a visible "
        "chip says so. You can remove it.",
    ])
    s.p("Your pictures are never part of a request (Chapter 13), and "
        "nothing is sent unless you press the button that asks for it.")

    # ------------------------------------------------------------------
    s.h2("The Open Item: the About Chip",
         idx=["About chip", "subject (assistant)", "assistant|open item"])
    s.p("In the desktop application the assistant, //Brainstorm// and "
        "//Describe this scene// know which item is open in the binder. "
        "That item is the //subject// of what you ask. Open a character "
        "and ask “What does she want?”, and the assistant is shown that "
        "character's note along with your question; you do not have to "
        "paste it or attach it.")
    s.p("What is sent as the subject depends on what is open.")
    s.table("t_about", "What the open item adds to a request",
            ["Open item", "What is sent with your question"], [
        ["A scene", "The scene, as it always was (Chapter 10): the text, "
         "the notes of the characters and places it mentions, and the "
         "scene's POV and place."],
        ["A character, place or object note", "The note's text (without "
         "its header block), labeled with its kind, for example //SUBJECT "
         "(character): Rook Tanaka//. At most 8,000 characters of it."],
        ["A notebook note", "Its text, labeled //SUBJECT (notebook "
         "note)//, at most 8,000 characters."],
        ["Nothing", "The project's titles and canon, as before."],
    ], [0.30, 0.70])
    s.p("Whenever a subject is being sent, the assistant's header shows a "
        "chip: **About: Rook Tanaka (character)**. The chip is the "
        "program telling you what it is doing, so it is always there when "
        "the note is sent and never there when it is not.")
    s.h3("Removing the chip", idx=["About chip|removing"])
    s.p("Click the small **x** on the chip. For the rest of that "
        "conversation the open item is //not// sent, and the question is "
        "about whatever else you attached or the scene context alone. A "
        "link, **Use the open item again**, takes the chip's place so that "
        "you can turn it back on. Starting a **New chat** resets this: the "
        "chip returns, following the item that is open.")
    s.note("The scope control under the question reads //Current scene//, "
           "//Project// or //Project + this note//, so you can see which "
           "kind of context the question has.")
    s.p("The terminal application's chat reads the open scene, or the "
        "project when none is open; it has no chip and no attachments.")

    # ------------------------------------------------------------------
    s.h2("What Was Sent", idx=["What was sent", "sent report"])
    s.p("A request to an AI service is built from parts: your question, "
        "the scene, the notes of the characters and places involved, your "
        "style guide, and so on. The //What was sent// report lists them. "
        "In the desktop application it appears as a small line you can "
        "open:")
    s.bullets([
        "under each reply in the assistant;",
        "in the review dialogs for new aliases and for story-bible "
        "updates;",
        "under the issues of a continuity check;",
        "behind a **What was sent** button on the notice that follows a "
        "draft, an expansion or a rewrite.",
    ])
    s.p("The line gives a short summary, such as //~3.2k tokens of 200k//. "
        "Open it and you see, for each part, its estimated size in "
        "//tokens//, and, if the part was a list of notes, how many of the "
        "available notes went (//4 of 9 sent//), with the names of the "
        "ones that did not. At the foot is the total against the model's "
        "//context window//, with a margin kept free for the reply.")
    s.p("A //token// is the unit AI services count in; a short English "
        "word is about one token. Chisel estimates a token as four "
        "characters, so the sizes are close but not exact; the line says "
        "so.", idx=["token"])
    s.p("When anything was left out or shortened, the report is shown in "
        "a warning style and the notice says so, so you do not have to "
        "open it to find out. The terminal application adds a one-line "
        "summary to the end of each AI notice, for example "
        "//sent ~3.2k tokens of 200k; 2 dropped//.")

    # ------------------------------------------------------------------
    s.h2("The Context Budget", idx=["context budget", "context window",
                                    "budget (AI)"])
    s.p("Every model has a //context window//: the most text it can read "
        "in one request. A short story fits any window. A long book, with "
        "a note for every character and place, does not: sent whole, the "
        "notes alone could be larger than the window, or could make every "
        "check slow and costly. So Chisel gives each request a size budget "
        "and builds it in a fixed order.")
    s.table("t_budget", "How a request is fitted",
            ["Kind of part", "What it includes", "When space is short"], [
        ["Always sent", "The scene, your question, your attachments and "
         "the About note.", "Never dropped. If these alone are too big, "
         "the request is refused (below)."],
        ["Sent if there is room", "The notes of characters and places, "
         "your style guide, voice samples, scene titles and research "
         "notes.", "Added best-first, one item at a time. The last item "
         "that fits may be shortened, at the end of a sentence or line, "
         "never in the middle of a word. The rest are dropped and "
         "listed by name."],
    ], [0.22, 0.40, 0.38])
    s.h3("Which notes are sent first", idx=["relevance", "notes sent|AI"])
    s.p("Continuity checks, story-bible updates and the alias finder look "
        "at the notes of the entities a scene is //about//. The notes go "
        "in this order: the entities named in the scene's prose; then the "
        "scene's POV and place (from its details, Chapter 5); then, only "
        "for a project with fewer than 40 characters and places, "
        "everyone else, if there is room. The effect is that a short "
        "book sends exactly what it always did, and a long one sends the "
        "notes that matter to the scene. The alias finder also needs the "
        "list of names that already exist, so that it does not propose "
        "them; that list is sent whole when it fits, and best-first when "
        "it does not. Drafting and chat have always sent only the "
        "entities the scene mentions.")
    s.h3("What it means when notes are dropped", idx=["notes dropped"])
    s.p("A dropped note was not seen by the model for that request. For "
        "a continuity check, this means a contradiction with that note "
        "cannot be found in this run. The report tells you which notes "
        "these were, so you can decide whether it matters. If it does:")
    s.bullets([
        "make sure the scene names the entity in its prose, or sets it as "
        "POV or place in the scene details, which raises its priority;",
        "shorten the style guide, a long note, or the number of "
        "attachments;",
        "choose a model with a larger context window in Settings (the "
        "model picker); or",
        "run the check again on a shorter scene or one scene at a time.",
    ])
    s.h3("Where the window comes from", idx=["context_window setting",
                                            "window size"])
    s.p("Chisel needs to know the window of the model you chose. It uses, "
        "in this order: the //context_window// setting if you have set "
        "one; otherwise the size listed in the catalog of models that the "
        "model picker downloaded (open **Choose…** in Settings once and "
        "Chisel remembers the sizes on your computer); otherwise a "
        "cautious 32,000 tokens. It always keeps 4,000 tokens free for the "
        "reply. It never goes to the network just to learn a size.")
    s.p("The //context_window// setting exists for models Chisel cannot "
        "look up, such as one you run yourself. It is a whole number of "
        "tokens, from 2,000 to 10,000,000, stored as `context_window` in "
        "`settings.json` in Chisel's state folder (Chapter 2). It is "
        "optional; remove the line to go back to automatic.")
    s.code("""\
{
  "context_window": 128000
}""")
    s.h3("A request that is too big", idx=["too large (request)"])
    s.p("If the parts that cannot be dropped are already larger than the "
        "window, nothing is sent and nothing is charged. A message says "
        "so, gives the sizes, names the largest parts, and says what to "
        "do: choose a model with a bigger window, shorten the scene, "
        "remove attachments, or turn off the About chip. If the window "
        "is the cautious default, the message says that too, and that "
        "opening the model list in Settings once will tell Chisel the "
        "real size.")

    # ------------------------------------------------------------------
    s.h2("Summary: What Leaves Your Computer", idx=["privacy|summary"])
    s.bullets([
        "Only what the //What was sent// report shows, and only after you "
        "press a button that uses the AI.",
        "Pictures and the files in `inspiration/` are never sent.",
        "The open item is sent only while the About chip is on.",
        "Without an API key, no AI feature runs and nothing is sent "
        "anywhere.",
    ])


GLOSSARY = [
    ("About chip", "The removable label in the desktop assistant's header "
     "(//About: Mara (character)//) that shows the open item is being sent "
     "with your question."),
    ("What was sent", "The report under an AI result that lists every part "
     "of the request with its estimated size, and names anything left out "
     "or shortened."),
    ("context window", "The most text a model can read in one request. "
     "Chisel fits each request inside it and says what it left out."),
    ("token", "The unit an AI service counts text in; Chisel estimates "
     "one token as four characters."),
    ("context budget", "The size limit Chisel gives each AI request: "
     "required parts first, optional notes best-first."),
]

MSG_TUI = {
    "info": [
        ["... - sent ~3.2k tokens of 200k; 2 dropped",
         "The end of an AI notice: the estimated size of the request "
         "against the model's window, and how many notes were left out."],
    ],
    "warn": [],
    "err": [
        ["This request is too large for the model's context window …",
         "Nothing was sent. Shorten the scene, remove attachments, or "
         "choose a model with a bigger window."],
    ],
}

MSG_GUI = [
    ["This request is too large for the model's context window …",
     "Nothing was sent and nothing was charged. The message names the "
     "largest parts and what to change."],
    ["… ~3.2k tokens of 200k; 2 dropped (What was sent)",
     "A notice after an AI result; the button opens the report that "
     "names what was left out."],
]

PROBLEMS = [
    ["The report says some notes were dropped.",
     "The request did not fit the model's window. Open //What was sent// "
     "to see which; name them in the scene, or choose a model with a "
     "bigger window (Chapter 15)."],
    ["The message says the window is assumed to be 32k.",
     "Chisel does not know your model's size yet. Open **Choose…** in "
     "Settings once, or set `context_window` (Chapter 15)."],
    ["The assistant answers about the wrong note.",
     "The About chip follows the open item. Remove the chip to stop "
     "sending it, or open the note you mean."],
]

PALETTE = []

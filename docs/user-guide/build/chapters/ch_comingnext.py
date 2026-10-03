"""Appendix D: What's Coming (planned features, clearly marked as not yet built)."""


def build(s, R):
    s.chapter("D", "What's Coming",
              "Features that are planned for Chisel and are not in this "
              "version.")
    s.attention("Everything in this appendix is //planned//. None of it "
                "exists in Version 0.5.0: there is no button, key, setting "
                "or file for it. The list is here so that you know what "
                "is intended, not as a promise of a date. Plans can "
                "change.")
    s.p("Each item is designed before it is built, and they are listed in "
        "the order they are expected to arrive.",
        idx=["planned features", "roadmap"])
    s.h2("Character Relationships")
    s.p("A section of a character's note for the people they are tied "
        "to (a sister, a rival, an employer), with the other side worked "
        "out for you, so that //Rook's sister// appears on the sister's "
        "note without your writing it twice. The AI would be able to "
        "suggest relationships from your prose and the continuity check "
        "would use them.")
    s.h2("Talk as a Character")
    s.p("A conversation with an AI playing one of your characters, "
        "limited to what that character could know at a point in the "
        "story you choose. It would never be shown scenes later than "
        "that point in story time (Chapter 16), and every answer would be "
        "labeled as an AI simulation, not as something you wrote.")
    s.h2("Local Models")
    s.p("The option to use an AI that runs on your own computer, through "
        "Ollama or another service with the same kind of interface, in "
        "place of OpenRouter. Your text would then not need to leave "
        "your machine for the AI features. The //context_window// "
        "setting (Chapter 15) is the first step towards it.")
    s.h2("Scene Summaries")
    s.p("A short summary of each scene, kept with the scene and "
        "refreshed on request, and a rolling summary of the story so far. "
        "They would let the AI features carry more of a long book in the "
        "same space (Chapter 15).")
    s.h2("A Timeline View")
    s.p("A view of the book's scenes laid out by story time (Chapter 16) "
        "rather than by reading order, for stories told out of order. It "
        "would only show; the book's order would still be the one you "
        "set.")


GLOSSARY = []

MSG_TUI = {"info": [], "warn": [], "err": []}

MSG_GUI = []

PROBLEMS = []

PALETTE = []

"""Chapter 12: Writing Aids (session stats, focus sprints, Brainstorm)."""


def build(s, R):
    s.chapter("12", "Writing Aids",
              "Numbers about your own writing, a timer to write against, and "
              "an AI that offers ideas when you are stuck.")
    s.p("This chapter covers three small helpers that sit beside the "
        "manuscript without touching it: //session stats//, which count the "
        "words you write and the days you write them; //focus sprints//, a "
        "countdown for writing against the clock; and //Brainstorm//, which "
        "asks the AI for a few ideas when a scene will not move. All three "
        "exist in both applications. None of them ever changes your prose "
        "on its own. Session stats and sprints work entirely on your "
        "computer; only Brainstorm uses the network.",
        idx=["writing aids", "session stats", "focus sprint", "Brainstorm"])

    # ------------------------------------------------------------------
    s.h2("Session Stats", idx=["session stats|what is counted", "stats"])
    s.p("Chisel keeps a quiet tally of your work: how many words you "
        "wrote today, how long you were actually typing, and how many days "
        "in a row you have met your daily goal. The numbers are for you. "
        "They are not part of the book.")
    s.h3("Where the Numbers Are Kept", idx=["stats|location"])
    s.p("Your numbers are stored in the //state folder//, never inside the "
        "project. A project folder holds the book; your daily word counts "
        "are personal data, so they live beside your other personal "
        "settings, in `~/.local/state/lorewrite/stats/`, in one small file "
        "for each project. Because the file is not in the project, it is "
        "not copied when you share, back up or commit the project "
        "(Appendix A lists every file).")
    s.h3("What Is Counted", idx=["stats|words counted", "net words"])
    s.p("Each day has these figures.")
    s.table("a_counted", "What a day of stats counts",
            ["Figure", "What it is"], [
        ["Words", "The //net// change in the words of your own prose, "
         "counted each time a scene is saved. Writing 600 words and "
         "cutting 200 makes +400. On a day of heavy cutting the figure "
         "can be negative."],
        ["AI words", "The words of an AI draft you //accepted// "
         "(Chapter 11), counted separately and never added to your own "
         "words. A draft you have not accepted is not counted anywhere."],
        ["Active minutes", "Time spent typing. Each keystroke adds the "
         "time since the one before it, but only if that gap was two "
         "minutes or less. Minutes of staring at the screen or making tea "
         "do not count."],
        ["Sessions", "A session starts with your first activity after "
         "30 idle minutes (or the first activity after starting "
         "Chisel). It is counted on the day it starts."],
    ], [0.22, 0.78])
    s.p("Only //scenes// count. Writing in a character note, the style "
        "guide, a research note or the dictionary does not add to your "
        "words. Pending AI drafts and the scene-details block at the top "
        "of a scene are not prose and are left out. Opening a scene counts "
        "nothing: Chisel notes how long the scene was when you opened "
        "it, and counts only the change from there. The same is true when "
        "a scene is reloaded from disk or restored from a snapshot "
        "(Chapter 8), and for the first save of a scene Chisel has "
        "never seen.")
    s.p("The word count follows the saves, not the keystrokes. Chisel "
        "autosaves as you type, so the figure is never far behind, but a "
        "sentence you typed a second ago may not be counted yet.")

    s.h3("The Daily Target and the Streak", idx=["daily target", "streak"])
    s.p("The //daily target// is the number of words you would like to "
        "write each day. It starts at 500. Set it to 0 to turn the target "
        "off. It is one setting for both applications and every project, "
        f"kept in your user settings ({R('a_target')}).")
    s.table("a_target", "Setting the daily target",
            ["", "Terminal application", "Desktop application"], [
        ["Where", "Settings, the //Writing goals// heading.",
         "Settings dialog, the //Writing goals// section "
         f"({R('g_goals')})."],
        ["Field", "`Daily word target (0 = off):`", "`Daily word target`, "
         "with the hint “words; 0 turns the target off. Your streak counts "
         "the days you met it.”"],
        ["Save", "The **Save** button.", "The **Save** button "
         "(**Cancel** discards)."],
        ["A bad value", "A warning: //The daily target must be a number "
         "from 0 to 100,000//.", "An error: //The daily target must be a "
         "whole number from 0 to 100,000.//"],
    ], [0.14, 0.43, 0.43])
    s.gfigure("g_goals", "g_goals", "The //Writing goals// section of "
              "Settings in the desktop application, with the daily word "
              "target", width=300)
    s.p("The //streak// is the number of days in a row on which you met "
        "the target. A day meets it when its words are at least the "
        "target; with the target off, a day meets it with a single word. "
        "A day on which you cut more than you wrote never meets it. "
        "Chisel counts backward from today. If you have not yet met the "
        "target //today//, it starts counting at yesterday, so your streak "
        "is not broken until the day is actually over.")
    s.note("The streak rule uses the target as it is //now//. If you raise "
           "the target from 500 to 1,000, old days are measured against the "
           "new figure, and a streak you had may shrink.")

    s.h3("The Status Bar", idx=["status bar|stats", "words today"])
    s.p("The status bar, along the bottom of both applications, carries "
        "the live figures. Each application shows the ones below "
        f"({R('a_statusbar')}).")
    s.table("a_statusbar", "Stats and sprint items in the status bar",
            ["Item", "Terminal application", "Desktop application"], [
        ["Words today", "`+120 / 500 today`. With the target off: "
         "`+120 today`.", "A button, `+120 / 500 words today`. Off: "
         "`+120 words today`. It changes color when today's target is "
         "met. Click it to open Session stats."],
        ["Streak", "`streak 3`, shown only when the streak is above zero.",
         "A button, `Streak 3`, always shown. Its tooltip reads, for "
         "example, “3 days in a row at 500+ words,” or “No streak yet: "
         "write to the daily target to start one.” Click it to open "
         "Session stats."],
        ["Sprint", "`SPRINT 24:05 (+120)`, only while a sprint runs.",
         "A **Sprint** button when idle; `24:05 · +120` while one runs."],
        ["Draft", "`Draft N` at the left of "
         "the line.", "`Draft N` at the left of the footer."],
    ], [0.14, 0.43, 0.43])
    s.p("The terminal status bar is one line of items separated by "
        "`|`; "
        f"{R('fig_statusbar')} shows the part that matters here. “Words "
        "today” counts across all your sessions that day, not merely "
        "since you opened the project, and accepted AI drafts are not in "
        "it. In the desktop application the right part of the bar looks "
        f"like {R('g_sprint_bar')}.")
    s.figure("fig_statusbar", "tui_statusbar", "The bottom of the terminal "
             "window: the draft word count, a running sprint countdown, "
             "words today against the target, and the streak")
    s.gfigure("g_sprint_bar", "g_sprint_bar", "The right part of the "
              "desktop status bar while a sprint runs, with the words-today "
              "and streak buttons", width=418)

    s.h3("The Session Stats Page", idx=["Session stats|page", "sparkline"])
    s.p("The Session stats page gathers everything in one place. In the "
        "terminal application press `ctrl+p` and choose "
        "`Action · Session stats`; there is no key for it. In the desktop "
        "application, click **Words today** or **Streak** in the status "
        "bar, or choose **Session stats** on the notice that appears when "
        "a sprint ends. There is no menu item for it.")
    s.p(f"The terminal page ({R('fig_stats')}) is a window titled "
        "//Session stats//, closed with `esc` or `enter`. It is plain text "
        "with a //sparkline//, a row of small bars, one character for each "
        "of the last 30 days, scaled to your best day.")
    s.figure("fig_stats", "tui_stats", "The Session stats window in the "
             "terminal application, with the 30-day sparkline")
    s.p(f"The desktop dialog ({R('g_stats')}) is the same information as "
        "tiles with a bar chart beneath them. It is read-only; the "
        "**Close** button dismisses it. Days that met the target are "
        "highlighted in the chart, and pointing at a bar names its day "
        "and count.")
    s.gfigure("g_stats", "g_stats", "The Session stats dialog in the "
              "desktop application: tiles for today, this session, streak, "
              "best day, per session and project, and the 30-day chart",
              width=330)
    s.table("a_statsrows", "What the Session stats page shows",
            ["Item", "Meaning"], [
        ["Today", "Net words, active minutes and sessions today, with "
         "“of 500” when a target is on, and the accepted AI words if there "
         "were any."],
        ["This session", "Words and active minutes since Chisel "
         "started, or since the last gap of 30 idle minutes."],
        ["Streak", "Days in a row, and whether today is already met. The "
         "desktop tile says “500+ words a day” (or “any day with a "
         "word” when the target is off) and adds “today is done.”"],
        ["Best day", "Your highest day and its date, or “none yet.”"],
        ["Per session", "Average words per session: the words of all "
         "your positive days divided by all recorded sessions."],
        ["Project", "The words now in the book (front matter and "
         "Parked scenes are not counted), and how many of them were "
         "written with Chisel."],
        ["Last 30 days", "The sparkline or chart. Days with no writing, "
         "or a negative total, show as the lowest bar."],
        ["Sprints today", "Each focus sprint of the day, with its words. "
         "A sprint ended early is marked //(stopped)// in the terminal "
         "and //(stopped early)// on the desktop."],
    ], [0.22, 0.78])

    s.h3("What the File Looks Like", idx=["stats|file format"])
    s.p("Each project's stats are one JSON file named for the project. "
        "The name is made from the project's folder path (the first 16 "
        "characters of a hash of it), so you will not recognize it. One "
        "day looks like this.")
    s.code("""\
{"version": 1, "project": "/home/ana/novels/residual",
 "days": {"2026-10-01": {
   "words": 420, "ai_words": 60, "seconds": 3100, "sessions": 2,
   "sprints": [{"at": "2026-10-01T09:30:00", "minutes": 25,
                "elapsed": 1500, "words": 310, "completed": true}]}}}
""")
    s.p("`seconds` is the active time (the page shows it in minutes). In a "
        "sprint, `minutes` is the length you chose, `elapsed` the seconds "
        "it actually ran, and `completed` is false for a sprint you "
        "stopped. The file is written safely: Chisel writes a temporary "
        "copy and then swaps it in, so a crash cannot leave half a file. "
        "If both applications are open on the same project they each add "
        "their own figures to the file, so neither overwrites the other.")
    s.attention("Your stats belong to the project's //path//. If you "
                "rename the project folder or move it, Chisel starts a "
                "fresh stats file for the new path. The old file is not "
                "lost, but it is no longer linked; there is no tool to "
                "merge them.")

    # ------------------------------------------------------------------
    s.h2("Focus Sprints", idx=["focus sprint", "sprint|timed writing"])
    s.p("A //focus sprint// is a timed stretch of writing: you choose 15, "
        "25 or 45 minutes (or your own length), a countdown appears in "
        "the status bar, and when time is up Chisel tells you how many "
        "words you wrote. There is no sound and nothing is sent anywhere; "
        "the end is a quiet notice.")
    s.p("The words in a sprint are the net words of your own prose saved "
        "since the sprint began. Accepted AI drafts are not included. "
        "Typing that has not been saved counts once it is saved, which "
        "autosave does for you; when the sprint ends, Chisel saves "
        "first, then counts. A sprint may be anything from 1 to 240 "
        "minutes, and only one can run at a time.")
    s.table("a_sprinttasks", "Running a focus sprint",
            ["Task", "Terminal application", "Desktop application"], [
        ["Start", "`ctrl+p`, then `Action · Focus sprint`. Choose "
         "**15 minutes**, **25 minutes**, **45 minutes** or "
         "**Custom length…**.", "Click **Sprint** in the status bar. "
         "Choose **15 min**, **25 min**, **45 min** or **Custom**; the "
         "default is 25. Click **Start sprint**."],
        ["Custom length", "Type the minutes in the prompt //Sprint length "
         "in minutes (1-240):// (it offers 30). Anything but a whole "
         "number gives //A sprint length is a whole number of minutes//.",
         "Type a number in the field that appears (it offers 30). "
         "**Start sprint** stays dimmed until the number is a whole "
         "number from 1 to 240. `enter` starts."],
        ["Hide the screen", "A second choice, **Start in writer mode "
         "(hides everything but the editor)**, or **Start, keep the "
         "screen as it is**.", "The check box **Hide everything but the "
         "page while it runs (focus mode, F11)**. The dialog remembers "
         "your choice."],
        ["Watch the clock", "`SPRINT 24:05 (+120)` in the status bar, "
         "counting down each second, with the sprint's words so far.",
         "`24:05 · +120` on the status-bar button, in the accent color. "
         "If you reload the window the countdown resumes."],
        ["Stop early", "Run `Action · Focus sprint` again. The choice "
         "is titled //Sprint running: 12:30 left//; choose "
         "**Stop the sprint (keeps what you wrote)**, or **Keep going**.",
         "Click the running timer. Confirm **Stop sprint** in the "
         "dialog //Stop the sprint//; **Cancel** keeps it going."],
    ], [0.15, 0.425, 0.425])
    s.figure("fig_sprint", "tui_sprint", "The Focus sprint choice in the "
             "terminal application: how long?")
    s.gfigure("g_sprint", "g_sprint", "The Focus sprint dialog in the "
              "desktop application", width=300)
    s.p(f"{R('fig_sprint')} and {R('g_sprint')} show the first step in "
        "each application. In the terminal, writer mode and the focus "
        "mode of the desktop application (Chapter 4) are the same idea: "
        "everything but the text is hidden. If you chose it, Chisel "
        "turns it on for the sprint and turns it off again at the end, "
        "but only if the sprint was what turned it on. If you were "
        "already in writer or focus mode, it stays on.")
    s.h3("When a Sprint Ends", idx=["sprint|end notice"])
    s.p("When time is up the notice tells you the length and the words, "
        "and, in the terminal application, your total for the day. The "
        "notice stays for 12 seconds in the terminal. On the desktop it "
        f"has an action button, **Session stats** ({R('g_sprint_toast')}).")
    s.gfigure("g_sprint_toast", "g_sprint_toast", "The notice at the end "
              "of a sprint in the desktop application", width=300)
    s.table("a_sprintmsgs", "The end-of-sprint notices",
            ["Application", "Finished", "Stopped early"], [
        ["Terminal", "`Sprint done: 25 minutes, +310 words (today +420)`",
         "`Sprint stopped: 25 minutes, +120 words (today +300)`"],
        ["Desktop", "`Sprint done: 25 minutes, +310 words.`",
         "`Sprint stopped: 12 minutes, +120 words.`"],
    ], [0.16, 0.42, 0.42], mono_cols=(1, 2))
    s.p("Word changes are written the same way everywhere in Chisel: "
        "//+310//, //\u22125// (with a true minus sign) and //\u00b10//, "
        "and thousands are separated, as in //+1,240//.")
    s.p("The terminal notice for a stopped sprint gives the length you "
        "//planned// (25 minutes), not the time it ran; the desktop "
        "notice, too, names the planned minutes. The record in your stats "
        "keeps both. A sprint always lands in the stats of the day it "
        "ended, with its words, whether you finished it or stopped it. A "
        "sprint that was stopped has `completed` set to false. If you "
        "quit Chisel while a sprint is running, the sprint is recorded "
        "as stopped; the exception is a sprint of less than a minute "
        "with no words, which is thrown away.")
    s.p("The Session stats page lists today's sprints. Earlier days' "
        "sprints are kept in the file but not shown.")

    # ------------------------------------------------------------------
    s.h2("Brainstorm: Ideas When You Are Stuck", idx=["Brainstorm|what it does", "ideas"])
    s.p("Brainstorm asks the AI for three to five ideas to get the scene "
        "moving. An idea is one or two concrete sentences, not prose: "
        "what if the letter is already opened; a small sensory detail "
        "that does not belong; a pressure point on a character; a loose "
        "thread from your own notes. You read them, throw away what "
        "does not fit, and, if one catches, either have the AI draft from "
        "it or save it to your notes. Brainstorm never writes into your "
        "scene by itself.")
    s.p("It uses the //writing// model chosen in Settings (Chapter 18) "
        "and needs your OpenRouter key (Chapter 10). Each request costs a "
        "small amount, which is added to the AI spend shown in the status "
        "bar and recorded under //brainstorm//.")
    s.h3("What It Sends", idx=["Brainstorm|what is sent", "privacy"])
    s.p("With a scene open, Brainstorm sends: your style guide in full; "
        "the scene text for about 500 words on each side of the cursor, "
        "with the cursor marked; the notes of the characters and places "
        "the scene mentions (at most 1,200 characters of each, 6,000 in "
        "all); and the scene's details block (point of view and so on). "
        "Pending AI drafts are removed first, because unaccepted AI text "
        "is not canon. Voice samples are not sent.")
    s.p("With no scene open (the terminal application with nothing "
        "open, or the desktop application with a note or the style guide "
        "open), it sends instead the style guide, the title of every "
        "scene in order, and the canon of every character and place, "
        "capped at 12,000 characters. The ideas are then about the book, "
        "not a scene.")
    s.h3("Using It in the Terminal Application", idx=["Brainstorm|terminal"])
    s.proc("To brainstorm:", [
        "Put the cursor in the scene where you are stuck.",
        "Press `ctrl+p` and choose `Action · Brainstorm`. A message says "
        "//Brainstorming…//.",
        f"When the ideas arrive, //Ideas ready// appears with the cost, and "
        f"a window opens ({R('fig_brainstorm')}), headed //Brainstorm - "
        "ideas to get unstuck//.",
        "Move through the numbered list and act on an idea with the keys "
        f"of {R('a_brkeys')}.",
    ])
    s.figure("fig_brainstorm", "tui_brainstorm", "The Brainstorm window in "
             "the terminal application, a numbered list of ideas with the "
             "keys at the bottom")
    s.table("a_brkeys", "Keys in the Brainstorm window",
            ["Key", "Action"], [
        ["enter, d", "**Draft from this.** Opens the writing prompt "
         "//What should the AI write here? (edit the idea if you like)// "
         "with the idea filled in. Change it if you want, then press "
         "`ctrl+g`. The result is an ordinary pending AI draft "
         "(Chapter 11) at the place the cursor was when you started "
         "Brainstorm. `esc` cancels. If no scene is open, or a different "
         "file now is, you see //Open the scene you want to draft into "
         "first//."],
        ["s", "**Save to notes.** Appends the idea to "
         "`research/assistant-notes.md` and says //Saved to "
         "research/assistant-notes.md//. The list reopens, so you can "
         "save several."],
        ["esc", "Close the window."],
    ], [0.14, 0.86], mono_cols=(0,))
    s.h3("Using It in the Desktop Application", idx=["Brainstorm|desktop"])
    s.p("Open the **Assistant** tab in the right-hand panel and click "
        "**Brainstorm** in the quick actions (its detail reads //Plot, "
        "character, image//). The chat shows your request, //Brainstorm: "
        "ideas to get unstuck.//, then the assistant's numbered list "
        f"({R('g_brainstorm')}). The button is dimmed while another AI "
        "request is running, and with no API key the panel says that AI "
        "features are off until you set one in Settings.")
    s.gfigure("g_brainstorm", "g_brainstorm", "Brainstorm ideas in the "
              "assistant panel, each with Draft from this and Save to "
              "notes buttons", width=215)
    s.table("a_brbuttons", "Buttons on Brainstorm ideas",
            ["Button", "What it does"], [
        ["Draft from this", "Opens the dialog //Draft from this idea//, "
         "with //What should the AI write? (edit the idea if you "
         "like)//. Click **Generate**. The result is a pending AI draft "
         "at the cursor, to accept with `F7` or reject with `F8`. With "
         "no scene open you get //Open a scene to draft into.//"],
        ["Save to notes", "Adds that idea to `research/assistant-notes.md` "
         "and shows //Idea saved to research/assistant-notes.md// with an "
         "**Open** button."],
        ["Regenerate", "Asks again and replaces the message."],
        ["Save all the ideas to notes", "Saves the whole list as one "
         "entry."],
        ["Copy", "Copies the message text."],
    ], [0.26, 0.74])
    s.p("A paperclip in the assistant lets you attach more material to "
        "send with the request, within a size limit. The terminal "
        "application has no attachments in Brainstorm. The conversation, "
        "ideas included, is saved with the project's assistant chats and "
        "is still there next time (Chapter 10).")
    s.h3("Saved Ideas", idx=["assistant-notes.md", "Brainstorm|saved ideas"])
    s.p("Saved ideas go into one research note, created if it is not "
        "there, with the newest last. Each idea gets a dated heading with "
        "the scene's title, and the prompt line repeats it.")
    s.code("""\
# Assistant notes

Answers saved from the assistant, newest last.

## 2026-10-01 - Brainstorm idea - Rain
**Prompt:** Brainstorm idea - Rain

The letter was opened before it reached her: the seal is a copy.
""")
    s.p("The note is a normal research note (Chapter 9): you can open it, "
        "edit it, or move it to the Trash. With no scene open the heading "
        "is just //Brainstorm idea//.")
    s.note("If the model returns something Chisel cannot read as a "
           "list, you see //the model returned no ideas// as a failure and "
           "nothing is shown. A reply with fewer than three ideas is "
           "still shown. A failed request says //Brainstorm failed: "
           "// followed by the reason in the terminal; the desktop "
           "application shows the reason as an error notice, and the chat "
           "says //That request failed. Nothing was changed.//")

    # ------------------------------------------------------------------
    s.h2("Limits Worth Knowing", idx=["stats|limits"])
    s.bullets([
        "**Stats move with the folder path.** Rename or move the project "
        "folder and the numbers start again, as described above.",
        "**No reset.** There is no way in either application to clear a "
        "project's stats. The file is plain text, and you may delete it "
        "from the state folder when Chisel is closed.",
        "**Sprint history is for today only.** Older sprints stay in the "
        "file but the pages show only the current day's.",
        "**Not synced.** Because the stats live outside the project, "
        "version control and file-sync tools that copy the project do not "
        "carry them to another computer.",
        "**Two applications, one file.** With both applications open on "
        "a project, each adds its own figures to the same file, and the "
        "page in either one shows the combined result.",
        "**Palette only in the terminal.** Session stats, Focus sprint "
        "and Brainstorm have no key of their own in the terminal "
        "application; use `ctrl+p`. The desktop application has no "
        "palette for them; use the status-bar buttons and the Assistant.",
    ])


GLOSSARY = [
    ("session stats", "The words, active time and streak that Chisel "
     "keeps for each project, in the state folder, not in the project."),
    ("daily target", "The number of words you aim to write each day, "
     "set in Settings; 500 by default, 0 to turn it off."),
    ("streak", "The number of days in a row on which you met your daily "
     "target, counted back from today."),
    ("net words", "Words added minus words cut. The daily figure of your "
     "own prose can be negative."),
    ("active minutes", "Time you were typing; a gap of more than two "
     "minutes between keystrokes is not counted."),
    ("session", "A stretch of work that ends with 30 idle minutes."),
    ("sparkline", "A row of small bars, one for each of the last 30 "
     "days, showing words per day in the terminal application."),
    ("focus sprint", "A timed stretch of writing with a countdown; the "
     "words written are recorded in the day's stats."),
    ("Brainstorm", "An AI request for three to five ideas to get "
     "unstuck, which can be drafted from or saved to notes."),
    ("assistant-notes.md", "The research note where saved Brainstorm "
     "ideas and other saved assistant answers are appended."),
]

MSG_TUI = {
    "info": [
        ["Sprint started: //N// minutes", "A focus sprint has begun."],
        ["Sprint done: //N// minutes, //+W// words (today //+T//)",
         "A sprint ran to the end."],
        ["Sprint stopped: //N// minutes, //+W// words (today //+T//)",
         "You stopped a sprint early; //N// is the planned length."],
        ["Brainstorming…", "The request is on its way."],
        ["Ideas ready", "Brainstorm's ideas have arrived."],
        ["Saved to research/assistant-notes.md",
         "An idea was added to the notes."],
    ],
    "warn": [
        ["The daily target must be a number from 0 to 100,000",
         "Fix the Daily word target field in Settings."],
        ["A sprint length is a whole number of minutes",
         "Enter whole minutes, from 1 to 240."],
        ["Open the scene you want to draft into first",
         "Draft from this needs the scene still open."],
    ],
    "err": [
        ["Brainstorm failed: //reason//",
         "The request failed; nothing was changed."],
        ["Could not save the idea: //reason//",
         "The notes file could not be written."],
    ],
}

MSG_GUI = [
    ["Sprint done: //N// minutes, //+W// words.",
     "A sprint ran to the end (button: Session stats)."],
    ["Sprint stopped: //N// minutes, //+W// words.",
     "You stopped a sprint early."],
    ["The daily target must be a whole number from 0 to 100,000.",
     "Fix the Daily word target field in Settings."],
    ["Open a scene to draft into.",
     "Draft from this needs an open scene."],
    ["Idea saved to research/assistant-notes.md",
     "An idea was added to the notes (button: Open)."],
    ["That request failed. Nothing was changed.",
     "Brainstorm or another AI request failed."],
    ["Wait for the current AI request to finish.",
     "Only one AI request runs at a time."],
]

PALETTE = [
    ["Session stats", "Show today, this session, streak, best day and the "
     "30-day sparkline.", ""],
    ["Focus sprint", "Start a 15, 25, 45 or custom-length timed sprint; "
     "while one runs, offers to stop it.", ""],
    ["Brainstorm", "Ask the AI for 3-5 ideas to get unstuck; draft from "
     "one or save it.", ""],
]

PROBLEMS = [
    ["My words today look too low.", "Words count when a scene is saved, "
     "and only the net change of your own prose in scenes. Accepted AI "
     "drafts, notes and the style guide are not counted."],
    ["The streak went back to zero.", "A day meets the target only if its "
     "words reach it; a day of net cutting does not. Raising the daily "
     "target in Settings also changes which old days count."],
    ["My stats vanished after I moved the project.", "Stats follow the "
     "folder path. A new path starts a new file in the state folder."],
    ["A sprint ended with 0 words.", "Only saved scene words count. Write "
     "in a scene, not a note, and check that the scene saves."],
    ["Brainstorm is dimmed or says AI is off.", "Set your OpenRouter key "
     "in Settings (Chapter 10); it is also dimmed while another AI "
     "request runs."],
    ["Brainstorm says it returned no ideas.", "Try again, or choose a "
     "different writing model in Settings (Chapter 18)."],
]

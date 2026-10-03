"""Chapter 13: Inspiration Images (AI pictures of a setting, kept as reference)."""


def build(s, R):
    s.chapter("13", "Inspiration Images",
              "A picture of the place you are writing about, to keep beside "
              "the page and never in it.")
    s.p("Sometimes a scene is easier to write when you can see where it "
        "happens. //Inspiration images// let you describe a setting (a "
        "dark subway platform, flickering lights) and get a picture of it "
        "from an AI image model. The picture is saved in your project and "
        "shown beside the scene as visual reference. It is the kind of "
        "thing a writer pins above the desk.",
        idx=["inspiration images", "pictures", "images|inspiration"])
    s.p("A picture can belong to a scene, a character, a place, an object "
        "or a note in your notebook, and you can add pictures of your own "
        "(a photograph, a sketch, a painting you found) as well as have "
        "them drawn. Both kinds are covered below.")
    s.p("Three rules hold for every part of this feature.")
    s.bullets([
        "**Reference only.** A picture is never inserted into a scene. It "
        "is not part of your prose, it is not counted as words, it is not "
        "spell-checked, it is not indexed for backlinks, and it is never "
        "sent to an AI.",
        "**Nothing is automatic.** An image costs real money (about $0.03), "
        "so you always start it yourself: first //Describe this scene//, "
        "if you want help with the wording, then //Generate//.",
        "**You stay in charge of the words.** The AI may write a first "
        "description, but you edit it before anything is drawn, and "
        "describing saves nothing.",
    ])
    s.p("The feature needs an OpenRouter API key (Chapter 10) and an "
        "//image model//, a model that can draw. The desktop application "
        "shows the pictures; the terminal cannot, so it saves them and "
        "opens them in your image viewer when you ask.")

    # ------------------------------------------------------------------
    s.h2("The Inspiration Tab", idx=["Inspiration tab", "assistant panel|Inspiration tab"])
    s.p("In the desktop application, the assistant panel on the right has "
        "four tabs: Assistant, Context, Notes and **Inspiration**. The "
        "Inspiration tab stays loaded when you switch away from it, so a "
        "description you were still writing is waiting when you come back. "
        f"{R('g_insp_tab')} shows the tab for a scene that has a pinned "
        "picture.")
    s.gfigure("g_insp_tab", "g_insp_tab",
              "The Inspiration tab of the assistant panel. The picture "
              "pinned to the open scene is shown large under //Pinned to// "
              "the scene's title; the other pictures of the scene sit in a "
              "grid below. The pinned picture here is a real example made "
              "with the default image model.", width=215)
    s.p("From top to bottom the tab holds a line saying that the pictures "
        "are reference only; the description box and its buttons; the "
        "picture or pictures pinned to the open scene; and a grid of the "
        "other pictures, with a **This scene** / **All** switch. Until you "
        "make a picture, the tab says “No pictures yet. Describe a place "
        "above and press Generate; the first one is saved in your project's "
        "inspiration folder.”")

    s.h3("Making a Picture", idx=["Describe this scene", "Generate (picture)", "image prompt"])
    s.proc("To make a picture in the desktop application:", [
        "Open a scene and put the cursor in the passage whose setting you "
        "want to picture. Open the **Inspiration** tab.",
        "Press **Describe this scene**. The AI reads the passage around "
        "your cursor and writes one paragraph describing what a camera "
        "would see: the place, the light, the time of day, the mood. It "
        "appears in the description box. (While it works, the button reads "
        "“Describing…”.) You can skip this step and type a description of "
        "your own.",
        "Edit the description. It is ordinary text: change the details, "
        "cut what you do not want, add what the AI missed. "
        f"{R('g_insp_prompt')} shows the area with a description ready.",
        "Leave **Pin to this scene** on if you want the picture to be "
        "shown with this scene (it is on by default, and unavailable when "
        "no scene is open).",
        "Press **Generate**, or press `Ctrl+Enter` in the description box. "
        "The note beside the button reminds you of the price: “about $0.03 "
        "per image”. Making the picture takes a few seconds, and the tab "
        "says so while you wait.",
        "The picture appears in the tab and is saved in the project. A "
        "message tells you where it went and what it cost, for example "
        "“Picture saved to inspiration/ (AI $0.0336).”",
    ])
    s.gfigure("g_insp_prompt", "g_insp_prompt",
              "The description area of the Inspiration tab. The box holds an "
              "editable description; below it are **Describe this scene** "
              "and **Generate**, the **Pin to this scene** checkbox and the "
              "cost note. The description here is a mock example.", width=215)
    s.p("**Describe this scene** is dimmed when no scene is open, and "
        "**Generate** is dimmed while the box is empty or another request is "
        "running. If you have not yet set an API key, pressing either "
        "button opens Settings instead.")
    s.note("A description works best as a place, not a plot. The AI that "
           "writes descriptions is told to describe a setting (architecture, "
           "objects, light, weather, palette, era), to leave out text, "
           "signs and logos, and not to name real people. Characters may "
           "appear only as unnamed figures, and only if the passage needs "
           "them in the frame.")

    s.h3("Where the Words Go: the Style Setting", idx=["image style", "style suffix|images"])
    s.p("Every picture request is the description you wrote followed by an "
        "//image style//, a short phrase that keeps the look consistent. "
        "The default is `cinematic, atmospheric, no text, no watermark`. "
        "You can change it, or empty it to send your description alone "
        "(see “Settings” below). The style is added only at the moment "
        "of sending. The description saved with the picture is your own "
        "text, without the style, so a style you change later applies the "
        "next time you generate or regenerate.")

    # ------------------------------------------------------------------
    s.h2("Pinned Pictures and the Gallery", idx=["pinned picture", "gallery"])
    s.p("A picture can be //pinned// to a scene. A pinned picture is shown "
        "large at the top of the Inspiration tab whenever that scene is "
        "open, and it follows you from scene to scene: open another scene "
        "and its pinned pictures take their place. A scene may have more "
        "than one pinned picture. A picture is pinned to one scene at a "
        "time: pinning it from a different scene moves the link.")
    s.p("Everything else is in the gallery grid. With a scene open, the "
        "**This scene** switch shows the pictures made for that scene and "
        "**All** shows every picture in the project. With no scene open "
        "(a note, say), the grid always shows all of them.")
    s.gfigure("g_insp_gallery", "g_insp_gallery",
              "The gallery of the Inspiration tab. Each card shows the "
              "picture and its name (or its description when it has no "
              "name), a pin mark on pinned ones, and an actions button "
              "(the three dots). The pictures in this figure are "
              "mock-generated stand-ins.", width=215)
    s.p("Each card has an actions button (three dots) opening a menu. "
        f"{R('g_insp_actions')} lists the entries; the same actions are "
        "buttons in the large view.")
    s.table("g_insp_actions", "Actions on a picture (desktop application)",
            ["Menu entry", "What it does"], [
        ["Open large", "Shows the picture in the large view (the "
         "lightbox). Clicking the picture does the same."],
        ["Pin to this scene / Unpin", "Pins the picture to the open scene, "
         "or removes the pin. Dimmed when no scene is open."],
        ["Regenerate (about $0.03)", "Makes another picture from the same "
         "description. See below."],
        ["Rename / notes…", "Opens the //Picture details// dialog."],
        ["Copy prompt", "Copies the description to the clipboard."],
        ["Reveal file", "Opens the folder that holds the picture in your "
         "file manager. This works only in the real application window; "
         "otherwise the message gives the file's path."],
        ["Move to Trash", "Moves the picture to the Trash after you "
         "confirm."],
    ], [0.34, 0.66])

    s.h3("The Large View", idx=["lightbox", "large view"])
    s.p("Click a picture, or choose **Open large**, to see it at full size "
        f"({R('g_insp_lightbox')}). Under the picture the large view shows "
        "the description, your notes if you have written any, and a line "
        "with the date, the image model, the cost and the scene it belongs "
        "to. Its buttons are **Pin to this scene** (or **Unpin**), "
        "**Regenerate**, **Copy prompt**, **Rename / notes…**, **Reveal "
        "file** and **Move to Trash**. Press `Esc`, click outside it, or "
        "use the close button to leave.")
    s.gfigure("g_insp_lightbox", "g_insp_lightbox",
              "The large view of a picture. The title and close button are "
              "at the top, then the picture, its description, a line of "
              "details, and the row of buttons. The picture is a real "
              "example made with the default image model.", width=380)

    s.h3("Regenerating", idx=["regenerate"])
    s.p("**Regenerate** sends the picture's saved description again and "
        "makes a //new// picture. Image models give a different result "
        "each time, so this is how you ask for “another one like it”. "
        "The old picture is not touched and stays in the gallery. The new "
        "picture belongs to the same scene but is not pinned; pin it "
        "yourself if you prefer it. Regenerating uses the image model and "
        "the image style as they are set now, and costs about $0.03 like "
        "any other picture.")

    s.h3("Names and Notes", idx=["picture notes", "picture name"])
    s.p("**Rename / notes…** opens the //Picture details// dialog with two "
        "fields. //Name// is shown instead of the description on the card "
        "and in the Trash (up to 120 characters). //Notes// is free text "
        "for yourself, such as what you like about the picture or what is "
        "wrong with it (up to 5,000 characters). Press **Save** to keep "
        "them or **Cancel** to leave them as they were.")

    s.h3("Deleting a Picture", idx=["Trash|pictures", "deleting|pictures"])
    s.p("**Move to Trash** asks first: “Move “//name//” to the Trash? You "
        "can restore it from the Trash later.” The picture and its notes "
        "go to the project Trash (Chapter 5) together. Nothing is lost "
        "until you delete it forever there.")
    s.p("In the Trash dialog a picture appears like a scene, but its line "
        "says //inspiration picture// where a scene's would say where it "
        "came from. **Restore** puts the picture and its notes back in the "
        "inspiration folder (under a free name if its own was taken in the "
        "meantime). A restored picture does not open as a document; it "
        "simply returns to the gallery. **Delete forever** and **Empty "
        "Trash** remove both files for good.")
    s.gfigure("g_insp_trash", "g_insp_trash",
              "The Trash dialog showing a deleted picture. Its line gives "
              "the picture's name or description, the words “inspiration "
              "picture”, and when it was deleted, with the **Restore** and "
              "**Delete forever** buttons.", width=330)

    # ------------------------------------------------------------------
    s.h2("Pictures for Any Item, and Your Own Pictures",
         idx=["pictures|any item", "upload|pictures", "Add picture",
              "uploaded pictures"])
    s.p("The Inspiration tab works for whatever is open in the binder: a "
        "scene, a character, a place or an object, or a note in your "
        "notebook. A picture made or pinned while a note is open belongs "
        "to that note and is shown with it, just as a scene's pictures are "
        "shown with the scene. The buttons follow what is open: **Describe "
        "this scene** becomes **Describe this note** for a note, and the "
        "description is written from the note's own text. Pin and Unpin "
        "say //this scene// or //this note// to match. The link is kept "
        "in the picture's sidecar (the `for` line in "
        f"{R('t_insp_fields')}), so a picture follows its item when you "
        "rename or move it.")
    s.h3("Adding Your Own Picture")
    s.p("To use a picture you already have, press **Add picture** in the "
        "Inspiration tab and choose one or more files, or drop the files "
        "onto the tab. The rules are these.")
    s.bullets([
        "**Formats.** JPG, PNG and WebP only. Chisel decides the format "
        "from the file's contents, not its name; a file whose name says "
        "one thing and whose contents say another is refused, and so are "
        "GIF, SVG and everything else.",
        "**Size.** At most 10 MB for each picture. An empty file is "
        "refused.",
        "**Where it goes.** A copy is saved in `inspiration/` with its "
        "sidecar, like any other picture, and linked to the open item. "
        "Your original is not touched, and the file's name becomes the "
        "picture's display name (the stored file is named by the date "
        "and time).",
        "**It is marked.** A picture you added carries an //uploaded// "
        "badge in the gallery. It has no description and no cost, so "
        "**Regenerate** is not offered for it.",
        "**It is never sent to an AI.** This is true of every picture in "
        "this chapter, drawn or added: the pictures are for your eyes "
        "only.",
    ])
    s.p("If a file cannot be added, a message names the file and says "
        "why (for example, that it is not a JPG, PNG or WebP picture, or "
        "that it is larger than 10 MB), and the other files you chose are "
        "still added.")

    # ------------------------------------------------------------------
    s.h2("Inspiration Images in the Terminal Application", idx=["inspiration images|terminal"])
    s.p("A terminal cannot show a picture well, so the terminal application "
        "does the work and leaves the looking to your own image viewer. "
        "The pictures are saved in the same `inspiration/` folder and are "
        "the same pictures the desktop application shows. Four entries in "
        "the command palette cover the feature; they are listed "
        f"in {R('t_insp_palette')}.")
    s.table("t_insp_palette", "Inspiration entries in the command palette",
            ["Palette entry", "What it does"], [
        ["Action · Inspiration image…", "Opens the prompt form: describe a "
         "setting (or have it written from the open scene) and save a "
         "picture of it."],
        ["Action · Inspiration images", "Lists the open scene's pictures "
         "(or all of them) so you can open, pin or trash one."],
        ["Action · Open last inspiration image", "Opens the newest picture "
         "(the open scene's newest, if it has any) in your image viewer."],
        ["Action · Open inspiration folder", "Opens the project's "
         "`inspiration/` folder in your file manager."],
    ], [0.38, 0.62])
    s.attention("Chisel starts your image viewer or file manager "
                "(through `xdg-open`) only when you choose **Open last "
                "inspiration image**, **Open inspiration folder** or open a "
                "picture from the list. A new picture is never opened "
                "automatically. If no viewer can be started, a message "
                "gives the path of the file so you can open it yourself.")

    s.h3("The Prompt Form", idx=["prompt form"])
    s.p("**Action · Inspiration image…** opens a window titled “Inspiration "
        "image - describe the setting” (" f"{R('tui_insp_prompt')}). It "
        "repeats the rule that the picture is reference only. A text box "
        "holds the description, and a checkbox, **Pin to the open scene** "
        "followed by the scene's title, decides whether the picture is "
        "pinned (it is on by default, and dimmed when no scene is open).")
    s.figure("tui_insp_prompt", "tui_insp_prompt",
             "The prompt form of the terminal application: the title, the "
             "reference-only line, the description box, the pin checkbox and "
             "the key hints at the bottom.")
    s.table("t_insp_keys", "Keys in the prompt form",
            ["Key", "What it does"], [
        ["`Ctrl+D`", "**Describe this scene.** Writes a description from "
         "the passage around your cursor in the open scene and returns "
         "you to the form with the text filled in. Needs an open scene."],
        ["`Ctrl+G`", "**Generate** (about $0.03). Sends the description "
         "and saves the picture. The box must not be empty."],
        ["`Esc`", "Close the form without doing anything."],
    ], [0.18, 0.82], mono_cols=())
    s.p("After **Ctrl+D** the form comes back with the AI's description in "
        "the box and a message: “Edit the description if you like, then "
        "ctrl+g to generate.” After **Ctrl+G** the form closes and a "
        "message says “Making the picture (about $0.03)…”. When the "
        "picture is saved a second message gives its path and what it "
        "cost: “Saved //path// (AI $0.0336). Action · Open "
        "last inspiration image shows it.” If the model returns no "
        "picture, the form opens again with your description in it, so "
        "nothing you typed is lost.")

    s.h3("The Picture List", idx=["picture list"])
    s.p("**Action · Inspiration images** opens a list titled “Inspiration "
        "images - pictures for //scene//” followed by the count "
        f"({R('tui_insp_list')}). Each row shows the picture's name or "
        "description and the date it was made; a pinned picture is marked "
        "with an asterisk and the word //pinned//. If the project has no "
        "pictures at all, you get a message instead of a list.")
    s.figure("tui_insp_list", "tui_insp_list",
             "The picture list of the terminal application, with one "
             "pinned picture marked by an asterisk. The key hints at the "
             "bottom show what each key does.")
    s.table("t_insp_list_keys", "Keys in the picture list",
            ["Key", "What it does"], [
        ["`Enter` or `O`", "Open the picture in your image viewer."],
        ["`P`", "Pin the picture to the open scene, or unpin it. Without "
         "an open scene, pinning is refused."],
        ["`T`", "Move the picture to the Trash, after a confirmation: "
         "“Move the picture ‘//name//’ to the Trash? You can restore it "
         "from Action · Open Trash.”"],
        ["`A`", "Switch between this scene's pictures and all pictures."],
        ["`Esc`", "Close the list."],
    ], [0.22, 0.78])
    s.p("The terminal application has no regenerate command and no name "
        "or notes editor for pictures. To make another picture from an "
        "old description, copy it from the desktop application or write "
        "it again in the prompt form; to name a picture or add notes, use "
        "the desktop application or edit its sidecar file (see “How "
        "Pictures Are Stored”). Restoring a picture from the Trash works "
        "in both applications (**Action · Open Trash**), and the terminal "
        "says “Restored the inspiration image”.")

    s.h2("Both Applications Side by Side", idx=["inspiration images|tasks"])
    s.table("t_insp_tasks", "Inspiration tasks in both applications",
            ["Task", "Terminal application", "Desktop application"], [
        ["Write a description from the scene",
         "`Ctrl+D` in the prompt form.",
         "**Describe this scene** in the Inspiration tab."],
        ["Make a picture", "`Ctrl+G` in the prompt form.",
         "**Generate**, or `Ctrl+Enter` in the description box."],
        ["See the pictures", "**Action · Inspiration images** lists "
         "them; open one in your viewer.",
         "The tab shows them; click one for the large view."],
        ["Pin or unpin", "`P` in the list; the checkbox in the form.",
         "The checkbox before generating; the menu or large view later."],
        ["Another picture from the same description",
         "Not available; use the form again.", "**Regenerate**."],
        ["Name a picture or add notes", "Not available.",
         "**Rename / notes…**"],
        ["Delete", "`T` in the list.", "**Move to Trash**."],
        ["Restore", "**Action · Open Trash**.", "**Restore** in the Trash "
         "dialog."],
    ], [0.24, 0.38, 0.38])

    # ------------------------------------------------------------------
    s.h2("Settings", idx=["settings|image model", "image model", "image style|setting"])
    s.p("Two settings control the feature. Both are among your user "
        "settings, so they apply to every project and to both "
        "applications (Chapter 18).")
    s.table("t_insp_settings", "The image settings",
            ["Setting", "Terminal application", "Desktop application"], [
        ["Image model",
         "The field “Image model (inspiration pictures, about $0.03 each):” "
         "and its **Choose…** button.",
         "The //Image model// field under //Models//, with the hint "
         "“Inspiration pictures; about $0.03 per image. Only models that "
         "draw.” and its **Choose…** button."],
        ["Image style",
         "The field “Image style (added to every picture description; "
         "empty = off):”.",
         "The //Image style// field, with the hint “added to every picture "
         "description; empty turns it off”."],
    ], [0.18, 0.41, 0.41])
    s.gfigure("g_insp_settings", "g_insp_settings",
              "The image rows of the desktop Settings dialog: the //Image "
              "model// field with its **Choose…** button, and the //Image "
              "style// field below the models.", width=300)
    s.figure("tui_settings_images", "tui_settings_images",
             "The terminal Settings screen scrolled to the image rows: the "
             "image model field with **Choose…**, and the image style "
             "field.")
    s.p("**The image model.** The default is `google/gemini-3.1-flash-lite-"
        "image`, the least expensive of the models tried; in testing it "
        "returned one picture in under four seconds for about $0.034. To use "
        "another, type its OpenRouter name in the field, or press "
        "**Choose…** to open a searchable list. The list shows only models "
        "that can output images, and for each one the price per image when "
        "OpenRouter publishes it. Leave the field empty to go back to the "
        "default. A project can override the model for itself with an "
        "`image_model` line in the `[ai]` section of its `project.toml`; "
        "when it does, the desktop Settings says so under the field.")
    s.p("**The image style.** Type the words you want added to every "
        "description, up to 300 characters. Leave the field empty to turn "
        "the style off and send your description alone. If your "
        "description already contains the style phrase, it is not added a "
        "second time.")

    # ------------------------------------------------------------------
    s.h2("Privacy and Cost", idx=["privacy|inspiration images", "cost|inspiration images", "OpenRouter|images"])
    s.p("Making a picture uses the network and your OpenRouter account. "
        "Two kinds of request exist, and they send different things.")
    s.table("t_insp_sent", "What each request sends",
            ["Request", "What is sent", "Model used"], [
        ["Describe this scene",
         "About 500 words either side of your cursor in the open scene "
         "(pending AI drafts removed), the notes of the places and "
         "characters that passage mentions, and the scene's details "
         "(point of view and place). Not your style guide.",
         "Your fast model."],
        ["Generate / Regenerate",
         "Only the description text, plus the image style. No scene text "
         "and no notes.", "Your image model."],
    ], [0.22, 0.56, 0.22])
    s.p("If you type your own description and never press **Describe this "
        "scene**, no part of your manuscript leaves your computer. If you "
        "do press it, the passage and notes described above go to the "
        "fast model through OpenRouter, and the text of that passage "
        "should be treated like any other text you send to an AI "
        "(Chapter 10). The picture itself is never sent anywhere.")
    s.p("Both requests are recorded in your AI spending total shown in the "
        "status bar (Chapter 10). Describing is cheap; a picture costs "
        "about $0.03 on the default model, and more or less on others. "
        "When the model reports the cost, it is saved with the picture and "
        "shown in the large view. If one request returns several pictures, "
        "the cost is divided among them and only the first is pinned.")

    # ------------------------------------------------------------------
    s.h2("How Pictures Are Stored", idx=["inspiration folder", "sidecar file|pictures", "files|inspiration"])
    s.p("Pictures are ordinary files in the `inspiration/` folder of your "
        "project, in the project itself and not in the hidden "
        "`.lorewrite/` folder. Each picture is two files with the same "
        "name: the image (`.jpg`, `.png` or `.webp`, whichever the model "
        "returned) and a Markdown //sidecar// file with the details. The "
        "name is the date and time followed by the first words of the "
        "description, for example "
        "`20261001-182821-a-claustrophobic-futuristic-capsule-hotel.jpg` "
        "and `20261001-182821-a-claustrophobic-futuristic-capsule-hotel.md`.")
    s.p("The sidecar begins with a small block of settings between lines "
        "of three dashes, as scenes and notes do. Anything below the block "
        "is your notes. This is the sidecar of the example picture shown "
        "in this chapter (its notes are empty).")
    s.code("""\
---
prompt: A claustrophobic, futuristic capsule hotel room, barely larger
  than a coffin, with fiberglass walls the color of weak tea. ...
model: google/gemini-3.1-flash-lite-image
for: manuscript/02-capsule-7-19.md
created: '2026-10-01T18:28:21'
cost: 0.033624
pinned: true
---
""")
    s.table("t_insp_fields", "The fields of a picture's sidecar",
            ["Field", "Meaning"], [
        ["prompt", "The description you generated from (without the "
         "style)."],
        ["model", "The image model that made it."],
        ["for", "The item it belongs to (a scene, a character, place or "
         "object note, or a notebook note), as a path inside the project. "
         "Optional. Sidecars written by an earlier version say `scene:`; "
         "they are still read and are rewritten as `for:` the next time "
         "the picture is saved."],
        ["created", "When it was made, in local time."],
        ["cost", "What the request cost in US dollars, if the model "
         "reported it."],
        ["pinned", "`true` when the picture is shown with its item. "
         "Needs a `for`."],
        ["title", "The name you gave it, if any."],
        ["source", "`upload` for a picture you added yourself. It has no "
         "prompt and no cost, and its model is `upload`."],
    ], [0.18, 0.82], mono_cols=(0,))
    s.p("The sidecar is plain text you may edit in any editor. Because "
        "the pictures are ordinary files, they are copied when you copy, "
        "back up or put the project under version control, and they are "
        "never rebuilt from anything: if you delete the file, the picture "
        "is gone (unless it is in the Trash). Appendix A lists the folder "
        "among the project's files.")
    s.p("If you rename or move a scene in the binder (Chapter 5), or "
        "rename a character everywhere (Chapter 17), the pictures that "
        "belong to it follow: their `for` line is rewritten for you. If "
        "you delete an item, its pictures stay where they are and are "
        "listed as //Unlinked// under **All**; restoring the item "
        "reconnects them.")

    # ------------------------------------------------------------------
    s.h2("Limits and Quirks", idx=["inspiration images|limits"])
    s.bullets([
        "**A key and the right kind of model are required.** With no "
        "OpenRouter key, the feature is off, and in the desktop "
        "application pressing either button opens Settings. The image "
        "model must be one that outputs images; an ordinary text model "
        "will return words and no picture.",
        "**A request can come back without a picture.** The model may "
        "refuse, or answer only in words. Chisel then shows “The model "
        "did not return an image.” followed by whatever the model said "
        "(up to 300 characters). The terminal application reopens the "
        "form with your description so you can change it and try again. "
        "You are charged whatever the provider charges, even for a "
        "request that gave no picture.",
        "**Only embedded pictures are kept.** Chisel saves pictures "
        "that arrive inside the reply. It never downloads a picture from a "
        "web address the model gives it. Kinds other than JPEG, PNG and "
        "WebP are skipped.",
        "**One AI request at a time.** While one request runs, a second "
        "waits: “Wait for the current request to finish.” in the desktop "
        "application.",
        "**Regeneration can differ a lot.** The new picture can look "
        "quite different from the first; that is why the first is kept.",
        "**The description limit.** A description is trimmed to 2,000 "
        "characters when sent.",
        "**No focus-mode picture.** Pictures are shown in the assistant "
        "panel only. They do not appear in focus mode or in the editor, "
        "and they are not part of an export (Chapter 14).",
        "**Sample pictures are examples.** The pictures in the figures of "
        "this chapter are either mock-generated stand-ins or, where a "
        "caption says so, a real example made with the default model. "
        "Your own results will differ.",
    ])
    s.attention("A picture's file name is its identity. If you rename or "
                "move picture files by hand, move the `.jpg` and its `.md` "
                "sidecar together and give them the same base name. A "
                "picture without its sidecar, or a sidecar without its "
                "picture, is not listed.")


GLOSSARY = [
    ("inspiration image",
     "A reference picture of a setting, made by an AI image model, saved "
     "in the project's inspiration folder and shown beside the writing. "
     "It is never part of the prose."),
    ("Inspiration tab",
     "The tab of the desktop assistant panel for describing, generating "
     "and browsing inspiration images."),
    ("image model",
     "An AI model that can output pictures. It is set in Settings; the "
     "default is google/gemini-3.1-flash-lite-image."),
    ("image style",
     "A short phrase added to every picture description when it is sent, "
     "to keep the look consistent. Empty turns it off."),
    ("pinned picture",
     "A picture linked to a scene so that it is shown large whenever that "
     "scene is open."),
    ("lightbox",
     "The large view of one picture, with its description, details and "
     "buttons."),
    ("Describe this scene",
     "The button (terminal: Ctrl+D in the prompt form) that has the fast "
     "model write a picture description from the passage around the "
     "cursor."),
    ("regenerate",
     "Make a new picture from a picture's saved description. The old "
     "picture is kept."),
    ("sidecar (picture)",
     "The Markdown file beside a picture that holds its description, "
     "model, scene, date, cost, pin and your notes."),
]

MSG_TUI = {
    "info": [
        ["Describing the scene…",
         "The fast model is writing a description."],
        ["Edit the description if you like, then ctrl+g to generate.",
         "The description is in the form; nothing has been drawn yet."],
        ["Making the picture (about $0.03)…",
         "The image request has started."],
        ["Saved //path// (AI $//cost//). Action · Open last inspiration "
         "image shows it.", "The picture is saved in the project."],
        ["No inspiration images yet (Action · Inspiration image… makes "
         "one)", "The project has no pictures."],
        ["Pinned to this scene / Unpinned", "A pin was changed in the list."],
        ["Moved to the Trash (Action · Open Trash restores it)",
         "The picture is in the Trash."],
        ["Restored the inspiration image",
         "A picture came back from the Trash."],
    ],
    "warn": [
        ["Open a scene to describe it",
         "Ctrl+D needs an open scene."],
        ["Describe the picture first (ctrl+d writes a description from "
         "the open scene)", "Ctrl+G with an empty box."],
        ["Open a scene to pin a picture to it", "Pinning needs a scene."],
        ["Could not start a viewer; the file is //path//",
         "No image viewer could be started; open the file yourself."],
        ["Could not start a file manager; the folder is //path//",
         "No file manager could be started."],
    ],
    "err": [
        ["Could not describe the scene: //reason//",
         "The description request failed; your text is kept."],
        ["No picture: //reason//",
         "The image request failed or returned no picture; the form "
         "reopens."],
        ["Could not save the picture: //reason//",
         "The picture arrived but could not be written."],
    ],
}

MSG_GUI = [
    ["Open a scene to describe it.", "Describe this scene needs an open "
     "scene."],
    ["Describe the picture first.", "Generate with an empty description."],
    ["Edit the description if you like, then press Generate.",
     "The description is in the box."],
    ["Picture saved to inspiration/ (AI //cost//).",
     "The picture is saved; the number is the spend."],
    ["Another picture saved (AI //cost//). The first is still there.",
     "Regenerate finished."],
    ["The model did not return an image: //what it said//",
     "The model answered in words or refused."],
    ["Wait for the current request to finish.",
     "One AI request runs at a time."],
    ["Add your OpenRouter API key first. AI features are off until then.",
     "No key is set; Settings opens."],
    ["Moved the picture to the Trash.", "The delete went through."],
    ["Prompt copied.", "The description is on the clipboard."],
    ["Opened the folder. / File: //path//",
     "Reveal file opened the folder, or gave the path when it could not."],
    ["Picture file missing", "A card's picture file is gone from "
     "inspiration/."],
]

PALETTE = []

PROBLEMS = [
    ["The Inspiration buttons open Settings.",
     "No API key is set. Add your OpenRouter key (Chapter 10)."],
    ["“The model did not return an image.”",
     "The image model refused or replied in words. Reword the "
     "description, or choose another image model in Settings."],
    ["I cannot find an image model in the Choose… list.",
     "The list shows only models that output images. Search by name, or "
     "type the model's OpenRouter name straight into the field."],
    ["Nothing opens when I choose Open last inspiration image.",
     "No viewer could be started. The message gives the file path; open "
     "it from your file manager."],
    ["A picture is missing from the gallery.",
     "It needs both its image file and its `.md` sidecar with the same "
     "name in `inspiration/`. Check the Trash too."],
    ["The pictures no longer show with my renumbered scene.",
     "After restoring a deleted scene under a new number, pin its "
     "pictures to it again."],
]

# LiveAI
voice and share screen chat with your web chatbot, free of tokens

## Run

For packaged Windows releases, use the China or Global installer from the
[releases page](https://github.com/ok-oldking/live-gpt/releases). China uses
[CNB](https://cnb.cool/ok-oldking/live-gpt-update) for app updates and Aliyun for
Python packages; Global uses
[GitHub](https://github.com/ok-oldking/live-gpt-update) and PyPI. The pyappify
launcher manages Python 3.12, dependencies, and app updates. Full installers
include the Python runtime and the default pet; optional voice models are
downloaded through LiveAI's settings. The online installer and portable
launcher download the runtime and dependencies during initial setup.

To run from source:

```powershell
.\.venv\Scripts\Activate.ps1
LiveAI
```

## Build Windows releases

The [Windows Release workflow](.github/workflows/build.yml) follows the
pyappify build used in `ok-wuthering-waves`. It validates the deployed app,
syncs the runtime files listed in `deploy.txt` to both update repositories,
then builds unsigned China and Global installers, an online installer, and a
portable launcher. The launcher profiles are configured in `pyappify.yml`.
Runtime dependencies, including transitive dependencies, are pinned in
`requirements.txt`; source updates run directly from `src`.

Configure these Actions secrets in the **live-gpt source repository**:

| Secret | Purpose |
| --- | --- |
| `CNB_USERNAME` | CNB Git HTTPS username with access to the update repository. |
| `CNB_TOKEN` | CNB token with permission to push branches and tags to `ok-oldking/live-gpt-update`. |
| `UPDATE_REPO_SECRET` | GitHub token with permission to push branches and tags to `ok-oldking/live-gpt-update`. |

Push a version tag such as `v0.1.0` to build and publish a release. Prerelease
tags such as `v0.1.0-beta.1` publish prereleases. You can also run the workflow
manually with an existing tag. Artifacts are uploaded to the workflow and to
the corresponding GitHub release. No code signing or signing credentials are
used. Launcher and installer icons come from `icons/`.

To validate the release package locally:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install ".[build]"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_packaging.py -v
```

After changing runtime dependencies in `pyproject.toml`, update the pinned
runtime dependencies in `requirements.txt` and rerun this validation.

## Using LiveAI

The app starts as a translucent, always-on-top overlay centered above the
bottom of the screen and also places an icon in the Windows system tray. Drag
any non-interactive area of the overlay to reposition it, or drag any border or corner to resize
it. The lock button beside **Configure** freezes both its position and size;
click it again to unlock. Screen pointer tracking keeps the overlay visible within a 5% margin on each
edge. Outside that boundary, everything except the pet becomes transparent,
including the input, subtitles, and dictation area. The overlay stays visible
while dragging or resizing. The **Auto-hide** button hides the overlay completely so clicks pass
through to the underlying app. In auto-hide mode it reappears for dictation,
incoming replies, and Read Aloud, then hides five seconds after playback ends.
If dictation produces text, the overlay stays visible so that text can be
reviewed or sent; enabling auto-hide does not hide unsent text or interrupt
dictation, response generation, playback, or an expanded subtitle. Text recorded with the UI microphone stays in the input until you explicitly
send it. Recording hotkeys automatically send successful dictation. English (ASCII)
voice input must contain at least two characters; non-English input can be sent
with one character. Leading and trailing whitespace is trimmed from dictation
and sent prompts. A one-character English voice result remains in the editor
for correction; manually typed one-character
messages are still allowed.
Click or double-click the tray icon, or choose **Show LiveAI** from its menu,
to reveal the overlay and turn auto-hide off. Its controls stay visible until
you move the pointer onto the overlay. Monitor, resolution, and display scaling
changes automatically move an offscreen overlay back into the usable screen
area; revealing it from the tray also checks its position. The **Exit**
button closes the app.

To capture the overlay in broadcast software, add a **Window capture** source
and select **LiveAI** (the executable may be listed as `python.exe`,
`pythonw.exe`, or `live-gpt.exe`). Keep the overlay shown and turn **Auto-hide**
off while streaming. The overlay uses a normal top-level window so broadcast
window lists can include it. A hidden owner keeps it out of the Windows taskbar;
use the system tray icon to reveal it.
If a capture method produces a blank image, try **Windows Graphics Capture**
if your broadcast software offers it. Transparency support depends on the
capture method and broadcast software.

Press and hold the microphone button to start ChatGPT's browser dictation
through Playwright. Releasing it clicks ChatGPT's **Done** control, waits for
the dictated text to appear in ChatGPT's composer, and copies that text into
the LiveAI input. If ChatGPT returns no words, the overlay leaves the finishing
state when the browser microphone is ready again. The transcription wait is
limited to 20 seconds. The ChatGPT tab owns microphone capture and speech
recognition, so the browser may ask for microphone permission the first time.
LiveAI does not record audio locally or download a speech-recognition model.
While the button is held, the input area is replaced by a waiting state until
ChatGPT's dictation-end control appears, followed by a listening state. Closing
the app cancels these browser waits promptly. Before a new session, LiveAI
cancels any stale browser dictation. A mouse dictation must remain held for at
least 0.5 seconds after it is pressed or it is cancelled. The global
hold hotkey waits 0.3 seconds before starting, so a quick tap has no effect.

The recognized text remains editable. Its paper-plane button sends the current
text through Playwright to the selected
ChatGPT tab, and its **X** button clears the editor. The app fills ChatGPT's
composer and clicks its send button, then clears the local text after ChatGPT
accepts it. The **X** button also clears the selected ChatGPT tab's composer.
These browser interactions run without intentionally bringing its window to
the foreground. A send initiated inside the overlay restores focus to the
previous app; a global-hotkey send leaves focus unchanged.

The screenshot selector lists one choice for each desktop display and then
visible windows ordered from largest to smallest. It restores the last selected
source when available and defaults to **Screenshot desktop** when no source was
saved or the saved source is unavailable. Window preferences match the executable,
window class, and title instead of a reusable Windows handle. Legacy handle-only
preferences need one manual reselection. A missing or ambiguous window never
selects another window automatically; a temporarily missing selection is restored
when it returns unless you choose a different source. A window is listed only when its area
is greater than one eighth of the display containing it. When sending with a
screenshot, LiveAI removes existing ChatGPT image attachments, captures the
chosen source, scales its longest edge down to 1920 pixels when necessary, and
uploads it as lossless WebP before clicking Send. Window capture uses the
BitBlt/PrintWindow approach with full-content rendering enabled.
Window screenshots include the visible mouse cursor by default. Turn off
**Configure → Screenshots → Capture mouse cursor in window screenshots** to
omit it. The setting is saved as `capture_cursor` and applies to manual sends
and recording screenshots. Desktop screenshots keep their existing behavior.
When a screenshot source is selected, the **With Screenshot** action remains
available even with an empty prompt. If the editor also contains text, a
paper-plane **No Screenshot** action appears so the prompt can be sent without
changing the selector. For dictated prompts, LiveAI
captures and pastes the selected screenshot into ChatGPT after the microphone
has remained pressed for 0.5 seconds. With browser dictation, it waits for the
image attachment to appear and begin uploading before clicking ChatGPT's
dictation microphone. The image can finish uploading while you speak; sending
still waits for upload completion. A cancelled short press uploads nothing.
Releasing while the browser is still preparing cancels startup and removes
the pending screenshot. Moving dictation controls (microphone, stop, and cancel)
are clicked only after they are visible, enabled, and no longer busy. If a
dictation operation fails, LiveAI cancels any remaining browser recording
and restores the original composer text when possible.
Starting another recording before the pending prompt is sent removes the
previously uploaded screenshot before preparing the new one.

The **Configure** button opens the application settings, organized into
Shortcuts, Screenshots, Language, Recording, Playing, and Pet pages in the left navigation.
**Language** offers **English** and **简体中文** (Simplified Chinese).
On first launch, or when `language` in `config.json` is missing or empty, the app
matches the operating system's display language to one of these options and
saves that choice. Chinese locales select Simplified Chinese; other languages
fall back to English. Changes apply immediately to the overlay, settings, and
tray menu and persist across restarts. Existing explicit language choices are
preserved. In `config.json`, `language` is `"en"` or `"zh"`; set it to `""` to
detect the system language again on the next launch.
Every valid change is saved immediately, so the styled title-bar close
button is the only dismissal control and there is no separate Save Changes step.
Recording independently chooses the browser or local Sherpa-ONNX, while
Playing independently chooses browser playback or an existing
[GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) installation with its
embedded Python runtime. Local controls stay hidden when browser playback is selected.
Old Qwen3 and CosyVoice playback selections fall back to browser playback.

For GPT-SoVITS, select the installation folder and reference audio, and optionally
set the reference transcript and reference/output languages. You can provide a
GPT `.ckpt` model and a SoVITS `.pth` model. Both paths must point to existing
files, or both must be blank to use the installation's configured models.
Incomplete pairs are not saved and cannot be checked or played. Changing the
pair restarts the local server before the next synthesis; clearing both restores
the installation defaults.
The NVIDIA GPU selector defaults to GPU 0 (the first GPU). GPT-SoVITS always
loads models on the selected CUDA device in FP16 and reports its name in the
check result and logs. Changing GPUs reloads the server on the next check or
playback. A CUDA-enabled embedded PyTorch runtime is required; CPU fallback is
disabled, and an unavailable GPU causes a visible startup error.

LiveAI copies `sovits_server.py` into the selected installation and runs it with
`runtime/python.exe`. Before reporting ready, it warms pronunciation models and
performs a silent synthesis with the selected reference voice. First startup can
take several minutes and has a separate 240-second limit. It reuses reference-audio features and
streams speech through one audio output. Complete sentences enter the synthesis
queue while ChatGPT is still generating its reply. If ChatGPT replaces an
intermediate reply with a final answer, the changed sentences are also read.
The “Thinking” / “正在思考” status stays visible without being spoken.
Reply timeouts and send errors are also spoken in the interface language.
Screenshot uploads are checked before sending; failed uploads retry the same
capture up to three total attempts. If all attempts fail, the prompt stays in
the editor and the app reports the upload error instead of waiting for a reply.

The STT catalog includes Mandarin and English models. Recording settings can
install the Sherpa runtime and download models into the working directory's
`models` folder. Installation supports official PyPI, Aliyun, and SJTUG without
changing global pip settings. **Record microphone** tests transcription;
**Play text** tests GPT-SoVITS playback.
Synthesis errors appear in the playback status and server output is captured in
the logs. After warmup, speech streams in sentence fragments. If no audio arrives
for 30 seconds during playback, LiveAI stops the speech server
and reports a timeout; the next attempt starts a fresh server.

Hotkey defaults are
**Right Alt** (record and send with the selected screenshot) and
**Right Ctrl** (record and send without a screenshot).
These are the two global shortcuts, and both are enabled by default.
Click a shortcut field and press a key or combination to change it;
left and right Alt, Ctrl, and Shift are recognized separately.
Use the **×** inside a shortcut field to clear it and disable that action.
Cleared shortcuts stay empty after restarting; changes are saved automatically.
Recording shortcuts automatically send successful dictation meeting the
character minimum above; the UI microphone always requires manual sending. Starting either
recording shortcut stops active local or
browser voice playback. The shortcuts work while the
overlay is hidden or unfocused. LiveAI observes their key state without
registering or swallowing the keys, so the foreground program continues to
receive the same keystrokes. Changes are saved for the current Windows user.

If microphone shortcuts stop working when a game is in the foreground, check
LiveAI's warning: staying in the same administrator window for 15 continuous
seconds triggers a system notification and brings the overlay forward, if
LiveAI is not elevated and a microphone shortcut is enabled. Leaving that
window resets the wait. The warning shows the window title and asks you to run
LiveAI as administrator so microphone shortcuts work in that window. Dismiss
the warning with OK; it appears only once per app run.

Preferences are stored as JSON in `%APPDATA%\Live GPT\config.json`. The file is
updated automatically when a preference changes and includes the language,
hotkeys, auto-hide state, selected screenshot source, selected
ChatGPT conversation, independent recording/playback backends, local STT/TTS
models, GPT-SoVITS installation, paired model paths,
languages, reference-audio path and transcript, overlay position
and size, and
position-lock state. A
missing, unreadable, or invalid configuration falls back to safe defaults and
is repaired on disk. Existing registry-based hotkeys are migrated on the first
JSON-configured launch.
The editor and microphone remain disabled until a ChatGPT window is connected.
Status tips appear as the editor hint rather than in a separate row; errors use
a red hint and a visible, wrapping banner above the input. When ChatGPT shows
a usage-limit notice, LiveAI displays its message, including any reset time,
and stops waiting for a reply. Prompts rejected before sending stay in the editor
so they can be sent after usage resets.

Sending switches directly to a subtitle view with four rows by default.
**Configure → Playing → Subtitle rows** sets the number of rows from 2 to 10;
changes apply immediately and are saved as `subtitle_rows`. The subtitle panel
fits the height of those rows even when the overlay is tall. While ChatGPT
responds, the upper rows show the prompt or incoming response and the last row
shows the current status. When **Read aloud** starts, all rows show the response.
During playback, subtitles follow the browser
media's progress and roll forward one line at a time. Hover over the subtitle
area to expand a formatted HTML response with paragraphs, lists, tables, and links.
Reply images load as thumbnails, preserving image galleries. Click an image to
open it in a borderless, resizable window centered on the reply's screen.
Scroll to zoom, then hold the left mouse button and drag the image to pan in any direction,
and use **Fit image** to reset the view. The maximize button toggles between
maximized and restored sizes; drag the header to move the window. Close it with
**×** or **Esc** to return to the reply. Images and their controls are excluded from
subtitles and speech.
Code blocks use rounded cards with spacing above them and padding around the text.
They keep their original line breaks and indentation, with a language label and
a copy icon that copies only that block's text to the clipboard and briefly shows a checkmark.
Its height fits the rendered content. Moving
the pointer outside the whole overlay restores the configured rows at the current playback
line. Use the **×** button in the expanded reply to close it and return to an empty
message input. Closing the reply stops browser or local read-aloud, including
queued speech. Citation badges such as “Forever +1” are excluded from subtitles
and local speech, while their available source links appear in the expanded reply.
If a closed citation exposes only its favicon's source domain, its link opens
that website's home page. If neither an article URL nor a domain is exposed,
the link is marked **(ChatGPT)** and opens the original conversation.
Subtitle progress follows consumed
audio, so pauses and buffering do not advance it. While streamed audio has no
final duration, timing uses an estimate that counts both words and CJK characters
and carries playback time across audio chunks. This remains approximate within
sentences because browser playback does not provide word timestamps. If ChatGPT
does not expose its media element, timing falls back to an elapsed-time estimate.
Press the microphone or its hotkey to dismiss subtitles and dictate
another prompt. Press
**Enter** to send a prompt or **Shift+Enter** to insert a newline. With no
screenshot selected, the send actions remain hidden while the editor is empty.

At startup, LiveAI connects through Playwright to a local Chromium browser
that was started with remote debugging enabled. It discovers ChatGPT tabs and
lists them by page title beside the **LiveAI** heading, refreshing the list as
tabs open, close, or navigate. Tab titles come from the browser's target list,
so a busy or frozen ChatGPT page does not stall discovery after approval.
After connecting, if no ChatGPT tab is found, LiveAI opens `chatgpt.com` in a
new tab in that browser. It checks once per connection to avoid duplicate tabs.
When no debuggable browser is available, LiveAI
opens the current user's `edge://inspect/#remote-debugging` or
`chrome://inspect/#remote-debugging` settings page. LiveAI turns on **Allow
remote debugging for this browser instance** through Windows accessibility,
verifies that the browser's per-user `DevToolsActivePort` marker contains a live
endpoint, and then connects. If the browser is already open, the settings page
opens in a new tab without replacing the active page. The browser can still ask
the user to approve the incoming connection. LiveAI keeps one approval request
pending until the user chooses **Allow** or **Deny**, preventing unanswered
requests from creating a stack of dialogs. After choosing **Deny**, click
**Enable Debugging** to make another request; the browser tabs remain unchanged.
If opening or enabling the debugging settings fails, LiveAI stops automatic
setup attempts. Click **Enable Debugging** to retry after correcting the issue;
it checks that the browser address bar is accessible before opening a new tab.
Attached ChatGPT pages retain the browser's native color scheme through
Playwright's `no_defaults` connection option (Playwright 1.62+). LiveAI uses
focus emulation to keep the selected ChatGPT tab active while you use another
window, without bringing the browser forward. Switching tabs, disconnecting,
or exiting restores normal tab focus. This may reduce background completion
notifications; phone notification delivery also depends on ChatGPT's settings.
LiveAI does not launch the browser with debugging flags or create
a separate profile. The optional `LIVE_GPT_CDP_ENDPOINT` environment variable
can point the app at a specific CDP HTTP or WebSocket endpoint.

## Pet

The default pet is `assets/pets/feibi-jiubi`. Open **Settings → Pet** to choose
a pet from the folders under `assets/pets`; changes apply immediately.
Idle animation can always play, stay on a still pose, or play for a duration
(default 10 seconds) each time the pet returns to idle. Looking and activity
animations are unaffected. Settings are saved automatically. You can also set
`pet_path` in the user configuration to an external pet directory or `pet.json`
(restart after manual configuration edits). An empty path uses the bundled default. Both v1 (8×9)
and v2 (8×11) sprite sheets with 192×208 cells are supported; an omitted
`spriteVersionNumber` is treated as v1. Invalid custom pets fall back to the default.

The pet uses idle at rest, waiting during dictation, running while awaiting a
response, review during speech playback, and failed for errors. Dragging uses
running-right or running-left and restores the current activity on release.
V2 pets look toward the screen pointer while idle when its distance from the
pet is less than half the height of the screen containing the pet. Moving
farther away or leaving the pointer still for five seconds restores the idle
loop. The lock button locks overlay dragging and resizing.

Mouse-out hiding and auto-hide only run while a ChatGPT browser tab is connected.
Before connection or after disconnection, the full overlay stays visible so you
can reconnect. Your auto-hide preference is retained for the next connection.

Dragging keeps the overlay inside the usable area of the screen under the
pointer. Move the pointer onto another monitor to transfer the overlay there.
If the overlay is larger than that screen's usable area, its top-left corner
stays on-screen so its controls remain reachable.

Select and copy text directly from the formatted reply. Its HTTP(S) links open
in a new tab in the default browser. Holding the microphone for at least
0.5 seconds clears the previous input; shorter taps preserve it.

Hover anywhere over the overlay to expand the input vertically to fit its
content. Expansion is limited to the screen's usable height, with scrolling
for longer text. Moving away restores the compact window size.

## Download pets

In **Configure → Pet**, paste a public GitHub folder URL (for example,
`https://github.com/legeling/awesome-codex-pet/tree/main/pets/citlali--zaytsevzy`)
and click **Download pet**. The folder must contain `pet.json` and
`spritesheet.webp`. Both `/tree/` and `/blob/` folder URLs are supported.
Find pet folder links in [awesome-codex-pet](https://github.com/legeling/awesome-codex-pet).
After validation, the pet is saved under
`download/pets/<folder-name>`, added to the list, and selected immediately.
Downloaded pets remain available after restarting. Existing valid downloads
are reused; failed downloads leave the selected pet unchanged.

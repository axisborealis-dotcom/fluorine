```
 ███████ ██      ██    ██  ██████  ██████  ██ ███    ██ ███████
 ██      ██      ██    ██ ██    ██ ██   ██ ██ ████   ██ ██
 █████   ██      ██    ██ ██    ██ ██████  ██ ██ ██  ██ █████
 ██      ██      ██    ██ ██    ██ ██   ██ ██ ██  ██ ██ ██
 ██      ███████  ██████   ██████  ██   ██ ██ ██   ████ ███████
```

⚠️ Epilepsy warning: this app has flashing lights and colors. Do not run it if you have photosensitive epilepsy.

## Download
**[Fluorine.zip](../../raw/main/Fluorine.zip)** - everything in one file: `Fluorine.exe`, `Fluorine-safety.exe`,
the Windows Sandbox config, the Python source, the Scratch project, the icon and the pre-rendered audio.

ESC ends it, any time.

## Scratch version
`Fluorine.sb3` is a Scratch 3 recreation: all 6 phases, the red X cursor, and the bytebeat audio. Open it at scratch.mit.edu with File > Load from your computer.

## Building
`pyinstaller --onefile --noconsole --uac-admin --icon fluorine.ico --name Fluorine fluorine.py`

`--uac-admin` makes Fluorine ask for administrator when it starts (shield icon).

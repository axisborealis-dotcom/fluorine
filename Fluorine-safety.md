# Fluorine — Safety

## ⚠️ Flashing lights warning

Fluorine flashes bright, fast-changing colors and inverts the whole screen,
especially in the last two parts. **Do not run it if you or anyone watching
has photosensitive epilepsy or is sensitive to flashing lights.**

It also plays loud 8-bit bytebeat audio — turn your volume down first.

## ⌨️ How to stop it

Press **ESC** at any time. The effects stop, the sound stops, and the
screen redraws back to normal.

## What it does

- Draws effects directly on top of your screen (GDI) for about 3 minutes, in 6 parts.
- Plays a bytebeat soundtrack through the default audio device.

## What it does NOT do

- Does not install anything or run at startup.
- Does not change, delete, or read your files.
- Does not change system settings or the registry.
- Does not use the network.
- Nothing stays after you press ESC or it closes.

## Want to be extra safe?

Run it inside Windows Sandbox (`Fluorine.wsb`) — everything is thrown away
when the sandbox closes.

# Building Fluorine.exe

The DPI manifest must be embedded, or a scaled/large display only melts part
of the screen (a runtime SetProcessDpiAwareness call can be too late in the
frozen exe). Always pass --manifest:

    pyinstaller --onefile --noconsole --icon fluorine.ico \
        --manifest fluorine.manifest --name Fluorine fluorine.py

`fluorine.manifest` declares PerMonitorV2 DPI awareness so GetSystemMetrics
returns real physical pixels and the melt fills the whole screen.

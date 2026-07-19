# Inkbit

Inkbit is the Manga Factory pixel companion. The GUI maps its states to actual worker phases:

- `running-right` - downloading pages
- `running` - cleanup, strip stitching, script writing, and PDF binding
- `review` - scene cuts, OCR, dialogue, and context work
- `waiting` - a stopped or input-needed run
- `jumping` - completed chapter
- `failed` - worker or output error

The spritesheet is an 8x11 v2 atlas with 192x208 cells. `idle.png` is a transparent fallback for startup or WebP-loading failures.

The stage is driven by WorkerThread updates, including the transition states after a
download, cleanup, stitch, and scene-cut phase. It is not connected to a fake timer
or an estimated progress value.

# Test media attribution

Big Buck Bunny trailer, Blender Foundation, 2008.

(c) copyright 2008, Blender Foundation / www.bigbuckbunny.org

- [Official source](https://download.blender.org/peach/trailer/trailer_iphone.m4v)
- [Blender's license statement](https://peach.blender.org/about/)
- [Creative Commons Attribution 3.0](https://creativecommons.org/licenses/by/3.0/)

`scripts/download_sample.py` downloads the unmodified ISO MP4 bytes to `media/sample.mp4`. The original filename ends in `.m4v`; only the filename changes. The movie file is excluded from Git. `web/art/hero.jpg` is a frame extracted from the same trailer for the interface. The SVG sample-card illustrations were drawn for this project and do not copy the other films' artwork. No Blender logo is used.

This is a 480 x 270, 25 fps H.264 Constrained Baseline + AAC LC stereo test. It checks basic playback, not HD/4K decoding capacity or DRM.

## Catalog and brand assets

TMDB supplies catalog metadata and artwork when configured. The TMDB logo is retained for attribution under its [branding requirements](https://developer.themoviedb.org/docs/branding). This product uses the TMDB API but is not endorsed or certified by TMDB. Catalog artwork is fetched at runtime and is not included in the repository.

The application mark and the Sintel/Elephants Dream sample-card SVG illustrations are original project assets under the code's MIT license. The Blender trailer frame remains CC BY 3.0. Provider names and logos retain their owners' trademark and other applicable rights. Dependencies retain their own licenses; the project MIT license does not replace third-party terms.

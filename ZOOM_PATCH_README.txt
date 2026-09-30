Mississippi River dashboard zoom/pan patch

Preferred: replace the prior weighted-tributary HTML with Mississippi_Flow_Coverage_Zoomable_v2.html.

Alternative: put patch_zoom_pan.py beside Mississippi_Flow_Coverage_Weighted_Tributaries.html and run:
    python patch_zoom_pan.py

Added behavior:
- Mouse wheel / trackpad zoom centered on pointer
- + / - zoom buttons
- Reset button
- Click-drag panning
- Touch pinch zoom
- Touch/pointer handling
- Pan/pinch click suppression so reaches/stations are not accidentally selected
- Existing reach/station click behavior and continuity-width rendering retained

No additional libraries, CSS files, JS files, or data files are required.

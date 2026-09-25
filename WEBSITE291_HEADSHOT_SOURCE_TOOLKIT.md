# Website291 — Historical Headshot Source Toolkit

This build intentionally does not change the website's existing headshot imagery. It adds a source-acquisition toolkit after the persistent failures with converting Basketball-Reference JPGs into acceptable card portraits.

The toolkit searches Wikimedia Commons for exact-name image files and accepts only **already-transparent PNGs**. JPEG/WEBP images are not automatically converted or installed. Every accepted candidate is staged locally and marked for visual review before it can become canonical.

This is deliberately source-agnostic: if a better historical PNG source becomes available, the same manifest format can be used without rewriting the site's card rendering pipeline.

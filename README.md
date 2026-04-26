# Frankfurt History Archive

Automated archive of location data from the [Frankfurt History](https://play.google.com/store/apps/details?id=de.frankfurt.history) app by [dotcombinat](https://dotcombinat.de/) / Historisches Museum Frankfurt.

The app documents historical locations across Frankfurt am Main through texts, photographs, audio guides, and interactive before/after image comparisons. This repository preserves that content as plain markdown files with YAML frontmatter, suitable for search, offline reading, and long-term archival.

## Structure

```
data/
├── frankfurt-und-der-ns/        1572 locations
├── neues-frankfurt/              125 locations
├── frankfurt-stories/            89 locations
├── feministisches-frankfurt/     81 locations
├── revolution-1848-49/          42 locations
├── leichte-sprache/             16 locations
└── images/                      ~2500 photographs (Git LFS)
```

Each location is a markdown file with frontmatter containing its ID, title, GPS coordinates, categories, and last-updated timestamp. The body holds the historical text, image references, gallery sections, and links to audio/video content.

## Automation

A GitHub Actions workflow runs weekly (Monday 03:00 UTC) to fetch the latest data from the app's API and commit any changes. It can also be triggered manually from the Actions tab.

## License

All content — texts, images, and metadata — is sourced from the Frankfurt History app and remains under the original authors' licensing terms. Most content is published under **CC BY-SA 4.0** (Creative Commons Attribution-ShareAlike 4.0 International). Individual items may carry different terms; the author and license for each piece of content are preserved in the markdown files exactly as provided by the source.

This repository is a non-commercial archival mirror. It does not claim any rights beyond what the original licenses grant and does not alter, remix, or rebrand the content. Attribution metadata is kept intact for every text and image.

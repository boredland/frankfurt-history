"""Initiative-specific scrapers for Stolpersteine.

Each module exports a ``Scraper`` class implementing the contract below.
The top-level dispatcher (``scripts/enrich_stolpersteine.py``) discovers
modules in this package and routes records to whichever scraper claims
to handle the record's ``refs.website`` host.

Contract:

    class Scraper:
        host: str                       # canonical host this scraper claims
        source_key: str                 # label used in record["enrichers"][...]

        def can_handle(self, url: str) -> bool: ...

        def fetch(self, record: dict) -> EnrichmentResult | None:
            '''Returns enrichment data or None if the page couldn't be fetched.'''

EnrichmentResult shape (all top-level keys optional):

    {
      "biographies": [
        {
          "source":     "stolpersteine-berlin.de",
          "source_url": "https://www.stolpersteine-berlin.de/de/...",
          "lang":       "de",
          "text":       "...",
          "text_en":    "...",                          # optional
          "author":     "Initiative ..."                # optional, attribution
        }
      ],
      "images": [
        {
          "url":     "https://...",
          "caption": "...",
          "source":  "stolpersteine-berlin.de",
          "kind":    "portrait" | "stone" | "document"  # best-effort
        }
      ],
      "person_updates": {                                # merged into record["person"]
        "birth_place":       "Berlin",
        "death_place":       "Auschwitz",
        "deported_to":       ["Theresienstadt", "Auschwitz"],
        "deportation_dates": ["1943-01-26", "1944-10-23"],
        "fate":              "Ermordet",
      },
      "address_updates": {"district": "Wilmersdorf"},   # merged into record["address"]
      "extras": {},                                      # initiative-specific raw payload
    }
"""

from __future__ import annotations

# Licence of the files in this folder

The JSON files in `raw/` are **not** covered by the project's Apache-2.0 licence.

- **Data:** Formula 1 timing data from the [Jolpica-F1](https://github.com/jolpica/jolpica-f1) project and its contributors, served through its Ergast-compatible API (`https://api.jolpi.ca/ergast/f1/`). Jolpica-F1 continues the Ergast Developer API's data and response format.
- **Licence:** [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)](https://creativecommons.org/licenses/by-nc-sa/4.0/), as stated in the [Jolpica-F1 Terms of Use](https://github.com/jolpica/jolpica-f1/blob/main/TERMS.md).
- **Changes:** none. The files are stored byte-for-byte as downloaded on 2026-10-12 by `validation/fetch_reference.py`.

What the licence means here:

- **Attribution:** credit "Jolpica-F1 / Ergast", link to the licence, and say whether you changed the data.
- **NonCommercial:** use for learning, research and portfolio projects is fine. Commercial use needs permission. The Terms of Use say to ask the Jolpica-F1 maintainers at admin@jolpi.ca.
- **ShareAlike:** if you publish an adapted version of this data, it must use the same licence.

The same licence also covers project files that reproduce values from this data:

- `validation/reports/validation_report.md`, which lists the reference lap times, pit-stop losses and race times;
- the fitted numbers in `validation/config/calibrated.json`.

Licensing is set out in [README.md](README.md) and in the repository's [NOTICE](../../NOTICE). This is not legal advice.

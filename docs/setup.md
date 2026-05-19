# Setup Notes

## WeasyPrint Runtime Packages

Install the Linux system packages required for CBC report PDF rendering:

```bash
sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0
```

WeasyPrint `62.3` is pinned in `requirements.txt`. Cairo is no longer required as a Python binding at runtime, but the system libraries above are still needed for reliable PDF rendering.
# Third-party components

The host vendors two small browser/serial dependencies so it works offline and
with `python -I`:

| Component | Version | License | Location |
| --- | --- | --- | --- |
| pyserial | 3.5 | BSD-3-Clause | `vendor/pyserial-3.5.LICENSE.txt` |
| xterm.js | 5.3.0 | MIT | `web/vendor/xterm/LICENSE` |

Both are unmodified upstream releases. pyserial was installed with:

```bash
python -m pip install --target chip-adapt/sifli/host/vendor --no-deps pyserial==3.5
```

The `bin/` directory produced by pip was removed; only the `serial` package and
its metadata are kept. xterm.js and its CSS were downloaded from jsDelivr.

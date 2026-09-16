# IBM Plex Sans static font provenance

Prepared: 2026-09-15

## Official upstream source

- Repository: https://github.com/IBM/plex
- Immutable source commit: https://github.com/IBM/plex/tree/242c4cccd37e87985a5337815c99b960ef13c65c
- Release tag resolving to that commit: https://github.com/IBM/plex/tree/v6.4.2
- Static-font directory at the immutable commit: https://github.com/IBM/plex/tree/242c4cccd37e87985a5337815c99b960ef13c65c/IBM-Plex-Sans/fonts/complete/ttf
- License at the immutable commit: https://raw.githubusercontent.com/IBM/plex/242c4cccd37e87985a5337815c99b960ef13c65c/LICENSE.txt

The included TTFs are unmodified copies of the four files from that static-font
directory. Their OpenType name table reports IBM Plex Sans and version 3.005.
`v6.4.2` is the upstream repository release tag; `3.005` is the font's embedded
version, so the two version strings describe different layers.

## Files and SHA-256

| File | SHA-256 |
| --- | --- |
| `fonts/IBMPlexSans-Regular.ttf` | `975dcda37d80f038dcd143c22e33ca2d97a0cc5a929aace1c749153b0fe1afa5` |
| `fonts/IBMPlexSans-Medium.ttf` | `331c8639d7598b2cde62a911a71db195e30cb655cd6bdf2e324a7e984955f907` |
| `fonts/IBMPlexSans-SemiBold.ttf` | `a20caf8286023a6a7a85e40b1d2a4ae9fc3e3b1f9eda8f4c542dd4986af67bb1` |
| `fonts/IBMPlexSans-Italic.ttf` | `a9c6ef9942c49e49d11e11a6dacc0b3a087978757e9b22a06b8ac22a6400fb15` |
| `OFL-1.1.txt` | `7e6b2818edbd8f6a01ae80641cc8f16a51080d08fb4e532be3a0b6f74adb07da` |

## Reference comparison

Each of the four TTFs is byte-identical (`cmp -s`) to its same-named file in
`/home/peter/DEV/formulafinance/back_sideprojects/Redesign/cr-print/report/fonts`.

## License

Copyright © 2017 IBM Corp. with Reserved Font Name "Plex". The font software is
licensed under the SIL Open Font License, Version 1.1. The complete, verbatim
license is included as `OFL-1.1.txt`; retain it when bundling these fonts.

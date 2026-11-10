# Super Mario 64 DS -> Sega Saturn (LibSaturn)

Experimental source-level port of Super Mario 64 DS to a **stock Sega Saturn**, using the [LibSaturn](https://github.com/celsowm/libsaturn) public APIs and [SM64DS decompilation](https://github.com/tangosdev/sm64ds-decomp) as a behavioral reference.

**Current status:** asset-converter prototype and plans only. No Saturn bootable game has been delivered yet.

## Current milestone

The [local model/animation converter](tools/sm64ds_convert.py) accepts a privately supplied ASME USA Rev.00 ROM, resolves `ARCHIVE/arc0.narc:131` to the 16-bone Mario model, decodes packed GX vertex streams and four BCA clips, and emits flat-color **C assets** for the LibSaturn runtime skeleton, rigid skin and geometry APIs.

It **does not yet produce textures** or a playable scene. It refuses unhandled animated scaling, weighted BMD matrices and GX opcodes instead of silently misrendering them. The output C requires a Saturn-side consumer to perform per-actor skeleton evaluation and skinning.

```sh
python3 -m unittest discover -s tests -v

# Optional local-ROM tests (never in public CI):
SM64DS_ROM='/private/path/Super Mario 64 DS (USA).nds' \
  python3 -m unittest discover -s tests -v

python3 tools/sm64ds_convert.py \
  --rom '/private/path/Super Mario 64 DS (USA).nds' \
  --model 'ARCHIVE/arc0.narc:131' \
  --out ./generated \
  --name mario_preview
```

### Technical documents

- [Port plan and milestones](docs/PORT_PLAN.md)
- [Local ROM metadata audit](docs/ROM_AUDIT.md)
- [Converter format/limits and tests](docs/CONVERTER.md)

## Legal / asset policy

This public repository contains no Nintendo ROM or extracted Nintendo assets. Bring your own legitimately obtained cartridge dump for private local tests. Generated C files, images and pose data derived from the ROM must stay out of public commits; `.gitignore` protects conventional locations and file types, but use your own private output path. The decompilation project's license covers original source contributions, **not** commercial Nintendo game contents.

"""
Extracts files from the Jaguar port of Wolfenstein 3-D.
"""
from extractor.wad import WADFile, LumpType
import argparse
import logging

logging.basicConfig(level=logging.INFO)


def extract_files(file, output_path, separate_maps=False, lumps=None, raw=False, lump_type: str = None,
                  make_sprites_128x128: bool = False):
    with open(file, "rb") as f:
        f.seek(0x20000)
        wad = WADFile(f)
        WADFile.COMBINE_MAPS_INTO_ONE_FILE = not separate_maps
        WADFile.DUMP_RAW_DATA = raw
        WADFile.MAKE_SPRITE_128X128 = make_sprites_128x128
        if lumps is None:
            if lump_type is not None:
                lumps = wad.get_lumps_of_type(lump_type)
            else:
                lumps = wad.get_all_lump_names()
        for entry in lumps:
            entry_index = wad.get_lump_index(entry)
            if entry_index < 0:
                logging.error(f"Unknown entry: {entry}")
                break
            wad.save_lump(entry_index, output_path)
        wad.save_combined_map_file(output_path)
        if lump_type is None or lump_type == LumpType.Instrument.name:
            wad.save_instruments_to_soundfont(output_path)


def main():
    parser = argparse.ArgumentParser(description="Extracts files from the Jaguar port of Wolfenstein 3-D.")
    parser.add_argument("-i", "--input", type=str, help="The path to the Jaguar j64 file.", required=True)
    parser.add_argument("-o", "--outpath", type=str, help=r"The path to extract the data to. Default: .\output",
                        default=r".\output")
    parser.add_argument("--separatemaps", action="store_true", help="When set, saves maps as individual files instead "
                                                                    "of one file with all.")
    parser.add_argument("--sprites128", action="store_true", help="When set, sprites will be exported as 128x128 "
                                                                  "instead of their original size.")
    parser.add_argument("--raw", action="store_true", help="When set, dumps the raw lump data.")
    parser.add_argument("-l", "--lumps", type=str, nargs="*", help="The lump names to extract.  Defaults to all lumps "
                                                                   "unless lumptype is given.")
    parser.add_argument("-t", "--lumptype", type=str, help="Extracts all lumps with the given lump type.")
    # parser.print_help()
    args = parser.parse_args()
    extract_files(file=args.input, output_path=args.outpath, separate_maps=args.separatemaps, lumps=args.lumps,
                  raw=args.raw, lump_type=args.lumptype, make_sprites_128x128=args.sprites128)


if __name__ == '__main__':
    main()

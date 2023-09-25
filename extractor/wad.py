from dataclasses import dataclass
from enum import IntEnum, auto
import extractor.crypalette as cry
import extractor.soundfont as soundfont
import extractor.wav as wav
from extractor.gamemap import GameMap
import logging
import os
import png
import struct
import typing as _typing

logger = logging.getLogger("wad")


def _read_little_endian_uint32(f) -> int:
    return struct.unpack('<I', f.read(4))[0]


def _read_big_endian_uint16(f) -> int:
    return struct.unpack('>H', f.read(2))[0]


class LumpType(IntEnum):
    Unknown = auto()
    Marker = auto()
    Map = auto()
    Sprite = auto()
    Wall = auto()
    Sound = auto()
    Song = auto()
    Instrument = auto()
    RGBPalette = auto()
    CrYPalette = auto()
    Image = auto()
    CrYImage = auto()
    Font = auto()
    MapIcons = auto()


@dataclass
class Lump:
    name: str
    offset: int
    length: int
    is_compressed: bool
    type: LumpType
    args: _typing.Any


class WADFile:
    _WALL_SIZE = 128
    COMBINE_MAPS_INTO_ONE_FILE = True
    DUMP_RAW_DATA = False
    MAKE_SPRITE_128X128 = False

    def __init__(self, f):
        self._f = f
        self._file_offset = f.tell()
        # read the WAD header
        if f.read(4) != b'IWAD':
            raise ValueError("Expected IWAD file signature.")
        self._lumps = self._load_directory()
        self._cached_lumps = {}
        self._maps = []

    def _load_directory(self):
        lumps = []
        lump_count = _read_little_endian_uint32(self._f)
        directory_offset = _read_little_endian_uint32(self._f)
        self._f.seek(self._file_offset + directory_offset)
        last_marker = None
        for index in range(lump_count):
            offset = _read_little_endian_uint32(self._f)
            length = _read_little_endian_uint32(self._f)
            name = self._f.read(8)
            is_compressed = bool(name[0] & 0x80)
            name = (bytes([name[0] & 0x7f]) + name[1:]).split(b'\x00')[0].decode()
            lump_type = self._determine_lump_type(name, offset, length, last_marker)
            try:
                lump_type, *args = lump_type
            except TypeError:
                args = None
            lump = Lump(name, offset, length, is_compressed, lump_type, args)
            lumps.append(lump)
            if lump.type == LumpType.Marker:
                last_marker = lump.name
        return lumps

    @staticmethod
    def _determine_lump_type(name, offset, length, last_marker):
        if offset == 0 and length == 0:
            return LumpType.Marker
        if name == "MAPICONS":
            return LumpType.MapIcons
        elif name.startswith("MAP"):
            return LumpType.Map
        elif name.startswith("SPR") or name.startswith("WP"):
            return LumpType.Sprite, True
        elif (name.startswith("NUM") or name in ("BLANK", "GKEY", "SKEY", "BLANKAMM", "FIRSTFAC") or
                name.startswith("AMMO") or name.startswith("FACE")):
            return LumpType.Sprite
        elif name.startswith("WALL"):
            return LumpType.Wall
        elif name == "RGBPALS":
            return LumpType.RGBPalette
        elif name in ("CRYPALS", "BRIEFPAL"):
            return LumpType.CrYPalette
        elif name == "BRIEF":
            return LumpType.Image, "BRIEFPAL"
        elif (name.startswith("I_") or name.startswith("M_")
              or name in ("SLIDBAR", "SLIDER", "CREDITS", "LOGO", "MTCAST")
              or name.startswith("CM_")):
            return LumpType.Image
        elif name == "WOLFTITE":
            return LumpType.CrYImage
        elif name == "FONT8":
            return LumpType.Font
        elif name.startswith("0"):
            return LumpType.Song
        elif last_marker == "SOUNDS" and name not in ("STEPTABL",):
            if name in ("ACHTUN18",):
                return LumpType.Sound, 18000
            if name.startswith("D_") or name in ("KEY02",):
                return LumpType.Sound, 22050
            return LumpType.Sound, 11025
        elif last_marker == "SONGEND" and (name.startswith("I") or name.startswith("P")):
            return LumpType.Instrument
        return LumpType.Unknown

    @property
    def number_of_lumps(self):
        return len(self._lumps)

    def get_lump_index(self, name) -> int:
        return next((index for index in range(len(self._lumps)) if self._lumps[index].name == name), -1)

    def get_lump_by_name(self, name):
        lump_index = self.get_lump_index(name)
        assert lump_index >= 0
        return self.get_lump(lump_index)

    def get_all_lump_names(self):
        return (lump.name for lump in self._lumps)

    def get_lumps_of_type(self, type_name: str):
        type_name = type_name.casefold()
        return (lump.name for lump in self._lumps if lump.type.name.casefold() == type_name)

    def get_lump_type(self, index):
        return self._lumps[index].type

    @staticmethod
    def _decompress(compressed_data):
        # https://doomwiki.org/wiki/WAD#Compression
        output_data = []
        position = 0
        finished = False
        while not finished:
            flag_byte = compressed_data[position]
            position += 1
            for _ in range(8):
                # get the current bit
                bit = flag_byte & 1
                flag_byte >>= 1
                if bit:
                    # 16-bit offset length pair
                    offset = compressed_data[position]
                    position += 1
                    length = compressed_data[position]
                    position += 1
                    offset = (offset << 4) + ((length & 0xf0) >> 4)
                    length &= 0x0f
                    if not length:
                        finished = True
                        break
                    assert offset > 0
                    length += 1
                    offset = len(output_data) - offset
                    for __ in range(length):
                        output_data.append(output_data[offset])
                        offset += 1
                else:
                    # uncompressed byte
                    output_data.append(compressed_data[position])
                    position += 1
        return bytes(output_data)

    def get_lump(self, index: int) -> _typing.Tuple[str, _typing.Optional[bytes]]:
        lump = self._lumps[index]
        logger.debug(f"Getting lump: {lump.name}")
        if lump.length == 0:
            return lump.name, None
        assert lump.offset > 0
        assert lump.length > 0
        self._f.seek(self._file_offset + lump.offset)
        if lump.is_compressed:
            next_index = index + 1
            while not self._lumps[next_index].offset:
                next_index += 1
            compressed_length = self._lumps[next_index].offset - lump.offset
            data = self._f.read(compressed_length)
            data = self._decompress(data)
            assert len(data) == lump.length
        else:
            data = self._f.read(lump.length)
        return lump.name, data

    def _get_cached_lump_data(self, name):
        if name in self._cached_lumps:
            data = self._cached_lumps.get(name, None)
        else:
            data = self.get_lump_by_name(name)[1]
            self._cached_lumps[name] = data
        return data

    def _get_lump_type_save_method(self, lump_type):
        if lump_type == LumpType.Map:
            return self._save_map
        if lump_type == LumpType.Sprite:
            return self._save_sprite_lump
        if lump_type == LumpType.Wall:
            return self._save_wall_lump
        if lump_type == LumpType.CrYPalette:
            return self._save_cry_palette
        if lump_type == LumpType.Image:
            return self._save_image
        if lump_type == LumpType.CrYImage:
            return self._save_cry_image
        if lump_type == LumpType.Song:
            return self._save_song
        if lump_type == LumpType.Sound:
            return self._save_sound
        if lump_type == LumpType.Font:
            return self._save_font
        if lump_type == LumpType.MapIcons:
            return self._save_map_icons
        if lump_type == LumpType.Instrument:
            return self._save_instrument_sound
        return self._save_raw_data

    def save_lump(self, index, output_path):
        name, data = self.get_lump(index)
        if data is None:
            return
        lump = self._lumps[index]
        filename = os.path.join(output_path, name)
        if WADFile.DUMP_RAW_DATA:
            logger.info(f"Saving lump as raw data: {name}")
            self._save_raw_data(filename, data)
        else:
            logger.info(f"Saving lump: {name}")
            save_method = self._get_lump_type_save_method(lump.type)
            save_method(filename, data, *lump.args if lump.args else [])

    # noinspection PyMethodMayBeStatic
    def _save_raw_data(self, filename, data, *_):
        with open(filename, "wb") as f:
            f.write(data)

    # noinspection PyMethodMayBeStatic
    def _save_map(self, filename, data, *_):
        GameMap.DETECT_PUSHWALL_DIRECTION_WHEN_CONVERTING_TO_DOS = True
        gamemap = GameMap(os.path.split(filename)[1], data)
        if WADFile.COMBINE_MAPS_INTO_ONE_FILE:
            self._maps.append(gamemap.generate_dos_map())
        else:
            gamemap.save(filename + ".map")

    def save_combined_map_file(self, output_path):
        if WADFile.COMBINE_MAPS_INTO_ONE_FILE and self._maps:
            logger.info("Saving combined map file as MAPS.map.")
            GameMap.save_as_wdc_map_file(os.path.join(output_path, "MAPS.map"), self._maps)

    def _get_rgb_palette(self):
        palette_data = self._get_cached_lump_data("RGBPALS")
        palette = [(int(palette_data[index]), int(palette_data[index + 1]), int(palette_data[index + 2]), 255)
                   for index in range(0, len(palette_data), 3)][0:256]  # Only want the first palette in the lump
        return palette

    def _get_cry_palette(self, lump_name="CRYPALS"):
        palette_data = self._get_cached_lump_data(lump_name)
        palette = cry.convert_cry_palette_to_rgba(palette_data)[0:256]  # Only want the first palette in the lump
        return palette

    def _save_sprite_lump(self, filename, data, make_128x128=False, *_):
        offset_x, offset_y, width, height = data[0:4]
        # Clone the RGB palette and make color 0 be transparent.
        palette = self._get_rgb_palette()[:]
        palette[0] = (255, 255, 255, 0)
        # The first 8 bytes are header.  Skip them.
        data = data[8:]
        # Sprite pixels are row major.
        pixels = [[data[x + y * width] for x in range(width)] for y in range(height)]
        # Fit in 128x128 image
        if make_128x128 and WADFile.MAKE_SPRITE_128X128:
            temp_pixels = [[0 for _ in range(WADFile._WALL_SIZE)] for _ in range(WADFile._WALL_SIZE)]
            if offset_x + width > WADFile._WALL_SIZE:
                offset_x = width - WADFile._WALL_SIZE
                # Some sprites end up with a negative x offset, fudge a bit.
                if offset_x < 0:
                    offset_x = 0
            assert offset_x + width <= WADFile._WALL_SIZE
            assert offset_y + height <= WADFile._WALL_SIZE
            for y in range(height):
                temp_pixels[y + offset_y][offset_x:offset_x+width] = pixels[y]
            pixels = temp_pixels
        with open(filename + ".png", "wb") as f:
            w = png.Writer(len(pixels[0]), len(pixels), palette=palette, bitdepth=8)
            w.write(f, pixels)

    def _save_wall_lump(self, filename, data, *_):
        assert len(data) == 16384
        palette = self._get_rgb_palette()
        # Wall pixels are column major.
        pixels = [[data[x * WADFile._WALL_SIZE + y] for x in range(WADFile._WALL_SIZE)]
                  for y in range(WADFile._WALL_SIZE)]
        with open(filename + ".png", "wb") as f:
            w = png.Writer(len(pixels[0]), len(pixels), palette=palette, bitdepth=8)
            w.write(f, pixels)

    def _save_map_icons(self, filename, data, *_):
        palette = self._get_rgb_palette()
        # Pixels are row major.
        width = 320
        assert len(data) % width == 0
        height = len(data) // 320
        pixels = [[data[x + y * width] for x in range(width)] for y in range(height)]
        with open(filename + ".png", "wb") as f:
            w = png.Writer(len(pixels[0]), len(pixels), palette=palette, bitdepth=8)
            w.write(f, pixels)

    # noinspection PyMethodMayBeStatic
    def _save_cry_palette(self, filename, data, *_):
        palette = cry.convert_cry_palette_to_rgba(data)
        self._save_raw_data(filename + ".rgb", b''.join([bytes(color[0: 3]) for color in palette]))
        # TODO Export as PNG as well.

    def _save_image(self, filename, data, palette_lump="CRYPALS", *_):
        palette = self._get_cry_palette(palette_lump)
        width, height, depth, index = struct.unpack('>HHHH', data[0:8])
        assert index == 0
        # The first 16 bytes are header.  Skip them.
        data = data[16:]
        # Image pixels are row major.
        pixels = [[data[x + y * width] for x in range(width)] for y in range(height)]
        with open(filename + ".png", "wb") as f:
            w = png.Writer(len(pixels[0]), len(pixels), palette=palette, bitdepth=8)
            w.write(f, pixels)

    # noinspection PyMethodMayBeStatic
    def _save_cry_image(self, filename, data, *_):
        width, height, depth, index = struct.unpack('>HHHH', data[0:8])
        assert index == 0
        # The first 24 bytes are header.  Skip them.
        data = data[24:]
        data = [cry.cry_to_rgba(data[index: index + 2]) for index in range(0, len(data), 2)]
        pixels = [b''.join([bytes(pixel[0:3]) for pixel in data[index:index+width]])
                  for index in range(0, len(data), width)]
        with open(filename + ".png", "wb") as f:
            w = png.Writer(width, height, bitdepth=8, greyscale=False, alpha=False)
            w.write(f, pixels)

    # noinspection PyMethodMayBeStatic
    def _save_sound(self, filename, data, sample_rate, *_):
        with open(filename + ".wav", "wb") as f:
            writer = wav.Writer(int(sample_rate), 1, 8)
            writer.write(f, data)

    # noinspection PyMethodMayBeStatic
    def _save_instrument_sound(self, filename, data, *_):
        data_length, loop_start, loop_end, note_number = struct.unpack('>IIII', data[0:16])
        if loop_start == 0xffffffff:
            loop_start = None
            # loop_end = None
        # The first 16 bytes are header.  Skip them.
        data = data[16:]
        with open(filename + ".wav", "wb") as f:
            writer = wav.Writer(22050, 1, 8)
            writer.write(f, data, loop_start)

    # noinspection PyMethodMayBeStatic
    def _save_font(self, filename, data, *_):
        assert len(data) % 2 == 0
        width = 8
        height = len(data) // 2
        palette = [(0, 0, 0, 0),
                   (0x55, 0x55, 0x55, 0xff),
                   (0xaa, 0xaa, 0xaa, 0xff),
                   (0xff, 0xff, 0xff, 0xff)]

        def get_bits(b):
            return ((b[0] >> 6) & 0x3, (b[0] >> 4) & 0x3, (b[0] >> 2) & 0x3, (b[0] >> 0) & 0x3,
                    (b[1] >> 6) & 0x3, (b[1] >> 4) & 0x3, (b[1] >> 2) & 0x3, (b[1] >> 0) & 0x3)

        pixels = [get_bits(data[index: index + 2]) for index in range(0, len(data), 2)]
        with open(filename + ".png", "wb") as f:
            w = png.Writer(width, height, palette=palette, bitdepth=2, greyscale=False, alpha=False)
            w.write(f, pixels)

    def _save_song(self, filename, data, *_):
        self._save_raw_data(filename + ".mid", data)

    def save_instruments_to_soundfont(self, output_path):
        logger.info(f"Saving instrument data to soundfont: JAGWOLF3D.SF2")
        instrument_lumps = list(self.get_lumps_of_type(LumpType.Instrument.name))
        melodic_instruments = [name for name in instrument_lumps if name.startswith("I")]
        percussion_instruments = [name for name in instrument_lumps if name.startswith("P")]

        def add_instrument_from_lump(name):
            logger.info(f"Loading {name}")
            name, data = self.get_lump_by_name(name)
            data_length, loop_offset, loop_end, pitch = struct.unpack('>IIII', data[0:16])
            # logger.debug(f"{pitch:02x}, {pitch:08b}, {pitch} => {pitch & 0x7f} - {loop_offset}")
            if loop_offset == 0xffffffff:
                loop_offset = 0
                loop_end = 0
            # The first 16 bytes are header.  Skip them.
            data = data[16:]
            return (sf2.add_sample(name, data, loop_offset, loop_end, 22050, pitch & 0x7f,
                                   bits_per_sample=8, signed=False),
                    sf2.add_instrument(name),
                    bool(loop_offset > 0))

        sf2 = soundfont.SoundFontBuilder()
        sf2.bank_name = b"JAGWOLF3D.SF2"
        # Melodic instruments first.
        for lump_name in melodic_instruments:
            sample_index, instrument_index, loops = add_instrument_from_lump(lump_name)
            sf2.add_instrument_zone(
                sf2.create_instrument_generators(
                        sample_index, key_range=(0, 127), vel_range=(0, 127),
                        sample_modes=soundfont.SampleMode.LOOPING if loops else soundfont.SampleMode.NO_LOOP
                ), ()
            )
            sf2.add_preset(lump_name, int(lump_name[1:]) - 1, 0)
            sf2.add_preset_zone(
                sf2.create_prefix_generators(
                        instrument_index
                ), ()
            )
        # Percussion instruments last.  They hang from the same preset
        if percussion_instruments:
            # Use a single preset for all percussion instruments/samples.
            sf2.add_preset("PERCUSSION", 0, 128)
            for lump_name in percussion_instruments:
                sample_index, instrument_index, loops = add_instrument_from_lump(lump_name)
                drum_note = int(lump_name[1:])
                sf2.add_instrument_zone(
                        sf2.create_instrument_generators(
                                sample_index,
                                key_range=(drum_note, drum_note),
                                vel_range=(0, 127),
                                release_vol_env=1200,  # 2 second release so percussion isn't choppy,1200log2(2) = 1200
                                sample_modes=soundfont.SampleMode.LOOPING if loops else soundfont.SampleMode.NO_LOOP,
                                overriding_root_key=drum_note,
                        ), (
                            # soundfont.ModulatorList.midi_note_on_velocity_to_filter_cutoff()
                        )
                )
                sf2.add_preset_zone(
                        sf2.create_prefix_generators(
                                instrument_index
                        ), ()
                )
        sf2_data = sf2.build()
        with open(os.path.join(output_path, "JAGWOLF3D.SF2"), "wb") as f:
            f.write(sf2_data)

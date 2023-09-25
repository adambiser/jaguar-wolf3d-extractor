import io
import logging
import struct
from extractor.utils import read_ubyte, read_ushort, write_int, write_short

logger = logging.getLogger("gamemaps")


class GameMap:
    """Reads a Wolfenstein 3D map stored in the Jaguar format.

    Can convert to the DOS format and save to the WDC file format.
    """
    # Config settings
    DETECT_PUSHWALL_DIRECTION_WHEN_CONVERTING_TO_DOS = False
    # Constants
    _MAP_SIZE = 64
    _PLANE_COUNT = 2
    _FLOOR_CODE_START = 0x6c
    _FLOOR_CODE_STOP = 0x8f
    _DOOR_CODE_START = 0x5a
    _DOOR_CODE_STOP = 0x61
    _PUSHWALL = 0x62
    # For pushwall direction detection
    _NORTH = 0x1
    _SOUTH = 0x2
    _WEST = 0x4
    _EAST = 0x8

    def __init__(self, name, data):
        self.name = name
        self._f = io.BytesIO(data)
        self._floorcodes = None
        self._walls = None
        self._objects = None
        self._read_tiles()
        self._read_objects()

    def _read_tiles(self):
        self._walls = [read_ubyte(self._f) for _ in range(GameMap._MAP_SIZE * GameMap._MAP_SIZE)]
        self._floorcodes = [read_ubyte(self._f) for _ in range(64)]

    def _read_objects(self):
        object_count = read_ushort(self._f)
        self._f.seek(0x6, io.SEEK_CUR)
        # Read the object list.
        self._objects = []
        for o in range(object_count):
            bytes_x = self._f.read(1)
            if bytes_x == '':
                break
            x = struct.unpack('<B', bytes_x)[0]  # type: int
            y = read_ubyte(self._f)
            # assert 0 <= x <= Map._MAP_SIZE, 'Object off the map at {}, {}'.format(x, y)
            # assert 0 <= y <= Map._MAP_SIZE, 'Object off the map at {}, {}'.format(x, y)
            if not (0 <= x <= GameMap._MAP_SIZE and 0 <= y <= GameMap._MAP_SIZE):
                logger.warning(f'{self.name} had an object located off the map at {x}, {y}. Correcting.')
            # Correct out of bounds objects... TODO why does this happen?
            if x < 0:
                x += GameMap._MAP_SIZE
            if x >= GameMap._MAP_SIZE:
                x -= GameMap._MAP_SIZE
            if y < 0:
                y += GameMap._MAP_SIZE
            if y >= GameMap._MAP_SIZE:
                y -= GameMap._MAP_SIZE
            object_code = read_ubyte(self._f)
            self._objects.append({
                'x': x,
                'y': y,
                'code': object_code
                })
            # Pushwalls have an extra byte indicating its wall tile.
            if object_code == GameMap._PUSHWALL:
                self._objects[-1]['wall'] = read_ubyte(self._f)

    def generate_dos_map(self):
        """Converts the SNES map data to DOS map format.

        This is not perfect because of how pushwalls work in the SNES.
        See _fix_pushwall() for further information.

        Returns a dict with the map's name in 'name' and plane data in 'tiles'.
        """
        # Convert wall code
        # noinspection PyUnusedLocal
        tiles = [[0 for x in range(len(self._walls))] for p in range(GameMap._PLANE_COUNT)]
        for index in range(0, len(self._walls)):
            tiles[0][index] = self._walls[index]
            if tiles[0][index] >= 0x80:
                tiles[0][index] -= 0x80
            elif tiles[0][index] < 64:
                tiles[0][index] = GameMap._FLOOR_CODE_START + self._floorcodes[tiles[0][index]]
        # Place objects.
        for obj in self._objects:
            index = obj['x'] + obj['y'] * GameMap._MAP_SIZE
            # Doors are stored in the object plane. The wall plane has a floor code for these tiles.
            # Place doors in the wall plane instead.
            if GameMap._DOOR_CODE_START <= obj['code'] <= GameMap._DOOR_CODE_STOP:
                tiles[0][index] = obj['code']
            else:
                tiles[1][index] = obj['code']
                # Pushwalls have an extra byte indicating the wall tile. The wall plane has a floor code.
                # Place the wall tile in the wall plane for DOS maps.
                if obj['code'] == GameMap._PUSHWALL:
                    GameMap._fix_pushwall(self.name, tiles, obj)
        return {
            'name': self.name,
            'tiles': tiles,
            }

    @staticmethod
    def _fix_pushwall(map_name, tiles, obj):
        """Converts the SNES pushwalls into tiles that DOS pushwalls need to work.

        SNES pushwalls are objects with a wall code that moves two spaces and go into a wall in its final resting spot.

        DOS pushwalls are moving walls and move two spots or until they hit a wall.

        This code places a pushwall's wall code into the wall plane and when
        DETECT_PUSHWALL_DIRECTION_WHEN_CONVERTING_TO_DOS is True, this attempts to find the direction the pushwall is
        supposed to move and sets that wall tile to the appropriate floor code.
        """
        index = obj['x'] + obj['y'] * GameMap._MAP_SIZE
        tiles[0][index] = obj['wall']
        if not GameMap.DETECT_PUSHWALL_DIRECTION_WHEN_CONVERTING_TO_DOS:
            return
        # Check each direction to find all valid moves.
        move_dir = 0
        if GameMap._is_valid_pushwall_direction(tiles, obj, 'y', -1):
            move_dir |= GameMap._NORTH
        if GameMap._is_valid_pushwall_direction(tiles, obj, 'y', 1):
            move_dir |= GameMap._SOUTH
        if GameMap._is_valid_pushwall_direction(tiles, obj, 'x', -1):
            move_dir |= GameMap._WEST
        if GameMap._is_valid_pushwall_direction(tiles, obj, 'x', 1):
            move_dir |= GameMap._EAST
        # If there's only one valid move direction, set the end tile to be the floor code.
        if move_dir == GameMap._NORTH:
            tiles[0][index - GameMap._MAP_SIZE * 2] = tiles[0][index - GameMap._MAP_SIZE]
        elif move_dir == GameMap._SOUTH:
            tiles[0][index + GameMap._MAP_SIZE * 2] = tiles[0][index + GameMap._MAP_SIZE]
        elif move_dir == GameMap._WEST:
            tiles[0][index - 2] = tiles[0][index - 1]
        elif move_dir == GameMap._EAST:
            tiles[0][index + 2] = tiles[0][index + 1]
        else:
            # Did not find one and only one direction. Report it.
            dirs = []
            if move_dir == 0:
                dirs.append("none")
            else:
                if move_dir & GameMap._NORTH:
                    dirs.append("north")
                if move_dir & GameMap._SOUTH:
                    dirs.append("south")
                if move_dir & GameMap._WEST:
                    dirs.append("west")
                if move_dir & GameMap._EAST:
                    dirs.append("east")
            logger.error(f'{map_name} - Could not determine direction for pushwall at {obj["x"]},{obj["y"]}, '
                         f'choices: {", ".join(dirs)}')

    @staticmethod
    def _is_valid_pushwall_direction(tiles, obj, move_coord_name, move_step):
        """Returns true if direction is a valid move for a pushwall."""
        other_coord_name = 'x' if move_coord_name == 'y' else 'y'
        steps = [{
            move_coord_name: obj[move_coord_name] + (x + 1) * move_step,
            other_coord_name: obj[other_coord_name]
            } for x in range(2)]
        # Bounds check.
        if not (1 <= steps[1][move_coord_name] < GameMap._MAP_SIZE - 1):
            return False
        # Make sure the first step is a floor code.
        if not GameMap._is_dos_floor_code(tiles[0][steps[0]['x'] + steps[0]['y'] * GameMap._MAP_SIZE]):
            return False
        # See if the last step is a wall that matches the pushwall wall code.
        return tiles[0][steps[1]['x'] + steps[1]['y'] * GameMap._MAP_SIZE] == obj['wall']

    @staticmethod
    def _is_dos_floor_code(code: int) -> bool:
        """Returns True when code is a valid DOS map floor code."""
        return GameMap._FLOOR_CODE_START <= code <= GameMap._FLOOR_CODE_STOP

    @staticmethod
    def save_as_wdc_map_file(filename: str, maps):
        """Saves all given maps to a single WDC map file

        This assumes that the given maps are in the DOS map format.
        """
        # print "Saving %d maps to %s" % (len(maps), filename)
        with open(filename, 'wb') as f:
            f.write(b'WDC3.1')
            write_int(f, len(maps))
            write_short(f, GameMap._PLANE_COUNT)
            write_short(f, 16)  # map name length
            for m in maps:
                # print(m['name'])
                f.write(bytes(m['name'] + '\00' * (16 - len(m['name'])), encoding="ascii"))
                write_short(f, GameMap._MAP_SIZE)
                write_short(f, GameMap._MAP_SIZE)
                for p in range(GameMap._PLANE_COUNT):
                    f.write(struct.pack('<{}H'.format(len(m['tiles'][p])), *m['tiles'][p]))

    def save(self, filename):
        """Saves the map to a WDC map file."""
        GameMap.save_as_wdc_map_file(filename, [self.generate_dos_map()])

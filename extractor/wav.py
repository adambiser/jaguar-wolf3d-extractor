import struct


def write_short(f, x: int):
    """Writes a signed short"""
    f.write(struct.pack('<h', x))


def write_int(f, x: int):
    """Writes a signed integer."""
    f.write(struct.pack('<i', x))


def clamp_short(x):
    """Clamps a signed short to be within its upper and lower bounds."""
    return -32768 if x < -32768 else 32767 if x > 32767 else x


class Writer:
    # Configuration constants
    INCLUDE_LOOP_CUE_CHUNK_IN_WAV = True
    INCLUDE_LOOP_SMPL_CHUNK_IN_WAV = True

    def __init__(self, sample_rate: int,
                 channels: int,
                 bits_per_sample: int,
                 signed: bool = False):
        self.sample_rate = sample_rate
        self.channels = channels
        self.bits_per_sample = bits_per_sample
        self.bytes_per_sample = self.bits_per_sample // 8
        self.signed = signed

    def write(self, file, sound_data: bytes, loop_offset=None):
        """Saves the sound data to a WAV file."""
        # Write the header.
        if self.bytes_per_sample == 1 and len(sound_data) % 2 == 1:
            # pad to word align the data
            sound_data += b'\00' if self.signed else b'\x80'
        chunk_size = 36 + len(sound_data) * self.bytes_per_sample
        if loop_offset is not None:
            if Writer.INCLUDE_LOOP_CUE_CHUNK_IN_WAV:
                chunk_size += 36  # cue_chunk_size
                chunk_size += 30  # list_chunk_size
            if Writer.INCLUDE_LOOP_SMPL_CHUNK_IN_WAV:
                chunk_size += 68  # smpl_chunk_size
        # WAV header.
        file.write(b"RIFF")
        write_int(file, chunk_size)
        file.write(b"WAVE")
        file.write(b"fmt ")
        write_int(file, 16)  # subchunk size
        write_short(file, 1)  # PCM
        write_short(file, self.channels)
        write_int(file, self.sample_rate)
        write_int(file, self.sample_rate * self.bytes_per_sample * self.channels)
        write_short(file, self.bytes_per_sample * self.channels)
        write_short(file, self.bits_per_sample)
        # data chunk
        file.write(b"data")
        write_int(file, len(sound_data) * self.bytes_per_sample)
        pack_fmt = 'B' if self.bits_per_sample == 8 else "h"
        file.write(struct.pack(pack_fmt * len(sound_data), *sound_data))
        if loop_offset is not None:
            # smpl chunk (put first or Goldwave complains about internal chunk size)
            if Writer.INCLUDE_LOOP_SMPL_CHUNK_IN_WAV:
                file.write(b"smpl")
                write_int(file, 60)  # chunk size
                write_int(file, 0)  # manufacturer
                write_int(file, 0)  # product
                write_int(file, 1000000000 // self.sample_rate)  # sample period (samples per nanosecond)
                write_int(file, 60)  # MIDI unity note (C5)
                write_int(file, 0)  # MIDI pitch fraction
                write_int(file, 0)  # SMPTE format
                write_int(file, 0)  # SMPTE offset
                write_int(file, 1)  # sample loops
                write_int(file, 0)  # sampler data
                write_int(file, 0)  # cue point ID
                write_int(file, 0)  # type (loop forward)
                write_int(file, loop_offset)  # start sample number
                write_int(file, len(sound_data) // self.channels)  # end sample number
                write_int(file, 0)  # fraction
                write_int(file, 0)  # playcount
            if Writer.INCLUDE_LOOP_CUE_CHUNK_IN_WAV:
                # cue chunk
                file.write(b"cue ")
                write_int(file, 4 + 1 * 24)  # chunk data size
                write_int(file, 1)  # number of cue points
                write_int(file, 0)  # ID
                write_int(file, loop_offset)  # play order position
                file.write(b"data")  # data chunk id
                write_int(file, 0)  # chunk start
                write_int(file, 0)  # block start
                write_int(file, loop_offset)  # sample offset
                # list chunk, for cue label
                file.write(b"LIST")  # Goldwave only recognizes uppercase
                write_int(file, 22)  # 4 + 4 + 4 + 4 + 6
                file.write(b"adtl")
                file.write(b"labl")
                write_int(file, 4 + 6)  # "loop" + NUL + NUL
                write_int(file, 0)  # cue point id
                file.write(b"loop\0\0")

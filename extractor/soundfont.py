# A simple SoundFont file (sf2) builder.
# TODO support 24-bit samples, format 2.4
from dataclasses import dataclass as _dataclass
from enum import IntEnum
import extractor.riff as riff
import struct as _struct
import typing as _typing

# Constant to use to make global zones a bit clearer.
GLOBAL_ZONE = None


class SampleType(IntEnum):
    MONO = 1
    RIGHT = 2
    LEFT = 4
    LINKED = 8
    ROM_MONO = 32769
    ROM_RIGHT = 32770
    ROM_LEFT = 32772
    ROM_LINKED = 32776


# Generator.sample_modes values.
class SampleMode(IntEnum):
    NO_LOOP = 0
    LOOPING = 1
    NO_LOOP2 = 2
    LOOPING_PLUS_REMAINDER = 3


# Modulator index values when CC flag is 0.
class SourceController(IntEnum):
    NONE = 0
    NOTE_ON_VELOCITY = 2
    NOTE_ON_KEY_NUMBER = 3
    POLY_PRESSURE = 10
    CHANNEL_PRESSURE = 13
    PITCH_WHEEL = 14
    PITCH_WHEEL_SENSITIVITY = 16
    LINK = 127


# Modulator direction values.
class SourceDirection(IntEnum):
    MIN_TO_MAX = 0
    MAX_TO_MIN = 1


# Modulator polarity values.
class SourcePolarity(IntEnum):
    UNIPOLAR = 0  # 0..1
    BIPOLAR = 1  # -1..1


# Modulator type values.
class SourceType(IntEnum):
    LINEAR = 0
    CONCAVE = 1
    CONVEX = 2
    SWITCH = 3


# Modulator transform values.
class ModulatorTransform(IntEnum):
    LINEAR = 0
    ABSOLUTE_VALUE = 2


class Generator(IntEnum):
    START_ADDRS_OFFSET = 0
    END_ADDRS_OFFSET = 1
    STARTLOOP_ADDRS_OFFSET = 2
    ENDLOOP_ADDRS_OFFSET = 3
    START_ADDRS_COARSE_OFFSET = 4
    MOD_LFO_TO_PITCH = 5
    VIB_LFO_TO_PITCH = 6
    MOD_ENV_TO_PITCH = 7
    INITIAL_FILTER_FC = 8
    INITIAL_FILTER_Q = 9
    MOD_LFO_TO_FILTER_FC = 10
    MOD_ENV_TO_FILTER_FC = 11
    END_ADDRS_COARSE_OFFSET = 12
    MOD_LFO_TO_VOLUME = 13
    # UNUSED1 = 14
    CHORUS_EFFECTS_SEND = 15
    REVERB_EFFECTS_SEND = 16
    PAN = 17
    # UNUSED2 = 18
    # UNUSED3 = 19
    # UNUSED4 = 20
    DELAY_MOD_LFO = 21
    FREQ_MOD_LFO = 22
    DELAY_VIB_LFO = 23
    FREQ_VIB_LFO = 24
    DELAY_MOD_ENV = 25
    ATTACK_MOD_ENV = 26
    HOLD_MOD_ENV = 27
    DECAY_MOD_ENV = 28
    SUSTAIN_MOD_ENV = 29
    RELEASE_MOD_ENV = 30
    KEYNUM_TO_MOD_ENV_HOLD = 31
    KEYNUM_TO_MOD_ENV_DECAY = 32
    DELAY_VOL_ENV = 33
    ATTACK_VOL_ENV = 34
    HOLD_VOL_ENV = 35
    DECAY_VOL_ENV = 36
    SUSTAIN_VOL_ENV = 37
    RELEASE_VOL_ENV = 38
    KEYNUM_TO_VOL_ENV_HOLD = 39
    KEYNUM_TO_VOL_ENV_DECAY = 40
    INSTRUMENT = 41
    # RESERVED1 = 42
    KEY_RANGE = 43
    VEL_RANGE = 44
    STARTLOOP_ADDRS_COARSE_OFFSET = 45
    KEYNUM = 46
    VELOCITY = 47
    INITIAL_ATTENUATION = 48
    # RESERVED2 = 49
    ENDLOOP_ADDRS_COARSE_OFFSET = 50
    COARSE_TUNE = 51
    FINE_TUNE = 52
    SAMPLE_ID = 53
    SAMPLE_MODES = 54
    # RESERVED3 = 55
    SCALE_TUNING = 56
    EXCLUSIVE_CLASS = 57
    OVERRIDING_ROOT_KEY = 58
    # UNUSED5 = 59
    # END_OPEN = 60


@_dataclass
class _PresetHeader:
    name: str  # char[20]
    preset: int  # word
    bank: int  # word
    preset_bag_index: int  # word
    library: int = 0  # dword
    genre: int = 0  # dword
    morphology: int = 0  # dword

    def pack(self):
        return _struct.pack("<20sHHHIII", self.name.encode("ascii"), self.preset, self.bank, self.preset_bag_index,
                            self.library, self.genre, self.morphology)


@_dataclass
class _Bag:  # PresetBag, InstBag
    generator_index: int  # word
    modulator_index: int  # word

    def pack(self):
        return _struct.pack("<HH", self.generator_index, self.modulator_index)


@_dataclass
class ModulatorSource:
    source_type: _typing.Union[int, SourceType]
    polarity: _typing.Union[int, SourcePolarity]
    direction: _typing.Union[int, SourceDirection]
    cc_flag: bool
    index: _typing.Union[int, SourceController]

    @classmethod
    def empty(cls):
        return ModulatorSource(0, 0, 0, False, 0)

    def pack(self, is_amount_source: bool = False):
        # Perform some value checking here.
        assert self.source_type & ~0x3f == 0
        assert self.polarity & ~1 == 0
        assert self.direction & ~1 == 0
        if self.cc_flag:
            assert self.index not in (0, 6, 32, 38, 98, 99, 100, 101, 120, 121, 122, 123, 124, 125, 126, 127), \
                f"An index of {self.index} is illegal when the CC flag is set."
        else:
            assert self.index in (0, 2, 3, 10, 13, 14, 16), \
                f"An index of {self.index} is illegal when the CC flag is not set."
            assert not (is_amount_source and self.index == 127), \
                f"An index of {self.index} when the CC flag is not set is not supported for an amount source."
        return ((self.source_type << 10) +
                (self.polarity << 9) +
                (self.direction << 8) +
                (self.cc_flag << 7) +
                self.index)


@_dataclass
class ModulatorList:
    source: ModulatorSource
    destination: Generator
    amount: int  # short, signed
    amount_source: ModulatorSource
    transform: _typing.Union[int, ModulatorTransform]

    def pack(self):
        return _struct.pack("<HHhHH",
                            self.source.pack(False), self.destination, self.amount,
                            self.amount_source.pack(True), self.transform)

    # Some default modulators from the specs
    @classmethod
    def midi_note_on_velocity_to_initial_attenuation(cls, amount=960):
        return cls(ModulatorSource(SourceType.CONCAVE,
                                   SourcePolarity.UNIPOLAR,
                                   SourceDirection.MAX_TO_MIN,
                                   False, SourceController.NOTE_ON_VELOCITY),
                   Generator.INITIAL_ATTENUATION, amount, ModulatorSource.empty(), ModulatorTransform.LINEAR),

    @classmethod
    def midi_note_on_velocity_to_filter_cutoff(cls, amount=-2400):
        return cls(ModulatorSource(SourceType.LINEAR,
                                   SourcePolarity.UNIPOLAR,
                                   SourceDirection.MAX_TO_MIN,
                                   False, SourceController.NOTE_ON_VELOCITY),
                   Generator.INITIAL_FILTER_FC, amount, ModulatorSource.empty(), ModulatorTransform.LINEAR),

    @classmethod
    def midi_channel_pressure_to_vibrato_lfo_pitch_depth(cls, amount=50):
        return cls(ModulatorSource(SourceType.LINEAR,
                                   SourcePolarity.UNIPOLAR,
                                   SourceDirection.MIN_TO_MAX,
                                   False, SourceController.CHANNEL_PRESSURE),
                   Generator.VIB_LFO_TO_PITCH, amount, ModulatorSource.empty(), ModulatorTransform.LINEAR),

    @classmethod
    def midi_continuous_controller_1_to_vibrato_lfo_pitch_depth(cls, amount=50):
        return cls(ModulatorSource(SourceType.LINEAR,
                                   SourcePolarity.UNIPOLAR,
                                   SourceDirection.MIN_TO_MAX,
                                   True, 1),
                   Generator.VIB_LFO_TO_PITCH, amount, ModulatorSource.empty(), ModulatorTransform.LINEAR),

    @classmethod
    def midi_continuous_controller_7_to_initial_attenuation(cls, amount=960):
        return cls(ModulatorSource(SourceType.CONCAVE,
                                   SourcePolarity.UNIPOLAR,
                                   SourceDirection.MAX_TO_MIN,
                                   True, 7),
                   Generator.INITIAL_ATTENUATION, amount, ModulatorSource.empty(), ModulatorTransform.LINEAR),

    @classmethod
    def midi_continuous_controller_10_to_pan_position(cls, amount=1000):
        return cls(ModulatorSource(SourceType.LINEAR,
                                   SourcePolarity.BIPOLAR,
                                   SourceDirection.MIN_TO_MAX,
                                   True, 10),
                   Generator.PAN, amount, ModulatorSource.empty(), ModulatorTransform.LINEAR),

    @classmethod
    def midi_continuous_controller_11_to_initial_attenuation(cls, amount=960):
        return cls(ModulatorSource(SourceType.CONCAVE,
                                   SourcePolarity.UNIPOLAR,
                                   SourceDirection.MAX_TO_MIN,
                                   True, 11),
                   Generator.INITIAL_ATTENUATION, amount, ModulatorSource.empty(), ModulatorTransform.LINEAR),

    @classmethod
    def midi_continuous_controller_91_to_reverb_effects_send(cls, amount=200):
        return cls(ModulatorSource(SourceType.LINEAR,
                                   SourcePolarity.UNIPOLAR,
                                   SourceDirection.MIN_TO_MAX,
                                   True, 91),
                   Generator.REVERB_EFFECTS_SEND, amount, ModulatorSource.empty(), ModulatorTransform.LINEAR),

    @classmethod
    def midi_continuous_controller_93_to_chorus_effects_send(cls, amount=200):
        return cls(ModulatorSource(SourceType.LINEAR,
                                   SourcePolarity.UNIPOLAR,
                                   SourceDirection.MIN_TO_MAX,
                                   True, 9),
                   Generator.CHORUS_EFFECTS_SEND, amount, ModulatorSource.empty(), ModulatorTransform.LINEAR),

    @classmethod
    def midi_pitch_wheel_to_initial_pitch_controlled_by_midi_pitch_wheel_sensitivity(cls, amount=12700):
        return cls(ModulatorSource(SourceType.LINEAR,
                                   SourcePolarity.BIPOLAR,
                                   SourceDirection.MIN_TO_MAX,
                                   False, SourceController.PITCH_WHEEL),
                   # Specs say "Initial Pitch"?
                   Generator.FINE_TUNE, amount,
                   ModulatorSource(SourceType.LINEAR,
                                   SourcePolarity.UNIPOLAR,
                                   SourceDirection.MIN_TO_MAX,
                                   False, SourceController.PITCH_WHEEL_SENSITIVITY),
                   ModulatorTransform.LINEAR),


@_dataclass
class AmountType:
    amount: bytes  # short

    def __init__(self, amount):
        try:
            low, high = amount
            self.amount = _struct.pack("<BB", low, high)
        except TypeError:
            if amount < 0:
                self.amount = _struct.pack("<h", amount)
            else:
                self.amount = _struct.pack("<H", amount)

    def pack(self):
        return self.amount  # should already be packed


@_dataclass
class GeneratorList:
    operator: Generator
    amount: AmountType

    def pack(self):
        return _struct.pack("<H2s", self.operator, self.amount.pack())


@_dataclass
class _Instrument:
    name: str  # char[20
    instrument_bag_index: int  # word

    def pack(self):
        return _struct.pack("<20sH", self.name.encode("ascii"), self.instrument_bag_index)


@_dataclass
class _Sample:
    name: str  # char[20]
    start: int  # dword
    end: int  # dword
    start_loop: int  # dword
    end_loop: int  # dword
    sample_rate: int  # dword
    original_pitch: int  # byte
    pitch_correction: int = 0  # char
    sample_link: int = 0  # word
    sample_type: int = SampleType.MONO  # SFSampleLink

    def pack(self):
        return _struct.pack("<20sIIIIIBbHH", self.name.encode("ascii"), self.start, self.end,
                            self.start_loop, self.end_loop, self.sample_rate, self.original_pitch,
                            self.pitch_correction, self.sample_link, self.sample_type)


class SoundFontBuilder:
    def __init__(self):
        # Info
        self.sound_engine = b'EMU8000'  # Required. Refers to the target Sound Engine.  ASCII.  256 byte limit.
        self.bank_name = b'General MIDI'  # Required. Refers to the Sound Font Bank Name.  ASCII.  256 byte limit.
        self.rom_name = b''  # Refers to the Sound ROM Name.  ASCII.  256 byte limit.
        self.rom_version = b''  # Refers to the Sound ROM Version.  Major.Minor
        self.creation_date = b''  # Refers to the Date of Creation of the Bank.  ASCII.  256 byte limit.
        self.sound_designers_and_engineers = b''  # Sound Designers and Engineers for the Bank.  ASCII.  256 byte limit.
        self.intended_product = b''  # Product for which the Bank was intended.  ASCII.  256 byte limit.
        self.copyright = b''  # Contains any Copyright message.  ASCII.  256 byte limit.
        self.comments = b''  # Contains any Comments on the Bank.  ASCII.  65536 byte limit.
        self.tools_used = b''  # The tools used to create and alter the bank  ASCII.  256 byte limit.
        # Sample data.
        self._smpl = b''
        # self._sm24 = b''  # Only for file version 2.4
        # Initialize lists with the terminator record.
        self._phdr = [_PresetHeader("EOP", 0, 0, 0, 0, 0, 0)]  # The Preset Headers
        self._pbag = [_Bag(0, 0)]  # The Preset Index list
        self._pmod = [ModulatorList(ModulatorSource.empty(), Generator(0), 0,
                                    ModulatorSource.empty(), 0)]  # The Preset Modulator list
        self._pgen = [GeneratorList(Generator(0), AmountType(0))]  # The Preset Generator list
        self._inst = [_Instrument("EOI", 0)]  # The Instrument Names and Indices
        self._ibag = [_Bag(0, 0)]  # The Instrument Index list
        self._imod = [ModulatorList(ModulatorSource.empty(), Generator(0), 0,
                                    ModulatorSource.empty(), 0)]  # The Instrument Modulator list
        self._igen = [GeneratorList(Generator(0), AmountType(0))]  # The Instrument Generator list
        self._shdr = [_Sample("EOS", 0, 0, 0, 0, 0, 0, 0, 0, 0)]  # The Sample Headers

    @staticmethod
    def _add_records(record_list, records_to_add):
        # Always return the current index, even when not actually adding.
        index = len(record_list) - 1
        if records_to_add:
            # Can't use extend because we're inserting in front of the terminal record.
            for record in records_to_add:
                record_list.insert(-1, record)
        return index

    def add_preset(self, name: str, preset: int, bank: int):
        assert 0 < len(name) <= 20
        assert 0 <= preset <= 127
        assert 0 <= bank <= 128
        library = 0  # reserved
        genre = 0  # reserved
        morphology = 0  # reserved
        bag_index = len(self._pbag) - 1
        self._phdr.insert(-1, _PresetHeader(name, preset, bank, bag_index, library, genre, morphology))
        return len(self._phdr) - 2  # -2 because -1 is the terminal record.

    def add_preset_zone(self,
                        generator: _typing.Iterable[GeneratorList],
                        modulator: _typing.Iterable[ModulatorList]):
        modulator_index = SoundFontBuilder._add_records(self._pmod, modulator)
        generator_index = SoundFontBuilder._add_records(self._pgen, generator)
        SoundFontBuilder._add_records(self._pbag, [_Bag(generator_index, modulator_index)])

    def add_instrument(self, name: str):
        bag_index = len(self._ibag) - 1
        self._inst.insert(-1, _Instrument(name, bag_index))
        return len(self._inst) - 2  # -2 because -1 is the terminal record.

    def add_instrument_zone(self,
                            generator: _typing.Iterable[GeneratorList],
                            modulator: _typing.Iterable[ModulatorList]):
        generator_index = SoundFontBuilder._add_records(self._igen, generator)
        modulator_index = SoundFontBuilder._add_records(self._imod, modulator)
        SoundFontBuilder._add_records(self._ibag, [_Bag(generator_index, modulator_index)])

    def add_sample(self, name: str, data: bytes, start_loop: int, end_loop: int, sample_rate: int, original_pitch: int,
                   pitch_correction: int = 0, sample_type: int = SampleType.MONO,
                   bits_per_sample: int = 16, signed: bool = True):
        """Adds a 16-bit signed sample."""
        assert 0 <= start_loop < len(data)
        assert 0 <= end_loop <= len(data)
        assert 400 <= sample_rate <= 50000
        assert 0 <= original_pitch <= 127 or original_pitch == 255
        assert -128 <= pitch_correction <= 127
        assert bits_per_sample in (8, 16)
        data = _convert_sample_to_16bit_signed(data, bits_per_sample, signed)
        start_index = len(self._smpl) // 2
        self._smpl += data
        end_index = len(self._smpl) // 2
        # Specs: Each sample is followed by a minimum of forty-six zero valued sample data points.
        self._smpl += b'\x00\x00' * 46
        self._shdr.insert(-1, _Sample(name, start_index, end_index, start_index + start_loop, start_index + end_loop,
                                      sample_rate, original_pitch, pitch_correction, 0, sample_type))
        return len(self._shdr) - 2  # -2 because -1 is the terminal record.

    def create_prefix_generators(
            self, instrument: _typing.Union[int, GLOBAL_ZONE],  *,
            key_range: _typing.Tuple[int, int] = None, vel_range: _typing.Tuple[int, int] = None,
            # General
            mod_lfo_to_pitch: int = None, vib_lfo_to_pitch: int = None, mod_env_to_pitch: int = None,
            initial_filter_fc: int = None, initial_filter_q: int = None, mod_lfo_to_filter_fc: int = None,
            mod_env_to_filter_fc: int = None, mod_lfo_to_volume: int = None, chorus_effects_send: int = None,
            reverb_effects_send: int = None, pan: int = None, delay_mod_lfo: int = None, freq_mod_lfo: int = None,
            delay_vib_lfo: int = None, freq_vib_lfo: int = None, delay_mod_env: int = None, attack_mod_env: int = None,
            hold_mod_env: int = None, decay_mod_env: int = None, sustain_mod_env: int = None,
            release_mod_env: int = None, keynum_to_mod_env_hold: int = None, keynum_to_mod_env_decay: int = None,
            delay_vol_env: int = None, attack_vol_env: int = None, hold_vol_env: int = None, decay_vol_env: int = None,
            sustain_vol_env: int = None, release_vol_env: int = None, keynum_to_vol_env_hold: int = None,
            keynum_to_vol_env_decay: int = None, initial_attenuation: int = None,  coarse_tune: int = None,
            fine_tune: int = None, scale_tuning: int = None):
        """
        Adds generators that can be on preset zones.
        Use an instrument of None to add the global zone (must only be 1 and must be the first zone).
        Performs value checking.
        """
        generators = []  # type: _typing.List[GeneratorList]
        # Required
        assert instrument is GLOBAL_ZONE or 0 <= instrument < len(self._inst) - 1
        # Optional, but must be first.
        if vel_range is not None and key_range is None:
            key_range = (0, 127)
        if key_range is not None:
            assert 0 <= key_range[0] <= 127 and 0 <= key_range[1] <= 127
            generators.append(GeneratorList(Generator.KEY_RANGE, AmountType(key_range)))
        if vel_range is not None:
            assert 0 <= vel_range[0] <= 127 and 0 <= vel_range[1] <= 127
            generators.append(GeneratorList(Generator.VEL_RANGE, AmountType(vel_range)))
        # Optional
        generators.extend(_create_optional_generators(
                mod_lfo_to_pitch, vib_lfo_to_pitch, mod_env_to_pitch,
                initial_filter_fc, initial_filter_q, mod_lfo_to_filter_fc,
                mod_env_to_filter_fc, mod_lfo_to_volume, chorus_effects_send,
                reverb_effects_send, pan, delay_mod_lfo, freq_mod_lfo,
                delay_vib_lfo, freq_vib_lfo, delay_mod_env, attack_mod_env,
                hold_mod_env, decay_mod_env, sustain_mod_env,
                release_mod_env, keynum_to_mod_env_hold, keynum_to_mod_env_decay,
                delay_vol_env, attack_vol_env, hold_vol_env, decay_vol_env,
                sustain_vol_env, release_vol_env, keynum_to_vol_env_hold,
                keynum_to_vol_env_decay, initial_attenuation, coarse_tune,
                fine_tune, scale_tuning
        ))
        # Must be last unless this is a global zone.
        if instrument is not GLOBAL_ZONE:
            generators.append(GeneratorList(Generator.INSTRUMENT, AmountType(instrument)))
        return generators

    def create_instrument_generators(
            self, sample_id: _typing.Union[int, GLOBAL_ZONE],  *,
            key_range: _typing.Tuple[int, int] = None, vel_range: _typing.Tuple[int, int] = None,
            # Instrument only
            start_addrs_offset: int = None, end_addrs_offset: int = None, startloop_addrs_offset: int = None,
            endloop_addrs_offset: int = None, start_addrs_coarse_offset: int = None,
            end_addrs_coarse_offset: int = None, startloop_addrs_coarse_offset: int = None,
            endloop_addrs_coarse_offset: int = None, keynum: int = None, velocity: int = None,
            sample_modes: int = None, exclusive_class: int = None, overriding_root_key: int = None,
            # General
            mod_lfo_to_pitch: int = None, vib_lfo_to_pitch: int = None, mod_env_to_pitch: int = None,
            initial_filter_fc: int = None, initial_filter_q: int = None, mod_lfo_to_filter_fc: int = None,
            mod_env_to_filter_fc: int = None, mod_lfo_to_volume: int = None, chorus_effects_send: int = None,
            reverb_effects_send: int = None, pan: int = None, delay_mod_lfo: int = None, freq_mod_lfo: int = None,
            delay_vib_lfo: int = None, freq_vib_lfo: int = None, delay_mod_env: int = None, attack_mod_env: int = None,
            hold_mod_env: int = None, decay_mod_env: int = None, sustain_mod_env: int = None,
            release_mod_env: int = None, keynum_to_mod_env_hold: int = None, keynum_to_mod_env_decay: int = None,
            delay_vol_env: int = None, attack_vol_env: int = None, hold_vol_env: int = None, decay_vol_env: int = None,
            sustain_vol_env: int = None, release_vol_env: int = None, keynum_to_vol_env_hold: int = None,
            keynum_to_vol_env_decay: int = None, initial_attenuation: int = None,  coarse_tune: int = None,
            fine_tune: int = None, scale_tuning: int = None):
        """
        Adds generators that can be on instrument zones.
        Use an instrument of None to add the global zone (must only be 1 and must be the first zone).
        Performs value checking.
        """
        generators = []  # type: _typing.List[GeneratorList]
        # Required, unless adding a global zone, for which it should be None.
        assert sample_id is GLOBAL_ZONE or 0 <= sample_id < len(self._shdr) - 1
        # Optional, but must be first.
        if vel_range is not None and key_range is None:
            key_range = (0, 127)
        if key_range is not None:
            assert 0 <= key_range[0] <= 127 and 0 <= key_range[1] <= 127
            generators.append(GeneratorList(Generator.KEY_RANGE, AmountType(key_range)))
        if vel_range is not None:
            assert 0 <= vel_range[0] <= 127 and 0 <= vel_range[1] <= 127
            generators.append(GeneratorList(Generator.VEL_RANGE, AmountType(vel_range)))
        # Instrument-only, optional
        if sample_id is not GLOBAL_ZONE:
            sample_start = self._shdr[sample_id].start
            sample_end = self._shdr[sample_id].end - 1
            _add_generators(generators, [
                (Generator.START_ADDRS_OFFSET, start_addrs_offset, sample_start, sample_end),
                (Generator.END_ADDRS_OFFSET, end_addrs_offset, sample_start, sample_end),
                (Generator.STARTLOOP_ADDRS_OFFSET, startloop_addrs_offset, sample_start, sample_end),
                (Generator.ENDLOOP_ADDRS_OFFSET, endloop_addrs_offset, sample_start, sample_end),
                (Generator.START_ADDRS_COARSE_OFFSET, start_addrs_coarse_offset, sample_start, sample_end),
                (Generator.END_ADDRS_COARSE_OFFSET, end_addrs_coarse_offset, sample_start, sample_end),
                (Generator.STARTLOOP_ADDRS_COARSE_OFFSET, startloop_addrs_coarse_offset, sample_start, sample_end),
                (Generator.ENDLOOP_ADDRS_COARSE_OFFSET, endloop_addrs_coarse_offset, sample_start, sample_end),
            ])
        _add_generators(generators, [
            (Generator.KEYNUM, keynum, 0, 127),  # Desc says number; chart says range.
            (Generator.VELOCITY, velocity, 0, 127),  # Desc says number; chart says range.
            (Generator.SAMPLE_MODES, sample_modes, SampleMode.NO_LOOP, SampleMode.LOOPING_PLUS_REMAINDER),
            (Generator.EXCLUSIVE_CLASS, exclusive_class, 1, 127),
            (Generator.OVERRIDING_ROOT_KEY, overriding_root_key, 0, 127),  # Desc says number; chart says range.
        ])
        # Optional
        generators.extend(_create_optional_generators(
                mod_lfo_to_pitch, vib_lfo_to_pitch, mod_env_to_pitch,
                initial_filter_fc, initial_filter_q, mod_lfo_to_filter_fc,
                mod_env_to_filter_fc, mod_lfo_to_volume, chorus_effects_send,
                reverb_effects_send, pan, delay_mod_lfo, freq_mod_lfo,
                delay_vib_lfo, freq_vib_lfo, delay_mod_env, attack_mod_env,
                hold_mod_env, decay_mod_env, sustain_mod_env,
                release_mod_env, keynum_to_mod_env_hold, keynum_to_mod_env_decay,
                delay_vol_env, attack_vol_env, hold_vol_env, decay_vol_env,
                sustain_vol_env, release_vol_env, keynum_to_vol_env_hold,
                keynum_to_vol_env_decay, initial_attenuation, coarse_tune,
                fine_tune, scale_tuning
        ))
        # Must be last unless this is a global zone.
        if sample_id is not GLOBAL_ZONE:
            generators.append(GeneratorList(Generator.SAMPLE_ID, AmountType(sample_id)))
        return generators

    @staticmethod
    def _pack_records(records):
        return b''.join(record.pack() for record in records)

    @staticmethod
    def _pack_version(version):
        major, minor = str(version).split(".", 1)
        return _struct.pack("<HH", int(major), int(minor))

    def build(self):
        # Prepare terminal records
        self._phdr[-1].preset_bag_index = len(self._pbag) - 1
        self._pbag[-1].generator_index = len(self._pgen) - 1
        self._pbag[-1].modulator_index = len(self._pmod) - 1
        self._inst[-1].instrument_bag_index = len(self._ibag) - 1
        self._ibag[-1].generator_index = len(self._igen) - 1
        self._ibag[-1].modulator_index = len(self._imod) - 1
        # return file data
        riff_data = riff.make_riff(b'sfbk', [
            riff.make_list(b'INFO', [
                riff.make_chunk(b'ifil', SoundFontBuilder._pack_version('2.1')),  # 2.1 - Sound Font File Version
                riff.make_chunk(b'isng', self.sound_engine + b'\x00'),
                riff.make_chunk(b'INAM', self.bank_name + b'\x00'),
                riff.make_chunk(b'irom', self.rom_name + b'\x00') if self.rom_name else b'',
                riff.make_chunk(b'iver', SoundFontBuilder._pack_version(self.rom_version))
                if self.rom_version else b'',  # Sound ROM Version
                riff.make_chunk(b'ICRD', self.creation_date + b'\x00') if self.creation_date else b'',
                riff.make_chunk(b'IENG', self.sound_designers_and_engineers + b'\x00')
                if self.sound_designers_and_engineers else b'',
                riff.make_chunk(b'IPRD', self.intended_product + b'\x00') if self.intended_product else b'',
                riff.make_chunk(b'ICOP', self.copyright + b'\x00') if self.copyright else b'',
                riff.make_chunk(b'ICMT', self.comments + b'\x00') if self.comments else b'',
                riff.make_chunk(b'ISFT', self.tools_used + b'\x00') if self.tools_used else b'',
            ]),
            riff.make_list(b'sdta', [
                riff.make_chunk(b'smpl', self._smpl),  # The Digital Audio Samples for the upper 16 bits
                # [<sm24-ck>] ; The Digital Audio Samples for the lower 8 bits
            ]),
            riff.make_list(b'pdta', [
                riff.make_chunk(b'phdr', SoundFontBuilder._pack_records(self._phdr)),  # The Preset Headers
                riff.make_chunk(b'pbag', SoundFontBuilder._pack_records(self._pbag)),  # The Preset Index list
                riff.make_chunk(b'pmod', SoundFontBuilder._pack_records(self._pmod)),  # The Preset Modulator list
                riff.make_chunk(b'pgen', SoundFontBuilder._pack_records(self._pgen)),  # The Preset Generator list
                riff.make_chunk(b'inst', SoundFontBuilder._pack_records(self._inst)),  # Instrument Names and Indices
                riff.make_chunk(b'ibag', SoundFontBuilder._pack_records(self._ibag)),  # The Instrument Index list
                riff.make_chunk(b'imod', SoundFontBuilder._pack_records(self._imod)),  # The Instrument Modulator list
                riff.make_chunk(b'igen', SoundFontBuilder._pack_records(self._igen)),  # The Instrument Generator list
                riff.make_chunk(b'shdr', SoundFontBuilder._pack_records(self._shdr)),  # The Sample Headers
            ]),
        ])
        return riff_data


def _convert_sample_to_16bit_signed(sample_data: bytes, bits_per_sample: int, signed: bool):
    if bits_per_sample == 16:
        if signed:
            return sample_data
        else:
            raise ValueError("16-bit unsigned data is not yet supported.")
    elif bits_per_sample == 8:
        sign_delta = 0 if signed else 128
        return b''.join([b'\x00' + bytes([b - sign_delta & 0xff]) for b in sample_data])
    raise ValueError(f"{bits_per_sample}-bit data is not yet supported.")


def _create_optional_generators(
        mod_lfo_to_pitch: int = None, vib_lfo_to_pitch: int = None, mod_env_to_pitch: int = None,
        initial_filter_fc: int = None, initial_filter_q: int = None, mod_lfo_to_filter_fc: int = None,
        mod_env_to_filter_fc: int = None, mod_lfo_to_volume: int = None, chorus_effects_send: int = None,
        reverb_effects_send: int = None, pan: int = None, delay_mod_lfo: int = None, freq_mod_lfo: int = None,
        delay_vib_lfo: int = None, freq_vib_lfo: int = None, delay_mod_env: int = None, attack_mod_env: int = None,
        hold_mod_env: int = None, decay_mod_env: int = None, sustain_mod_env: int = None,
        release_mod_env: int = None, keynum_to_mod_env_hold: int = None, keynum_to_mod_env_decay: int = None,
        delay_vol_env: int = None, attack_vol_env: int = None, hold_vol_env: int = None, decay_vol_env: int = None,
        sustain_vol_env: int = None, release_vol_env: int = None, keynum_to_vol_env_hold: int = None,
        keynum_to_vol_env_decay: int = None, initial_attenuation: int = None, coarse_tune: int = None,
        fine_tune: int = None, scale_tuning: int = None):
    """Adds all optional generators that can be on either preset or instrument zones.  Performs value checking."""
    generators = []
    _add_generators(generators, [
        (Generator.MOD_LFO_TO_PITCH, mod_lfo_to_pitch, -12000, 12000),
        (Generator.VIB_LFO_TO_PITCH, vib_lfo_to_pitch, -12000, 12000),
        (Generator.MOD_ENV_TO_PITCH, mod_env_to_pitch, -12000, 12000),
        (Generator.INITIAL_FILTER_FC, initial_filter_fc, 1500, 13500),
        (Generator.INITIAL_FILTER_Q, initial_filter_q, 0, 960),
        (Generator.MOD_LFO_TO_FILTER_FC, mod_lfo_to_filter_fc, -12000, 12000),
        (Generator.MOD_ENV_TO_FILTER_FC, mod_env_to_filter_fc, -12000, 12000),
        (Generator.MOD_LFO_TO_VOLUME, mod_lfo_to_volume, -960, 960),
        (Generator.CHORUS_EFFECTS_SEND, chorus_effects_send, 0, 1000),
        (Generator.REVERB_EFFECTS_SEND, reverb_effects_send, 0, 1000),
        (Generator.PAN, pan, -500, 500),
        (Generator.DELAY_MOD_LFO, delay_mod_lfo, -12000, 5000),
        (Generator.FREQ_MOD_LFO, freq_mod_lfo, -16000, 4500),
        (Generator.DELAY_VIB_LFO, delay_vib_lfo, -12000, 5000),
        (Generator.FREQ_VIB_LFO, freq_vib_lfo, -16000, 4500),
        (Generator.DELAY_MOD_ENV, delay_mod_env, -12000, 5000),
        (Generator.ATTACK_MOD_ENV, attack_mod_env, -12000, 8000),
        (Generator.HOLD_MOD_ENV, hold_mod_env, -12000, 5000),
        (Generator.DECAY_MOD_ENV, decay_mod_env, -12000, 8000),
        (Generator.SUSTAIN_MOD_ENV, sustain_mod_env, 0, 1000),
        (Generator.RELEASE_MOD_ENV, release_mod_env, -12000, 8000),
        (Generator.KEYNUM_TO_MOD_ENV_HOLD, keynum_to_mod_env_hold, -1200, 1200),
        (Generator.KEYNUM_TO_MOD_ENV_DECAY, keynum_to_mod_env_decay, -1200, 1200),
        (Generator.DELAY_VOL_ENV, delay_vol_env, -12000, 5000),
        (Generator.ATTACK_VOL_ENV, attack_vol_env, -12000, 8000),
        (Generator.HOLD_VOL_ENV, hold_vol_env, -12000, 5000),
        (Generator.DECAY_VOL_ENV, decay_vol_env, -12000, 8000),
        (Generator.SUSTAIN_VOL_ENV, sustain_vol_env, 0, 1440),
        (Generator.RELEASE_VOL_ENV, release_vol_env, -12000, 8000),
        (Generator.KEYNUM_TO_VOL_ENV_HOLD, keynum_to_vol_env_hold, -1200, 1200),
        (Generator.KEYNUM_TO_VOL_ENV_DECAY, keynum_to_vol_env_decay, -1200, 1200),
        (Generator.INITIAL_ATTENUATION, initial_attenuation, 0, 1440),
        (Generator.COARSE_TUNE, coarse_tune, -120, 120),
        (Generator.FINE_TUNE, fine_tune, -99, 99),
        (Generator.SCALE_TUNING, scale_tuning, 0, 1200),
    ])
    return generators


def _add_generators(generator_list: _typing.List[GeneratorList],
                    generators_to_add: _typing.Iterable[_typing.Tuple[Generator, int, int, int]]):
    for generator_info in generators_to_add:
        generator_type, value, min_allowed, max_allowed = generator_info
        if value is not None:
            assert min_allowed <= value <= max_allowed
            generator_list.append(GeneratorList(generator_type, AmountType(value)))

# How it works

Notes for anyone changing the code. All of this was worked out from the game files and tested in-game.

## Where the music lives

`Data\dt40_all.cpk` holds the menu music in every supported game:

| File | Purpose |
|---|---|
| `BGM_P2P.awb` | The audio: unencrypted HCA |
| `BGM_P2P.acb` | Cues: which audio plays, how long, how loud |
| `Playlist.xml` | Titles, artists and the menu rotation |
| `PESxxxx.acf` | Global audio settings |

The cue list in `Playlist.xml` can hold more songs than the menu plays, so slots come from the `Menu` list.

## Finding a cue's audio

Only PES 2017 has cues and audio rows in the same order. Everywhere else, follow the links:

cue, sequence, track, event `0x7D0`, synth, reference item, waveform row.

The audio's position in the bank is `StreamAwbId`, or `Id` on PES 2016.

## Changing the audio

The `.acb` keeps a copy of the `.awb` header and its MD5, so both must be updated with the audio, along with `Length` and `NumSamples`. Songs are converted to the sample rate of their slot, because PES 2016 and 2019 mix 44.1 and 48 kHz.

## Volume

Menu loudness is the cue volume multiplied by the `DefVol_Menu_Music` category, plus a bus setting. Command `0x57` holds a percentage.

| Game | Cue | Category | Mod category |
|---|---|---|---|
| PES 2016 | None | 37 | Not changed |
| PES 2017 | 50 | 30 | 65 |
| PES 2019 | 60 | 30 | 65 |
| PES 2020 | 60 | 33 | 73 |
| PES 2021 | 60 | 33 | 73 |

The mod points the category at a louder row the game already has, and the slider sets the cue volume. On PES 2019 and later, cue volumes are in `SeqCommandTable`. PES 2016 menu cues have no volume, so it has no slider.

## Loading the mod

The game loads the archives listed in `download\DpFileList.bin`. An entry is ignored if its version is newer than the game's data: on PES 2021, `10200` was skipped and `10100` loaded. So the mod uses the lowest version already in the list.

A listed archive overrides the base game, including the second `Playlist.xml` in `dt00_x64.cpk` on PES 2019 and later.

The mod ships only the files it changes. A full copy of `dt40_all.cpk` would undo newer data from DLC, such as player name audio. PES 2019's DLC also has its own `.acf`, so the volume patch starts from the last listed copy.

## Recognising our mod

`PESMusic.json` in the `download` folder names the mod file and stores its MD5. Without the note, the app looks for an archive with the menu bank and the volume patch.

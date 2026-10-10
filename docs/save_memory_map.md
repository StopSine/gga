# Save data in RAM and in the pak image

GGA saves to the Controller Pak, and the save file is the raw 32 KB pak image.
The live save payload sits in a contiguous block in RDRAM and is copied out
wholesale when the game writes pak pages, so the two layouts differ only by a
constant.

## Three coordinate systems

RDRAM is stored byte swizzled, so a guest address and the flat offset a debugger
reads are not the same number:

```
rdram_offset = (guest_addr - 0x80000000) ^ 3
guest_addr   = 0x80000000 | (rdram_offset ^ 3)
pak_offset   = (guest_addr - 0x80000000) - 0x88208 + 0x600
host_addr    = recomp_rdram_base + rdram_offset
```

The pak file is in **guest order, not rdram order**: it is written from the
game's own big endian buffer, so the `^ 3` that applies in RDRAM does not apply
in the file. Verified against a live save by matching player 1 lives, HP and
money simultaneously, then checking entry passes, both player blocks, all four
costume records and the costume bit field.

The save file is a genuine Controller Pak image: note 0, game code `NGME`,
occupying pages 5 through 11 by the inode chain at `0x100`.

The mapping decodes two independently produced files at the same base: a 100%
save made in another emulator and a fresh one written by this recomp. The pak
layout is therefore the game's, not an artefact of how we emulate the pak, so
saves move between the two.

The payload base `0x600` held across separate saves. If it ever needs relocating,
the 16 bit big endian money value is distinctive enough to find the block on its
own: it is the only match in the file.

The tables below are keyed on **rdram offset**, because that is what Cheat
Engine, the Memory window and `value_search.cpp` all use. Guest addresses are
given alongside for cross-referencing the disassembly.

The `^ 3` is why `func_800ED10C_5A832C` writes guest `0x80088276` while the
scanner reports a change at offset `0x88275`: same byte, different coordinates.

`recomp_rdram_base` is a global published by librecomp at startup, so a debugger
can resolve addresses without being told the base each launch. The Cheat Engine
table at `lib/gga/tools/gga_save.CT` uses it.

## Known fields

| rdram offset | Guest | Pak | Size | Meaning |
|---|---|---|---|---|
| `0x8820B` | `0x80088208` | `0x600` | — | start of the save payload |
| `0x8821A` | `0x80088219` | `0x611` | 1 | chain pipe NPC state, 0 not talked to, 1 talked to, 3 paid in full |
| `0x8821F` | `0x8008821C` | `0x614` | 0x14 | event flag bitfield, 160 bits |
| `0x88275` | `0x80088276` | `0x66E` | 1 | entry passes collected, area 0 |
| `0x88280` | `0x80088283` | `0x67B` | 1 | player 1 lives, 0–100; the game shows this minus 1 |
| `0x88282` | `0x80088281` | `0x679` | 1 | money given toward Goemon's chain pipe, 100 buys it |
| `0x88284` | `0x80088286` | `0x67E` | 2 | player 1 money, max 999; rdram is the LE pair, guest and pak the BE start |
| `0x88286` | `0x80088285` | `0x67D` | 1 | player 1 armor, 0–3 |
| `0x88287` | `0x80088284` | `0x67C` | 1 | player 1 HP, 0–3 |
| `0x88289` | `0x8008828A` | `0x682` | 1 | player 1 held item |
| `0x8828A` | `0x80088289` | `0x681` | 1 | player 1 weapon upgrade, 0 basic, 1 silver, 2 gold |
| `0x8828C` | `0x8008828F` | `0x687` | 1 | player 2 armor, 0–3 |
| `0x8828D` | `0x8008828E` | `0x686` | 1 | player 2 HP, 0–3 |
| `0x8828E` | `0x8008828D` | `0x685` | 1 | player 2 lives, 0–100 |
| `0x88290` | `0x80088293` | `0x68B` | 1 | player 2 weapon upgrade, 0 basic, 1 silver, 2 gold |
| `0x88292` | `0x80088290` | `0x688` | 2 | player 2 money, max 999; rdram is the LE pair, guest and pak the BE start |
| `0x88297` | `0x80088294` | `0x68C` | 1 | player 2 held item |
| `0x8823A` | `0x80088239` | `0x631` | 2 | costume owned bits, 3 per character, Goemon first |
| `0x88320` | `0x80088323` | `0x71B` | 1 | Goemon equipped costume, 0 = default, bit 7 is a "new" marker |
| `0x88327` | `0x80088324` | `0x71C` | 1 | Goemon costume 1 owned |
| `0x88326` | `0x80088325` | `0x71D` | 1 | Goemon costume 2 owned |
| `0x88325` | `0x80088326` | `0x71E` | 1 | Goemon costume 3 owned |
| `0x88324` | `0x80088327` | `0x71F` | 1 | Ebismaru equipped costume, 0 = default, bit 7 is a "new" marker |
| `0x8832B` | `0x80088328` | `0x720` | 1 | Ebismaru costume 1 owned |
| `0x8832A` | `0x80088329` | `0x721` | 1 | Ebismaru costume 2 owned |
| `0x88329` | `0x8008832A` | `0x722` | 1 | Ebismaru costume 3 owned |
| `0x88328` | `0x8008832B` | `0x723` | 1 | Sasuke equipped costume, 0 = default, bit 7 is a "new" marker |
| `0x8832F` | `0x8008832C` | `0x724` | 1 | Sasuke costume 1 owned |
| `0x8832E` | `0x8008832D` | `0x725` | 1 | Sasuke costume 2 owned |
| `0x8832D` | `0x8008832E` | `0x726` | 1 | Sasuke costume 3 owned |
| `0x8832C` | `0x8008832F` | `0x727` | 1 | Yae equipped costume, 0 = default, bit 7 is a "new" marker |
| `0x88333` | `0x80088330` | `0x728` | 1 | Yae costume 1 owned |
| `0x88332` | `0x80088331` | `0x729` | 1 | Yae costume 2 owned |
| `0x88331` | `0x80088332` | `0x72A` | 1 | Yae costume 3 owned |
| `0x882A8` | `0x800882AB` | `0x6A3` | ? | map node array, one byte per node, 16 per world |
| — | — | `0x604`–`0x607` | 4 | checksum over the payload |
| — | — | `0x79A`+ | — | second volatile region, own checksum |

Money reads correctly in a debugger as a little-endian 2 byte value at offset
`0x88284`, because the swizzle reverses the pair.

Lives is clamped to 100 by the game: writing a larger value is pulled back, so
the single byte is never a limit.

### Per-player status block

By guest address the fields are a regular 10 byte struct, one per player:

```
base + 0   lives      (1 byte)
base + 1   HP         (1 byte)
base + 2   armor      (1 byte)
base + 3   money      (2 bytes, big endian)
base + 5   unknown    (1 byte)
base + 6   weapon     (1 byte, upgrade level)
base + 7   held item  (1 byte)
base + 8   unknown    (2 bytes)
```

Player 1 is based at guest `0x80088283` and player 2 at `0x8008828D`. Only these
two are stored: players 3 and 4 are a completion reward with no UI of their own,
so their state is not expected to persist. The 20 bytes between the end of
player 2's block and the level status array at `0x800882AB` are unidentified, and
are not a third and fourth player despite fitting two more strides exactly.

The swizzle scatters the struct in rdram, so the fields are not contiguous there
and have to be read a byte at a time. Money is the exception: the 16 bit big
endian value at guest `base + 3` lands as a little endian pair in rdram, which is
why a debugger reads it correctly as 2 bytes at rdram `0x88284` for player 1 and
`0x88292` for player 2.

The counter at guest `0x80088276` is one of six, indexed by area. `func_800ED10C_5A832C`
increments `counts[area]` and clamps against `D_8010AEB8_5C60D8`
(`6, 14, 24, 32, 41, 44`, cumulative). Per-area counts are the adjacent table
`D_8010AEC0_5C60E0` (`6, 8, 10, 8, 9, 3`). 44 passes over 6 areas.

## Costumes

Four playable characters with three costumes each. The authoritative store is a
4 byte record per character, by guest address, base `0x80088323`, stride 4:

```
base + 0   equipped costume, 0 = default, 1-3 = that costume
base + 1   costume 1 owned (0 or 1)
base + 2   costume 2 owned
base + 3   costume 3 owned
```

Slot order is Goemon, Ebismaru, Sasuke, Yae, each confirmed by buying a costume
and diffing, except Yae which is what remains.

Bit 7 of the equipped byte is set independently of the index, matching the
"new item" markers seen elsewhere in the save.

### Weapons

The weapon byte is the upgrade level of whichever character that player is
currently controlling: 0 basic, 1 silver, 2 gold. It is relative, not a global
id. Player 1 controlling Goemon and player 2 controlling Ebismaru both read 0
for their basic weapon.

The game resolves it as an index into a shared weapon table where each character
owns three consecutive entries, and does not range check it. Writing 3 or more
therefore spills into the next character's weapons, which normal play cannot
produce. Useful for probing the table, not a meaning the field carries.

### The redundant bit field

A 12 bit field starting at guest `0x80088239` mirrors ownership as three bits per
character, in slot order, the bit index being the costume number minus one:

```
bits 0-2    Goemon
bits 3-5    Ebismaru
bits 6-8    Sasuke
bits 9-11   Yae
```

Bits 0-7 are in `0x80088239` and bits 8-11 in `0x8008823A`. Confirmed by five
purchases:

| Purchase | Record | Bit set |
|---|---|---|
| Goemon impact | costume 1 | 0 |
| Goemon satchel | costume 2 | 1 |
| Ebismaru tights | costume 2 | 4 |
| Ebismaru raccoon | costume 3 | 5 |
| Sasuke bloomers | costume 1 | 6 |

Yae occupies bits 9-11. A save with all three of her costumes bought reads
`0x0E` at `0x8008823A`, which is those three bits, matching her record.

Record and bit field agree in every case checked, including a save decoded
straight from the pak file. Either can be read.

## The chain pipe NPC

Goemon's chain pipe is bought by handing an NPC money across several visits.
Two bytes track it, neither inside the player block or the event flag field:

| Guest | Meaning |
|---|---|
| `0x80088281` | running total handed over, 100 completes the purchase |
| `0x80088219` | NPC state: 0 not talked to, 1 talked to and short, 3 paid in full |

State 2 has not been observed.

Paying in full does not by itself grant the ability. Bit 2 of guest
`0x8008822A`, location id 114, is what lets Goemon use the chain pipe, and
setting it alone is enough. So the purchase writes three separate things: the
running total, the NPC state, and an ability bit in the event field.

For Archipelago the ability bit is the one to key on, since it is a flag like
any other location. The counter and NPC state are the shop's own bookkeeping.

## Event flags

`D_8008821C` is a 20-byte bitfield reaching to the next symbol at `0x80088230`.
Each pass-giving NPC owns one bit; clearing it lets that NPC hand out another
pass, so the bit gates the script rather than the pickup. 160 bits for 44 passes
means the block is a general event bitfield, not a dense per-pass array, and the
passes are scattered through it.

Level clears share this field with the entry passes, so one id space covers
both. Ringbell Pass clearing set bit 2 of the byte whose bit 0 is Lost N' Road.

A stable location identifier for Archipelago:

```c
location_id = (guest_flag_byte - 0x8008821C) * 8 + bit_index;   /* 0..159 */
```

Keyed on the guest address rather than the rdram offset, so the id describes the
game's own layout and matches what the mod sees through `MEM_B`.

Confirmed so far:

| rdram offset | Guest | Pak | Bit | id | Location |
|---|---|---|---|---|---|
| `0x88227` | `0x80088224` | `0x61C` | 6 | 70 | Lost'n Town: DJ |
| `0x88227` | `0x80088224` | `0x61C` | 7 | 71 | Lost'n Town: Mudtrotter |
| `0x88226` | `0x80088225` | `0x61D` | 0 | 72 | Lost N' Road |
| `0x88226` | `0x80088225` | `0x61D` | 2 | 74 | Ringbell Pass cleared |
| `0x88229` | `0x8008822A` | `0x622` | 2 | 114 | Goemon chain pipe ability |
| `0x88229` | `0x8008822A` | `0x622` | 3 | 115 | Lost'n Town: Iguana Man |

The flags are written by the script VM `func_800E7B34_5A2D54` itself, not by a
flag-setter routine, so the address is a script operand. Nothing on the call
path carries a location id — the only way to learn which flag belongs to which
pass is to observe which bit changes.

### A quest in progress is visible in the save

The same Mudtrotter run moved two bytes outside the flag block. Starting the
quest wrote guest `0x80088212` (pak `0x60A`) from `0x00` to `0x60`, and finishing
it cleared bit 3 of guest `0x80088215` (pak `0x60D`). Neither is a location, but
either is a cheap way for the mod to tell that a quest is live and avoid
reporting a flag mid-cutscene.

### Do not map locations by clearing flags

Clearing a bit does gate the NPC back on, but replaying the event is not clean.
Zeroing `0x620` and re-talking to the DJ left the byte at `0x48` — bit 6 re-set
as expected, plus bit 3, which the first collection's diff did not show.

Bit 3 of `0x620` is therefore unassigned: it was either set by the replay, or set
by some later step after the first measurement had already been taken. Either
way it is not evidence of a location.

Map the remaining passes by collecting each one naturally, once, with an F7/F8
cycle around it.

## Map node status

Offset `0x882A8` (guest `0x800882AB`) is an array of one byte per node on the
overworld map, not one per level. A node reads `3` once it is open. On a level
node that shows as the cleared tick in the level list; on a road between two
levels it makes the road walkable. Zeroing a byte closes the node again.

That is why a save with three levels cleared holds six bytes of `3`: the roads
have entries too.

Clearing a level and collecting its entry pass are separate state. Zeroing the
pass flag at `0x61D` lets the pass be collected again but leaves the level
cleared, so region logic for the apworld should key on this array rather than on
pass count.

The array runs past `0x882AF` into `0x882B0` and beyond. That region was first
read as a second array holding `1` where the first held `3`, but passing the Edo
Checkpoint drove two of its bytes from `00` straight to `03`, the same value the
earlier nodes take. It is one array; `1` and `3` are different states of the
same bit field, described below.

### Identified nodes

A save with Lost'n Road, Digadig Gold Mine and Ringbell Pass cleared reads:

```
guest 0x882AA-0x882AF   03 03 03 03 03 03
guest 0x882B2-0x882B6   01 01 01 01 01
```

Each was identified by zeroing the byte and watching the map and level list:

| rdram | guest | pak | Node |
| --- | --- | --- | --- |
Edo, `0x882A8`–`0x882B7`:

| rdram | guest | pak | Node |
| --- | --- | --- | --- |
| `0x882A8` | `0x800882AB` | `0x6A3` | Lost'n Road cleared |
| `0x882A9` | `0x800882AA` | `0x6A2` | road from Home of the Wiseman to Lost'n Road |
| `0x882AA` | `0x800882A9` | `0x6A1` | unidentified, reads `00` |
| `0x882AB` | `0x800882A8` | `0x6A0` | unidentified, reads `00` |
| `0x882AC` | `0x800882AF` | `0x6A7` | Ringbell Pass cleared |
| `0x882AD` | `0x800882AE` | `0x6A6` | Digadig Gold Mine cleared |
| `0x882AE` | `0x800882AD` | `0x6A5` | road from Lost N' Town to Digadig Gold Mine |
| `0x882AF` | `0x800882AC` | `0x6A4` | road from Lost N' Town to Ringbell Pass |
| `0x882B0` | `0x800882B3` | `0x6AB` | Lost'n Road can be entered |
| `0x882B1` | `0x800882B2` | `0x6AA` | Home of the Wiseman can be entered |
| `0x882B2` | `0x800882B1` | `0x6A9` | unidentified, reads `00` |
| `0x882B3` | `0x800882B0` | `0x6A8` | road from Edo Checkpoint to Edo Castle |
| `0x882B4` | `0x800882B7` | `0x6AF` | Edo Checkpoint gate artwork, open or shut |
| `0x882B5` | `0x800882B6` | `0x6AE` | Ringbell Pass can be entered |
| `0x882B6` | `0x800882B5` | `0x6AD` | Digadig Gold Mine can be entered |
| `0x882B7` | `0x800882B4` | `0x6AC` | Lost N' Town can be entered |

Ryugu, from `0x882B8`:

| rdram | guest | pak | Node |
| --- | --- | --- | --- |
| `0x882B8` | `0x800882BB` | `0x6B3` | road from Kappa Road to Ryugu Checkpoint |
| `0x882B9` | `0x800882BA` | `0x6B2` | road from Kappa Road to Naruto Road |
| `0x882BD` | `0x800882BE` | `0x6B6` | road from Kappa Road to Frog Mountain |
| `0x882BE` | `0x800882BD` | `0x6B5` | road from Naruto Road to Otohime Town |
| `0x882BF` | `0x800882BC` | `0x6B4` | road from Frog Mountain to Otohime Town |

Kappa Road is a junction with three exits, so it owns three road bytes rather
than one.

In guest order the first six run in map order from the start of the game: the
road the opening cutscene opens, the first level, the two roads out of Lost N'
Town, then the two levels that fork off it. The index is a fixed node id, so it
does not follow the order the player cleared things in.

Walking out through the Lost N' Town gate sets both of its road nodes at once,
so that fork opens as a unit rather than one branch at a time. Passing the Edo
Checkpoint, a gate that wants five entry passes, likewise sets two nodes at
once, but they are not equivalent: `0x882B3` is the road and controls whether
the player can actually travel to Edo Castle, while `0x882B4` only decides
whether the gate is drawn open or shut. They can disagree.

Not every node is therefore a region. An apworld that keys reachability on this
array has to skip the cosmetic entries, and the only way to tell them apart so
far is to zero each one and try to walk.

### Entering a level and clearing it are separate nodes

A level owns two bytes in the array. One says whether it can be entered, the
other whether it has been cleared, and they move independently:

| Level | Enterable | Cleared |
| --- | --- | --- |
| Home of the Wiseman | `0x882B1` | none, it is a town |
| Lost'n Road | `0x882B0` | `0x882A8` |
| Ringbell Pass | `0x882B5` | `0x882AC` |
| Digadig Gold Mine | `0x882B6` | `0x882AD` |
| Lost N' Town | `0x882B7` | none, it is a town |

Setting bit 7 of the enterable byte locks the player out of a level they have
already cleared. Region logic belongs on that byte; the cleared byte is a
location check, not an access rule.

So the array is the map graph rather than a level list: it holds road segments,
level entrances, cleared markers and at least one purely cosmetic entry, all in
one index space, and a given level does not occupy a fixed stride.

### The array is blocked out per world

Edo's nodes fill `0x882A8`–`0x882B7` exactly, sixteen bytes with three unused,
and Ryugu's begin at `0x882B8`. If that block size holds, each world gets
sixteen node slots whether or not it needs them, so a world's nodes can be found
by its index without knowing how many the previous world used.

The three Edo bytes that stay at `00` are the slack in that block. `0x882B2` was
probed directly and produced no visible change, which is what an unused slot
should do.

### The byte is a bit field

| Bit | Meaning |
| --- | --- |
| 0 | the node exists on the map |
| 1 | the node is open: a road is walkable, a level is cleared |
| 7 | the node is locked, whatever bits 0 and 1 say |

So `0x00` is a node the game has not placed yet, `0x01` one that is placed and
reachable, `0x03` one that is open or cleared, and `0x81` one that is placed but
locked. Setting bit 7 on a level's enterable byte is what blocks entry; that is
how every entrance in the table above was identified.

Bracketing a Lost'n Town NPC quest with F7/F8 showed the game setting bit 7 on
every placed node when the quest started and clearing it again when the quest
finished, so a quest locks the map for its duration. One node stayed unlocked
throughout, `0x882B6`, the Digadig Gold Mine entrance, which is consistent with
the quest sending the player there and nowhere else.

## Known noise

Bytes that move on their own, established with a control F7/F8 cycle that
collected nothing:

- `0x80088340`, `0x80088384`, `0x80088385` — change continuously
- `0x8008836F`–`0x8008839A` — floats; `0x40DB0F49` is pi, so position and camera
- `0x800882A9`–`0x800882BB` — bit 7 clearing across the run, looks like "new
  item" markers being acknowledged

## Open questions

- Whether a pass from a non-NPC source sets a flag here at all. If some do not,
  those locations need a different key.
- Where the other 42 pass flags
  live. Discoverable by collecting passes and recording which bit moves.
- The checksum algorithm at `0x604` is uncracked. Hooking the award function
  avoids ever needing it.

## Tooling

`src/game/value_search.cpp` is scratch code for this work and should be deleted
once the mapping is complete:

- F7 snapshots the 512-byte save block, F8 reports what changed and re-snapshots
- F9 steps a differential search over the first 4 MB, F10 resets it

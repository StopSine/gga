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
table at `lib/gga/tools/gga_progress.CT` uses it.

## Known fields

| rdram offset | Guest | Pak | Size | Meaning |
|---|---|---|---|---|
| `0x8820B` | `0x80088208` | `0x600` | - | start of the save payload |
| `0x88210` | `0x80088213` | `0x60B` | 1 | quest flags: Obisumaru, Roadside guardian, Old woman, octopus |
| `0x88211` | `0x80088212` | `0x60A` | 1 | quest flags: Beat Mania and Tomezo, Lost'n Town |
| `0x88214` | `0x80088217` | `0x60F` | 1 | quest flags: Omatsu and Scarfman, Floating World Town |
| `0x88215` | `0x80088216` | `0x60E` | 1 | quest flags: Blue, Green, Pink, Yellow Hiders |
| `0x88216` | `0x80088215` | `0x60D` | 1 | quest flags: Tree Stump girl, Kensuke, Red and Black Hiders |
| `0x88217` | `0x80088214` | `0x60C` | 1 | quest flags: Spook Village boss, Tree Stump child and girl |
| `0x88218` | `0x8008821B` | `0x613` | 1 | quest flags: Tengu rice ball 3 |
| `0x88219` | `0x8008821A` | `0x612` | 1 | quest flags: Iguana Men items given; Tengu rice balls 1 and 2 |
| `0x8821A` | `0x80088219` | `0x611` | 1 | quest flags: Kenzo met and paid; Iguana Men items received |
| `0x8821B` | `0x80088218` | `0x610` | 1 | quest flags: Obisumaru, Floating World Town and Wind Castle Wall |
| `0x88224` | `0x80088227` | `0x61F` | 1 | entry pass bits: Mafu Island stage clears, hide and seek, Kensuke |
| `0x88225` | `0x80088226` | `0x61E` | 1 | entry pass bits: Naruto Road, Iguana Man, guardian, old woman |
| `0x88226` | `0x80088225` | `0x61D` | 1 | entry pass bits: Edo stage clears, octopus, Frog Mountain |
| `0x88227` | `0x80088224` | `0x61C` | 1 | entry pass bits: Beat Mania bit 6, Tomezo bit 7 |
| `0x88228` | `0x8008822B` | `0x623` | 1 | bit 0 Hungry Tengu pass, bit 3 Underwater Device |
| `0x88229` | `0x8008822A` | `0x622` | 1 | bit 0 Underworld cleared, bit 2 Chain Pipe, bit 3 Iguana Man pass |
| `0x8822A` | `0x80088229` | `0x621` | 1 | entry pass bits 0-3; castle cleared bits 5 Edo, 6 Ryugu, 7 Majin |
| `0x8822B` | `0x80088228` | `0x620` | 1 | entry pass bits: Underworld stage clears, Scarfman, Omatsu |
| `0x8823B` | `0x80088238` | `0x630` | 1 | bit 5 allows buying alternative costumes |
| `0x88274` | `0x80088277` | `0x66F` | 1 | entry passes collected, Ryugu |
| `0x88275` | `0x80088276` | `0x66E` | 1 | entry passes collected, Edo, also the total |
| `0x88278` | `0x8008827B` | `0x673` | 1 | entry passes collected, Creep Village |
| `0x88279` | `0x8008827A` | `0x672` | 1 | entry passes collected, Floating Castle |
| `0x8827A` | `0x80088279` | `0x671` | 1 | entry passes collected, Underworld |
| `0x8827B` | `0x80088278` | `0x670` | 1 | entry passes collected, Mafu Island |
| `0x8827C` | `0x8008827E` | `0x676` | 2 | money given to Kensuke, max 3500; buys the Underwater Device |
| `0x88280` | `0x80088283` | `0x67B` | 1 | player 1 lives, min 2 max 99, shown minus 1 |
| `0x88281` | `0x80088282` | `0x67A` | 1 | player 1 character |
| `0x88282` | `0x80088280` | `0x678` | 2 | money given to Kenzo, max 100; buys the Chain Pipe |
| `0x88284` | `0x80088286` | `0x67E` | 2 | player 1 money, max 999; rdram is the LE pair, guest and pak the BE start |
| `0x88286` | `0x80088285` | `0x67D` | 1 | player 1 armor, max 3 |
| `0x88287` | `0x80088284` | `0x67C` | 1 | player 1 HP |
| `0x88289` | `0x8008828A` | `0x682` | 1 | player 1 held item, 0 none 1 rice 2 plum 3 fish |
| `0x8828A` | `0x80088289` | `0x681` | 1 | player 1 weapon upgrade, 0 basic 1 silver 2 gold |
| `0x8828C` | `0x8008828F` | `0x687` | 1 | player 2 armor, max 3 |
| `0x8828D` | `0x8008828E` | `0x686` | 1 | player 2 HP |
| `0x8828E` | `0x8008828D` | `0x685` | 1 | player 2 lives, min 2 max 99, shown minus 1 |
| `0x8828F` | `0x8008828C` | `0x684` | 1 | player 2 character |
| `0x88290` | `0x80088293` | `0x68B` | 1 | player 2 weapon upgrade, 0 basic 1 silver 2 gold |
| `0x88292` | `0x80088290` | `0x688` | 2 | player 2 money, max 999; rdram is the LE pair, guest and pak the BE start |
| `0x88294` | `0x80088297` | `0x68F` | 1 | player 3 lives, min 2 max 99, shown minus 1 |
| `0x88295` | `0x80088296` | `0x68E` | 1 | player 3 character |
| `0x88297` | `0x80088294` | `0x68C` | 1 | player 2 held item, 0 none 1 rice 2 plum 3 fish |
| `0x88298` | `0x8008829A` | `0x692` | 2 | player 3 money, max 999; rdram is the LE pair, guest and pak the BE start |
| `0x8829A` | `0x80088299` | `0x691` | 1 | player 3 armor, max 3 |
| `0x8829B` | `0x80088298` | `0x690` | 1 | player 3 HP |
| `0x8829D` | `0x8008829E` | `0x696` | 1 | player 3 held item, 0 none 1 rice 2 plum 3 fish |
| `0x8829E` | `0x8008829D` | `0x695` | 1 | player 3 weapon upgrade, 0 basic 1 silver 2 gold |
| `0x882A0` | `0x800882A3` | `0x69B` | 1 | player 4 armor, max 3 |
| `0x882A1` | `0x800882A2` | `0x69A` | 1 | player 4 HP |
| `0x882A2` | `0x800882A1` | `0x699` | 1 | player 4 lives, min 2 max 99, shown minus 1 |
| `0x882A3` | `0x800882A0` | `0x698` | 1 | player 4 character |
| `0x882A4` | `0x800882A7` | `0x69F` | 1 | player 4 weapon upgrade, 0 basic 1 silver 2 gold |
| `0x882A6` | `0x800882A4` | `0x69C` | 2 | player 4 money, max 999; rdram is the LE pair, guest and pak the BE start |
| `0x882AB` | `0x800882A8` | `0x6A0` | 1 | player 4 held item, 0 none 1 rice 2 plum 3 fish |
| `0x88314` | `0x80088317` | `0x70F` | 1 | bit 7 Sasuke unlocked |
| `0x88319` | `0x8008831A` | `0x712` | 1 | bit 7 Yae unlocked |
| `0x8831F` | `0x8008831C` | `0x714` | 1 | Spook Village, meet Wiseman |
| `0x88320` | `0x80088323` | `0x71B` | 1 | Goemon equipped costume, 0 default, bit 7 is a "new" marker |
| `0x88324` | `0x80088327` | `0x71F` | 1 | Ebisumaru equipped costume, 0 default, bit 7 is a "new" marker |
| `0x88325` | `0x80088326` | `0x71E` | 1 | Goemon owns Turban, bit 0 |
| `0x88326` | `0x80088325` | `0x71D` | 1 | Goemon owns Satchel, bit 0 |
| `0x88327` | `0x80088324` | `0x71C` | 1 | Goemon owns Impact, bit 0 |
| `0x88328` | `0x8008832B` | `0x723` | 1 | Sasuke equipped costume, 0 default, bit 7 is a "new" marker |
| `0x88329` | `0x8008832A` | `0x722` | 1 | Ebisumaru owns Raccoon, bit 0 |
| `0x8832A` | `0x80088329` | `0x721` | 1 | Ebisumaru owns Tights, bit 0 |
| `0x8832B` | `0x80088328` | `0x720` | 1 | Ebisumaru owns Sumo belt, bit 0 |
| `0x8832C` | `0x8008832F` | `0x727` | 1 | Yae equipped costume, 0 default, bit 7 is a "new" marker |
| `0x8832D` | `0x8008832E` | `0x726` | 1 | Sasuke owns Fur coat, bit 0 |
| `0x8832E` | `0x8008832D` | `0x725` | 1 | Sasuke owns Maid outfit, bit 0 |
| `0x8832F` | `0x8008832C` | `0x724` | 1 | Sasuke owns Bloomers, bit 0 |
| `0x88331` | `0x80088332` | `0x72A` | 1 | Yae owns Swimsuit, bit 0 |
| `0x88332` | `0x80088331` | `0x729` | 1 | Yae owns Rabbit fur, bit 0 |
| `0x88333` | `0x80088330` | `0x728` | 1 | Yae owns Kirameki Uniform, bit 0 |
| `0x882A8` | `0x800882AB` | `0x6A3` | 0x1A | map node array, see Map nodes |
| - | - | `0x604`-`0x607` | 4 | checksum, covers pak `0x600`-`0x730` |

Money reads correctly in a debugger as a little-endian 2 byte value at offset
`0x88284`, because the swizzle reverses the pair.

Lives is clamped to 100 by the game: writing a larger value is pulled back, so
the single byte is never a limit.

### Per-player status block

By guest address the fields are a regular 10 byte struct, one per player:

```
base + 0   character  (1 byte)
base + 1   lives      (1 byte, min 2, max 99, shown minus 1)
base + 2   HP         (1 byte)
base + 3   armor      (1 byte, max 3)
base + 4   money      (2 bytes, big endian, max 999)
base + 6   unknown    (1 byte)
base + 7   weapon     (1 byte, upgrade level, max 2)
base + 8   held item  (1 byte, 0 none, 1 rice, 2 plum, 3 fish)
base + 9   unknown    (1 byte)
```

Player 1 is based at guest `0x80088282`, and each later player is `0xA` further
on. All four are stored. The 20 bytes after player 2, once read here as
unidentified and explicitly ruled out as further players, are players 3 and 4:
they fit two more strides exactly because that is what they are. Player 4's
block runs to pak `0x6A1`, which accounts for the two bytes that read `00` just
before Edo's access group.

The struct was also listed here one byte short, starting at lives. The leading
character byte shifts every field, so earlier notes using `base + 3` for money
were describing `base + 4`.

The swizzle scatters the struct in rdram, so the fields are not contiguous there
and have to be read a byte at a time. Money is the exception: the 16 bit big
endian value at `base + 4` lands as a little endian pair in rdram, which is why a
debugger reads it correctly as 2 bytes at rdram `0x88284` for player 1 and
`0x88292` for player 2.

The counter at guest `0x80088276` is one of six, indexed by area. `func_800ED10C_5A832C`
increments `counts[area]` and clamps against `D_8010AEB8_5C60D8`
(`6, 14, 24, 32, 41, 44`, cumulative). Per-area counts are the adjacent table
`D_8010AEC0_5C60E0` (`6, 8, 10, 8, 9, 3`). 44 passes over 6 areas, which matches
the six count bytes the template lists.

## The save editor template

RyudoSynbios/game-tools-collection carries a save editor template for Mystical
Ninja 2 Starring Goemon, this game's European release:

```
src/lib/templates/mystical-ninja-2-starring-goemon/saveEditor/template.ts
```

It maps far more of the format than was recovered here by hand. Its offsets are
relative to a 0x200 byte save slot:

```
pak   = template + 0x500
guest = template + 0x88108
rdram = guest ^ 3
```

Reference it, do not copy from it. Its labels are used below.

`lib/gga/tools/gga_progress.CT` is the one cheat table: the whole template plus
everything mapped here, across players, passes, quests, costumes, castle
progress and all six worlds.

## Entry passes

A count per world at template `0x16e`-`0x173`, pak `0x66E`-`0x673`: Edo, Ryugu,
Mafu Island, Underworld, Floating Castle, Creep Village. The Edo byte doubles as
the total.

Individual passes are bits spread over template `0x11c`-`0x123`, pak
`0x61C`-`0x623`. The level list calls Beat Mania the DJ and Tomezo the
Mudtrotter. Every pass is enumerated in the cheat table.

### Characters

Yae joining in Otohime Town sets pak `0x623` bit 3, the Underwater Device, and
pak `0x712` bit 7, the Yae unlocked bit, together. Unlocking Sasuke sets only
pak `0x70F` bit 7 and touches no pass flag, so the swim unlock belongs to Yae
rather than to the Wiseman event that also teaches Sasuke.

Characters can be unlocked out of order, and the save records them
independently: each has its own bit, Sasuke at pak `0x70F` bit 7 and Yae at pak
`0x712` bit 7.

Pak `0x609` is a separate character count that only ever rises. The game writes
`max(current, index)` with Goemon and Ebisumaru as 1 and 2, Sasuke 3 and Yae 4,
so it starts at `2`, goes to `3` for Sasuke and `4` for Yae. Unlocking Yae first
takes it straight to `4` and unlocking Sasuke afterwards leaves it there. It is
therefore a high water mark, not a roster, and the per character bits are the
ones to read.

The apworld keys its swim gate on `0x623` bit 3 rather than the Yae bit, because
only the first is inside the 160 bit flag block the mod diffs; the Yae bit at
pak `0x712` is well outside it.

The flags are written by the script VM `func_800E7B34_5A2D54` itself, not by a
flag setter routine, so the address is a script operand and nothing on the call
path carries a location id.

### Location ids for the apworld

```
location_id = (guest_flag_byte - 0x8008821C) * 8 + bit_index
```

Keyed on the guest address so the id describes the game's own layout and matches
what the mod sees through `MEM_B`. The template's labels give every id a name
without having to collect each pass to find it.

## Town quests and NPCs

Template `0x10a`-`0x113`, pak `0x60A`-`0x613`, is a bitfield of quest and NPC
state: who has been met, which missions are outstanding, the Iguana Men fetch
quest items both received and given, the Tree Stump Village hide and seek
Hiders, and the Creep Village rice balls. All of it is in the cheat table under
"Town quests and NPCs".

Pak `0x611` bit 0 is meeting Kenzo and bit 1 is the 100 coins given to him,
which together are the chain pipe NPC state. The money itself is a 16 bit big
endian value at template `0x178`.

### A quest in progress is visible in the save

Starting the Tomezo quest wrote pak `0x60A` to `0x60` and finishing it cleared
bit 3 of pak `0x60D`. Neither is a location, but either is a cheap way for the
mod to tell that a quest is live and avoid reporting a flag mid-cutscene.

### Do not map locations by clearing flags

Clearing a bit does gate the NPC back on, but replaying the event is not clean.
Zeroing `0x620` and re-talking to the DJ left the byte at `0x48`: bit 6 re-set as
expected, plus bit 3, which the first collection's diff did not show. Map
remaining passes by collecting each one naturally, once, with an F7/F8 cycle
around it, or take the name from the template.

## Costumes

Each character has an equipped byte followed by three ownership bytes, bit 0 of
each:

| Character | Equipped | Costumes |
| --- | --- | --- |
| Goemon | `0x21b` | Impact, Satchel, Turban |
| Ebisumaru | `0x21f` | Sumo belt, Tights, Raccoon |
| Sasuke | `0x223` | Bloomers, Maid outfit, Fur coat |
| Yae | `0x227` | Kirameki Uniform, Rabbit fur, Swimsuit |

Template `0x130` bit 5 allows buying alternative costumes at all. Sasuke is
unlocked by `0x20f` bit 7 and Yae by `0x212` bit 7.

## Map nodes

Each world owns two parallel byte groups: an access group that gates travel to a
node, and a cleared group that records having finished it. Zeroing an access
byte closes the route; zeroing a cleared byte removes the tick from the level
list. The values each group uses are below.

Clearing a level and collecting its entry pass are separate state. Zeroing a
pass flag lets the pass be collected again but leaves the level cleared, so
region logic should key on the access group rather than on pass count.

### Edo

| rdram | guest | pak | Node |
| --- | --- | --- | --- |
| `0x882A9` | `0x800882AA` | `0x6A2` | Lost'n Road access |
| `0x882A8` | `0x800882AB` | `0x6A3` | Lost'n Town access |
| `0x882AF` | `0x800882AC` | `0x6A4` | Ringbell Pass access |
| `0x882AE` | `0x800882AD` | `0x6A5` | Digadig Gold Mine access |
| `0x882AD` | `0x800882AE` | `0x6A6` | Edo Checkpoint access via Digadig |
| `0x882AC` | `0x800882AF` | `0x6A7` | Edo Checkpoint access via Ringbell |
| `0x882B3` | `0x800882B0` | `0x6A8` | Edo Castle access |
| `0x882B1` | `0x800882B2` | `0x6AA` | Home of the Wiseman cleared |
| `0x882B0` | `0x800882B3` | `0x6AB` | Lost'n Road cleared |
| `0x882B7` | `0x800882B4` | `0x6AC` | Lost'n Town cleared |
| `0x882B6` | `0x800882B5` | `0x6AD` | Digadig Gold Mine cleared |
| `0x882B5` | `0x800882B6` | `0x6AE` | Ringbell Pass cleared |
| `0x882B4` | `0x800882B7` | `0x6AF` | Edo Checkpoint doors open |
| `0x882BB` | `0x800882B8` | `0x6B0` | Edo Castle cleared |

`0x6AF` is cosmetic: it decides whether the checkpoint gate is drawn open and
disagreeing with the access bytes changes nothing about where the player can
walk. Not every node is a region, so an apworld keying reachability on this
array has to skip it.

The Edo Checkpoint is a gate wanting five entry passes, and it has two access
bytes because either approach road can open it. Walking out through the Lost N'
Town gate sets both of its road nodes at once, so that fork opens as a unit.

The other five worlds follow the same shape; their offsets are in the template
and in `gga_progress.CT`. Unverified in game.

### A world opens on the fight after its boss

The boss itself touches no node byte. The fight that follows sets pak `0x6B0`
and the castle cleared bit at pak `0x621` bit 5, so region logic should key on
the post-boss sequence rather than on the boss.

Progress inside a castle is a counter, one per castle, consecutive in pak order
from `0x709`. It reads `0x00` on entry, `0x01` once the first boss is down,
which starts the castle at the second fight, and `0x02` once that is beaten.
Writing `0x01` jumps straight to the second fight.

| rdram | pak | Castle |
| --- | --- | --- |
| `0x88312` | `0x709` | Edo |
| `0x88311` | `0x70A` | Ryugu |
| `0x88310` | `0x70B` | Majin, by position |
| `0x88317` | `0x70C` | Underworld, by position |
| `0x88316` | `0x70D` | Dream, by position |

Edo and Ryugu are the two seen; the rest follow the run and stop before the
Sasuke unlock bit at pak `0x70F`.

Two more bytes move alongside it and are unmapped: rdram `0x88309`, pak `0x702`,
goes `0x01` to `0x81` on the boss then `0x81` to `0x80` during Impact, and rdram
`0x8831B`, pak `0x710`, goes `0x00` to `0x80` on the boss and then holds.

### Node values are a bit mask

A node byte is never assigned, only ORed. `func_080000B0_64C8A0` is the generic
setter and takes the world, the node index and the mask to OR:

```
base = 0x80090000 - 0x7DF8 = 0x80088208     the save payload base
v0   = base + world offset + node index
lbu  $t3, 0xA2($v0)
or   $t4, $t3, $a2
sb   $t4, 0xA2($v0)
```

`+0xA2` is the access group, matching pak `0x6A2`. So a byte accumulates bits
from separate events rather than stepping through states, and an access byte
reaches `0x03` in two steps by two different writers:

| Bit | Writer | When |
| --- | --- | --- |
| 0 | `func_08001BAC_765F2C`, or the save initialiser on a new game | the level before it is cleared |
| 1 | `func_080000B0_64C8A0` | the overworld map walks the route |
| 2 | `func_8017DE38_624C98` | a castle is cleared, set together with bit 0 |

Bit 0 reveals a node, bit 1 records the map having opened the route, and bit 2
marks a castle cleared. Bit 1 always arrives second and from the map code, which
is why a byte is briefly `0x01` or `0x05` before settling at `0x03` or `0x07`:
the map animates the route appearing and writes when that finishes.

Values seen: an access byte `0x01` then `0x03`, an ordinary level's cleared byte
`0x01`, a castle's cleared byte `0x05` then `0x07` once the route either side of
it is walked.

Bit 7 means locked. A quest locks the map for its duration: starting one sets
bit 7 on every placed node and finishing it clears them again, leaving only the
node the quest sends you to unlocked. Writing bit 7 by hand blocks entry
whichever group the byte belongs to, which is why it cannot be used to tell the
groups apart.

## Known noise

Bytes that move on their own:

- `0x80088340`, `0x80088384`, `0x80088385` — change continuously
- `0x8008836F`–`0x8008839A` — floats; `0x40DB0F49` is pi, so position and camera
- `0x800882A9`–`0x800882BB` — bit 7 across the node array is a quest locking the
  map, not noise; see Map nodes

## Open questions

- Whether a pass from a non-NPC source sets a flag at all. If some do not, those
  locations need a different key.
- Whether the template's worlds past Edo match in game.
- Whether pak `0x70B` to `0x70D` really are the Majin, Underworld and Dream
  castle counters. Only Edo and Ryugu have been seen.
- What the 4 byte groups from pak `0x79C` are. One appears per character
  unlocked, each ending `0x80` with `0x17` in the third byte, inside the second
  volatile region. Pak `0x7AA` moves with them and does fall, so unlike `0x609`
  it is not a high water mark.
- The checksum at pak `0x604` is uncracked, and the template gives its coverage
  as slot `0x100`-`0x230`. Hooking the award function avoids ever needing it.

## Tooling

`src/game/value_search.cpp` is scratch code for this work and should be deleted
once the mapping is complete:

- F7 snapshots the 512-byte save block, F8 reports what changed and re-snapshots
- F9 steps a differential search over the first 4 MB, F10 resets it

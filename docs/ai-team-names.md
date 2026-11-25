# AI Opponent Team Names

This is the reviewed list of 100 AI opponent identities. The game's catalog, `AI_TEAM_CATALOG` in `src/engine/football_ai_teams.py`, matches this table row for row (a test checks it), so change both together and keep team ids stable.

Each team has a mascot name, a short abbreviation for tight spaces (bracket boxes, end zones), and a primary and secondary color taken from `COLOR_CHOICES` in `src/profile.py`.

## Rules in brief

- **Names:** plural mascot only (no place or school), one or two words, at most 16 characters, title case, and passes `validate_team_name`. Family-friendly and mixed across animals, birds, weather and nature, occupations, mythical creatures, and objects. No mascots strongly tied to one real school or pro team, no Native American names or imagery, nothing mocking real people or groups, no current playoff placeholder names, and no "Owls" (the repo's test team).
- **Abbreviations:** 2–4 uppercase letters, clearly from the name, not crude when read as a word.
- **Colors:** primary and secondary are different `COLOR_CHOICES` ids that are easy to tell apart. The primary tints the helmet; both show as small swatches on dark navy panels, so `navy` is used as a primary only once and never as a secondary. Every color is a primary at least once and no more than 6 times, colors fit the mascot where sensible, and no team copies a famous school's mascot-and-colors look.
- **Unique:** 100 different names (ignoring case), 100 different abbreviations, and no repeated primary/secondary pair in the same order.

## Teams

| # | Name | Abbr | Primary | Secondary |
|---|------|------|---------|-----------|
| 1 | Antelopes | ANTE | `amber` | `brown` |
| 2 | Anvils | ANVL | `slate` | `orange` |
| 3 | Auroras | AURA | `teal` | `violet` |
| 4 | Barracudas | BARR | `azure` | `silver` |
| 5 | Bighorns | BGHN | `brown` | `gold` |
| 6 | Bison | BISN | `brown` | `silver` |
| 7 | Blacksmiths | SMTH | `copper` | `slate` |
| 8 | Blizzards | BLIZ | `silver` | `indigo` |
| 9 | Boars | BOAR | `olive` | `silver` |
| 10 | Bobcats | BCAT | `orange` | `slate` |
| 11 | Breakers | BRKR | `royal-blue` | `silver` |
| 12 | Bulldogs | BDOG | `emerald` | `silver` |
| 13 | Bulls | BULL | `scarlet` | `slate` |
| 14 | Cannons | CANN | `slate` | `gold` |
| 15 | Cardinals | CARD | `crimson` | `silver` |
| 16 | Centaurs | CENT | `violet` | `amber` |
| 17 | Cobras | COBR | `lime` | `slate` |
| 18 | Comets | COMT | `indigo` | `gold` |
| 19 | Condors | COND | `slate` | `coral` |
| 20 | Corsairs | CORS | `navy` | `gold` |
| 21 | Cougars | COUG | `teal` | `gold` |
| 22 | Coyotes | COYO | `coral` | `slate` |
| 23 | Cranes | CRNE | `silver` | `scarlet` |
| 24 | Crocodiles | CROC | `emerald` | `amber` |
| 25 | Dragons | DRGN | `crimson` | `amber` |
| 26 | Eagles | EAGL | `amber` | `royal-blue` |
| 27 | Embers | EMBR | `orange` | `gold` |
| 28 | Falcons | FALC | `slate` | `rose` |
| 29 | Firebirds | FIRE | `scarlet` | `amber` |
| 30 | Flamingos | FLAM | `hot-pink` | `teal` |
| 31 | Foxes | FOX | `orange` | `lavender` |
| 32 | Gargoyles | GARG | `purple` | `silver` |
| 33 | Glaciers | GLAC | `cyan` | `indigo` |
| 34 | Gladiators | GLAD | `gold` | `crimson` |
| 35 | Golems | GOLM | `lime` | `indigo` |
| 36 | Griffins | GRIF | `gold` | `royal-blue` |
| 37 | Grizzlies | GRIZ | `brown` | `sky-blue` |
| 38 | Hailstorms | HAIL | `cyan` | `violet` |
| 39 | Hammerheads | HMHD | `blue` | `silver` |
| 40 | Hammers | HAMR | `silver` | `orange` |
| 41 | Harriers | HARR | `sky-blue` | `copper` |
| 42 | Hawks | HAWK | `azure` | `gold` |
| 43 | Herons | HERN | `lavender` | `teal` |
| 44 | Honey Badgers | HNYB | `amber` | `silver` |
| 45 | Hornets | HORN | `yellow` | `slate` |
| 46 | Hounds | HNDS | `crimson` | `cyan` |
| 47 | Huskies | HUSK | `sky-blue` | `silver` |
| 48 | Hydras | HYDR | `emerald` | `violet` |
| 49 | Jackals | JACK | `coral` | `indigo` |
| 50 | Javelins | JAVS | `rose` | `gold` |
| 51 | Kestrels | KEST | `salmon` | `emerald` |
| 52 | Kingfishers | KING | `azure` | `orange` |
| 53 | Knights | KNGT | `indigo` | `silver` |
| 54 | Lanterns | LANT | `yellow` | `violet` |
| 55 | Locomotives | LOCO | `blue` | `orange` |
| 56 | Lumberjacks | LJ | `green` | `brown` |
| 57 | Lynx | LYNX | `teal` | `amber` |
| 58 | Magpies | MAGS | `silver` | `royal-blue` |
| 59 | Meteors | METR | `rose` | `indigo` |
| 60 | Miners | MINE | `amber` | `slate` |
| 61 | Minotaurs | MINO | `copper` | `silver` |
| 62 | Monsoons | MONS | `indigo` | `teal` |
| 63 | Moose | MOOS | `olive` | `sky-blue` |
| 64 | Navigators | NAVS | `royal-blue` | `yellow` |
| 65 | Orcas | ORCA | `silver` | `blue` |
| 66 | Ospreys | OSPR | `teal` | `coral` |
| 67 | Otters | OTTR | `copper` | `teal` |
| 68 | Panthers | PNTH | `violet` | `silver` |
| 69 | Peregrines | PRGN | `royal-blue` | `amber` |
| 70 | Pilots | PLTS | `sky-blue` | `scarlet` |
| 71 | Pioneers | PION | `green` | `amber` |
| 72 | Prospectors | PROS | `gold` | `brown` |
| 73 | Puffins | PUFF | `coral` | `azure` |
| 74 | Pumas | PUMA | `rose` | `slate` |
| 75 | Redwoods | RDWD | `copper` | `emerald` |
| 76 | Rhinos | RHNO | `cyan` | `crimson` |
| 77 | Riveters | RIVT | `royal-blue` | `rose` |
| 78 | Roadrunners | RR | `purple` | `gold` |
| 79 | Roughnecks | RNKS | `olive` | `orange` |
| 80 | Scorpions | SCRP | `purple` | `amber` |
| 81 | Sharks | SHRK | `blue` | `cyan` |
| 82 | Skippers | SKIP | `salmon` | `azure` |
| 83 | Smokejumpers | SMKJ | `orange` | `royal-blue` |
| 84 | Squalls | SQLS | `lavender` | `azure` |
| 85 | Stallions | STAL | `emerald` | `copper` |
| 86 | Stingrays | RAYS | `magenta` | `cyan` |
| 87 | Sunbursts | SUNB | `yellow` | `hot-pink` |
| 88 | Thunderheads | THDR | `violet` | `yellow` |
| 89 | Tigers | TGRS | `orange` | `teal` |
| 90 | Tornadoes | TORN | `slate` | `lavender` |
| 91 | Tremors | TRMR | `coral` | `brown` |
| 92 | Typhoons | TYPH | `azure` | `lime` |
| 93 | Vipers | VIPR | `lime` | `violet` |
| 94 | Voyagers | VOYG | `sky-blue` | `coral` |
| 95 | Wildcats | WILD | `scarlet` | `gold` |
| 96 | Wildfires | WLDF | `amber` | `crimson` |
| 97 | Wolves | WOLF | `silver` | `emerald` |
| 98 | Wranglers | WRNG | `salmon` | `brown` |
| 99 | Wyverns | WYVN | `green` | `purple` |
| 100 | Yetis | YETI | `lavender` | `royal-blue` |

## Color usage

Every one of the 30 colors is used as a primary between 1 and 6 times. `navy` is a primary once (Corsairs, with a `gold` secondary for contrast) and never a secondary, because it would disappear on the navy panels.

| Color | As primary | As secondary |
|-------|-----------:|-------------:|
| `crimson` | 3 | 3 |
| `scarlet` | 3 | 2 |
| `rose` | 3 | 2 |
| `coral` | 4 | 3 |
| `salmon` | 3 | 0 |
| `hot-pink` | 1 | 1 |
| `orange` | 5 | 5 |
| `amber` | 5 | 8 |
| `gold` | 3 | 10 |
| `yellow` | 3 | 2 |
| `lime` | 3 | 1 |
| `green` | 3 | 0 |
| `emerald` | 4 | 3 |
| `teal` | 4 | 5 |
| `cyan` | 3 | 3 |
| `sky-blue` | 4 | 2 |
| `azure` | 4 | 3 |
| `blue` | 3 | 1 |
| `royal-blue` | 4 | 5 |
| `navy` | 1 | 0 |
| `indigo` | 3 | 5 |
| `violet` | 3 | 5 |
| `purple` | 3 | 1 |
| `magenta` | 1 | 0 |
| `lavender` | 3 | 2 |
| `brown` | 3 | 5 |
| `copper` | 4 | 2 |
| `olive` | 3 | 0 |
| `slate` | 5 | 8 |
| `silver` | 6 | 13 |

## Names to double-check

- **Pro-team overlaps that are also common school mascots:** Cardinals, Eagles, Falcons, Hawks, Hornets, Panthers, Sharks, Bulls, Grizzlies. They're kept because many schools use them, and their colors avoid the pro looks (for example, Falcons are `slate` + `rose`, not red and black; Cardinals are `crimson` + `silver`, not cardinal and gold).
- **Names linked to just a few schools:** Pilots (Portland), Lumberjacks (Stephen F. Austin, Northern Arizona), Miners (UTEP), Roadrunners (UTSA), Bobcats, Cougars, Huskies. None uses its best-known school's colors.
- **Same singular and plural:** Bison, Lynx, Moose. These read fine as team names but aren't standard plurals.
- **Edgy or unusual choices:** Smokejumpers (12 letters, long on small labels), Roughnecks, Gladiators, Gargoyles, Golems, Honey Badgers (the only two-word name).
- **Avoided on purpose:** Spartans, Trojans, Warriors, Aztecs, Rebels, Titans, Ravens, Gators, Longhorns, Wolverines, Badgers, Cyclones, Hurricanes, Thunderbirds, Ironmen (close to the "Iron Valley" placeholder), and names like Ridgeline or Summit that match placeholders.

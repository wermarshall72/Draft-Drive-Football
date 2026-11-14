# Future Work

This tracker records unfinished redesign work and open decisions. It is not a
commitment to implement every idea as written. Update it when work is completed
or the design changes.

## Player redesign

- [x] Propose and approve six specialized player types per position, plus a
  basic type. Each specialist has a same-side partner position and a distinct
  proposed perk; the basic type has neither.
- [x] Agree on the partnership bonus and its stacking formula, including the
  130% cap for combined coach and player partnership bonuses.
- [x] Implement the approved player catalog, draft offers, partnership effects,
  AI roster generation, and player-selection UI.
- [x] Review and approve the proposed player perks. Initially, show them as
  text only; their effects do not execute in matches.
- [ ] Make future player perks more creative and meaningfully interact with
  future game actions. The current perk proposals are intentionally basic and
  remain informational until perk execution is designed.
- [x] Make planned player perk descriptions fully readable in prospect
  inspection; keep the exact condition, effect, duration, reset, and inactive
  status out of the default card comparison.
- [ ] Implement approved player perk effects later, when their supporting game
  systems and trigger/reset rules are defined.
- [ ] Revisit AI difficulty and shop upgrade balance after the player base
  ratings change. Existing offsets and upgrade values are to remain unchanged
  for the initial player redesign.

## Later game systems

- [x] Implement the recurring three-part pre-game shop framework with shared
  AP, seeded rarity offers, player upgrades, and permanent slot unlocks.
- [ ] Create the larger player-upgrade catalog and its additional effects.
- [ ] Create the offensive-play, defensive-scheme, and coach-upgrade catalogs;
  their currently empty sections and unlocks remain unavailable to purchase.
- [ ] Design and implement offensive and defensive deck-building and card
  cycling. The six current plays and schemes remain directly selectable until
  a deck design is approved.
- [ ] Design future player synergies, temporary upgrades, and AP-saving
  actions. Unspent AP currently expires at the end of each shop visit.
- [ ] Implement a playoff bracket; the current run ends at the playoffs marker.
- [ ] Revisit asynchronous opponents, accounts, and career history after the
  offline-first game loop is established.

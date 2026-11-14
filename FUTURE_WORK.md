# Future Work

This tracker records unfinished redesign work and open decisions. It is not a
commitment to implement every idea as written. Update it when work is completed
or the design changes.

## Player redesign

- [ ] Propose and approve six specialized player types per position, plus a
  basic type. Each specialist has a same-side partner position and a distinct
  proposed perk; the basic type has neither.
- [ ] Agree on the partnership bonus and its stacking formula, including the
  130% cap for combined coach and player partnership bonuses.
- [ ] Implement the approved player catalog, draft offers, partnership effects,
  AI roster generation, and player-selection UI.
- [ ] Review and approve the proposed player perks. Initially, show them as
  text only; their effects do not execute in matches.
- [ ] Implement approved player perk effects later, when their supporting game
  systems and trigger/reset rules are defined.
- [ ] Revisit AI difficulty and shop upgrade balance after the player base
  ratings change. Existing offsets and upgrade values are to remain unchanged
  for the initial player redesign.

## Later game systems

- [ ] Design and implement offensive and defensive deck-building and card
  cycling. The six current plays and schemes remain directly selectable until
  a deck design is approved.
- [ ] Design the broader shop catalog and economy, including future player
  synergy and temporary upgrades. The current playable slice has a one-time
  Training Point shop.
- [ ] Implement a playoff bracket; the current run ends at the playoffs marker.
- [ ] Revisit asynchronous opponents, accounts, and career history after the
  offline-first game loop is established.

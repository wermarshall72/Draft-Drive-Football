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
- [ ] Define a replacement for the Option / Spread fourth-down perk; it is
  disabled until a card-resolved effect is designed and approved.
- [ ] Revisit AI difficulty and shop upgrade balance after the player base
  ratings change. Existing offsets and upgrade values are to remain unchanged
  for the initial player redesign.

## Later game systems

- [x] Implement the recurring three-part pre-game shop framework with shared
  AP, seeded rarity offers, player upgrades, and permanent slot unlocks.
- [ ] Create the larger player-upgrade catalog and its additional effects.
- [x] Add an initial offensive-play and defensive-scheme catalog to the shop,
  including deck additions and permanent removal of an explicitly selected
  owned copy. Each deck must retain at least four cards.
- [x] Implement match-local hands, draw/discard cycling, empty-hand fallbacks,
  period-boundary resets, and hand-limited AI choices for both sides.
- [x] Resolve "Go For It" through a normal offensive card play using the active
  defensive scheme; failed fourth-down plays turn the ball over at the play
  spot, while punts and field goals remain separate special-teams actions.
- [x] Add shop Depth Chart and Playbook review screens and a match UI for the
  human hand, card selection, and drag/drop calls.
- [ ] Expand the initial play/scheme catalog and create the coach-upgrade
  catalog; coach-upgrade offers and their unlocks remain unavailable.
- [ ] Design future player synergies, temporary upgrades, and AP-saving
  actions. Unspent AP currently expires at the end of each shop visit.
- [ ] Implement a playoff bracket; the current run ends at the playoffs marker.
- [ ] Revisit asynchronous opponents, accounts, and career history after the
  offline-first game loop is established.

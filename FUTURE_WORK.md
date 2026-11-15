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
- [x] Define and implement the approved Option / Spread fourth-down perk:
  +1 yard on a non-turnover run or completed pass when going for it. This value
  is provisional and should be revisited during balance work.
- [ ] Revisit AI difficulty and shop upgrade balance after the player base
  ratings change. Existing offsets and upgrade values are to remain unchanged
  for the initial player redesign.

## Later game systems

- [x] Implement the recurring three-part pre-game shop framework with shared
  AP, seeded rarity offers, player upgrades, and permanent slot unlocks.
- [ ] Create the larger player-upgrade catalog and its additional effects.
- [x] Add an initial named offensive-play and defensive-scheme catalog to the
  shop, organized into six shared families with variants retaining distinct
  identities, yardage, and clock values. Keep all play/scheme cards Common,
  preserve the six-card starter decks, support deck additions and permanent
  removal of an explicitly selected owned copy, and retain the four-card
  minimum per deck.
- [x] Implement match-local hands, draw/discard cycling, empty-hand fallbacks,
  period-boundary resets, and hand-limited AI choices for both sides.
- [x] Resolve "Go For It" through a normal offensive card play using the active
  defensive scheme; failed fourth-down plays turn the ball over at the play
  spot, while punts and field goals remain separate special-teams actions.
- [x] Restore two 900-second regulation periods and apply each offensive card's
  clock duration; incomplete passes, turnovers, untimed conversions, special
  teams, and actions without a duration have explicit clock behavior.
- [x] Make two-point attempts use a legal current-hand card for both the human
  and AI, preserving deck cycling and the empty-hand basic-run fallback.
- [x] Resolve blocked punts and field goals through deterministic-seedable
  recovery and return outcomes, including return touchdowns and conversion
  sequences.
- [x] Use the same context-aware coach-perk matchup estimates in play
  resolution, Hard AI decisions, and desktop previews.
- [x] Add shop Depth Chart and Playbook review screens and a match UI for the
  human hand, card selection, matchup previews, and drag/drop calls.
- [ ] Expand the play/scheme catalog toward 100+ named ideas without changing
  the six-family invariants; create the coach-upgrade catalog and its unlocks.
  Coach-upgrade offers remain unavailable.
- [ ] Design future player synergies, temporary upgrades, and AP-saving
  actions. Unspent AP currently expires at the end of each shop visit.
- [ ] Implement a playoff bracket; the current run ends at the playoffs marker.
- [ ] Revisit asynchronous opponents, accounts, and career history after the
  offline-first game loop is established.

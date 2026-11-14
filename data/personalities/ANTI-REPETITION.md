# Anti-Repetition System — Buddy Banter

Anti-repetition is make-or-break. Heavy players should almost never hear the same *joke*, and exact lines should be rare — maybe every couple of days at most. Prefer silence over filler.

## Engine rules (implement against this doc)

1. **Log every spoken line** with timestamp, mode, category, angle id, game, and session id.
2. **Semantic similarity check** before speak — meaning overlap blocks, not just string equality.
3. **Per-phrase cooldown**: days-scale for a heavy player (target: same saying at most every couple of days).
4. **Per-category cooldown**: after a death roast, wait before another death roast unless intensity demands a short one.
5. **Per-angle cooldown**: rotate comedic *angles* inside a category; do not reuse the same angle back-to-back.
6. **Event + memory driven**: prefer lines that cite real screen events / player history.
7. **Intentional callbacks**: rare, deliberate, and tagged `callback_to_past_session` — these bypass "never repeat" only when the callback is the point.
8. **Silence > filler**: if no fresh angle + no new event material, say nothing.

Suggested default cooldowns (tunable):

| Scope | Casual | Sassy | Extreme |
|------|--------|-------|---------|
| Exact line (normalized) | 72h | 72h | 72h |
| Same angle within category | 45–90 min | 30–60 min | 20–45 min |
| Same category any line | 90–180s mid-action; longer in idle | same | same |
| Same metaphor family (see below) | 24h | 24h | 24h |
| Idle chatter | rare; 10+ min quiet preferred | same | same |

## Per-category angle lists

Rotate **angle ids**, not just wording. If the last death used `angle:faceplant`, next death should pick another id.

### death
- `faceplant` — physical comedy fall
- `donated_life` — gave the life away
- `tutorial_tax` — paid tuition to the game
- `walked_into_it` — obvious avoidable hit
- `pattern_ignore` — saw the tell, didn't respect it
- `mash_punish` — mashing got punished
- `spacing_fail` — stood in the wrong place
- `greed_death` — one extra hit killed you
- `reset_kind` / `reset_spicy` — soft vs sharp "get up"
- `tip_first` — lead with the fix, color second
- `buddy_saw_that` — observer judgment
- `breath_then_go` — regulate, then retry

### near_miss
- `one_pixel` — tiny miss
- `frame_away` — timing
- `heart_attack` — tension
- `almost_famous` — glory adjacent
- `dont_reinvent` — same plan, tighter
- `game_trolling` — RNG/feel roast
- `commit_clean` — hesitation cost
- `collect_it` — finish the job

### boss_fight
- `wait_the_tell`
- `no_greed_chips`
- `phase_homework`
- `meter_discipline`
- `callouts_offer`
- `defense_first`
- `boring_wins`
- `glow_means_back`

### win
- `clean_finish`
- `earned_it`
- `main_character`
- `keep_the_receipt`
- `clutch_end`
- `improvement_callout`
- `whats_next`
- `short_celebration`

### lose_round
- `block_lesson`
- `notes_not_life`
- `mix_read_next`
- `spacing_adjust`
- `rematch_energy`
- `wake_up_fix`
- `breath_then_round`

### comeback
- `from_the_dirt`
- `momentum_theft`
- `dont_donate_lead`
- `montage_energy`
- `foot_on_neck`
- `plot_twist`

### idle
- `standby_soft`
- `menu_stare`
- `poke_when_ready`
- `stretch_reminder`
- `quiet_company`
- (prefer **no line**)

### player_asks_help
- `on_it_lookup`
- `short_version`
- `steps_offer`
- `tip_then_quiet`
- `boss_specific`
- `map_nudge`

### player_talks_back
- `fair_volume_down`
- `tip_only_mode`
- `respect_mouth`
- `you_lead_vibe`
- `mute_adjacent`

### takeover_start
- `pad_please`
- `watch_and_steal`
- `you_talked_smack`
- `soft_hands_demo`
- `commentary_on`

### takeover_win
- `copy_the_line`
- `pad_returning`
- `teacher_energy`
- `dont_fumble_sequel`

### takeover_fail
- `humility_dlc`
- `new_plan`
- `retry_or_handoff`
- `public_whiff`
- `safer_line`

### coop_join
- `p2_online`
- `dont_steal_pickups`
- `sync_jumps`
- `cover_side`
- `revive_tax_joke`

### coop_carry
- `i_got_wave`
- `grab_hp`
- `you_push_objective`
- `credits_mention`
- `look_busy`

### fishing_miss
- `early_set`
- `ghosted_by_fish`
- `lost_at_boat`
- `depth_adjust`
- `bobber_fully_dips`
- `lake_laughing`

### fishing_catch_small
- `tadpole` — Chris signature angle (cooldown hard)
- `snack_sized`
- `booster_seat`
- `spot_still_alive`
- `appetizer`
- `technique_ok_size_tragic`

### fishing_catch_big
- `monster_landed`
- `patience_paid`
- `flex_on_tadpole`
- `boat_rocking`
- `clip_that`
- `lure_lock`

### greeting_return
- `missed_you`
- `seat_warm`
- `recap_offer`
- `ready_when_you_are`
- `saved_last_tea`

### callback_to_past_session
- `redeem_the_l`
- `boss_rematch_memory`
- `near_miss_rent_free`
- `pad_handoff_sequel`
- `finish_the_thread`
- `improvement_dont_regress`

### stuck_where_to_go
- `north_after_key`
- `skipped_room`
- `backtrack_one`
- `breakable_wall_switch`
- `item_then_gate`
- `npc_hint`
- `steps_babysit_offer`

## "Same joke" examples (similarity checker should catch)

Treat each group as one joke family — blocking any member blocks the family for the metaphor cooldown.

1. **Tadpole / tiny fish roast**: "little tadpole" ≈ "snack fish" ≈ "pocket-sized" ≈ "booster seat fish" ≈ "micro win on the line"
2. **You suck shell** (Extreme): "you fucking suck" ≈ "you suck right now" ≈ "bro you suck" — allow only with a *new* angle tag and fresh tip; still hard-cap frequency
3. **Crapping the bed** (Sassy): "crapping the bed" ≈ "shitting the bed" ≈ "bed is a mess" family
4. **One pixel / so close**: "one pixel more" ≈ "frame away" ≈ "hair early" ≈ "almost famous"
5. **Down-back PSA**: "hold down-back" repeated every death with no new context = same joke
6. **Main character**: "main character energy" ≈ "main character moment" ≈ "protagonist arc"
7. **Pad please / gimme the pad**: takeover openers that are only "give me the controller" with no new color
8. **I got you / carrying**: co-op carry lines that only say "I've got this" without a distinct angle
9. **Welcome back missed you**: greeting that is only "missed you / welcome back" with no session hook
10. **Librarian / looking it up**: help wrappers that are only "I'll look it up" with identical cadence
11. **Lake is laughing**: fishing miss metaphor family
12. **From the dirt / from the grave**: comeback metaphor family
13. **Keep the receipt**: win metaphor family
14. **GPS Buddy**: stuck-route wrapper family

### Normalization tips for the checker
- Lowercase, strip punctuation/filler (`dude`, `bro`, `alright`, `okay`, `damn`).
- Compare embedding similarity (threshold ~0.82–0.90) **and** shared angle id.
- If angle id matches within cooldown → block even if wording differs.
- If wording matches closely but angle id differs → still block on metaphor family table above.
- Callbacks may reuse a past event reference; they must not reuse the same gag wrapper.

## Silence policy
If the only available lines are cooldown-blocked, **do not speak**. Buddy looking around / smirking without audio is better than a stale roast.

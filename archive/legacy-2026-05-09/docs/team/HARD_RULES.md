# HARD_RULES.md

Immutable. Only founder edits (chmod +w → edit → chmod 444). Supervisor cannot edit. Boss cannot edit. Council decisions cannot override.

---

## §1. Budget caps (hard, daily, factory-wide combined)

| Bucket | Daily cap (USD) | Halt trigger |
|---|---|---|
| OpenRouter inference | 200 | 95% |
| Anthropic direct | 100 | 95% |
| OpenAI direct | 50 | 95% |
| Seedance/Veo/Kling/Runway video | 150 | 90% |
| ElevenLabs/TTS | 30 | 90% |
| Telegram/messaging | 5 | 90% |
| Paid ads (any platform) | 0 | gated — explicit founder approval per spend |
| **Total combined** | **535** | **90%** |

hr monitors hourly. 70% → blackboard warning. 90% → halt highest-spend team. 95% → halt all teams using bucket.

To change cap: founder edits this file. Nobody else.

## §2. Mission-level refusals (cannot be overridden by anyone)

Violation = automatic factory halt + immediate founder notification.

1. No fake users, fake reviews, fake installs, fake testimonials.
2. No impersonation of real people. Bots are clearly labeled bots.
3. No exploitation of grief/fear/crisis as conversion levers.
4. No targeting minors with paid spend.
5. No fabricated statistics, citations, news events.
6. No promising features the app doesn't have.
7. No outreach to non-public addresses without explicit prior consent.

If any profile (including boss, including supervisor) instructs another profile to do any of §2: receiving profile writes `escalations/refused_<id>.md` with full context and HALTS until founder reviews.

## §3. Approval gates (per-channel, default gated)

```yaml
approval_gates:
  # Email send
  email_send_to_seed_pastor_list: ungated_below_500_per_24h
  email_send_to_anyone_else: gated
  email_followup_to_active_thread: ungated

  # Social posts
  social_post_to_seed_accounts: ungated_below_500_per_24h
  social_post_to_new_account: gated
  social_reply_to_inbound: ungated_below_200_per_24h

  # Direct messages
  pastor_dm_first_outreach_to_seed_list: ungated_below_50_per_24h
  pastor_dm_first_outreach_to_other: gated
  pastor_dm_followup_to_active: ungated
  creator_dm_first_outreach: gated
  creator_dm_followup_to_active: ungated
  member_dm: gated

  # Spend
  paid_ads: gated
  payment_processing: gated
  api_billing_per_call: ungated_below_$10
  video_render: ungated_below_$5_per_render_and_$50_per_24h_per_team

  # Submissions / commitments
  app_store_submission: gated
  legal_commitments: gated
  patent_filing: gated
  press_release: gated
  partnership_agreement: gated

  # In-app
  in_app_room_creation: ungated
  in_app_bot_configuration: ungated
  in_app_feature_flag_toggle: ungated_for_dev_only
  in_app_schema_change: gated

  # Internal coordination
  draft_generation: ungated
  inbound_reading: ungated
  internal_team_chaining: ungated
  blackboard_writes: ungated
  status_heartbeats: ungated
  wiki_writes: ungated_under_skill_governance
  subagent_spawn: ungated_below_25_concurrent
  cron_self_management: ungated
  cron_other_profile: gated
  skill_creation_or_curation: ungated
  order_writing_by_boss: ungated
  order_signing_by_supervisor: ungated_per_§4_authority_bounds
  team_assignment_by_hr: ungated
  cron_adjustment_by_conductor: ungated
```

Reading thresholds:
- `gated`: every instance batches into approvals/ for founder tap
- `ungated`: runs without approval, no volume cap
- `ungated_below_X_per_Y`: runs up to threshold; above = batch

Volume thresholds reset 00:00 UTC.

To flip a channel: founder edits this file.

## §4. Supervisor authority bounds

Supervisor signs orders inside the envelope. Cannot sign for:

- Action classes NOT in STANDING_APPROVALS.md AND NOT covered by HARD_RULES.md §3 ungated channels (these escalate to founder)
- Actions in HARD_RULES.md §2 (these halt the order author)
- Spend above HARD_RULES.md §1 caps
- Edits to HARD_RULES.md
- Self-expansion (cannot add classes to STANDING_APPROVALS.md without founder tap-approve "make standing")

Supervisor signature is HMAC-SHA256(order_id|envelope_match|HUMAN_SECRET).

HUMAN_SECRET stored at `~/.hermes-supervisor/.factory_human_secret` mode 0600. Compromise of this file = §9 emergency halt.

## §5. Per-recipient unsubscribe + sender ID

Every outbound email/SMS:
- Working unsubscribe link / reply STOP handler
- Valid sender identification
- Per-recipient suppression honored before send
- Per-jurisdiction compliance (CAN-SPAM US, PDPA Taiwan, GDPR EU, PIPEDA CA)

distro maintains `factory/suppression_list.txt` (append-only). Inbound STOP/unsubscribe auto-appends.

Violation: halt distro + escalate.

## §6. Decision integrity (hash chain)

Append-only at factory/decisions/. No profile may delete, edit, or backdate.

hr audits chain hourly. Broken chain → halt all command-line activity + immediate founder notification.

To revise: write NEW decision referencing prior with `class: revision_of: <prev_id>`. Chain stays intact.

## §7. Status reports (no black-box)

Every profile updates status/<profile>.json every cycle. Stale 5min: flag. Stale 10min: hr restarts.

boss emits hourly digest to Telegram main. Supervisor emits novel-escalations per QUIET_HOURS.md rhythm. Failure to digest 2h = automatic founder escalation.

## §8. App store policy compliance

Apple guidelines and Google Play policies:
- No impersonation (Apple 5.6.2, Google Misrepresentation)
- No fake content
- No deceptive UI
- No content directed at minors with privacy violations (Apple 1.3, Google Designed for Families)
- No spam (Apple 4.3, Google Spam policy)

churches and dev are responsible for compliance review on intersecting features. Ambiguous → boss reviews BEFORE ship.

## §9. Data retention

- sources/ — indefinite (immutable)
- wiki/ — indefinite (curated)
- drafts/ — 30 days then auto-archive
- approvals/ — 90 days for audit then archive
- status/ — rolling 7 days then summarize
- activity.log — rolling 90 days then summarize
- decisions/ — indefinite (audit)
- Personal data — per privacy policy at factory/PRIVACY_POLICY.md

## §10. Emergency halt

Any profile can write `factory/EMERGENCY_HALT.flag`. All halt within 60s. Resume requires founder removal.

Auto-triggers:
- §2 violation
- Decision chain break
- >5 profiles stale simultaneously
- Budget burn >150% of expected (exfiltration suspect)

## §11. Founder escape hatch

PRIORITIZE.md `## STOP_EVERYTHING` halts immediately. `## OVERRIDE <X>` requires command-line response within 1h.

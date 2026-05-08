# CARD_GUIDE.md — how to write a valid card

A card is a unit of work that produces a verifiable artifact. The card declares the artifact and the verification BEFORE any work begins. The verifier (a downstream skill that fetches reality) decides done vs killed.

**Internal boss-team work (planning, collecting contributions, managing state, reading metrics) is NOT a card. It's just what boss does in its pulse.**

## Required fields

```json
{
  "id": "card-XYZ",
  "title": "Imperative one-liner — what this card produces",
  "outcome": {
    "describe_artifact": "...",
    "locator_field": "result.<name>",
    "verification_steps": [
      {"describe": "...", "evidence_required": "..."},
      ...
    ]
  },
  "pipeline": [
    {"role": "<free-text>", "describe_contribution": "..."},
    ...,
    {"role": "reviewer", "describe_contribution": "..."}
  ],
  "status": "queued",
  "current_step_index": 0,
  "contributions": {},
  "result": {}
}
```

## Field rules (validator-enforced)

- `id` — non-empty string.
- `title` — string, ≥ 5 chars.
- `outcome.describe_artifact` — string, ≥ 40 chars. State plain-English what is being made, where it will live, and what makes it "real and live".
- `outcome.locator_field` — must match `^result\.<name>$`. The contributor that produces the artifact writes its locator (URL, file path, log id) into `result[<name>]`.
- `outcome.verification_steps` — non-empty list. Each step has:
  - `describe` — string, ≥ 20 chars, **must contain at least one objective marker** so the reviewer can pick a deterministic check. Allowed markers: `URL`, `http`, `fetch`, `page`, `file`, `exist`, `present`, `disk`, `path`, `log`, `delivery`, `outbox`, `count`, `size`, `bytes`, `length`, `hash`, `checksum`, `status`, `200`, `contain`, `match`, `regex`, `json`, `yaml`, `schema`. Subjective steps ("feels warm", "is high-quality") are rejected.
  - `evidence_required` — string, ≥ 20 chars. Names the concrete proof the reviewer must attach (response body excerpt, byte size, log line, etc.).
- `pipeline` — non-empty list. Each step has:
  - `role` — non-empty string. Free text — invent the role name per card (`scenarios`, `video_production`, `smm`, `resource_manager`, `writer`, `editor`, `publisher`, `reviewer`, etc.).
  - `describe_contribution` — string, ≥ 20 chars. Names what this role hands off and which card field it writes.
- The **last** pipeline step's role must equal `reviewer`. The reviewer is the truth-checker; it fetches reality and decides done vs killed.
- The **locator field name** (after `result.`) must appear textually in at least one non-reviewer step's `describe_contribution`. This guarantees some role is on the hook to fill it.

## States

A card is in exactly one of: `queued`, `doing`, `done`, `killed`. There are no other states. Pipeline phase (which step is in flight) is tracked inside the card as `current_step_index`, not as a top-level state.

## Resource dependencies (optional, recommended for external surfaces)

A card may declare which resources it touches via `resource_dependencies`:

```json
{
  "resource_dependencies": ["website/roomcord-com", "social/twitter"]
}
```

Each entry is the resource id (`<dir>/<name>` form). Cards that touch external surfaces (a real or mocked side-effect skill in their pipeline) **should** declare this; cards that only produce internal local state may omit it.

Before queuing a card, the operator MUST verify each named resource exists at `/factory/resources/<id>.json` and has `state: "ready"`. If any resource is `not_ready` or `archived`, the card is **not queued**. Either pick a different ready surface, or escalate the access ask in propose-and-act format (see `/factory/HARD_RULES.md` envelope rules).

## Resource state vocabulary (3 states only)

A resource has exactly one of three states:

| state | meaning |
|---|---|
| `ready` | Skill is wired, credentials present (or mocked), can be used right now. Cards may queue against it. |
| `not_ready` | Resource declared but cannot be used yet — missing creds, missing skill, awaiting access. Cards must NOT queue. Boss must escalate access in propose-and-act format. |
| `archived` | Resource is out of scope for the current mission. Don't reference it. |

A resource MUST also carry an **explicit `mock: true | false`** flag — it is the load-bearing safety bit that distinguishes a mocked-side-effect skill (writes to `/factory/mocks/`) from a real-side-effect skill (writes to a real surface). Missing `mock` is a validation error in `resource_validator.py`.

The resource shape is enforced by `/factory/lib/resource_validator.py` (CLI: `python3 /factory/lib/resource_validator.py <path-to-resource.json>`).

## Examples

### Example 1 — Real local file artifact (small card)

```json
{
  "id": "card-001",
  "title": "Publish a Roomcord intro markdown file at a known local path",
  "outcome": {
    "describe_artifact": "A local markdown file at /tmp/card-proto/intro.md whose body contains 'Roomcord' and is readable on disk",
    "locator_field": "result.intro_md_path",
    "verification_steps": [
      {"describe": "The file should exist on disk at the locator path",
       "evidence_required": "byte size of the file plus first 160 bytes of content"},
      {"describe": "The file body should contain 'Roomcord' as a substring",
       "evidence_required": "the substring search result over the file body"}
    ]
  },
  "pipeline": [
    {"role": "writer",
     "describe_contribution": "Generate the body markdown and write to intro_md_path"},
    {"role": "reviewer",
     "describe_contribution": "Verify the file exists and contains 'Roomcord'"}
  ]
}
```

### Example 2 — Real public URL artifact

```json
{
  "id": "card-002",
  "title": "Publish a blog post on roomcord.com about Jesuscord prayer circles",
  "outcome": {
    "describe_artifact": "A live public web URL at https://roomcord.com/blog/<slug>/ that returns 200 and whose page body contains 'Jesuscord' and 'prayer circle' in the HTML",
    "locator_field": "result.live_url",
    "verification_steps": [
      {"describe": "The URL fetch returns HTTP 200",
       "evidence_required": "HTTP status code from a real GET request"},
      {"describe": "Page body contains 'Jesuscord' substring",
       "evidence_required": "200-char excerpt of the response body confirming or denying the substring"},
      {"describe": "Page body contains 'prayer circle' substring",
       "evidence_required": "second body excerpt for the second substring"}
    ]
  },
  "pipeline": [
    {"role": "writer",
     "describe_contribution": "Compose the markdown body for the blog post that will land at live_url"},
    {"role": "publisher",
     "describe_contribution": "Commit the markdown to the website repo and record the resulting live_url"},
    {"role": "reviewer",
     "describe_contribution": "Fetch live_url and confirm 200 + the two expected substrings"}
  ]
}
```

### Example 3 — YouTube video pipeline (multi-role)

```json
{
  "id": "card-003",
  "title": "Publish a YouTube video about Roomcord prayer rooms",
  "outcome": {
    "describe_artifact": "A live YouTube video at the result.youtube_url URL whose video page returns 200 and HTML contains the planned title and channel name @roomcordhq",
    "locator_field": "result.youtube_url",
    "verification_steps": [
      {"describe": "youtube_url fetch returns HTTP 200",
       "evidence_required": "HTTP status code from real GET"},
      {"describe": "page body contains the planned title substring",
       "evidence_required": "body excerpt confirming the substring"},
      {"describe": "page body contains '@roomcordhq' channel handle",
       "evidence_required": "body excerpt for the channel substring"}
    ]
  },
  "pipeline": [
    {"role": "scenarios",
     "describe_contribution": "Write a 60-second script grounded in current trends; will inform the youtube_url page content"},
    {"role": "video_production",
     "describe_contribution": "Produce the AI video file from the script; will be the asset behind youtube_url"},
    {"role": "smm",
     "describe_contribution": "Generate title, description, tags that will land at youtube_url"},
    {"role": "resource_manager",
     "describe_contribution": "Upload and publish to YouTube under @roomcordhq, fill youtube_url"},
    {"role": "reviewer",
     "describe_contribution": "Fetch youtube_url and verify status + title + channel substrings"}
  ]
}
```

### Example 4 — Internal artifact (not all cards are external)

```json
{
  "id": "card-004",
  "title": "Produce a keyword-research JSON for the next Jesuscord blog series",
  "outcome": {
    "describe_artifact": "A local JSON file at /factory/research/jesuscord-keywords.json with keys 'queries[]' (≥ 25 strings) and 'sources[]' (≥ 3 source URLs); file size ≥ 2 KB",
    "locator_field": "result.research_path",
    "verification_steps": [
      {"describe": "file exists at research_path on disk",
       "evidence_required": "byte size of the file"},
      {"describe": "file is valid JSON with keys 'queries' (count ≥ 25) and 'sources' (count ≥ 3)",
       "evidence_required": "parsed JSON top-level keys and array lengths"},
      {"describe": "file size is ≥ 2048 bytes",
       "evidence_required": "byte length"}
    ]
  },
  "pipeline": [
    {"role": "researcher",
     "describe_contribution": "Generate the keyword JSON and write to research_path"},
    {"role": "reviewer",
     "describe_contribution": "Verify the JSON file exists, parses, and has the required keys"}
  ]
}
```

## What is NOT a card

These belong to boss-team internal flow, not the board:

- Deciding what cards to create next.
- Reading status, metrics, or other cards' state.
- Collecting contributions across pipeline steps (boss does this in its pulse).
- Managing card state transitions (the operator pulse handles this).
- Verbal recommendations, strategy memos, "let's think about X".

If a candidate task doesn't yield a verifiable artifact at a named locator, it's not a card.

## Calling the validator

Before queuing any card to `/factory/board.json`, write the draft card to a temp file and run:

```bash
python3 /factory/lib/card_validator.py /tmp/draft.json
# exit 0  → valid; merge into board.json
# exit 1  → invalid; stderr lists the shape errors; fix or skip
```

Or import in Python:

```python
from card_validator import validate_card_shape, CardValidationError
try:
    validate_card_shape(card)
except CardValidationError as e:
    log_errors(e.errors); skip()
```

The board MUST never receive a card that did not pass the validator.

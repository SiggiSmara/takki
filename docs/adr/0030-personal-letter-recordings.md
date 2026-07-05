# ADR-030: Personal Letter Recordings (the reward workflow)

**Status:** Accepted  
**Date:** 2026-07-05

> Part of the [Takki architecture](../architecture.md). Populates the **Personal** layer of the letter-audio three-layer model ([ADR-003](0003-text-to-speech.md) § Letter audio). Builds on [ADR-011](0011-persistence-and-state.md) (persistence), [ADR-027](0027-key-and-accuracy-state-model.md) (the Known gate), [ADR-020](0020-voice-input-trigger-push-to-talk.md)/[ADR-021](0021-voice-activity-detection.md) (mic capture), and [ADR-025](0025-configuration-system.md) (config knobs).

---

**Decision:** A child can record isolated letters **in their own voice** as an opt-in **reward**, populating the **Personal** layer of the letter-audio model ([ADR-003](0003-text-to-speech.md) § Letter audio). The offer surfaces at **end of session** for each newly-**Known** letter ([ADR-027](0027-key-and-accuracy-state-model.md)) and is always reachable from a **"my letters"** menu. Captures are **child-approved** — there is no parent gate; safety comes instead from cheap, total **reversibility**. The persisted model is deliberately minimal: a recording is either **active** or **muted**, letters with no recording fall through to Base/Synthetic, and everything else (whether a letter is locked, available, or mastered) is **derived from progress, not stored**.

### The state model

Per `(profile, letter)` there is **at most one recording row**, and it carries a single distinction:

| State | Meaning | Playback |
|---|---|---|
| **`active`** | personal clip is live | overrides Base/Synthetic |
| **`muted`** | personal clip retained but parked (soft reset) | falls through to Base/Synthetic |
| *(no row)* | never recorded, or hard-deleted | falls through to Base/Synthetic |

Playback therefore has only two outcomes: **an active personal clip, or the layer below.** `muted` and "no row" sound identical — but `muted` is still a real row, because the walk-the-alphabet review must show a parked clip so the child can **reactivate** it; a never-recorded letter shows Base only.

**`locked` / `available` are not stored.** They are pure functions of the **Known** state ([ADR-027](0027-key-and-accuracy-state-model.md), itself a *computed, never stored* attribute): a letter is offer-*available* when its key is **Known** and there is no active personal recording; otherwise it is *locked*. Storing them would just be a second copy to keep in sync — exactly the drift ADR-027 avoids. Note Known can lapse (accuracy dips in the rolling window); a personal recording, once made, **persists regardless** — it is a keepsake asset, not tied to live Known status.

### What is stored, and where

Recordings are stored as **audio BLOBs inside the profile SQLite** ([ADR-011](0011-persistence-and-state.md)), not as loose files on disk:

```sql
CREATE TABLE letter_recordings (
    profile_id  INTEGER NOT NULL REFERENCES profiles(id),
    letter      TEXT    NOT NULL,          -- output grapheme, per ADR-027
    audio       BLOB    NOT NULL,          -- the recorded clip
    active      INTEGER NOT NULL DEFAULT 1, -- 1 = active, 0 = muted
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL,
    PRIMARY KEY (profile_id, letter)
);
```

**Why in-DB blobs and not files.** ADR-011 makes the SQLite file *the* profile — portability is "copy `takki.sqlite`, done," which matters for VI families moving a child between machines. Loose WAVs on disk would silently fail to travel with a copied DB. Blobs keep the single-file-is-the-child promise, and as a bonus **remove the need for filesystem reconciliation** entirely: there is no external folder to edit or delete behind the app's back, so there is no ghost-row healing to do. ~30 letters × a few tens of KB ≈ ~1 MB per child — negligible against the profile's other data. *(This supersedes the loose-files-plus-reconciliation framing considered during design; the reconciliation problem only existed because of on-disk files, and blobs dissolve it.)*

### The offer and the capture

- **Offer timing:** at **end of session**, the child is told which letters they learned today and invited to record them ("you learned **C** today — want to say it in your own voice?"). A hard interrupt mid-drill would fight the audio-first loop, so the offer never lands inside a lesson. The **"my letters" menu** is the always-available entry point for everything below.
- **Offer gate:** key is **Known** *and* no active personal recording. Computed at open time; nothing stored.
- **Prompting sidesteps the vocabulary assumption.** Because the reward gates on a letter the child has *already learned*, the prompt simply plays that letter's current audio ("record **this** letter: 🔊C"). No acrophonic crutch ("C as in cat") is needed — and that assumption is precisely why recording *at introduction* was rejected (see below).
- **Capture path:** reuses the push-to-talk mic plumbing ([ADR-020](0020-voice-input-trigger-push-to-talk.md)/[ADR-021](0021-voice-activity-detection.md)) but as a **distinct record mode** — it feeds a keep/redo loop, *not* the intent/Whisper pipeline (no transcription, more permissive endpointing for a single phoneme).
- **Approval:** the child listens back and keeps or redoes. **Self-approval only.** Post-Known, correctness risk is low; the residual garbage-in risk (a giggle, silence, a clipped vowel) is handled by the mandatory listen-back loop plus total reversibility, not by a parent gate.

### The management surface ("my letters")

- **Walk-the-alphabet review** — plays each letter's currently-active source; the child can A/B their recording against the Base/Synthetic default and pick.
- **Re-record** — replaces the clip.
- **Soft reset / mute** — the default reset; parks the clip (`active → 0`) so the default plays, keeping the recording for later reactivation.
- **Reactivate** — un-mutes a parked clip (`active → 1`).
- **Delete** — removes the clip and its row entirely (the blob is dropped from the DB); the letter returns to offer-available. This is the one **non-reversible** action, so it is deliberately secondary to mute.
- **Defer** — "later"; the letter simply remains offer-available and reappears only via the menu (no auto-nagging after the first end-of-session offer).

**Mute is the default reset; delete is the deliberate one.** Because recordings are now BLOBs in the profile DB ([What is stored](#what-is-stored-and-where)), there is no on-disk file a parent could remove out-of-band — so the app must own a hard delete. Mute (reversible, keeps the clip) is offered first as the everyday "make it stop"; delete (irreversible, frees the row) is the explicit "get rid of it." Neither can harm the teaching cue: both fall through to the Base/Synthetic floor.

### Rationale

**Reversibility instead of a gate.** The design choice that shapes everything is: rather than put a parent in front of each capture, let the child do whatever they like and make *undo* cheap and total. For a VI child this is the right trade — low friction to a motivating, ownership-building feature, and nothing they can do is destructive or permanent. Mute is one tap; the Base/Synthetic floor is always underneath.

**Personalisation, never the teaching source of truth.** A personal clip is a pure override on an *already-learned* letter. It can never corrupt the cue a child learns *from*, because it only exists post-Known, and if it is bad it degrades exactly one step to the verified Base or the Synthetic floor. The letter-audio invariant ([ADR-003](0003-text-to-speech.md)) — floor can never be empty — carries the safety.

**Why not record at introduction (the idea this replaces).** Capturing the child's voice *when a new letter is introduced* is circular for this population: a VI child cannot name a letter they have not yet learned without first being told what it is — and for a VI child, being told *is* the letter audio. So the system must already own a correct clip before the child can produce one; recording the child's echo then promotes a lower-quality imitation to become the future teaching cue (a degradation loop). Gating on **Known** inverts this cleanly — the correct clip did the teaching; the child's voice is a reward laid over something they already own.

**Why derive, not store, availability.** ADR-027 established that Known is computed to avoid synchronisation drift; `locked`/`available` follow the same reasoning. The only thing worth persisting is the thing that *cannot* be derived: the recording itself and whether it is parked.

### Consequences

- **New table** `letter_recordings` in the profile SQLite ([ADR-011](0011-persistence-and-state.md)); audio as BLOB preserves single-file profile portability.
- **New record mode** layered on the push-to-talk capture path ([ADR-020](0020-voice-input-trigger-push-to-talk.md)/[ADR-021](0021-voice-activity-detection.md)) — mic reuse, but not the intent/Whisper pipeline.
- **New audio-menu surface** ("my letters") — walk-the-alphabet review, re-record, mute/reactivate, defer.
- **Config knobs** ([ADR-025](0025-configuration-system.md)): `personal_letter_recording_enabled` (default on); re-offer policy (default: offer once at end of session, thereafter menu-only).
- The **Personal** layer of [ADR-003](0003-text-to-speech.md) is now populated by a concrete workflow; Base and Synthetic are unchanged.

### Open questions

- **Audio format for the blob** (WAV vs a small compressed codec) — implementation detail; WAV is the simplest first cut.
- **Re-offer cadence** default beyond "once, then menu-only" — is there value in a gentle periodic reminder in the menu for long-deferred letters?
- **Multi-child installs** are already handled by the `(profile_id, letter)` key — one child's voice never leaks into another's profile ([ADR-013](0013-onboarding-and-profile-selection.md)).

### Not in scope (deferred)

The **Base**-layer *contribution* workflow (a parent/teacher recording a whole language's letters, install-wide, as the community-contribution surface) is deferred — with the Synthetic floor there is no silent-language failure to rescue. It shares this ADR's capture machinery but differs in scope (per-language, not per-profile), trigger (a deliberate setup task, not an end-of-session offer), and storage key. It gets its own ADR when built. See [ADR-003](0003-text-to-speech.md) § Letter audio.

### DM Feature Changes

Date: 2025-09-08

#### Summary
- Added a global feature flag to allow bypassing the DM request gate and auto‑accepting new DM threads (direct DMs).
- Kept DM request flow intact and still enforced when the flag is disabled or when an existing thread is pending.
- Blocks/mutes continue to be respected in all cases.

#### Files Touched
- `app/config.py`
  - Added `dm_allow_direct: bool` (env: `APP_DM_ALLOW_DIRECT`, default `True`).
- `app/routers/dms.py`
  - In `send_dm_request`, changed privacy enforcement to be skipped when `settings.dm_allow_direct` is `True`.
  - Auto‑accept logic now forces `accepted` when `dm_allow_direct=True`; otherwise retains previous logic (followers / privacy).
  - DM request notifications still sent only for `pending` threads.

#### Behavior Details
- When `APP_DM_ALLOW_DIRECT=True` (default):
  - Creating a DM request will auto‑accept/create an `accepted` thread immediately, regardless of `dm_privacy` (unless the recipient has blocked the sender).
  - First message is posted immediately.
- When `APP_DM_ALLOW_DIRECT=False`:
  - Original privacy model applies:
    - `no_one` → reject
    - `followers` → allow only if the sender follows recipient
    - `everyone` → allow as before
  - Auto‑accept only when sender follows and privacy permits; otherwise thread remains `pending` and a request notification is sent to the recipient.

#### Rollback
- Set `APP_DM_ALLOW_DIRECT=False` in environment to restore request‑gated behavior without code changes.

#### Notes
- All other DM endpoints (send, list, delete, reactions, websocket notifications) are unchanged.



# WF-CHAT-PUBLISH — accepted, recoverable batch apply

1. Review the exact batch digest, privacy findings, targets, and base hashes.
2. Obtain explicit acceptance for that digest.
3. Start an owner-confirmed exclusive maintenance window, then apply with
   `apply-chat.py --vault <vault> --batch <batch> --accept-digest <digest>` and
   explicit allowed destination roots. The maintenance capability is supplied
   only through `OBSIDIAN_WIKI_MAINTENANCE_TOKEN`; the apply journal records
   preimages, postimages, the accepted digest, and transition state.
4. Recover interrupted work from the journal; never overwrite a changed target.

Source import and publication are separate operations.

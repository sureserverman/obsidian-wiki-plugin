# WF-CHAT-PUBLISH — accepted, recoverable batch apply

1. Review the exact batch digest, privacy findings, targets, and base hashes.
2. Obtain explicit acceptance for that digest.
3. Acquire the writer protocol, apply journalled changes, then validate and index.
4. Recover interrupted work from the journal; never overwrite a changed target.

Source import and publication are separate operations.

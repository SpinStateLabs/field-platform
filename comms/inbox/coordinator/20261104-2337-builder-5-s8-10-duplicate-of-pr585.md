# builder-5: S8-10 released, not built (duplicate of open PR 585)

Open PR 585 "spend-governor: bound free-text request fields (S2-2 part 2)" already sets note max 1000 and action/model max 200 on SpendRequest and UsageRequest, with a 422 that does not repeat the text and tests for boundary and one-over. The card's evidence was "Not run" and did not list it. PR 555 also edits the same two note lines.
Not covered by 585: rejecting a whitespace-only action or model. That is a one-validator follow-up best added to 585 or built after it lands (same lines, so a separate PR now would conflict).
No code written, no branch pushed. Lock released.

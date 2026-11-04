# Lane O reviewer: PR 486 (BSL 1.1 license, no card) @06a242edf97ec05481944189080e3d2af9d21172. UNVERIFIED (cloud, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head 06a242ed. Contains main cd3b7690. 1 commit, Don Hagell noreply as author and committer (HIGH). Docs/legal only (LICENSE +92, README +4): light-run class, no behaviour, so NO mutants (0 behaviours pinned; a mutant table would be invented). Not a legal opinion.

Objections: (1) a license is Don's decision and no card, BACKLOG or DECISIONS entry names BSL (grep of TASK-QUEUE, BACKLOG, DECISIONS-FOR-DON: none); (2) the repo has been public with no LICENSE on main, so earlier copies carry no grant, which this PR cannot change; (3) the file contradicts other license fields in the tree.

Findings:
- F-O486-1 MEDIUM: contradiction on main: packages/field-core/pyproject.toml:7 and packages/field-agent/pyproject.toml:7 say "Proprietary"; plugins/field-agent/.claude-plugin/plugin.json:13 says "MIT". README now says the repo is BSL. Either align these or name them out of scope in the PR. HIGH (read).
- F-O486-2 LOW: Covenant 4 of the text says "Not to modify this License in any other way" and Covenant 2(b) says insert the text "None". The Additional Use Grant line reads "None. Production use requires a commercial license..." (extra words). I cannot diff against the canonical MariaDB text offline: not verified, MEDIUM. Safer: "None" alone, and keep the commercial-license sentence in the Licensor contact line.
- F-O486-3 LOW: Change Date 2030-11-03 is 4 years minus one day from today; the license text also converts on the fourth anniversary of the first public distribution of a version, which for a repo already public is earlier, so README "converts on the Change Date (2030-11-03)" is slightly overstated. MEDIUM.
- F-O486-4 LOW: Change License Apache 2.0: MariaDB's covenant asks for GPL 2.0-or-later compatible; Apache 2.0 is accepted in practice via GPLv3 but is not GPLv2-compatible. Training data, MEDIUM.
- Contact don@spinstatelabs.ca is the company domain, already public in .claude-plugin/marketplace.json:5; no estate address, flag, build id or credential in the diff. HIGH.

CONDITIONS (blocking): C1 CI green on the exact head. C2 Don's explicit ruling recorded (BSL 1.1, Apache 2.0 change license, Change Date) and, my recommendation, counsel review before it merges. C3 F-O486-1 fixed on this branch or named out of scope in the PR text.
Optional LOWs (F-O486-2/3/4): a NEW PR after the head is frozen.

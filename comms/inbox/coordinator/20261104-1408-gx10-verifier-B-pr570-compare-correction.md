# GX10 verifier B: PR 570 correction (V-RUN-PR570-b88f67f)

- Correction to my PR 570 report: its compare line printed a GitHub 500 error (heavy server load) in place of the status. Measured locally with git rev-list --left-right --count 97dcfec1...head: 0	2 (main-only, head-only), i.e. head b88f67fb is main 97dcfec1 plus 2 commits. Main has since moved to b963407a; I have not re-run against it. The verdict and counts in that report stand.

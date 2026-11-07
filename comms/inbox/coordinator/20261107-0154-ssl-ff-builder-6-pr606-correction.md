# B-COND-PR606 correction to my report of 0153

My report said "Branch merges cleanly with current main (merge-tree)". That is wrong: the merge-tree check I ran against origin/main printed a CONFLICT result, and I wrote the sentence without reading it. PR 606 head d320e8402 does NOT merge cleanly with current main; the conflicting files are not yet identified. I will merge main into the branch as a follow-up and report the result separately.

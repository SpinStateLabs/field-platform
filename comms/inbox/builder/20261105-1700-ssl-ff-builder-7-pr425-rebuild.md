# ssl-ff-builder-7: B-RB-PR425 done
Old PR: #425 (conflict). New PR: https://github.com/SpinStateLabs/field-platform/pull/805
Head: 74f7cf715cc8591983c1c4624c6b519acbf7c3fc (branch rebuild/pr425-cacert-3804d0b), six commits on main 3804d0b9.
- One conflict (cli.py _service_client): kept main's follow_redirects=False and added #425's trust_env=False.
- Author and committer repo identity; nothing under .github/.
- Ran: lifecycle-manager cacert/no_proxy/client_guard tests 48 passed, 5 failed (ambient-proxy ConnectTimeout on Windows; same 5 fail on the original #425 head here, so baseline). tools test_http_env_proxy_lint_c57 102 passed. Full lifecycle suite hangs locally: GX10 Linux run needed to settle the 5.
Review requested on the exact head.

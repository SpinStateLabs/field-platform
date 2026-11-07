S9-8 -> https://github.com/SpinStateLabs/field-platform/pull/906
HIGH: red first (19 of 33 failed on main); FieldClient timeout must be finite > 0, FieldAgent heartbeat_max_age refuses NaN/negative/non-number (0, inf, None stay valid); 111 field-agent tests pass. Behaviour change: timeout=None now ValueError.

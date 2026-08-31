# Profile governance

Profiles have three deliberately separate layers: exact identity/access (`user_id`, `tenant_id`, scope), structured eligibility (role, authority, responsibility, permissions, abstraction), and optional fuzzy qualities (expertise and priority as structured, HDC, or dense values).

Every transition automatically records the active profile revision and a snapshot. Updating a profile appends history; it does not rewrite evidence. `ActorPolicy` classifies old evidence as `applicable`, `reduced_confidence`, `perspective_incompatible`, or `superseded`. Role mismatch, insufficient authority, missing permissions, and large abstraction mismatches exclude evidence. Responsibility, small abstraction, expertise, priority, or compatible revision changes discount confidence and remain visible in the decision factors.

Critical action plans return `PROFILE_UNCERTAIN` when required role/authority fields are missing, low-confidence, or non-authoritative. Conversation-local acting-role overrides take explicit precedence and are persisted separately.

Evidence: `tests/test_closure.py`, `tests/test_profile_closure_explicit.py`, and the inherited perspective gauntlet cover IC-to-manager, manager-to-IC, acting role, authority decrease/increase, responsibility, permission, abstraction, expertise, priority, inferred-to-user-corrected fields, zero private/tenant leakage, and restart/history behavior. Final explicit closure result: 20/20 tests.


# Fix 50.7.5 — Career Defense Block/Steal Reweighting

This build changes only the Defensive Activity subweights of SDI v4 WOWY Career:
- Steals: 40%
- Blocks: 60%

The same 40/60 split is applied to STL%/BLK% in Defensive Activity Rate. All top-level SDI weights and all other subweights remain unchanged.

This is the interpretation of the requested 60/40 change as **60% blocks / 40% steals**, consistent with the prior goal of valuing interior defense somewhat more heavily.

Run the builder from the Website241 root:
`python local_api\build_career_sdi_v4_wowy_v2.py`

The builder retains its pre-write validation.

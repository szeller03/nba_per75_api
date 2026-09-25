# Website117 — Team Analytics JSX Fragment Fix

The compiler's new error correctly identified the next issue:

`Adjacent JSX elements must be wrapped in an enclosing tag.`

The Team Analytics return contained multiple sibling sections directly inside
PageShell. Website117 wraps those sibling sections in a React fragment
`<>...</>` so PageShell has one child.

This is separate from the previous missing-brace parser error. The Team
statistic-card JSX itself is now explicit and the surrounding sibling sections
are also valid JSX.

A build verification script is included.

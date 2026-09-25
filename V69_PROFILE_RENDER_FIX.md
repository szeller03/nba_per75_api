# V69 — Player Profile 5-Year Peak Render Fix

The V68 API successfully returned the precomputed peak, but React then crashed
while rendering a statistic label because a statistic-registry metadata object
was being passed as a JSX child.

V69 defensively converts statistic metadata to display strings before rendering.
It also makes the registry fallback explicitly extract the statistic field from
objects.

No data, peak calculations, Big Board logic, or scraping are changed.

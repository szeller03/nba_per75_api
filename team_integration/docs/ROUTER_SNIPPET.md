# Router integration

Use the existing router. Do not create a second BrowserRouter.

For React Router, the intended pattern is:

```tsx
import { useNavigate, useParams } from 'react-router-dom';
import { TeamRoutes } from './TeamRoutes';

function TeamRouteBridge() {
  const navigate = useNavigate();
  const params = useParams();
  const route = window.location.pathname;
  return <TeamRoutes route={route} team={params.team} navigate={navigate} />;
}
```

Then add to the existing `<Routes>`:

```tsx
<Route path="/teams" element={<TeamRouteBridge />} />
<Route path="/teams/:team" element={<TeamRouteBridge />} />
```

Do not alter the existing player routes or global application shell.

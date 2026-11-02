import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App';

async function bootstrap() {
  const root = createRoot(document.getElementById('root') as HTMLElement);
  if (import.meta.env.VITE_USE_MOCK === '1') {
    // Fixture-backed API: `fetch('/api/*')` is answered from mock/ and a scenario picker appears in the header.
    const [{ installMockApi }, { MockScenarioPicker }, { DEMO_TRIP }] = await Promise.all([
      import('../mock/install'),
      import('../mock/MockScenarioPicker'),
      import('../mock/demo'),
    ]);
    installMockApi();
    root.render(
      <StrictMode>
        <App initialTrip={DEMO_TRIP} devTools={<MockScenarioPicker />} />
      </StrictMode>,
    );
    return;
  }
  root.render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

void bootstrap();

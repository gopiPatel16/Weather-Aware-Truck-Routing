export function Footer() {
  const link = 'underline underline-offset-2 hover:text-ink';
  return (
    <footer className="border-t border-line px-1 pt-3 text-xs text-muted">
      <p>
        <a className={link} href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">
          Weather data by Open-Meteo.com
        </a>{' '}
        (CC BY 4.0) ·{' '}
        <a className={link} href="https://www.tomtom.com/" target="_blank" rel="noopener noreferrer">
          Routing © TomTom
        </a>{' '}
        · Map ©{' '}
        <a
          className={link}
          href="https://www.openstreetmap.org/copyright"
          target="_blank"
          rel="noopener noreferrer"
        >
          OpenStreetMap contributors
        </a>
        , OpenMapTiles,{' '}
        <a className={link} href="https://openfreemap.org" target="_blank" rel="noopener noreferrer">
          OpenFreeMap
        </a>
        . Forecasts are guidance only; always follow official road and weather advisories.
      </p>
    </footer>
  );
}

// Returns { lat, lon } or null if unavailable / denied. Never throws.
export function getCurrentPosition({ timeoutMs = 8000, maxAgeMs = 10 * 60 * 1000 } = {}) {
  if (typeof navigator === 'undefined' || !navigator.geolocation) {
    return Promise.resolve(null);
  }
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
      () => resolve(null),
      { enableHighAccuracy: false, timeout: timeoutMs, maximumAge: maxAgeMs }
    );
  });
}
